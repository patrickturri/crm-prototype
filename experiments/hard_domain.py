"""Hard-domain experiment (addresses review finding #9 + #8).

Runs the FULL CRM system and a BEST-OF-N + DEDUP baseline on the freshly-defined
non-standard integer-sequence domain (see crm/proposers_hard.py), where the
frozen LLM CANNOT recall the answer and must DISCOVER properties of g.

Three arms, all with the real sandboxed CodeExecCritic (never mocked) and the
real Anthropic proposer (offline fallback if no key):

  1. genealogy  — full system, mode="genealogy" (reasoned ledger conditioning).
  2. control    — full system, mode="control" (prior statements only, no WHY).
  3. best_of_N  — finding #8 baseline: one FLAT batch of rounds*k candidates with
                  NO conditioning context (no genealogy, no iteration), then the
                  SAME critic + significance gate + intra-set dedup. Same total
                  proposal budget, so the per-token comparison is apples-to-apples.

Per seed it records certified_novel, survival_rate, mean significance, the
per-kilo-token KPI, and (for genealogy/control) the same numbers run_arm
reports. Writes per-arm ledgers + a summary metrics.json + CSV under
results/findings/hard_domain/. Reports HONESTLY even if the model trivializes
the domain or genealogy does not help.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

import numpy as np

from crm.accounting import Accountant
from crm.genealogy import Entry, Ledger
from crm.novelty import certify_novel
from crm.run import (
    _build_critic,
    _build_proposer,
    _load_jsonl_statements,
)
from crm.significance import SignificanceCritic
from experiments._harness import run_arm
from experiments._indep_oracle import independent_trivial_rate


def _build_components(cfg: dict):
    proposer = _build_proposer(cfg.get("proposer", {}))
    critic = _build_critic(cfg.get("critic", "code_exec"), cfg)
    sig_cfg = cfg.get("significance", {})
    weights = cfg.get("weights", {})
    corpus = _load_jsonl_statements(cfg.get("corpus_path", "data/corpus.jsonl"))
    breadth = _load_jsonl_statements(
        cfg.get("breadth_targets_path", cfg.get("corpus_path", "data/corpus.jsonl"))
    )
    embedder = cfg.get("embedder")
    if cfg.get("offline_embedder", False):
        embedder = "hash"
    significance = SignificanceCritic(
        w_novelty=weights.get("novelty", 0.3),
        w_breadth=weights.get("breadth", 0.3),
        w_hardness=weights.get("hardness", 0.4),
        tau=cfg.get("tau", 0.25),
        perturbations=cfg.get("perturbations", 8),
        breadth_targets=sig_cfg.get("breadth_targets", 8),
        embedder=embedder,
        corpus_statements=corpus,
        breadth_target_statements=breadth,
        seed=int(cfg.get("seed", 0)),
        perturb_strategy=cfg.get("perturb_strategy", "literal"),
    )
    return proposer, critic, significance, corpus


def run_best_of_n(cfg: dict, *, seed: int, out_dir: Path) -> dict:
    """Best-of-N + dedup baseline (finding #8).

    Propose rounds*k candidates in ONE flat batch with NO conditioning context,
    then run the SAME critic + significance gate + intra-set dedup. This is the
    'just sample N and dedup' baseline the iterative genealogy loop must beat to
    justify its machinery, compared on a per-token basis.
    """
    rounds = int(cfg.get("rounds", 3))
    k = int(cfg.get("k", 6))
    n_total = rounds * k
    delta = float(cfg.get("delta", 0.35))

    proposer, critic, sig, corpus = _build_components(cfg)
    ledger = Ledger()
    acct = Accountant()

    random.seed(seed)
    np.random.seed(seed % (2**32))

    # ONE flat batch, EMPTY context (no genealogy, no prior-statement dedup hint).
    batch = proposer.propose("", k=n_total, seed=seed)
    acct.log_proposer(
        getattr(proposer, "last_tokens_in", 0),
        getattr(proposer, "last_tokens_out", 0),
    )

    accepted: list[str] = []
    for c in batch:
        c.round = 0
        cr = critic.check(c)
        acct.log_critic(cr.critic_seconds)
        entry = Entry.from_conjecture(c, cr, surviving=cr.valid)
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
        ledger.add(entry)
    acct.snapshot(round=0)

    out_dir.mkdir(parents=True, exist_ok=True)
    ledger.dump(out_dir / "ledger.jsonl")

    survivors = ledger.survivors()
    valid = [e for e in ledger.entries if e.crit.valid]
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
        "mean_significance": float(np.mean(sig_scores)) if sig_scores else 0.0,
        "survival_rate": len(survivors) / len(ledger.entries) if ledger.entries else 0.0,
        "proposer": getattr(proposer, "name", "?"),
        "using_fallback": bool(getattr(proposer, "using_fallback", False)),
    })
    (out_dir / "metrics.json").write_text(json.dumps(m, indent=2, sort_keys=True))
    return m


def main(argv: list[str] | None = None) -> int:
    from crm.run import load_config

    ap = argparse.ArgumentParser(description="Hard-domain experiment (#9 + #8).")
    ap.add_argument("--config", default="configs/hard_domain.yaml")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--results-dir", default="results/findings/hard_domain")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    rounds = int(cfg.get("rounds", 3))
    out_root = Path(args.results_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    print(
        f"[hard-domain] seeds={args.seeds} rounds={rounds} k={cfg.get('k')} "
        f"proposer={cfg.get('proposer', {}).get('kind')} embedder={cfg.get('embedder')}"
    )

    # ---- Arms 1 & 2: full system, genealogy vs control --------------------
    for mode in ("genealogy", "control"):
        for seed in range(args.seeds):
            res = run_arm(
                cfg, mode=mode, seed=seed, significance_on=True,
                out_dir=out_root / f"{mode}_seed{seed}",
            )
            row = {
                "arm": mode,
                "seed": seed,
                "certified_novel": res.cum_certified[-1] if res.cum_certified else 0,
                "surviving": res.cum_survivors[-1] if res.cum_survivors else 0,
                "total": res.cum_total[-1] if res.cum_total else 0,
                "mean_significance": round(res.mean_significance, 6),
                "survival_rate": round(res.survival_rate, 6),
                "trivial_rate": round(res.trivial_rate, 6),
                "indep_trivial_rate": round(res.indep_trivial_rate, 6),
                "per_kilo_token": round(
                    res.metrics.get("certified_novel_per_kilo_token", 0.0), 6
                ),
                "tokens_total": res.metrics.get("proposer_tokens_total", 0),
                "using_fallback": bool(
                    getattr(getattr(res, "critic", None), "_dummy", False)
                ),
            }
            rows.append(row)
            print(
                f"  {mode:9s} seed={seed} certified={row['certified_novel']} "
                f"surv={row['surviving']} mean_sig={row['mean_significance']:.3f} "
                f"trivial={row['trivial_rate']:.2f} indep_triv={row['indep_trivial_rate']:.2f} "
                f"cert/kt={row['per_kilo_token']:.3f}"
            )

    # ---- Arm 3: best-of-N + dedup baseline (#8) ---------------------------
    for seed in range(args.seeds):
        m = run_best_of_n(cfg, seed=seed, out_dir=out_root / f"best_of_N_seed{seed}")
        row = {
            "arm": "best_of_N",
            "seed": seed,
            "certified_novel": m["certified_novel"],
            "surviving": m["surviving"],
            "total": m["total_conjectures"],
            "mean_significance": round(m["mean_significance"], 6),
            "survival_rate": round(m["survival_rate"], 6),
            "trivial_rate": "",
            "indep_trivial_rate": "",
            "per_kilo_token": round(m.get("certified_novel_per_kilo_token", 0.0), 6),
            "tokens_total": m.get("proposer_tokens_total", 0),
            "using_fallback": m.get("using_fallback", False),
        }
        rows.append(row)
        print(
            f"  best_of_N seed={seed} certified={row['certified_novel']} "
            f"surv={row['surviving']} mean_sig={row['mean_significance']:.3f} "
            f"cert/kt={row['per_kilo_token']:.3f} fallback={row['using_fallback']}"
        )

    # ---- aggregate + write -------------------------------------------------
    fields = [
        "arm", "seed", "certified_novel", "surviving", "total",
        "mean_significance", "survival_rate", "trivial_rate",
        "indep_trivial_rate", "per_kilo_token", "tokens_total", "using_fallback",
    ]
    csv_path = out_root / "hard_domain.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    def agg(arm: str, key: str) -> tuple[float, float]:
        vals = [r[key] for r in rows if r["arm"] == arm and isinstance(r.get(key), (int, float))]
        if not vals:
            return (0.0, 0.0)
        return (float(np.mean(vals)), float(np.std(vals)))

    summary = {"config": args.config, "seeds": args.seeds, "rounds": rounds,
               "k": cfg.get("k"), "by_arm": {}}
    for arm in ("genealogy", "control", "best_of_N"):
        cm, cs = agg(arm, "certified_novel")
        sm, ss = agg(arm, "survival_rate")
        gm, gs = agg(arm, "mean_significance")
        ptm, _ = agg(arm, "per_kilo_token")
        summary["by_arm"][arm] = {
            "certified_novel_mean": round(cm, 4),
            "certified_novel_std": round(cs, 4),
            "survival_rate_mean": round(sm, 4),
            "survival_rate_std": round(ss, 4),
            "mean_significance_mean": round(gm, 4),
            "per_kilo_token_mean": round(ptm, 4),
        }
    g = summary["by_arm"]["genealogy"]["certified_novel_mean"]
    c = summary["by_arm"]["control"]["certified_novel_mean"]
    summary["genealogy_vs_control_delta"] = round(g - c, 4)
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"[hard-domain] wrote {csv_path} and {out_root/'summary.json'}")
    print(f"[hard-domain] genealogy_vs_control_delta (certified_novel) = "
          f"{summary['genealogy_vs_control_delta']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
