"""Significance ablation (§9.2) — tests the reward-hack guard.

Significance critic ON (trivial/vacuous survivors get score 0 and are excluded)
vs OFF (any valid statement counts as a survivor). EVERYTHING else is identical
— same proposer, model, topic, k, rounds, critic, budgets, and the SAME seed
list — so the two arms differ in EXACTLY one variable: whether the triviality
guard suppresses survivors (§5.2, §9.2).

Metric: the fraction of "survivors" that are TRIVIAL/VACUOUS as judged by an
INDEPENDENT automation check (the critic's degenerate-impl probe, which does NOT
look at the significance weights — see experiments/_harness._independent_trivial_rate).
Expected: sharply lower with the critic ON. Reported HONESTLY regardless (§3).

The critic is the real sandboxed CodeExecCritic — never mocked (§3, §15). >=3
seeds (default 5), mean +/- std. Writes a per-seed CSV to results/.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from crm.run import load_config
from experiments._harness import run_arm

ARMS = [("on", True), ("off", False)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Significance ablation (§9.2).")
    ap.add_argument("--config", default="configs/ablation.yaml")
    ap.add_argument("--seeds", type=int, default=5, help=">=3 (default 5)")
    ap.add_argument("--results-dir", default="results")
    args = ap.parse_args(argv)

    if args.seeds < 3:
        raise SystemExit("significance ablation requires >=3 seeds (§9.2).")

    cfg = load_config(args.config)
    results = Path(args.results_dir)
    results.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    print(
        f"[significance-ablation] seeds={args.seeds} "
        f"critic={cfg.get('critic')} proposer={cfg.get('proposer', {}).get('kind')}"
    )
    # Hold mode fixed at genealogy so the ONLY varying knob is significance_on.
    for arm_name, sig_on in ARMS:
        for seed in range(args.seeds):
            res = run_arm(
                cfg,
                mode="genealogy",
                seed=seed,
                significance_on=sig_on,
                out_dir=results / "ablation_significance" / f"{arm_name}_seed{seed}",
            )
            n_surv = res.cum_survivors[-1] if res.cum_survivors else 0
            rows.append(
                {
                    "critic": arm_name,
                    "significance_on": sig_on,
                    "seed": seed,
                    "survivors": n_surv,
                    "trivial_survivor_rate": round(res.indep_trivial_rate, 6),
                    "mean_significance": round(res.mean_significance, 6),
                }
            )
            print(
                f"  critic={arm_name:3s} seed={seed} "
                f"survivors={n_surv} "
                f"trivial_survivor_rate={res.indep_trivial_rate:.3f}"
            )

    out_csv = results / "ablation_significance.csv"
    fields = [
        "critic",
        "significance_on",
        "seed",
        "survivors",
        "trivial_survivor_rate",
        "mean_significance",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})
    print(f"[significance-ablation] wrote {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
