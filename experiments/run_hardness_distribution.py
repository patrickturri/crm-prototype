"""Hardness distribution experiment (review finding #6).

Computes hardness under ``strategy="literal"`` (old) vs ``strategy="rich"``
(new) over a fixed candidate set:

  1. The _POOL entries from OfflineCodeProposer (includes deliberately
     trivial/false entries so there is a real mix).
  2. The survivors from the best existing run
     (results/code-20260531-225343/artifacts.json).

For each candidate x strategy, we run hardness_for_conjecture() using the
CodeExecCritic, then report per-candidate hardness and aggregate
(min/mean/max/std) for both strategies.

Everything is deterministic (no API calls, no MiniLM — we use the hash
embedder so this is free and reproducible).

Outputs:
  results/findings/hardness_distribution.json
  docs/findings/hardness_distribution.md
"""

from __future__ import annotations

import json
import os
import statistics
from pathlib import Path
from typing import Any

# ---- project imports --------------------------------------------------------
from crm.critics.code_exec import CodeExecCritic
from crm.embedding import HashEmbedder
from crm.proposers_code import _POOL
from crm.significance import SignificanceCritic
from crm.types import Conjecture

REPO = Path(__file__).resolve().parent.parent
ARTIFACTS_PATH = REPO / "results" / "code-20260531-225343" / "artifacts.json"
OUT_DIR = REPO / "results" / "findings"
DOCS_DIR = REPO / "docs" / "findings"

PERTURBATIONS = 32   # large enough to distinguish distributions
SEED = 42


# ---- build candidate list ---------------------------------------------------

def _pool_candidates() -> list[dict[str, Any]]:
    """Return the offline proposer pool as (label, Conjecture) dicts."""
    out = []
    for i, entry in enumerate(_POOL):
        c = Conjecture(
            id=f"pool_{i:02d}",
            statement=entry["statement"],
            extra={
                "reference_impl": entry["reference_impl"],
                "tests": entry["tests"],
                "property": entry.get("property", ""),
                "domain": entry.get("domain", "[1,100]"),
            },
        )
        out.append({
            "id": c.id,
            "label": entry.get("nl_gloss", entry["statement"][:60]),
            "conjecture": c,
            "source": "pool",
        })
    return out


def _survivor_candidates() -> list[dict[str, Any]]:
    """Return the surviving artifacts as Conjectures."""
    if not ARTIFACTS_PATH.exists():
        print(f"[warn] artifacts not found at {ARTIFACTS_PATH}; skipping survivors")
        return []
    arts = json.loads(ARTIFACTS_PATH.read_text())
    out = []
    for cid, payload in arts.items():
        c = Conjecture(
            id=cid,
            statement=payload.get("statement", cid),
            extra={
                "reference_impl": payload.get("reference_impl", ""),
                "tests": payload.get("tests", ""),
                "property": payload.get("property", ""),
                "domain": payload.get("domain", "[1,100]"),
            },
        )
        # Use a short label from statement or id
        label = (payload.get("statement") or cid)[:70]
        out.append({
            "id": cid,
            "label": label,
            "conjecture": c,
            "source": "survivor",
        })
    return out


# ---- hardness computation ---------------------------------------------------

def compute_hardness(
    candidates: list[dict[str, Any]],
    strategy: str,
) -> list[dict[str, Any]]:
    """Run hardness for every candidate under the given strategy.

    Returns a list of result dicts with keys:
      id, label, source, strategy, hardness, n_perturbed, n_broken, ok
    """
    critic = CodeExecCritic(seed=SEED)
    sig = SignificanceCritic(
        perturbations=PERTURBATIONS,
        embedder="hash",
        seed=SEED,
        perturb_strategy=strategy,
    )
    results = []
    for rec in candidates:
        c = rec["conjecture"]
        try:
            h, details = sig.hardness_for_conjecture(c, critic)
            n_perturbed = len(details)
            n_broken = sum(1 for _, ok in details if not ok)
            ok = True
        except Exception as e:
            h = float("nan")
            n_perturbed = 0
            n_broken = 0
            ok = False
            print(f"  [error] {rec['id']}: {e}")

        results.append({
            "id": rec["id"],
            "label": rec["label"],
            "source": rec["source"],
            "strategy": strategy,
            "hardness": round(h, 6) if ok else None,
            "n_perturbed": n_perturbed,
            "n_broken": n_broken,
            "ok": ok,
        })
        status = f"{h:.3f}" if ok else "ERROR"
        print(f"    [{strategy}] {rec['id']}: hardness={status}  ({n_broken}/{n_perturbed} broken)")
    return results


# ---- aggregate stats --------------------------------------------------------

def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": None, "mean": None, "max": None, "std": None, "n": 0}
    return {
        "min": round(min(values), 6),
        "mean": round(statistics.mean(values), 6),
        "max": round(max(values), 6),
        "std": round(statistics.pstdev(values), 6),  # population std (fixed set)
        "n": len(values),
    }


# ---- main -------------------------------------------------------------------

def main() -> None:
    print("Building candidate set...")
    pool_cands = _pool_candidates()
    surv_cands = _survivor_candidates()
    all_cands = pool_cands + surv_cands
    print(f"  {len(pool_cands)} pool candidates, {len(surv_cands)} survivor candidates")

    print("\nComputing literal hardness...")
    lit_results = compute_hardness(all_cands, "literal")
    print("\nComputing rich hardness...")
    rich_results = compute_hardness(all_cands, "rich")

    # Build combined per-candidate view
    lit_map = {r["id"]: r for r in lit_results}
    rich_map = {r["id"]: r for r in rich_results}

    per_candidate = []
    for rec in all_cands:
        cid = rec["id"]
        lr = lit_map[cid]
        rr = rich_map[cid]
        per_candidate.append({
            "id": cid,
            "label": rec["label"],
            "source": rec["source"],
            "literal_hardness": lr["hardness"],
            "rich_hardness": rr["hardness"],
            "lit_n_perturbed": lr["n_perturbed"],
            "lit_n_broken": lr["n_broken"],
            "rich_n_perturbed": rr["n_perturbed"],
            "rich_n_broken": rr["n_broken"],
        })

    # Aggregate stats (exclude None / error rows)
    lit_vals = [r["hardness"] for r in lit_results if r["hardness"] is not None]
    rich_vals = [r["hardness"] for r in rich_results if r["hardness"] is not None]

    # Subsets by source
    def _vals(results, source):
        return [r["hardness"] for r in results if r["hardness"] is not None and r["source"] == source]

    lit_pool_vals = _vals(lit_results, "pool")
    rich_pool_vals = _vals(rich_results, "pool")
    lit_surv_vals = _vals(lit_results, "survivor")
    rich_surv_vals = _vals(rich_results, "survivor")

    # Does rich SEPARATE contentful from trivial?
    # Trivial pool entries are those whose nl_gloss/statement contains "vacuous",
    # "constant", "FALSE", or "double digit-reverse".  We identify them by id.
    trivial_ids = {
        rec["id"] for rec in pool_cands
        if any(k in (rec["label"] + rec["conjecture"].statement).lower()
               for k in ("vacuous", "constant-zero", "false:", "double digit-reverse"))
    }
    print(f"\nTrivial pool candidates: {trivial_ids}")

    trivial_lit  = [r["hardness"] for r in lit_results  if r["id"] in trivial_ids and r["hardness"] is not None]
    trivial_rich = [r["hardness"] for r in rich_results if r["id"] in trivial_ids and r["hardness"] is not None]
    content_ids  = {rec["id"] for rec in pool_cands} - trivial_ids
    content_lit  = [r["hardness"] for r in lit_results  if r["id"] in content_ids and r["hardness"] is not None]
    content_rich = [r["hardness"] for r in rich_results if r["id"] in content_ids and r["hardness"] is not None]

    # Separation: rich separates iff mean(contentful) > mean(trivial) by a
    # meaningful margin (>0.10 gap) AND the distributions do NOT overlap as badly.
    rich_gap = (statistics.mean(content_rich) if content_rich else 0.0) - \
               (statistics.mean(trivial_rich) if trivial_rich else 0.0)
    lit_gap  = (statistics.mean(content_lit) if content_lit else 0.0) - \
               (statistics.mean(trivial_lit) if trivial_lit else 0.0)
    rich_separates = bool(rich_gap > 0.10)

    output = {
        "meta": {
            "perturbations_per_candidate": PERTURBATIONS,
            "seed": SEED,
            "n_pool": len(pool_cands),
            "n_survivors": len(surv_cands),
            "n_total": len(all_cands),
            "trivial_pool_ids": sorted(trivial_ids),
        },
        "aggregate": {
            "literal": {
                "all": stats(lit_vals),
                "pool_only": stats(lit_pool_vals),
                "survivors_only": stats(lit_surv_vals),
                "trivial_pool": stats(trivial_lit),
                "contentful_pool": stats(content_lit),
            },
            "rich": {
                "all": stats(rich_vals),
                "pool_only": stats(rich_pool_vals),
                "survivors_only": stats(rich_surv_vals),
                "trivial_pool": stats(trivial_rich),
                "contentful_pool": stats(content_rich),
            },
        },
        "separation": {
            "literal_gap_contentful_minus_trivial": round(lit_gap, 6),
            "rich_gap_contentful_minus_trivial": round(rich_gap, 6),
            "rich_separates": rich_separates,
            "justification": (
                f"rich gap = {rich_gap:.3f} (content mean {statistics.mean(content_rich) if content_rich else 'N/A':.3f}"
                f" vs trivial mean {statistics.mean(trivial_rich) if trivial_rich else 'N/A':.3f}); "
                f"literal gap = {lit_gap:.3f}; "
                f"threshold for separation claim: >0.10"
            ),
        },
        "per_candidate": per_candidate,
    }

    # ---- write results files ------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "hardness_distribution.json"
    out_json.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {out_json}")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out_md = DOCS_DIR / "hardness_distribution.md"
    _write_md(output, out_md)
    print(f"Wrote {out_md}")

    # ---- print summary to stdout --------------------------------------------
    print("\n=== SUMMARY ===")
    lit_all = output["aggregate"]["literal"]["all"]
    rich_all = output["aggregate"]["rich"]["all"]
    print(f"Literal (all, n={lit_all['n']}):  mean={lit_all['mean']:.4f}  std={lit_all['std']:.4f}  min={lit_all['min']:.4f}  max={lit_all['max']:.4f}")
    print(f"Rich    (all, n={rich_all['n']}):  mean={rich_all['mean']:.4f}  std={rich_all['std']:.4f}  min={rich_all['min']:.4f}  max={rich_all['max']:.4f}")
    sep = output["separation"]
    print(f"Rich separates contentful from trivial: {sep['rich_separates']}")
    print(f"  {sep['justification']}")


def _write_md(output: dict, path: Path) -> None:
    meta = output["meta"]
    agg  = output["aggregate"]
    sep  = output["separation"]
    pcs  = output["per_candidate"]

    def _row(s: dict) -> str:
        if s["n"] == 0:
            return "n/a | n/a | n/a | n/a | 0"
        return f"{s['mean']:.3f} | {s['std']:.3f} | {s['min']:.3f} | {s['max']:.3f} | {s['n']}"

    lines = [
        "# Hardness Distribution: literal vs rich perturbation strategies",
        "",
        "Experiment addresses **review finding #6**: integer-literal +-1 mutations",
        "saturate hardness near 0.88 for all survivors, measuring syntactic",
        "brittleness rather than explanatory depth.",
        "",
        f"- Candidates: {meta['n_pool']} pool entries + {meta['n_survivors']} survivors = {meta['n_total']} total",
        f"- Perturbations per candidate per strategy: {meta['perturbations_per_candidate']}",
        f"- Seed: {meta['seed']}",
        f"- Embedder: hash (deterministic, no API)",
        "",
        "## Aggregate Hardness",
        "",
        "| Subset | Strategy | Mean | Std | Min | Max | N |",
        "|--------|----------|------|-----|-----|-----|---|",
        f"| All | literal | {_row(agg['literal']['all'])} |",
        f"| All | rich | {_row(agg['rich']['all'])} |",
        f"| Pool only | literal | {_row(agg['literal']['pool_only'])} |",
        f"| Pool only | rich | {_row(agg['rich']['pool_only'])} |",
        f"| Survivors | literal | {_row(agg['literal']['survivors_only'])} |",
        f"| Survivors | rich | {_row(agg['rich']['survivors_only'])} |",
        f"| Pool (trivial) | literal | {_row(agg['literal']['trivial_pool'])} |",
        f"| Pool (trivial) | rich | {_row(agg['rich']['trivial_pool'])} |",
        f"| Pool (contentful) | literal | {_row(agg['literal']['contentful_pool'])} |",
        f"| Pool (contentful) | rich | {_row(agg['rich']['contentful_pool'])} |",
        "",
        "## Separation Signal",
        "",
        f"- Literal gap (contentful minus trivial mean): **{sep['literal_gap_contentful_minus_trivial']:.3f}**",
        f"- Rich gap (contentful minus trivial mean): **{sep['rich_gap_contentful_minus_trivial']:.3f}**",
        f"- **Rich separates contentful from trivial: {sep['rich_separates']}**",
        f"- Threshold for separation claim: gap > 0.10",
        "",
        f"Justification: {sep['justification']}",
        "",
        "## Per-Candidate Hardness",
        "",
        "| id | source | label | literal | rich |",
        "|----|--------|-------|---------|------|",
    ]
    for r in pcs:
        lh = f"{r['literal_hardness']:.3f}" if r["literal_hardness"] is not None else "err"
        rh = f"{r['rich_hardness']:.3f}" if r["rich_hardness"] is not None else "err"
        label = (r["label"] or "")[:55].replace("|", "/")
        lines.append(f"| {r['id']} | {r['source']} | {label} | {lh} | {rh} |")

    lines += [
        "",
        "---",
        "*Numbers produced by `experiments/run_hardness_distribution.py`.*",
        "*All execution is real sandbox execution — no LLM-as-judge, no fabrication.*",
    ]
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
