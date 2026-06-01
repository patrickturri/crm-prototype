"""Best-of-N baseline vs the FULL CRM system (review finding #8).

The review asked: is the full pipeline (genealogy conditioning + significance
gate + intra-survivor embedding dedup + novelty certification) actually WORTH
the extra machinery, measured PER TOKEN, against a naive baseline?

This module pits two arms against each other on the SAME proposer, SAME critic,
SAME token budget:

  * BASELINE ("best-of-N + simple dedup"): propose N candidates with NO
    genealogy conditioning (control / empty-history context), keep the ones the
    real sandboxed critic certifies VALID, then dedup by NORMALISED STATEMENT
    STRING only (exact match after whitespace/case canonicalisation). NO
    significance gate, NO triviality suppression, NO embedding-distance novelty
    gate, NO intra-survivor embedding dedup. Its "certified" count is simply the
    number of distinct valid statements — the naive notion of "kept results".

  * FULL: the production pipeline via experiments._harness.run_arm with
    mode="genealogy", significance_on=True. Survivors are the significance-gated,
    novelty-certified, intra-survivor-deduped set.

Metrics compared (both arms, identical definitions):
  * certified_per_ktok   = #kept / (proposer_tokens / 1000)
  * trivial_rate         = fraction of the kept/surviving set that the GENUINELY
                           INDEPENDENT oracle (experiments._indep_oracle, the
                           one that shares no code with the gate, finding #5)
                           judges trivial/vacuous.

The honest question: the baseline keeps MORE statements per token (it gates on
nothing but validity + string identity), so if the full system "wins" it must be
on QUALITY (a much lower independent trivial rate), not raw throughput. We report
both numbers so the trade-off is explicit and un-spun.

Two run modes:
  * DETERMINISTIC FLOOR: offline_code proposer + hash embedder. Free, exactly
    reproducible. This is the number we trust and curate into docs.
  * API (labelled NONDETERMINISTIC): api_code proposer for a realistic
    comparison. Costs money; one seed; clearly flagged.

Outputs (results/ is gitignored but regenerable from configs + this module):
  results/findings/baseline.csv   — one row per (arm, seed)
  results/findings/baseline.json  — aggregated means/stds + provenance
  docs/findings/baseline.md       — curated human-readable summary (tracked)
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np

from crm.accounting import Accountant
from crm.genealogy import Entry, Ledger
from crm.novelty import _normalise
from crm.run import _build_critic, _build_proposer, _load_jsonl_statements
from crm.significance import SignificanceCritic
from experiments._harness import _independent_trivial_rate, run_arm


def _build_baseline_components(cfg: dict[str, Any]):
    """Proposer + critic for the baseline arm (same builders as the harness)."""
    proposer = _build_proposer(cfg.get("proposer", {}))
    critic = _build_critic(cfg.get("critic", "code_exec"), cfg)
    return proposer, critic


def run_baseline_arm(
    cfg: dict[str, Any],
    *,
    seed: int,
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Naive best-of-N + simple (string) dedup arm.

    NO genealogy (empty conditioning string each round, so the proposer never
    sees prior history), NO significance gate, NO embedding novelty gate, NO
    intra-survivor embedding dedup. Validity is still decided by the REAL
    sandboxed critic (the floor every arm shares). "Kept" = distinct VALID
    statements after exact normalised-string dedup.

    Returns a flat dict of metrics for one (baseline, seed) row, and the live
    (Entry, Conjecture) pairs of the kept set are fed to the SAME independent
    triviality oracle the full arm uses, so trivial_rate is apples-to-apples.
    """
    rounds = int(cfg.get("rounds", 3))
    k = int(cfg.get("k", 6))

    proposer, critic = _build_baseline_components(cfg)
    ledger = Ledger()
    acct = Accountant(
        est_cost_per_1k_in=cfg.get("est_cost_per_1k_in", 0.0),
        est_cost_per_1k_out=cfg.get("est_cost_per_1k_out", 0.0),
    )

    np.random.seed(seed % (2**32))

    # Best-of-N: N == rounds * k proposals total, but with NO conditioning. We
    # keep the round loop only to drive the proposer's per-call token accounting
    # identically to the full arm; the conditioning context is ALWAYS empty so
    # there is genuinely no genealogy signal.
    kept_norm_to_pair: dict[str, tuple[Entry, Any]] = {}
    n_valid = 0

    for r in range(rounds):
        ctx = ""  # NO genealogy conditioning — the defining baseline difference.
        batch = proposer.propose(ctx, k=k, seed=seed + r)
        acct.log_proposer(
            getattr(proposer, "last_tokens_in", 0),
            getattr(proposer, "last_tokens_out", 0),
        )
        for c in batch:
            c.round = r
            cr = critic.check(c)
            acct.log_critic(cr.critic_seconds)
            entry = Entry.from_conjecture(c, cr, surviving=cr.valid)
            ledger.add(entry)
            if not cr.valid:
                continue
            n_valid += 1
            # Simple dedup: exact match after normalisation (whitespace/case).
            # NO embedding distance — the naive baseline.
            norm = _normalise(c.statement)
            if norm in kept_norm_to_pair:
                # Mark the duplicate as not-surviving so survivor count == kept.
                entry.surviving = False
                continue
            entry.surviving = True
            entry.certified_novel = True  # baseline "certifies" any kept-distinct valid
            kept_norm_to_pair[norm] = (entry, c)
        acct.snapshot(round=r)

    kept_pairs = list(kept_norm_to_pair.values())
    n_kept = len(kept_pairs)

    metrics = acct.metrics(
        certified_novel=n_kept,
        surviving=n_kept,
        total_conjectures=len(ledger.entries),
    )

    # Independent triviality of the kept set — SAME oracle the full arm uses.
    indep_trivial = _independent_trivial_rate(kept_pairs, critic)

    tokens = metrics["proposer_tokens_total"]
    per_ktok = n_kept / (tokens / 1000.0) if tokens > 0 else 0.0

    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        ledger.dump(out / "ledger.jsonl")

    return {
        "arm": "baseline",
        "seed": seed,
        "kept": n_kept,
        "valid": n_valid,
        "total": len(ledger.entries),
        "tokens": tokens,
        "certified_per_ktok": per_ktok,
        "trivial_rate": indep_trivial,
        "critic_seconds": metrics["critic_seconds"],
        "proposer": getattr(proposer, "name", "?"),
        "using_fallback": bool(getattr(proposer, "using_fallback", False)),
    }


def run_full_arm(
    cfg: dict[str, Any],
    *,
    seed: int,
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    """FULL system arm via the production harness (genealogy + significance +
    intra-survivor dedup + novelty certification). certified = ledger.certified().
    """
    rr = run_arm(
        cfg,
        mode="genealogy",
        seed=seed,
        significance_on=True,
        out_dir=out_dir,
    )
    n_certified = rr.metrics["certified_novel"]
    tokens = rr.metrics["proposer_tokens_total"]
    per_ktok = n_certified / (tokens / 1000.0) if tokens > 0 else 0.0
    proposer_name = rr.metrics.get("proposer", "?")
    # "offline_code" is the deterministic generator; "api_code" that degraded is
    # also reported as api_code by name, so we flag offline by the proposer name.
    using_fallback = proposer_name == "offline_code"
    return {
        "arm": "full",
        "seed": seed,
        "kept": n_certified,
        "valid": rr.metrics["surviving"],
        "total": rr.metrics["total_conjectures"],
        "tokens": tokens,
        "certified_per_ktok": per_ktok,
        # trivial_rate of the SURVIVING set via the same independent oracle.
        "trivial_rate": rr.indep_trivial_rate,
        "critic_seconds": rr.metrics["critic_seconds"],
        "proposer": proposer_name,
        "using_fallback": using_fallback,
    }


def _agg(rows: list[dict], arm: str, key: str) -> dict[str, float]:
    vals = [r[key] for r in rows if r["arm"] == arm]
    if not vals:
        return {"mean": 0.0, "std": 0.0, "n": 0}
    mean = statistics.mean(vals)
    std = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return {"mean": mean, "std": std, "n": len(vals)}


def run_comparison(
    cfg: dict[str, Any],
    *,
    seeds: list[int],
    out_dir: Path,
    label: str,
) -> tuple[list[dict], dict]:
    """Run both arms across `seeds`, return (rows, aggregated summary)."""
    rows: list[dict] = []
    for s in seeds:
        rows.append(run_baseline_arm(cfg, seed=s, out_dir=out_dir / f"baseline_seed{s}"))
        rows.append(run_full_arm(cfg, seed=s, out_dir=out_dir / f"full_seed{s}"))

    summary = {
        "label": label,
        "seeds": seeds,
        "baseline_certified_per_ktok": _agg(rows, "baseline", "certified_per_ktok"),
        "full_certified_per_ktok": _agg(rows, "full", "certified_per_ktok"),
        "baseline_trivial_rate": _agg(rows, "baseline", "trivial_rate"),
        "full_trivial_rate": _agg(rows, "full", "trivial_rate"),
        "baseline_kept": _agg(rows, "baseline", "kept"),
        "full_kept": _agg(rows, "full", "kept"),
        "baseline_tokens": _agg(rows, "baseline", "tokens"),
        "full_tokens": _agg(rows, "full", "tokens"),
        # True if ANY arm used the deterministic offline generator (either
        # because proposer=offline_code, or an api_code call degraded to it).
        "any_offline_proposer": any(r["using_fallback"] for r in rows),
    }
    return rows, summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Best-of-N baseline vs full CRM (finding #8).")
    ap.add_argument("--config", default="configs/ablation.yaml")
    ap.add_argument("--seeds", default="0,1,2,3,4", help="comma-separated seeds")
    ap.add_argument(
        "--proposer",
        default="offline_code",
        choices=["offline_code", "api_code"],
        help="offline_code = deterministic free floor; api_code = nondeterministic realistic",
    )
    ap.add_argument("--out", default=None, help="results subdir (default by proposer)")
    args = ap.parse_args(argv)

    from crm.run import load_config

    cfg = load_config(args.config)
    # Force the chosen proposer + a deterministic free embedder for the floor.
    cfg["proposer"] = dict(cfg.get("proposer", {}))
    cfg["proposer"]["kind"] = args.proposer
    if args.proposer == "offline_code":
        cfg["embedder"] = "hash"
        cfg["offline_embedder"] = True
        deterministic = True
        label = "deterministic_floor(offline_code+hash)"
    else:
        deterministic = False
        label = "nondeterministic(api_code)"

    seeds = [int(s) for s in args.seeds.split(",") if s.strip() != ""]
    out_dir = Path(
        args.out
        or f"results/findings/baseline_{'offline' if deterministic else 'api'}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    rows, summary = run_comparison(cfg, seeds=seeds, out_dir=out_dir, label=label)
    summary["wall_seconds"] = round(time.monotonic() - t0, 3)
    summary["deterministic"] = deterministic
    summary["config"] = args.config

    # --- write CSV (one row per arm/seed) -----------------------------------
    # Curated deterministic floor -> baseline.csv/.json (the trusted numbers);
    # the nondeterministic API run -> baseline_api.csv/.json so it never clobbers
    # the reproducible floor.
    findings = Path("results/findings")
    findings.mkdir(parents=True, exist_ok=True)
    suffix = "" if deterministic else "_api"
    csv_path = findings / f"baseline{suffix}.csv"
    fields = [
        "arm", "seed", "kept", "valid", "total", "tokens",
        "certified_per_ktok", "trivial_rate", "critic_seconds",
        "proposer", "using_fallback",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})

    json_path = findings / f"baseline{suffix}.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(f"[baseline] {label}: {len(rows)} rows, {summary['wall_seconds']}s")
    print(f"[baseline]   baseline certified/ktok: "
          f"{summary['baseline_certified_per_ktok']['mean']:.4f} "
          f"+/- {summary['baseline_certified_per_ktok']['std']:.4f}")
    print(f"[baseline]   full     certified/ktok: "
          f"{summary['full_certified_per_ktok']['mean']:.4f} "
          f"+/- {summary['full_certified_per_ktok']['std']:.4f}")
    print(f"[baseline]   baseline trivial_rate:   "
          f"{summary['baseline_trivial_rate']['mean']:.4f} "
          f"+/- {summary['baseline_trivial_rate']['std']:.4f}")
    print(f"[baseline]   full     trivial_rate:   "
          f"{summary['full_trivial_rate']['mean']:.4f} "
          f"+/- {summary['full_trivial_rate']['std']:.4f}")
    print(f"[baseline]   CSV:  {csv_path}")
    print(f"[baseline]   JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
