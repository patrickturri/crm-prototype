"""Rounds-scaling / compounding experiment (review finding: deep-run regime).

All prior CRM results used only 3 rounds, so the central H2 claim — that a
REASONED GENEALOGY makes the FROZEN proposer compound knowledge over MANY
rounds — was barely tested. This experiment scales the round count R and asks a
sharp question: does the genealogy arm's certified-novel COUNT keep growing per
round (compounding), or does it PLATEAU like a memoryless sampler?

Three arms, same total proposal budget (R*k candidates), all judged by the real
sandboxed CodeExecCritic + significance gate + intra-set dedup (NO LLM-as-judge
for survive/die):

  1. genealogy  — full loop, mode="genealogy" (run_arm): each round's prompt
                  carries WHY past conjectures died + which survivors to build on.
  2. control    — full loop, mode="control" (run_arm): prior statements only,
                  no reasons, no build-on guidance. Isolates the genealogy bit.
  3. best_of_N  — ONE flat batch of R*k candidates, EMPTY context (no genealogy,
                  no iteration), then the SAME critic + gate + dedup. The
                  memoryless baseline the iterative loop must beat to justify its
                  machinery (finding #8). Its R*k candidates are chunked into R
                  pseudo-rounds of k so it has a comparable per-round trajectory.

PER-ROUND OUTPUTS (the compounding diagnostic), for every arm/seed:
  * cum_certified[r]  — cumulative distinct certified-novel survivors after
                        round r (monotone non-decreasing).
  * new_certified[r]  — newly certified-novel in round r alone (cum diff). A
                        compounding arm keeps this > 0 late; a plateauing arm
                        drives it to 0.

FALLBACK GUARD (hard rule): if the config uses an API proposer (api_code /
hard_api / ...) and ANY arm silently degraded to the offline, context-IGNORING
generator, the genealogy result is INVALID. We DETECT this and FAIL LOUDLY
(non-zero exit, no summary written) unless --allow-fallback is passed (which is
ONLY meaningful for an intentionally-offline smoke run). The default base config
(configs/ablation.yaml) is api_code + hash embedder; with no/invalid key it
degrades to offline, so the guard fires unless you opt in.

DETERMINISM: with proposer kind `offline_code` (or api_code degrading to it),
the run is fully deterministic and free — the smoke test exercises exactly that
path with --allow-fallback. The offline proposer IGNORES the conditioning
context, so genealogy==control by construction in the smoke run; that is the
point of the guard, and the smoke test only checks the plumbing, not H2.

Writes per-arm ledgers, a tidy per-round CSV, and a summary.json under
--results-dir. Reports HONESTLY: if iteration plateaus / loses to best_of_N, the
numbers say so.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any

import numpy as np

from crm.accounting import Accountant
from crm.genealogy import Entry, Ledger
from crm.novelty import certify_novel
from crm.run import load_config
from experiments._harness import _build_components, run_arm

ARMS = ("genealogy", "control", "best_of_N")

# Proposer kinds that are REAL LLM proposers (so a fallback to offline is a
# silent-invalidation event we must catch).
_API_PROPOSER_KINDS = {"api", "api_code", "code", "hard_api", "hard", "api_lean", "lean"}


def _is_api_config(cfg: dict[str, Any]) -> bool:
    kind = (cfg.get("proposer", {}).get("kind") or "").lower()
    return kind in _API_PROPOSER_KINDS


def cumulative_to_new(cum: list[int]) -> list[int]:
    """Per-round NEW count from a cumulative series (cum[r] - cum[r-1]).

    Pure helper (unit-tested): new[0] == cum[0]; new[r] == cum[r]-cum[r-1].
    A flat tail (all-zero `new`) is the plateau signature; a positive tail is
    the compounding signature.
    """
    new: list[int] = []
    prev = 0
    for c in cum:
        new.append(c - prev)
        prev = c
    return new


def run_best_of_n_rounds(
    cfg: dict[str, Any],
    *,
    rounds: int,
    k: int,
    seed: int,
    out_dir: Path,
) -> dict[str, Any]:
    """Best-of-N baseline with a per-round (chunked) certified-novel trajectory.

    Proposes rounds*k candidates in ONE flat batch with EMPTY context, judges
    each with the SAME critic + significance gate + intra-set dedup, then chunks
    the verdicts into R pseudo-rounds of k to produce a cum/new series that lines
    up round-for-round with the iterative arms. No conditioning, no iteration —
    the memoryless reference.
    """
    n_total = rounds * k
    delta = float(cfg.get("delta", 0.35))

    proposer, critic, sig, corpus = _build_components(cfg)
    ledger = Ledger()
    acct = Accountant(
        est_cost_per_1k_in=cfg.get("est_cost_per_1k_in", 0.0),
        est_cost_per_1k_out=cfg.get("est_cost_per_1k_out", 0.0),
    )

    random.seed(seed)
    np.random.seed(seed % (2**32))

    batch = proposer.propose("", k=n_total, seed=seed)
    acct.log_proposer(
        getattr(proposer, "last_tokens_in", 0),
        getattr(proposer, "last_tokens_out", 0),
    )

    accepted: list[str] = []
    # certified flag per candidate, IN ORDER, so we can chunk into pseudo-rounds.
    cert_flags: list[bool] = []
    for c in batch:
        c.round = 0
        cr = critic.check(c)
        acct.log_critic(cr.critic_seconds)
        entry = Entry.from_conjecture(c, cr, surviving=cr.valid)
        is_cert = False
        if cr.valid:
            s = sig.score(c, critic, corpus)
            entry.significance = s
            entry.surviving = not s.is_trivial
            entry.certified_novel = entry.surviving and certify_novel(
                c.statement, s, corpus, delta=delta, critic=critic,
                accepted_survivors=accepted,
            )
            if entry.certified_novel:
                accepted.append(c.statement)
                is_cert = True
        cert_flags.append(is_cert)
        ledger.add(entry)
    acct.snapshot(round=0)

    out_dir.mkdir(parents=True, exist_ok=True)
    ledger.dump(out_dir / "ledger.jsonl")

    # Chunk the in-order certified flags into R rounds of k to build cum/new.
    cum_certified: list[int] = []
    running = 0
    for r in range(rounds):
        chunk = cert_flags[r * k:(r + 1) * k]
        running += sum(1 for x in chunk if x)
        cum_certified.append(running)

    survivors = ledger.survivors()
    sig_scores = [e.significance.score for e in survivors if e.significance]
    m = acct.metrics(
        certified_novel=len(ledger.certified()),
        surviving=len(survivors),
        total_conjectures=len(ledger.entries),
    )
    m.update({
        "arm": "best_of_N",
        "seed": seed,
        "n_proposed": n_total,
        "cum_certified": cum_certified,
        "new_certified": cumulative_to_new(cum_certified),
        "mean_significance": float(np.mean(sig_scores)) if sig_scores else 0.0,
        "survival_rate": len(survivors) / len(ledger.entries) if ledger.entries else 0.0,
        "proposer": getattr(proposer, "name", "?"),
        "using_fallback": bool(getattr(proposer, "using_fallback", False)),
    })
    (out_dir / "metrics.json").write_text(json.dumps(m, indent=2, sort_keys=True))
    return m


class FallbackError(RuntimeError):
    """Raised when an API arm silently degraded to the offline proposer."""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rounds-scaling / compounding experiment.")
    ap.add_argument("--config", default="configs/ablation.yaml")
    ap.add_argument("--rounds", type=int, default=None,
                    help="round count R (overrides config rounds); total budget R*k.")
    ap.add_argument("--seeds", type=int, default=3, help=">=1 (use >=3 for stats)")
    ap.add_argument("--results-dir", default="results/rounds_scaling")
    ap.add_argument(
        "--allow-fallback", action="store_true",
        help="permit the offline (context-ignoring) proposer; ONLY for the "
             "deterministic offline smoke test. With an API config this "
             "DISABLES the silent-invalidation guard, so never use it for a "
             "reported genealogy number.",
    )
    args = ap.parse_args(argv)

    if args.seeds < 1:
        raise SystemExit("rounds-scaling requires >=1 seed.")

    cfg = load_config(args.config)
    rounds = int(args.rounds if args.rounds is not None else cfg.get("rounds", 3))
    # Make the chosen round count authoritative for BOTH the full-loop arms
    # (run_arm reads cfg["rounds"]) and the best_of_N budget.
    cfg = dict(cfg)
    cfg["rounds"] = rounds
    k = int(cfg.get("k", 6))
    is_api = _is_api_config(cfg)

    out_root = Path(args.results_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    print(
        f"[rounds-scaling] config={args.config} rounds={rounds} k={k} "
        f"seeds={args.seeds} proposer={cfg.get('proposer', {}).get('kind')} "
        f"embedder={'hash' if cfg.get('offline_embedder') else cfg.get('embedder')} "
        f"api={is_api} allow_fallback={args.allow_fallback}"
    )

    rows: list[dict] = []
    fallbacks: list[str] = []  # arm/seed labels that fell back

    # ---- Arms 1 & 2: full loop, genealogy vs control ----------------------
    for mode in ("genealogy", "control"):
        for seed in range(args.seeds):
            arm_dir = out_root / f"{mode}_seed{seed}"
            res = run_arm(
                cfg, mode=mode, seed=seed, significance_on=True,
                out_dir=arm_dir,
            )
            # Persist per-arm token/cost metrics so the per-token (finding #8)
            # comparison for the full-loop arms is reproducible from disk, just
            # like best_of_N's metrics.json.
            arm_dir.mkdir(parents=True, exist_ok=True)
            (arm_dir / "metrics.json").write_text(
                json.dumps(res.metrics, indent=2, sort_keys=True)
            )
            if res.using_fallback:
                fallbacks.append(f"{mode}/seed{seed} (proposer={res.proposer_name})")
            new = cumulative_to_new(res.cum_certified)
            for r in range(rounds):
                rows.append({
                    "arm": mode, "seed": seed, "round": r,
                    "cum_certified": res.cum_certified[r],
                    "new_certified": new[r],
                    "cum_survivors": res.cum_survivors[r],
                    "cum_total": res.cum_total[r],
                    "using_fallback": res.using_fallback,
                })
            print(
                f"  {mode:9s} seed={seed} cum_certified={res.cum_certified} "
                f"new={new} fallback={res.using_fallback}"
            )

    # ---- Arm 3: best-of-N (memoryless) ------------------------------------
    for seed in range(args.seeds):
        m = run_best_of_n_rounds(
            cfg, rounds=rounds, k=k, seed=seed,
            out_dir=out_root / f"best_of_N_seed{seed}",
        )
        if m["using_fallback"]:
            fallbacks.append(f"best_of_N/seed{seed} (proposer={m['proposer']})")
        cum = m["cum_certified"]
        new = m["new_certified"]
        for r in range(rounds):
            rows.append({
                "arm": "best_of_N", "seed": seed, "round": r,
                "cum_certified": cum[r],
                "new_certified": new[r],
                "cum_survivors": "",
                "cum_total": (r + 1) * k,
                "using_fallback": m["using_fallback"],
            })
        print(
            f"  best_of_N seed={seed} cum_certified={cum} new={new} "
            f"fallback={m['using_fallback']}"
        )

    # ---- FALLBACK GUARD (hard rule) ---------------------------------------
    # On an API config, a silent degrade to the offline (context-ignoring)
    # generator INVALIDATES the genealogy comparison. Fail loudly.
    if fallbacks and is_api and not args.allow_fallback:
        msg = (
            "FALLBACK DETECTED — genealogy result INVALID. The config requests an "
            f"API proposer but {len(fallbacks)} arm(s) degraded to the offline, "
            "context-IGNORING generator:\n  - " + "\n  - ".join(fallbacks) +
            "\nCheck ANTHROPIC_API_KEY / CRM_PROPOSER_PROVIDER. (For an "
            "intentional offline smoke run, pass --allow-fallback.)"
        )
        raise FallbackError(msg)

    # ---- write CSV --------------------------------------------------------
    fields = [
        "arm", "seed", "round", "cum_certified", "new_certified",
        "cum_survivors", "cum_total", "using_fallback",
    ]
    csv_path = out_root / "rounds_scaling.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k_: row.get(k_, "") for k_ in fields})

    # ---- summary: per-arm final cum (mean+/-std) and compounding signal ----
    summary = {
        "config": args.config, "rounds": rounds, "k": k, "seeds": args.seeds,
        "api": is_api, "allow_fallback": args.allow_fallback,
        "any_fallback": bool(fallbacks), "fallbacks": fallbacks,
        "by_arm": {},
    }
    for arm in ARMS:
        finals = [r["cum_certified"] for r in rows if r["arm"] == arm and r["round"] == rounds - 1]
        # Mean per-round NEW certified over the LAST third of rounds: a plateau
        # diagnostic (near 0 => memoryless/saturated; >0 => still compounding).
        tail_start = max(0, rounds - max(1, rounds // 3))
        tail_new = [
            r["new_certified"] for r in rows
            if r["arm"] == arm and r["round"] >= tail_start
        ]
        summary["by_arm"][arm] = {
            "final_cum_certified_mean": round(float(np.mean(finals)), 4) if finals else 0.0,
            "final_cum_certified_std": round(float(np.std(finals)), 4) if finals else 0.0,
            "tail_new_per_round_mean": round(float(np.mean(tail_new)), 4) if tail_new else 0.0,
        }
    g = summary["by_arm"]["genealogy"]["final_cum_certified_mean"]
    c = summary["by_arm"]["control"]["final_cum_certified_mean"]
    b = summary["by_arm"]["best_of_N"]["final_cum_certified_mean"]
    summary["genealogy_minus_control"] = round(g - c, 4)
    summary["genealogy_minus_best_of_N"] = round(g - b, 4)
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"[rounds-scaling] wrote {csv_path} and {out_root / 'summary.json'}")
    print(
        f"[rounds-scaling] final cum certified — genealogy={g} control={c} "
        f"best_of_N={b} | g-c={summary['genealogy_minus_control']} "
        f"g-bON={summary['genealogy_minus_best_of_N']}"
    )
    if fallbacks and args.allow_fallback:
        print(f"[rounds-scaling] NOTE: {len(fallbacks)} offline-fallback arm(s) "
              f"(allowed); genealogy claim is NOT valid for this run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
