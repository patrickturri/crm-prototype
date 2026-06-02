"""Post-hoc analysis of a rounds_scaling sweep (review: deep-run compounding test).

Reads the per-seed CSV (rounds_scaling.csv) and the per-arm token metrics
(metrics.json) written by experiments.rounds_scaling, and computes the four
reported quantities the deep-run finding needs:

  (a) per-round cumulative-certified trajectories per arm (mean +/- std);
  (b) ENDPOINT genealogy vs control: Welch t-test + Mann-Whitney U p-values;
  (c) COMPOUNDING test: mean NEW-certified-per-round in the FIRST third vs the
      LAST third of rounds, per arm (>0 late = still compounding; ~0 = plateau);
  (d) genealogy vs best_of_N at EQUAL budget, per-token (certified per 1k
      proposer tokens) — finding #8's efficiency lens.

No fabricated numbers: every value is derived from files under --results-dir.
Stats use scipy. Welch (unequal-variance) t and the non-parametric
Mann-Whitney U are reported side by side because n=8 is small.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy import stats

ARMS = ("genealogy", "control", "best_of_N")


def _load_csv(path: Path):
    rows = []
    with path.open() as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def _series_by_arm(rows, rounds):
    """{arm: {seed: {round: {cum, new}}}} -> arrays."""
    seeds = sorted({int(r["seed"]) for r in rows})
    out = {}
    for arm in ARMS:
        cum = np.zeros((len(seeds), rounds), dtype=float)
        new = np.zeros((len(seeds), rounds), dtype=float)
        for r in rows:
            if r["arm"] != arm:
                continue
            si = seeds.index(int(r["seed"]))
            rd = int(r["round"])
            cum[si, rd] = float(r["cum_certified"])
            new[si, rd] = float(r["new_certified"])
        out[arm] = {"cum": cum, "new": new, "seeds": seeds}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default="results/rounds_scaling")
    args = ap.parse_args(argv)
    root = Path(args.results_dir)

    summary = json.loads((root / "summary.json").read_text())
    rounds = int(summary["rounds"])
    k = int(summary["k"])
    rows = _load_csv(root / "rounds_scaling.csv")
    arms = _series_by_arm(rows, rounds)

    report = {
        "config": summary["config"], "rounds": rounds, "k": k,
        "seeds": summary["seeds"], "budget_candidates": rounds * k,
        "any_fallback": summary["any_fallback"], "fallbacks": summary["fallbacks"],
    }

    # ---- (a) trajectories: endpoint mean/std per arm ----------------------
    finals = {}
    for arm in ARMS:
        fc = arms[arm]["cum"][:, -1]
        finals[arm] = fc
        report[f"{arm}_final_mean"] = round(float(fc.mean()), 4)
        report[f"{arm}_final_std"] = round(float(fc.std()), 4)
        report[f"{arm}_traj_mean"] = [round(float(x), 3) for x in arms[arm]["cum"].mean(0)]
        report[f"{arm}_traj_std"] = [round(float(x), 3) for x in arms[arm]["cum"].std(0)]

    # ---- (b) endpoint genealogy vs control: Welch + Mann-Whitney ----------
    g, c, b = finals["genealogy"], finals["control"], finals["best_of_N"]
    tw, pw = stats.ttest_ind(g, c, equal_var=False)
    try:
        uu, pmw = stats.mannwhitneyu(g, c, alternative="two-sided")
    except ValueError:
        uu, pmw = float("nan"), float("nan")
    report["gen_final_mean"] = round(float(g.mean()), 4)
    report["gen_final_std"] = round(float(g.std()), 4)
    report["ctrl_final_mean"] = round(float(c.mean()), 4)
    report["ctrl_final_std"] = round(float(c.std()), 4)
    report["bestofn_final_mean"] = round(float(b.mean()), 4)
    report["bestofn_final_std"] = round(float(b.std()), 4)
    report["gen_minus_ctrl"] = round(float(g.mean() - c.mean()), 4)
    report["gen_vs_ctrl_welch_t"] = round(float(tw), 4)
    report["gen_vs_ctrl_p"] = round(float(pw), 4)  # Welch (primary)
    report["gen_vs_ctrl_mannwhitney_U"] = round(float(uu), 4)
    report["gen_vs_ctrl_mannwhitney_p"] = round(float(pmw), 4)

    # genealogy vs best_of_N endpoint too (count level)
    tb, pb = stats.ttest_ind(g, b, equal_var=False)
    report["gen_vs_bestofn_welch_t"] = round(float(tb), 4)
    report["gen_vs_bestofn_p"] = round(float(pb), 4)
    report["gen_minus_bestofn"] = round(float(g.mean() - b.mean()), 4)

    # ---- (c) COMPOUNDING test: first-third vs last-third NEW/round ---------
    third = max(1, rounds // 3)
    early_idx = list(range(0, third))
    late_idx = list(range(rounds - third, rounds))
    report["first_third_rounds"] = early_idx
    report["last_third_rounds"] = late_idx
    for arm in ARMS:
        new = arms[arm]["new"]  # (seeds, rounds)
        early = new[:, early_idx].mean(axis=1)  # per-seed mean new/round, early
        late = new[:, late_idx].mean(axis=1)
        # paired across seeds (same seed early vs late)
        tt, pp = stats.ttest_rel(late, early)
        report[f"{arm}_early_new_per_round_mean"] = round(float(early.mean()), 4)
        report[f"{arm}_late_new_per_round_mean"] = round(float(late.mean()), 4)
        report[f"{arm}_late_minus_early_new"] = round(float((late - early).mean()), 4)
        report[f"{arm}_late_vs_early_paired_t"] = round(float(tt), 4)
        report[f"{arm}_late_vs_early_paired_p"] = round(float(pp), 4)

    # convenience aliases the task asks for by name
    report["gen_late_vs_early_new_certified"] = report["genealogy_late_minus_early_new"]
    report["ctrl_late_vs_early"] = report["control_late_minus_early_new"]

    # ---- (d) per-token efficiency (equal candidate budget) ----------------
    def _arm_tokens(prefix):
        toks, certs = [], []
        for sd in arms[prefix]["seeds"] if prefix in arms else []:
            mp = root / f"{prefix}_seed{sd}" / "metrics.json"
            if mp.exists():
                m = json.loads(mp.read_text())
                toks.append(float(m.get("proposer_tokens_total", 0)))
                certs.append(float(m.get("certified_novel", 0)))
        return np.array(toks), np.array(certs)

    seeds = arms["genealogy"]["seeds"]
    eff = {}
    for arm in ARMS:
        toks, certs = _arm_tokens(arm)
        if len(toks) and toks.sum() > 0:
            per_seed_eff = np.where(toks > 0, certs / (toks / 1000.0), 0.0)
            eff[arm] = {
                "tokens_total_mean": round(float(toks.mean()), 1),
                "certified_total_mean": round(float(certs.mean()), 3),
                "certified_per_ktok_mean": round(float(per_seed_eff.mean()), 4),
                "certified_per_ktok_std": round(float(per_seed_eff.std()), 4),
                "n_seeds_with_metrics": int(len(toks)),
            }
        else:
            eff[arm] = {"note": "no token metrics persisted for this arm"}
    report["per_token"] = eff
    if "certified_per_ktok_mean" in eff.get("genealogy", {}) and \
       "certified_per_ktok_mean" in eff.get("best_of_N", {}):
        ge = eff["genealogy"]["certified_per_ktok_mean"]
        be = eff["best_of_N"]["certified_per_ktok_mean"]
        report["gen_vs_bestofn_per_ktok_ratio"] = round(ge / be, 4) if be else None
        report["gen_minus_bestofn_per_ktok"] = round(ge - be, 4)

    out = root / "analysis.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"\n[analyze] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
