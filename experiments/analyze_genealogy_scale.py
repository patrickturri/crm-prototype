"""Analyze the genealogy ablation at scale (review finding #3 + power).

Reads results/ablation_genealogy.csv (per-seed summary rows, round == -1),
computes per-seed values, the two-sample difference, and BOTH a Mann-Whitney U
and a Welch t-test (with p-values) on cumulative certified-novel AND on
trivial-rate. Writes:
  results/findings/genealogy_scale.json
  docs/findings/genealogy_scale.md   (with the per-seed table kept)

HONEST by construction: it reports whatever the data says, including a null /
non-significant / treatment-loses result, with the p-value attached. No number
is fabricated; every value is read from the CSV the real API run produced.
"""

from __future__ import annotations

import csv
import json
import statistics as st
from pathlib import Path

from scipy import stats

CSV = Path("results/ablation_genealogy.csv")
JSON_OUT = Path("results/findings/genealogy_scale.json")
MD_OUT = Path("docs/findings/genealogy_scale.md")


def _f(x: str) -> float:
    return float(x) if x not in ("", None) else float("nan")


def load_summary(csv_path: Path):
    """Return {mode: {seed: {certified, trivial_rate, survival_rate, mean_sig}}}."""
    by_mode: dict[str, dict[int, dict]] = {"genealogy": {}, "control": {}}
    with csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["round"]) != -1:
                continue  # only per-run summary rows
            mode = row["mode"]
            seed = int(row["seed"])
            by_mode.setdefault(mode, {})[seed] = {
                "cum_certified": int(row["cum_certified"]),
                "cum_survivors": int(row["cum_survivors"]),
                "cum_total": int(row["cum_total"]),
                "trivial_rate": _f(row.get("trivial_rate", "")),
                "survival_rate": _f(row.get("survival_rate", "")),
                "mean_significance": _f(row.get("mean_significance", "")),
            }
    return by_mode


def paired_series(by_mode, key):
    """Aligned per-seed lists for the seeds present in BOTH arms."""
    seeds = sorted(set(by_mode["genealogy"]) & set(by_mode["control"]))
    treat = [by_mode["genealogy"][s][key] for s in seeds]
    ctrl = [by_mode["control"][s][key] for s in seeds]
    return seeds, treat, ctrl


def stat_block(treat, ctrl):
    """Difference + Mann-Whitney U + Welch t, all with p-values."""
    treat_mean = st.mean(treat)
    ctrl_mean = st.mean(ctrl)
    treat_std = st.pstdev(treat) if len(treat) > 1 else 0.0
    ctrl_std = st.pstdev(ctrl) if len(ctrl) > 1 else 0.0
    block = {
        "treat_mean": treat_mean,
        "treat_std": treat_std,
        "ctrl_mean": ctrl_mean,
        "ctrl_std": ctrl_std,
        "diff_treat_minus_ctrl": treat_mean - ctrl_mean,
        "n_seeds": len(treat),
    }
    # Welch t-test (unequal variance), two-sided.
    try:
        t = stats.ttest_ind(treat, ctrl, equal_var=False)
        block["welch_t"] = float(t.statistic)
        block["welch_p"] = float(t.pvalue)
    except Exception as e:  # pragma: no cover
        block["welch_t"] = None
        block["welch_p"] = None
        block["welch_err"] = str(e)
    # Mann-Whitney U, two-sided.
    try:
        u = stats.mannwhitneyu(treat, ctrl, alternative="two-sided")
        block["mwu_u"] = float(u.statistic)
        block["mwu_p"] = float(u.pvalue)
    except Exception as e:  # pragma: no cover
        block["mwu_u"] = None
        block["mwu_p"] = None
        block["mwu_err"] = str(e)
    return block


def main() -> int:
    by_mode = load_summary(CSV)
    seeds, c_treat, c_ctrl = paired_series(by_mode, "cum_certified")
    _, t_treat, t_ctrl = paired_series(by_mode, "trivial_rate")

    certified = stat_block(c_treat, c_ctrl)
    trivial = stat_block(t_treat, t_ctrl)

    out = {
        "metric_primary": "cumulative certified-novel survivors (final round)",
        "metric_secondary": "trivial rate among valid conjectures",
        "n_seeds": len(seeds),
        "seeds": seeds,
        "proposer": "api_code (claude-sonnet-4-6)",
        "embedder": "hash (deterministic)",
        "per_seed": {
            str(s): {
                "genealogy_certified": by_mode["genealogy"][s]["cum_certified"],
                "control_certified": by_mode["control"][s]["cum_certified"],
                "genealogy_trivial_rate": by_mode["genealogy"][s]["trivial_rate"],
                "control_trivial_rate": by_mode["control"][s]["trivial_rate"],
            }
            for s in seeds
        },
        "certified_novel": certified,
        "trivial_rate": trivial,
    }

    # Honest one-line verdict on the primary metric.
    p = certified["welch_p"]
    diff = certified["diff_treat_minus_ctrl"]
    sig = (p is not None) and (p < 0.05)
    if not sig:
        verdict = (
            f"Genealogy does NOT significantly beat control on certified-novel "
            f"(diff={diff:+.2f}, Welch p={p:.3f}, MWU p={certified['mwu_p']:.3f}, "
            f"n={len(seeds)} seeds/arm). The H2 advantage is not established."
        )
    elif diff > 0:
        verdict = (
            f"Genealogy beats control on certified-novel "
            f"(diff={diff:+.2f}, Welch p={p:.3f}, n={len(seeds)})."
        )
    else:
        verdict = (
            f"Control beats genealogy on certified-novel "
            f"(diff={diff:+.2f}, Welch p={p:.3f}, n={len(seeds)})."
        )
    out["verdict"] = verdict

    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")

    # ---- Markdown ----------------------------------------------------------
    lines: list[str] = []
    lines.append("# Genealogy Ablation at Scale (H2)\n")
    lines.append(
        "Experiment addresses **review finding #3**: the genealogy ablation "
        "(the core H2 differentiator) did not beat control at n=3 and was "
        "underpowered. Re-run with the **real `api_code` proposer** (which reads "
        "the conditioning context, so the genealogy mechanism actually bites) at "
        f"**{len(seeds)} seeds per arm**.\n"
    )
    lines.append("- Proposer: api_code (claude-sonnet-4-6), temperature 0.7")
    lines.append("- Embedder: hash (deterministic), held fixed across arms")
    lines.append("- Critic: real sandboxed CodeExecCritic (never mocked)")
    lines.append(f"- Seeds: {seeds}\n")

    lines.append("## Verdict\n")
    lines.append(f"> {verdict}\n")

    lines.append("## Primary metric — cumulative certified-novel survivors\n")
    lines.append(
        "| seed | genealogy | control |\n|------|-----------|---------|"
    )
    for s in seeds:
        lines.append(
            f"| {s} | {by_mode['genealogy'][s]['cum_certified']} | "
            f"{by_mode['control'][s]['cum_certified']} |"
        )
    lines.append(
        f"| **mean +/- std** | **{certified['treat_mean']:.2f} +/- "
        f"{certified['treat_std']:.2f}** | **{certified['ctrl_mean']:.2f} +/- "
        f"{certified['ctrl_std']:.2f}** |\n"
    )
    lines.append(
        f"- Difference (treat - ctrl): **{certified['diff_treat_minus_ctrl']:+.2f}**"
    )
    lines.append(
        f"- Welch t-test: t = {certified['welch_t']:.3f}, "
        f"**p = {certified['welch_p']:.3f}**"
    )
    lines.append(
        f"- Mann-Whitney U: U = {certified['mwu_u']:.1f}, "
        f"**p = {certified['mwu_p']:.3f}**\n"
    )

    lines.append("## Secondary metric — trivial rate (among valid conjectures)\n")
    lines.append(
        "| seed | genealogy | control |\n|------|-----------|---------|"
    )
    for s in seeds:
        lines.append(
            f"| {s} | {by_mode['genealogy'][s]['trivial_rate']:.3f} | "
            f"{by_mode['control'][s]['trivial_rate']:.3f} |"
        )
    lines.append(
        f"| **mean +/- std** | **{trivial['treat_mean']:.3f} +/- "
        f"{trivial['treat_std']:.3f}** | **{trivial['ctrl_mean']:.3f} +/- "
        f"{trivial['ctrl_std']:.3f}** |\n"
    )
    lines.append(
        f"- Difference (treat - ctrl): **{trivial['diff_treat_minus_ctrl']:+.3f}**"
    )
    lines.append(
        f"- Welch t-test: t = {trivial['welch_t']:.3f}, "
        f"**p = {trivial['welch_p']:.3f}**"
    )
    lines.append(
        f"- Mann-Whitney U: U = {trivial['mwu_u']:.1f}, "
        f"**p = {trivial['mwu_p']:.3f}**\n"
    )

    lines.append("---")
    lines.append(
        "*Numbers produced by `experiments/ablation_genealogy.py` "
        "(8-seed API run) + `experiments/analyze_genealogy_scale.py`.*"
    )
    lines.append(
        "*Survive/die decisions are real sandbox execution; the proposer is the "
        "real Anthropic API. No number is fabricated.*"
    )

    MD_OUT.parent.mkdir(parents=True, exist_ok=True)
    MD_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(out, indent=2))
    print(f"\n[analyze] wrote {JSON_OUT} and {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
