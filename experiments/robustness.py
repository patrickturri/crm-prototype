"""Robustness / model-sensitivity of the genealogy null (review extension).

Every known CRM null (H2 not supported; best_of_N >= genealogy) was measured
with ONE proposer config: claude-sonnet-4-6 @ temperature 0.7. A fair reader
asks: are those conclusions a property of the MECHANISM, or an artefact of that
particular model/temperature? This experiment re-runs a SLICE of the
genealogy-vs-best_of_N comparison under three proposer settings:

  * sonnet@0.7  — the baseline used by every prior finding (control point).
  * sonnet@0.3  — same model, lower temperature (less stochastic proposing).
  * haiku@4-5   — a DIFFERENT (smaller/faster) model at the baseline temp.

Only TWO arms are run per setting (to stay within a bounded API budget; the
task asks specifically for genealogy-vs-best_of_N):

  1. genealogy  — full loop, mode="genealogy" (experiments._harness.run_arm):
                  each round's prompt carries WHY past conjectures died + which
                  survivors to build on. The mechanism under test.
  2. best_of_N  — ONE flat batch of R*k candidates, EMPTY context, then the SAME
                  sandboxed CodeExecCritic + significance gate + intra-set dedup
                  (experiments.rounds_scaling.run_best_of_n_rounds). The
                  memoryless reference the machinery must beat.

Metric: distinct certified-novel survivors after R rounds, mean over seeds.
Per setting we report gen_mean, bestofn_mean, delta = gen-bestofn, and a
Welch t-test (scipy) on the per-seed finals. The HONEST question: does the
sign/size of `delta` move when we change model or temperature?

FALLBACK GUARD (hard rule): both arms use the real LLM proposer. If ANY arm
silently degrades to the offline, context-IGNORING generator the genealogy
comparison is INVALID, so we DETECT it and raise FallbackError (non-zero exit,
no summary) — reusing experiments.rounds_scaling.FallbackError. NO LLM-as-judge:
survive/die is real sandbox execution throughout.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from crm.run import load_config
from experiments._harness import run_arm
from experiments.rounds_scaling import FallbackError, run_best_of_n_rounds

# (model, temperature, label) — label is the on-disk + reporting key.
SETTINGS: list[tuple[str, float, str]] = [
    ("claude-sonnet-4-6", 0.7, "sonnet_t07"),  # prior-findings baseline
    ("claude-sonnet-4-6", 0.3, "sonnet_t03"),  # same model, lower temp
    ("claude-haiku-4-5", 0.7, "haiku_t07"),    # different model
]


def _welch(a: list[float], b: list[float]) -> tuple[float, float]:
    """Welch's t-test (unequal variance). Returns (t, p); (nan, nan) if degenerate."""
    try:
        from scipy import stats
    except Exception:
        return float("nan"), float("nan")
    a_arr, b_arr = np.asarray(a, float), np.asarray(b, float)
    if len(a_arr) < 2 or len(b_arr) < 2 or (a_arr.std() == 0 and b_arr.std() == 0):
        return float("nan"), float("nan")
    t, p = stats.ttest_ind(a_arr, b_arr, equal_var=False)
    return float(t), float(p)


def _run_setting(
    base_cfg: dict[str, Any],
    *,
    model: str,
    temperature: float,
    label: str,
    rounds: int,
    k: int,
    seeds: int,
    out_dir: Path,
) -> dict[str, Any]:
    cfg = dict(base_cfg)
    cfg["rounds"] = rounds
    cfg["k"] = k
    # Override the proposer model/temperature for THIS setting only; everything
    # else (critic, embedder=hash, weights, corpus, breadth targets) is held
    # fixed so the comparison isolates the proposer config.
    prop = dict(cfg.get("proposer", {}))
    prop["model"] = model
    prop["temperature"] = temperature
    cfg["proposer"] = prop

    out_dir.mkdir(parents=True, exist_ok=True)
    fallbacks: list[str] = []

    gen_finals: list[int] = []
    bon_finals: list[int] = []
    gen_traj: list[list[int]] = []
    bon_traj: list[list[int]] = []
    proposer_names: set[str] = set()

    for seed in range(seeds):
        res = run_arm(
            cfg, mode="genealogy", seed=seed, significance_on=True,
            out_dir=out_dir / f"genealogy_seed{seed}",
        )
        proposer_names.add(res.proposer_name)
        if res.using_fallback:
            fallbacks.append(f"{label}/genealogy/seed{seed} (proposer={res.proposer_name})")
        gen_finals.append(res.cum_certified[-1] if res.cum_certified else 0)
        gen_traj.append(res.cum_certified)
        print(
            f"  [{label}] genealogy seed={seed} cum_certified={res.cum_certified} "
            f"proposer={res.proposer_name} fallback={res.using_fallback}"
        )

    for seed in range(seeds):
        m = run_best_of_n_rounds(
            cfg, rounds=rounds, k=k, seed=seed,
            out_dir=out_dir / f"best_of_N_seed{seed}",
        )
        proposer_names.add(m["proposer"])
        if m["using_fallback"]:
            fallbacks.append(f"{label}/best_of_N/seed{seed} (proposer={m['proposer']})")
        bon_finals.append(m["cum_certified"][-1] if m["cum_certified"] else 0)
        bon_traj.append(m["cum_certified"])
        print(
            f"  [{label}] best_of_N seed={seed} cum_certified={m['cum_certified']} "
            f"proposer={m['proposer']} fallback={m['using_fallback']}"
        )

    gen_mean = float(np.mean(gen_finals)) if gen_finals else 0.0
    bon_mean = float(np.mean(bon_finals)) if bon_finals else 0.0
    t, p = _welch([float(x) for x in gen_finals], [float(x) for x in bon_finals])

    result = {
        "label": label,
        "model": model,
        "temperature": temperature,
        "rounds": rounds,
        "k": k,
        "seeds": seeds,
        "proposer_names": sorted(proposer_names),
        "gen_finals": gen_finals,
        "bestofn_finals": bon_finals,
        "gen_mean": round(gen_mean, 4),
        "gen_std": round(float(np.std(gen_finals)), 4) if gen_finals else 0.0,
        "bestofn_mean": round(bon_mean, 4),
        "bestofn_std": round(float(np.std(bon_finals)), 4) if bon_finals else 0.0,
        "delta": round(gen_mean - bon_mean, 4),
        "welch_t": round(t, 4) if t == t else None,
        "welch_p": round(p, 4) if p == p else None,
        "gen_trajectories": gen_traj,
        "bestofn_trajectories": bon_traj,
        "any_fallback": bool(fallbacks),
        "fallbacks": fallbacks,
    }
    (out_dir / "setting.json").write_text(json.dumps(result, indent=2))
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Robustness / model-sensitivity sweep.")
    ap.add_argument("--config", default="configs/ablation.yaml")
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--results-dir", default="results/findings/robustness")
    ap.add_argument(
        "--allow-fallback", action="store_true",
        help="permit the offline proposer (ONLY for an offline smoke; with the "
             "API config this disables the silent-invalidation guard).",
    )
    ap.add_argument(
        "--resume", action="store_true",
        help="reuse an already-written setting.json for a label IF it matches "
             "the requested rounds/seeds/model/temperature (so a re-run after an "
             "interrupted sweep does not re-spend API calls on completed slices).",
    )
    args = ap.parse_args(argv)
    if args.seeds < 1:
        raise SystemExit("robustness requires >=1 seed.")

    base_cfg = load_config(args.config)
    k = int(base_cfg.get("k", 6))
    out_root = Path(args.results_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    print(
        f"[robustness] config={args.config} rounds={args.rounds} k={k} "
        f"seeds={args.seeds} settings={[s[2] for s in SETTINGS]}"
    )

    settings_out: list[dict[str, Any]] = []
    all_fallbacks: list[str] = []
    for model, temp, label in SETTINGS:
        existing = out_root / label / "setting.json"
        if args.resume and existing.exists():
            prior = json.loads(existing.read_text())
            # Only reuse if it was computed at the SAME rounds/seeds/model/temp,
            # so a resumed run is never silently mixing incompatible slices.
            if (
                prior.get("rounds") == args.rounds
                and prior.get("seeds") == args.seeds
                and prior.get("model") == model
                and float(prior.get("temperature", -1)) == float(temp)
            ):
                print(f"[robustness] === setting {label}: RESUMED from {existing} ===")
                settings_out.append(prior)
                all_fallbacks.extend(prior.get("fallbacks", []))
                continue
        print(f"[robustness] === setting {label}: model={model} temp={temp} ===")
        res = _run_setting(
            base_cfg, model=model, temperature=temp, label=label,
            rounds=args.rounds, k=k, seeds=args.seeds,
            out_dir=out_root / label,
        )
        settings_out.append(res)
        all_fallbacks.extend(res["fallbacks"])

    # ---- FALLBACK GUARD (hard rule) — fail loud on silent degrade ----------
    if all_fallbacks and not args.allow_fallback:
        msg = (
            "FALLBACK DETECTED — robustness result INVALID. An API arm degraded "
            f"to the offline, context-IGNORING generator in {len(all_fallbacks)} "
            "arm(s):\n  - " + "\n  - ".join(all_fallbacks) +
            "\nCheck ANTHROPIC_API_KEY / model availability. (For an intentional "
            "offline smoke, pass --allow-fallback.)"
        )
        raise FallbackError(msg)

    # ---- tidy CSV across settings -----------------------------------------
    csv_path = out_root / "robustness.csv"
    fields = [
        "label", "model", "temperature", "rounds", "k", "seeds",
        "gen_mean", "gen_std", "bestofn_mean", "bestofn_std",
        "delta", "welch_t", "welch_p", "any_fallback",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for s in settings_out:
            w.writerow({k_: s.get(k_, "") for k_ in fields})

    # ---- summary -----------------------------------------------------------
    summary = {
        "config": args.config,
        "rounds": args.rounds,
        "k": k,
        "seeds": args.seeds,
        "arms": ["genealogy", "best_of_N"],
        "metric": "distinct certified-novel survivors after R rounds (mean over seeds)",
        "any_fallback": bool(all_fallbacks),
        "fallbacks": all_fallbacks,
        "settings": [
            {
                "label": s["label"], "model": s["model"], "temperature": s["temperature"],
                "proposer_names": s["proposer_names"],
                "gen_mean": s["gen_mean"], "gen_std": s["gen_std"],
                "bestofn_mean": s["bestofn_mean"], "bestofn_std": s["bestofn_std"],
                "delta": s["delta"], "welch_t": s["welch_t"], "welch_p": s["welch_p"],
                "gen_finals": s["gen_finals"], "bestofn_finals": s["bestofn_finals"],
            }
            for s in settings_out
        ],
    }
    # Is the conclusion (best_of_N >= genealogy, i.e. delta <= 0 with no
    # significant positive delta) stable across every setting?
    deltas = [s["delta"] for s in settings_out]
    summary["all_deltas_nonpositive"] = all(d <= 0 for d in deltas)
    summary["any_significant_positive"] = any(
        (s["delta"] > 0 and s["welch_p"] is not None and s["welch_p"] < 0.05)
        for s in settings_out
    )
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"[robustness] wrote {csv_path} and {out_root / 'summary.json'}")
    for s in settings_out:
        print(
            f"[robustness] {s['label']:12s} model={s['model']} t={s['temperature']} "
            f"gen={s['gen_mean']}+/-{s['gen_std']} bON={s['bestofn_mean']}+/-{s['bestofn_std']} "
            f"delta={s['delta']} p={s['welch_p']}"
        )
    print(
        f"[robustness] all_deltas_nonpositive={summary['all_deltas_nonpositive']} "
        f"any_significant_positive_genealogy_advantage={summary['any_significant_positive']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
