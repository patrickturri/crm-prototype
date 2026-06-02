"""H-orthogonality-prompt-flips-h2: does inverting the survivor directive help?

HYPOTHESIS. The genealogy null (finding #3: genealogy ~= control, never beats
best-of-N) is an artefact of the "generalise or build on these survivors"
framing, which acts as an EXPLORATION BRAKE. Replacing that line with an
ORTHOGONALITY directive ("propose results NOT expressible via, and dissimilar
to, the listed survivors") should convert genealogy from a brake into an
accelerator, so a `genealogy_orthogonal` arm should beat BOTH control AND
best_of_N on distinct-certified per kilo-token at a matched budget.

PREDICTED OBSERVABLE.
  SUPPORTED  : genealogy_orthogonal distinct-certified/ktok > control AND > best_of_N.
  REFUTED    : it matches or still loses (mechanism, not wording, is the problem).

DESIGN (cheapest decisive version).
  Three arms, IDENTICAL R*k proposal budget, seeds 0,1,2:
    1. genealogy_orthogonal — full loop, mode="genealogy_orthogonal" (run_arm).
    2. control               — full loop, mode="control" (run_arm).
    3. best_of_N             — one flat R*k batch, EMPTY context
                               (rounds_scaling.run_best_of_n_rounds).
  Judged by the real sandboxed CodeExecCritic + significance gate + intra-set
  dedup (NO LLM-as-judge for survive/die, §3/§15). Primary metric:
  certified_novel_per_kilo_token (already computed by the Accountant on the SAME
  proposer-token meter for all three arms). We also report raw distinct-certified
  (final cum) and total proposer tokens.

FALLBACK GUARD (hard rule). The base config is api_code; if ANY arm silently
degraded to the offline, context-IGNORING proposer, the genealogy comparison is
INVALID. We detect using_fallback per arm and FAIL LOUDLY (FallbackError,
non-zero exit, no JSON written) — the orthogonality directive only "bites" if a
real LLM reads it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from crm.run import load_config
from experiments._harness import run_arm
from experiments.rounds_scaling import FallbackError, run_best_of_n_rounds

ARMS = ("genealogy_orthogonal", "control", "best_of_N")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="H-orthogonality-prompt-flips-h2 test.")
    ap.add_argument("--config", default="configs/ablation.yaml")
    ap.add_argument("--rounds", type=int, default=None,
                    help="round count R (overrides config rounds); total budget R*k.")
    ap.add_argument("--seeds", type=int, default=3, help=">=1 (use >=3 for stats)")
    ap.add_argument("--results-dir", default="results/orthogonality_prompt")
    args = ap.parse_args(argv)

    if args.seeds < 1:
        raise SystemExit("requires >=1 seed.")

    cfg = load_config(args.config)
    rounds = int(args.rounds if args.rounds is not None else cfg.get("rounds", 3))
    cfg = dict(cfg)
    cfg["rounds"] = rounds
    k = int(cfg.get("k", 6))

    out_root = Path(args.results_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    print(
        f"[orthogonality] config={args.config} rounds={rounds} k={k} "
        f"seeds={args.seeds} budget={rounds * k} "
        f"proposer={cfg.get('proposer', {}).get('kind')}"
    )

    # arm -> seed -> dict(metrics we care about)
    per_arm: dict[str, list[dict[str, Any]]] = {a: [] for a in ARMS}
    fallbacks: list[str] = []

    # ---- Arms 1 & 2: full loop (genealogy_orthogonal, control) -------------
    for mode in ("genealogy_orthogonal", "control"):
        for seed in range(args.seeds):
            res = run_arm(
                cfg, mode=mode, seed=seed, significance_on=True,
                out_dir=out_root / f"{mode}_seed{seed}",
            )
            if res.using_fallback:
                fallbacks.append(f"{mode}/seed{seed} (proposer={res.proposer_name})")
            m = res.metrics
            rec = {
                "seed": seed,
                "certified_novel": int(m["certified_novel"]),
                "proposer_tokens_total": int(m["proposer_tokens_total"]),
                "certified_novel_per_kilo_token": float(m["certified_novel_per_kilo_token"]),
                "surviving": int(m["surviving"]),
                "total_conjectures": int(m["total_conjectures"]),
                "using_fallback": bool(res.using_fallback),
                "proposer": res.proposer_name,
            }
            per_arm[mode].append(rec)
            print(
                f"  {mode:21s} seed={seed} certified={rec['certified_novel']} "
                f"tok={rec['proposer_tokens_total']} "
                f"cert/ktok={rec['certified_novel_per_kilo_token']:.4f} "
                f"fallback={rec['using_fallback']}"
            )

    # ---- Arm 3: best_of_N (memoryless, empty context) ----------------------
    for seed in range(args.seeds):
        m = run_best_of_n_rounds(
            cfg, rounds=rounds, k=k, seed=seed,
            out_dir=out_root / f"best_of_N_seed{seed}",
        )
        if m["using_fallback"]:
            fallbacks.append(f"best_of_N/seed{seed} (proposer={m['proposer']})")
        rec = {
            "seed": seed,
            "certified_novel": int(m["certified_novel"]),
            "proposer_tokens_total": int(m["proposer_tokens_total"]),
            "certified_novel_per_kilo_token": float(m["certified_novel_per_kilo_token"]),
            "surviving": int(m["surviving"]),
            "total_conjectures": int(m["total_conjectures"]),
            "using_fallback": bool(m["using_fallback"]),
            "proposer": m["proposer"],
        }
        per_arm["best_of_N"].append(rec)
        print(
            f"  {'best_of_N':21s} seed={seed} certified={rec['certified_novel']} "
            f"tok={rec['proposer_tokens_total']} "
            f"cert/ktok={rec['certified_novel_per_kilo_token']:.4f} "
            f"fallback={rec['using_fallback']}"
        )

    # ---- FALLBACK GUARD (hard rule) ---------------------------------------
    if fallbacks:
        raise FallbackError(
            "FALLBACK DETECTED — orthogonality result INVALID. The config requests "
            f"an API proposer but {len(fallbacks)} arm(s) degraded to the offline, "
            "context-IGNORING generator (the orthogonality directive is never "
            "read):\n  - " + "\n  - ".join(fallbacks) +
            "\nCheck ANTHROPIC_API_KEY / CRM_PROPOSER_PROVIDER."
        )

    # ---- aggregate ---------------------------------------------------------
    def agg(arm: str, key: str) -> tuple[float, float]:
        vals = [r[key] for r in per_arm[arm]]
        return (round(mean(vals), 4), round(pstdev(vals), 4)) if vals else (0.0, 0.0)

    by_arm: dict[str, Any] = {}
    for arm in ARMS:
        cpkt_mean, cpkt_std = agg(arm, "certified_novel_per_kilo_token")
        cert_mean, cert_std = agg(arm, "certified_novel")
        tok_mean, _ = agg(arm, "proposer_tokens_total")
        by_arm[arm] = {
            "cert_per_ktok_mean": cpkt_mean,
            "cert_per_ktok_std": cpkt_std,
            "certified_mean": cert_mean,
            "certified_std": cert_std,
            "tokens_mean": tok_mean,
            "seeds": per_arm[arm],
        }

    o = by_arm["genealogy_orthogonal"]["cert_per_ktok_mean"]
    c = by_arm["control"]["cert_per_ktok_mean"]
    b = by_arm["best_of_N"]["cert_per_ktok_mean"]
    beats_control = o > c
    beats_best_of_n = o > b
    supported = beats_control and beats_best_of_n

    summary = {
        "hypothesis": "H-orthogonality-prompt-flips-h2",
        "config": args.config,
        "rounds": rounds, "k": k, "seeds": args.seeds, "budget": rounds * k,
        "any_fallback": bool(fallbacks), "fallbacks": fallbacks,
        "metric": "certified_novel_per_kilo_token (distinct-certified after dedup / proposer ktok)",
        "by_arm": by_arm,
        "orthogonal_minus_control_per_ktok": round(o - c, 4),
        "orthogonal_minus_best_of_N_per_ktok": round(o - b, 4),
        "orthogonal_beats_control": beats_control,
        "orthogonal_beats_best_of_N": beats_best_of_n,
        "supported": supported,
        "verdict": "SUPPORTED" if supported else "REFUTED_OR_INCONCLUSIVE",
    }
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2))

    print(
        f"[orthogonality] cert/ktok — orthogonal={o} control={c} best_of_N={b} | "
        f"o-c={summary['orthogonal_minus_control_per_ktok']} "
        f"o-bON={summary['orthogonal_minus_best_of_N_per_ktok']} | "
        f"verdict={summary['verdict']}"
    )
    print(f"[orthogonality] wrote {out_root / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
