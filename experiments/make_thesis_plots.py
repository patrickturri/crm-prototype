"""Generate the thesis-pass figures for the README from REAL result data.

Three figures (no fabricated numbers — every value is parsed from a committed
result file; fallback-contaminated rounds-scaling seeds are excluded):

  docs/assets/rounds_scaling_compounding.png
      Left: cumulative certified-novel vs round (genealogy vs control, clean
      seeds, mean +/- std band) — shows the plateau.
      Right: new-certified per round, early third vs late third (bars) — shows
      iteration does not compound.
      Source: results/rounds_scaling_run.log (parsed), clean_analysis.json.

  docs/assets/significance_auc.png
      AUC of each significance signal at separating certified vs rejected.
      Source: results/findings/hyp_H-novelty-is-score.json.

  docs/assets/robustness.png
      genealogy vs best-of-N across temperature/model settings.
      Source: results/findings/robustness/robustness.csv.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "results" / "rounds_scaling_run.log"
ASSETS = REPO / "docs" / "assets"

LINE = re.compile(
    r"^\s*(genealogy|control|best_of_N)\s+seed=(\d+)\s+cum_certified=(\[[^\]]*\])\s+new=(\[[^\]]*\])\s+fallback=(True|False)"
)

GEN, CTRL = "#1f77b4", "#d62728"


def _parse_log():
    arms = {"genealogy": [], "control": []}
    for ln in LOG.read_text().splitlines():
        m = LINE.match(ln)
        if not m:
            continue
        arm, seed, cum, new, fb = m.groups()
        if arm not in arms or fb == "True":
            continue  # drop other arms + fallback-contaminated seeds
        arms[arm].append({"cum": json.loads(cum), "new": json.loads(new)})
    return arms


def _mean_band(series):
    """series: list of equal-length lists -> (rounds, mean, std)."""
    n = min(len(s) for s in series)
    mat = np.array([s[:n] for s in series], dtype=float)
    return np.arange(1, n + 1), mat.mean(0), mat.std(0)


def fig_compounding(arms):
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(11, 4.2))

    # Left: cumulative trajectories with std band.
    for arm, color in (("genealogy", GEN), ("control", CTRL)):
        cums = [d["cum"] for d in arms[arm]]
        x, mu, sd = _mean_band(cums)
        axL.plot(x, mu, color=color, lw=2,
                 label=f"{arm} (n={len(cums)} clean seeds)")
        axL.fill_between(x, mu - sd, mu + sd, color=color, alpha=0.15)
    axL.set_xlabel("round")
    axL.set_ylabel("cumulative certified-novel")
    axL.set_title("Cumulative certified-novel vs round\n(both flatten — saturation)")
    axL.legend(frameon=False, fontsize=9)
    axL.grid(alpha=0.25)

    # Right: new-certified early third vs late third (bars).
    third = max(1, min(len(d["new"]) for a in arms.values() for d in a) // 3)
    labels, early_m, early_s, late_m, late_s = [], [], [], [], []
    for arm in ("genealogy", "control"):
        early = [sum(d["new"][:third]) for d in arms[arm]]
        late = [sum(d["new"][-third:]) for d in arms[arm]]
        labels.append(arm)
        early_m.append(statistics.mean(early)); early_s.append(statistics.pstdev(early))
        late_m.append(statistics.mean(late)); late_s.append(statistics.pstdev(late))
    xpos = np.arange(len(labels)); w = 0.36
    axR.bar(xpos - w / 2, early_m, w, yerr=early_s, capsize=4,
            color="#4c9f70", label=f"first {third} rounds")
    axR.bar(xpos + w / 2, late_m, w, yerr=late_s, capsize=4,
            color="#bbbbbb", label=f"last {third} rounds")
    axR.set_xticks(xpos); axR.set_xticklabels(labels)
    axR.set_ylabel("new certified-novel (sum over window)")
    axR.set_title("New discovery: early vs late rounds\n(late ≈ 0 — no compounding)")
    axR.legend(frameon=False, fontsize=9)
    axR.grid(alpha=0.25, axis="y")

    fig.suptitle("Deep rounds-scaling (25 rounds, configs/ablation.yaml) — iteration saturates, it does not compound",
                 fontsize=11, y=1.02)
    fig.tight_layout()
    out = ASSETS / "rounds_scaling_compounding.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def fig_auc():
    d = json.loads((REPO / "results" / "findings" / "hyp_H-novelty-is-score.json").read_text())
    sigs = [("novelty", d["novelty_auc_cert_vs_noncert"]),
            ("hardness", d["hardness_auc_cert_vs_noncert"]),
            ("breadth", d["breadth_auc_cert_vs_noncert"])]
    fig, ax = plt.subplots(figsize=(5.6, 4))
    names = [s[0] for s in sigs]; vals = [s[1] for s in sigs]
    colors = ["#2c7fb8" if v >= 0.6 else "#bbbbbb" for v in vals]
    bars = ax.bar(names, vals, color=colors)
    ax.axhline(0.5, color="k", ls="--", lw=1)
    ax.text(2.4, 0.51, "0.5 = no signal", fontsize=8, ha="right", va="bottom")
    ax.set_ylim(0, 0.8)
    ax.set_ylabel("AUC: certified vs rejected-valid")
    ax.set_title("What does the significance score discriminate on?\nOnly novelty carries signal")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.2f}", ha="center", fontsize=9)
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    out = ASSETS / "significance_auc.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def fig_robustness():
    rows = list(csv.DictReader(open(REPO / "results" / "findings" / "robustness" / "robustness.csv")))
    labels = [r["label"].replace("_", "\n") for r in rows]
    gen = [float(r["gen_mean"]) for r in rows]; gen_s = [float(r["gen_std"]) for r in rows]
    bon = [float(r["bestofn_mean"]) for r in rows]; bon_s = [float(r["bestofn_std"]) for r in rows]
    x = np.arange(len(rows)); w = 0.36
    fig, ax = plt.subplots(figsize=(6.6, 4))
    ax.bar(x - w / 2, gen, w, yerr=gen_s, capsize=4, color=GEN, label="genealogy")
    ax.bar(x + w / 2, bon, w, yerr=bon_s, capsize=4, color="#7f7f7f", label="best-of-N")
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("certified-novel (mean ± std, 3 seeds)")
    ax.set_title("Robustness: genealogy never beats best-of-N\n(across temperature and model)")
    ax.legend(frameon=False, fontsize=9)
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    out = ASSETS / "robustness.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    fig_compounding(_parse_log())
    fig_auc()
    fig_robustness()


if __name__ == "__main__":
    main()
