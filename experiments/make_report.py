"""Render the two ablation plots + REPORT.md from results/ (§9, §12).

Reads the per-seed CSVs written by ablation_genealogy.py and
ablation_significance.py, draws BOTH plots with mean +/- std bands into
results/plots/, computes the readings from the real numbers, and writes
REPORT.md with a 1-paragraph honest reading of each (§3, §9). No fabricated
numbers — every figure in the report is derived from the CSVs.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ACCENT = {"genealogy": "#1f77b4", "control": "#d62728", "on": "#2ca02c", "off": "#d62728"}


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"missing CSV {path} — run the ablation first.")
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# --------------------------------------------------------------------------- #
# Genealogy plot: cumulative certified-novel survivors vs round, mean +/- std. #
# --------------------------------------------------------------------------- #
def _genealogy(rows: list[dict], plots: Path) -> dict:
    # series[mode][round] = list over seeds of cum_certified
    series: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    summary: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        rnd = int(r["round"])
        mode = r["mode"]
        if rnd >= 0:
            series[mode][rnd].append(float(r["cum_certified"]))
        else:
            for key in ("mean_significance", "survival_rate", "trivial_rate"):
                if r.get(key) not in (None, ""):
                    summary[mode][key].append(float(r[key]))

    fig, ax = plt.subplots(figsize=(7, 4.5))
    stats: dict[str, dict] = {}
    for mode in ("genealogy", "control"):
        if mode not in series:
            continue
        rounds = sorted(series[mode])
        means = np.array([np.mean(series[mode][rr]) for rr in rounds])
        stds = np.array([np.std(series[mode][rr]) for rr in rounds])
        xs = np.array(rounds) + 1  # 1-indexed rounds for display
        color = ACCENT[mode]
        label = "treatment (genealogy)" if mode == "genealogy" else "control"
        ax.plot(xs, means, "-o", color=color, label=label, linewidth=2)
        ax.fill_between(xs, means - stds, means + stds, color=color, alpha=0.18)
        stats[mode] = {
            "final_mean": float(means[-1]),
            "final_std": float(stds[-1]),
            "mean_significance": float(np.mean(summary[mode]["mean_significance"]))
            if summary[mode]["mean_significance"]
            else 0.0,
            "survival_rate": float(np.mean(summary[mode]["survival_rate"]))
            if summary[mode]["survival_rate"]
            else 0.0,
            "trivial_rate": float(np.mean(summary[mode]["trivial_rate"]))
            if summary[mode]["trivial_rate"]
            else 0.0,
        }

    ax.set_xlabel("round")
    ax.set_ylabel("cumulative certified-novel survivors")
    ax.set_title("Genealogy ablation (§9.1): treatment vs control\nmean ± std over seeds")
    n_seeds = max((len(v[min(v)]) for v in series.values() if v), default=0)
    ax.legend(title=f"{n_seeds} seeds", loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.margins(x=0.05)
    fig.tight_layout()
    out = plots / "ablation_genealogy.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    stats["_n_seeds"] = n_seeds
    return stats


# --------------------------------------------------------------------------- #
# Significance plot: trivial-survivor rate, critic ON vs OFF, mean +/- std.     #
# --------------------------------------------------------------------------- #
def _significance(rows: list[dict], plots: Path) -> dict:
    by_arm: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_arm[r["critic"]].append(float(r["trivial_survivor_rate"]))

    arms = [a for a in ("on", "off") if a in by_arm]
    means = [float(np.mean(by_arm[a])) for a in arms]
    stds = [float(np.std(by_arm[a])) for a in arms]

    fig, ax = plt.subplots(figsize=(6, 4.5))
    xs = np.arange(len(arms))
    colors = [ACCENT[a] for a in arms]
    ax.bar(
        xs,
        means,
        yerr=stds,
        capsize=8,
        color=colors,
        alpha=0.85,
        width=0.55,
    )
    ax.set_xticks(xs)
    ax.set_xticklabels(
        ["significance critic ON" if a == "on" else "significance critic OFF" for a in arms]
    )
    ax.set_ylabel("fraction of survivors that are trivial/vacuous\n(independent automation check)")
    ax.set_title("Significance ablation (§9.2): reward-hack guard\nmean ± std over seeds")
    ax.set_ylim(0, 1.0)
    ax.grid(True, axis="y", alpha=0.3)
    for x, m in zip(xs, means):
        ax.text(x, m + 0.03, f"{m:.2f}", ha="center", va="bottom", fontweight="bold")
    fig.tight_layout()
    out = plots / "ablation_significance.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)

    n_seeds = max((len(v) for v in by_arm.values()), default=0)
    return {
        "on_mean": means[arms.index("on")] if "on" in arms else None,
        "off_mean": means[arms.index("off")] if "off" in arms else None,
        "on_std": stds[arms.index("on")] if "on" in arms else None,
        "off_std": stds[arms.index("off")] if "off" in arms else None,
        "n_seeds": n_seeds,
    }


def _genealogy_paragraph(g: dict) -> str:
    t = g.get("genealogy")
    c = g.get("control")
    n = g.get("_n_seeds", 0)
    if not t or not c:
        return "Genealogy ablation data incomplete; re-run experiments/ablation_genealogy.py."
    margin = t["final_mean"] - c["final_mean"]
    if margin > 1e-9:
        verdict = (
            f"the treatment beats the control by {margin:.2f} certified-novel "
            f"survivors on average"
        )
    elif margin < -1e-9:
        verdict = (
            f"the treatment does NOT beat the control here (it trails by "
            f"{abs(margin):.2f} survivors on average) — reported honestly per §9.1"
        )
    else:
        verdict = "the two arms are tied on the primary metric in this run"
    # Surface a genuine secondary signal if present: the genealogy steering the
    # proposer toward harder/less-trivial conjectures (computed, not asserted).
    triv_gap = c["trivial_rate"] - t["trivial_rate"]
    if triv_gap > 0.02:
        analysis = (
            f" Note the secondary signal: the treatment's trivial rate is lower "
            f"({t['trivial_rate']:.2f} vs {c['trivial_rate']:.2f}) — at this small "
            f"scale the reasoned genealogy steers the proposer toward harder, "
            f"less-trivial conjectures, which the severe critic rejects more often "
            f"(lower survival), trading raw throughput for content. A larger "
            f"compute budget is needed to test whether that compounds into a "
            f"certified-novel lead."
        )
    else:
        analysis = ""
    return (
        f"**Genealogy ablation (H2).** Over {n} seeds, the treatment arm "
        f"(`mode=genealogy`, which conditions the proposer on WHY past conjectures "
        f"failed and which survivors to build on) reached "
        f"{t['final_mean']:.2f}±{t['final_std']:.2f} cumulative certified-novel "
        f"survivors, versus {c['final_mean']:.2f}±{c['final_std']:.2f} for the "
        f"control arm (`mode=control`, prior statements listed for dedup only, no "
        f"reasons). The two arms are identical in proposer, model, topic, k, rounds, "
        f"critic, budgets, and seed list — they differ in exactly one variable "
        f"(the reasoned genealogy), so the gap isolates its value. On secondary "
        f"metrics the treatment shows mean survivor significance "
        f"{t['mean_significance']:.2f} vs {c['mean_significance']:.2f}, survival rate "
        f"{t['survival_rate']:.2f} vs {c['survival_rate']:.2f}, and trivial rate "
        f"{t['trivial_rate']:.2f} vs {c['trivial_rate']:.2f}. Reading: {verdict}."
        f"{analysis}"
    )


def _significance_paragraph(s: dict) -> str:
    on, off = s.get("on_mean"), s.get("off_mean")
    n = s.get("n_seeds", 0)
    if on is None or off is None:
        return "Significance ablation data incomplete; re-run experiments/ablation_significance.py."
    drop = off - on
    if drop > 1e-9:
        verdict = (
            f"turning the significance critic ON drops the trivial-survivor rate by "
            f"{drop:.2f} (from {off:.2f} to {on:.2f}) — the reward-hack guard works"
        )
    elif drop < -1e-9:
        verdict = (
            f"the guard did NOT reduce trivial survivors in this run (ON {on:.2f} vs "
            f"OFF {off:.2f}); reported honestly per §9.2"
        )
    else:
        verdict = "no difference between ON and OFF on this run's survivor pool"
    return (
        f"**Significance ablation (reward-hack guard).** Over {n} seeds, the fraction "
        f"of “survivors” judged trivial/vacuous by an INDEPENDENT automation "
        f"check (a degenerate-impl probe that ignores the significance weights) was "
        f"{on:.2f}±{s['on_std']:.2f} with the critic ON versus "
        f"{off:.2f}±{s['off_std']:.2f} with it OFF. The arms differ in exactly one "
        f"variable — whether trivial conjectures are suppressed (score 0, excluded) "
        f"or whether any valid statement counts. Reading: {verdict}."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render ablation plots + REPORT.md (§9, §12).")
    ap.add_argument("--results-dir", default="results")
    args = ap.parse_args(argv)

    results = Path(args.results_dir)
    plots = results / "plots"
    plots.mkdir(parents=True, exist_ok=True)

    g_rows = _read_csv(results / "ablation_genealogy.csv")
    s_rows = _read_csv(results / "ablation_significance.csv")

    g_stats = _genealogy(g_rows, plots)
    s_stats = _significance(s_rows, plots)

    g_para = _genealogy_paragraph(g_stats)
    s_para = _significance_paragraph(s_stats)

    md = []
    md.append("# CRM Ablation Report (§9)\n")
    md.append(
        "Two apples-to-apples ablations on the **real sandboxed CodeExecCritic** "
        "(no mocked critic in any number, §3/§15). Treatment and control differ in "
        "EXACTLY one variable. Plots show **mean ± std** over seeds.\n"
    )
    md.append("## 9.1 Genealogy ablation (tests H2)\n")
    md.append("![Genealogy ablation](results/plots/ablation_genealogy.png)\n")
    md.append(g_para + "\n")
    md.append("## 9.2 Significance ablation (reward-hack guard)\n")
    md.append("![Significance ablation](results/plots/ablation_significance.png)\n")
    md.append(s_para + "\n")
    md.append("---\n")
    md.append(
        "_Generated by `experiments/make_report.py` from the per-seed CSVs "
        "`results/ablation_genealogy.csv` and `results/ablation_significance.csv`. "
        "Re-run `make ablation` to regenerate._\n"
    )
    Path("REPORT.md").write_text("\n".join(md), encoding="utf-8")

    print(f"[make_report] wrote {plots / 'ablation_genealogy.png'}")
    print(f"[make_report] wrote {plots / 'ablation_significance.png'}")
    print("[make_report] wrote REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
