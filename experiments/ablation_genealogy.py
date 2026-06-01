"""Genealogy ablation (§9.1) — tests H2 (the reasoned-genealogy mechanism).

Treatment `mode="genealogy"` vs control `mode="control"`. EVERYTHING else is
identical — same proposer, model, topic, k, rounds, critic, proof budgets, and
the SAME seed list — so the two arms differ in EXACTLY one variable: whether the
next round's prompt carries the reasoned genealogy (WHY conjectures failed +
which survivors to build on) or merely the prior statements for dedup (§5.1).

Seeds: >=3 (default 5). Reports mean +/- std.
Primary metric : cumulative CERTIFIED-NOVEL survivors vs round.
Secondary      : mean significance of survivors, survival rate, trivial rate.

The critic is the real sandboxed CodeExecCritic — never mocked (§3, §15). Writes
per-seed CSVs to results/ and a summary CSV consumed by make_report.py. Reports
results HONESTLY even if treatment does not beat control (§3, §9.1, §15).
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from crm.run import load_config
from experiments._harness import run_arm

MODES = ["genealogy", "control"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Genealogy ablation (§9.1).")
    ap.add_argument("--config", default="configs/ablation.yaml")
    ap.add_argument("--seeds", type=int, default=5, help=">=3 (default 5)")
    ap.add_argument("--results-dir", default="results")
    args = ap.parse_args(argv)

    if args.seeds < 3:
        raise SystemExit("genealogy ablation requires >=3 seeds (§9.1).")

    cfg = load_config(args.config)
    rounds = int(cfg.get("rounds", 3))
    results = Path(args.results_dir)
    results.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    print(
        f"[genealogy-ablation] seeds={args.seeds} rounds={rounds} "
        f"critic={cfg.get('critic')} proposer={cfg.get('proposer', {}).get('kind')}"
    )
    for mode in MODES:
        for seed in range(args.seeds):
            res = run_arm(
                cfg,
                mode=mode,
                seed=seed,
                significance_on=True,  # genealogy ablation holds significance ON
                out_dir=results / "ablation_genealogy" / f"{mode}_seed{seed}",
            )
            for r in range(rounds):
                rows.append(
                    {
                        "mode": mode,
                        "seed": seed,
                        "round": r,
                        "cum_certified": res.cum_certified[r],
                        "cum_survivors": res.cum_survivors[r],
                        "cum_total": res.cum_total[r],
                    }
                )
            rows.append(
                {
                    "mode": mode,
                    "seed": seed,
                    "round": -1,  # sentinel: per-run summary
                    "cum_certified": res.cum_certified[-1] if res.cum_certified else 0,
                    "cum_survivors": res.cum_survivors[-1] if res.cum_survivors else 0,
                    "cum_total": res.cum_total[-1] if res.cum_total else 0,
                    "mean_significance": round(res.mean_significance, 6),
                    "survival_rate": round(res.survival_rate, 6),
                    "trivial_rate": round(res.trivial_rate, 6),
                }
            )
            print(
                f"  mode={mode:9s} seed={seed} "
                f"certified={res.cum_certified[-1] if res.cum_certified else 0} "
                f"survivors={res.cum_survivors[-1] if res.cum_survivors else 0} "
                f"mean_sig={res.mean_significance:.3f} "
                f"survival={res.survival_rate:.2f} trivial={res.trivial_rate:.2f}"
            )

    out_csv = results / "ablation_genealogy.csv"
    fields = [
        "mode",
        "seed",
        "round",
        "cum_certified",
        "cum_survivors",
        "cum_total",
        "mean_significance",
        "survival_rate",
        "trivial_rate",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})
    print(f"[genealogy-ablation] wrote {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
