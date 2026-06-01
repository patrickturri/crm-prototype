"""Render SURVIVORS.md from a REAL critic run (§12.3) — never hand-authored.

Reads a run's ledger.jsonl (+ artifacts.json) produced by `make demo` on a REAL
critic (code-exec or Lean — never the mock, §3/§15) and emits the top certified-
novel survivors, each with:

  - the statement and nl_gloss exactly as the proposer wrote it,
  - the verifiable proof artifact the critic actually ran (the Python reference
    impl + property/tests for the code critic, or the Lean proof for Lean),
  - the significance breakdown (novelty · breadth · hardness → score),
  - the certify_novel verdict,
  - and the FAILED genealogy siblings from the same run with WHY each died
    (refuted-false + counterexample, or rejected-trivial + hardness) — §12.3.

Every line is copied from the run; nothing is invented. If a run has no
certified-novel survivors (e.g. a weak Lean run), the file says so honestly and
points at the run that carries the headline.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path


def _latest_run_with_certified(results: str) -> str | None:
    cands = sorted(
        glob.glob(os.path.join(results, "*", "ledger.jsonl")),
        key=os.path.getmtime,
        reverse=True,
    )
    for led in cands:
        run = os.path.dirname(led)
        if "smoke" in os.path.basename(run):
            continue  # mock critic — never a reported result (§3)
        n = sum(
            1
            for line in open(led, encoding="utf-8")
            if json.loads(line).get("certified_novel")
        )
        if n:
            return run
    return None


def _why_died(e: dict) -> str:
    cr = e.get("crit", {})
    sig = e.get("significance") or {}
    rc = cr.get("reason_class", "")
    detail = (cr.get("detail") or "").strip()
    if not cr.get("valid"):
        if rc == "FALSE":
            return f"REFUTED false — {detail}"
        if rc == "ILLFORMED":
            return f"ILL-FORMED — {detail}"
        if rc in ("UNPROVEN_BUDGET",):
            return f"UNPROVEN in budget — {detail}"
        if rc == "TIMEOUT":
            return "TIMEOUT — critic budget exceeded"
        return f"{rc} — {detail}"
    if sig.get("is_trivial"):
        hard = sig.get("hardness", 0.0)
        tau = 0.25
        if hard < tau:
            why = f"low hardness {hard:.2f} < tau {tau} (a trivial/vacuous truth — many true neighbours)"
        else:
            why = (
                f"closeable by automation/degenerate impl alone (hardness {hard:.2f} but "
                f"the independent automation probe also passes — no genuine content)"
            )
        return f"REJECTED trivial — {why}; score forced to 0"
    return "did not survive significance"


def _proof_block(e: dict, art: dict) -> str:
    a = art.get(e["id"], {})
    cr = e.get("crit", {})
    method = cr.get("proof_method", "")
    # Lean track: a supplied Lean proof.
    if a.get("lean_statement") or e.get("proof_attempt"):
        lean_stmt = a.get("lean_statement") or e.get("statement")
        proof = e.get("proof_attempt") or ""
        body = f"theorem crm_candidate : {lean_stmt} := {proof}".strip()
        return f"Proof method: {method} (verified by `lake env lean`)\n\n```lean\n{body}\n```"
    # Code track: the reference impl + property/tests the sandbox executed.
    impl = (a.get("reference_impl") or "").strip()
    prop = (a.get("property") or "").strip()
    lines = [f"Proof method: {method} (verified by real sandboxed execution — {cr.get('detail','')})"]
    if impl:
        block = impl
        if prop:
            block += f"\n\n# property checked over the sampled domain + adversarial inputs:\n{prop}"
        lines.append(f"\n```python\n{block}\n```")
    return "\n".join(lines)


def render(run: str, top: int = 5) -> str:
    led = os.path.join(run, "ledger.jsonl")
    entries = [json.loads(l) for l in open(led, encoding="utf-8")]
    art_path = os.path.join(run, "artifacts.json")
    art = json.load(open(art_path, encoding="utf-8")) if os.path.exists(art_path) else {}
    metrics = {}
    mp = os.path.join(run, "metrics.json")
    if os.path.exists(mp):
        metrics = json.load(open(mp, encoding="utf-8"))

    all_survivors = [e for e in entries if e.get("certified_novel")]
    n_certified = len(all_survivors)
    survivors = sorted(
        all_survivors,
        key=lambda e: e.get("significance", {}).get("score", 0),
        reverse=True,
    )
    survivors = survivors[:top]

    # Honest hardness curation note: the displayed top-N may all share one
    # hardness value while the full certified set does not (review finding #6).
    shown_hard = sorted({round(e.get("significance", {}).get("hardness", 0.0), 2) for e in survivors})
    all_hard = sorted({round(e.get("significance", {}).get("hardness", 0.0), 2) for e in all_survivors})

    # Optional: an intra-survivor dedup finding produced by
    # crm.novelty.dedup_survivors on this run (review finding #7). If present,
    # surface the raw-vs-deduped count so the headline is not overstated.
    dedup = {}
    for cand in (
        os.path.join(run, "dedup_collapse.json"),
        os.path.join("results", "findings", "dedup_collapse.json"),
        os.path.join("docs", "findings", "dedup_collapse.json"),
    ):
        if os.path.exists(cand):
            try:
                dedup = json.load(open(cand, encoding="utf-8"))
            except Exception:
                dedup = {}
            break

    # Siblings = every non-certified entry, grouped by round (genealogy story).
    failed = [e for e in entries if not e.get("certified_novel")]
    by_round: dict[int, list[dict]] = {}
    for e in failed:
        by_round.setdefault(e.get("round", 0), []).append(e)

    out: list[str] = []
    out.append("# Certified-novel survivors (real critic)\n")
    out.append(
        f"Top {len(survivors)} certified-novel survivors from a **real** run "
        f"(`{os.path.basename(run)}`, critic = `{metrics.get('critic','?')}`, "
        f"proposer = `{metrics.get('proposer','?')}`). Every survivor below was "
        f"produced by the loop and verified by the critic — **none is "
        f"hand-authored** (§3, §12.3). Each carries its verifiable proof/tests, "
        f"its significance breakdown, and the failed genealogy siblings from the "
        f"same run that explain WHY they didn't survive.\n"
    )
    out.append(
        f"> Headline KPIs for this run (seed {metrics.get('seed','?')}; "
        f"3-seed ablation means in REPORT.md): "
        f"**{metrics.get('certified_novel','?')}** certified-novel survivors · "
        f"**{metrics.get('certified_novel_per_kilo_token',0):.3f}** per kilo-token · "
        f"**{metrics.get('critic_seconds',0):.2f}s** total critic time "
        f"(~{1000*metrics.get('critic_seconds',0)/max(metrics.get('critic_invocations',1),1):.0f} ms/conjecture; "
        f"not annualized) "
        f"({metrics.get('total_conjectures','?')} conjectures over "
        f"{metrics.get('n_rounds','?')} rounds).\n"
    )

    # Honest reframing (review pass): operational novelty, intra-run dedup,
    # hardness-curation, and the testing-is-not-proof caveat.
    out.append(
        "> **Read this honestly.** *Certified-novel* here means **operational** "
        "novelty: a claim that is not a corpus restatement, is not closeable by a "
        "degenerate-impl probe, and is at embedding-distance >= 0.35 from the static "
        "corpus. It is **fuzz-tested on bounded integers, not proved** — see "
        "[`docs/FINDINGS.md`](FINDINGS.md). The survivors below are classical "
        "textbook number-theory identities (Mobius inversion = phi, sum phi(d) = n, "
        "sum floor(n/k) = sum d(n)); the system **rediscovers** them, it does not "
        "discover new mathematics.\n"
    )
    if dedup.get("raw_certified") and dedup.get("deduped_certified"):
        out.append(
            f"> **Intra-run dedup (finding #7).** This run did not apply "
            f"intra-survivor dedup at certification time. Re-measured with "
            f"`crm.novelty.dedup_survivors` (same MiniLM embedder, delta=0.35), the "
            f"**{dedup['raw_certified']}** certified survivors collapse to "
            f"**{dedup['deduped_certified']}** distinct clusters "
            f"({dedup.get('n_collapsed','?')} are intra-run near-duplicates) — see "
            f"[`docs/findings/dedup_collapse.md`](findings/dedup_collapse.md). The "
            f"updated `certify_novel` gate now blocks such duplicates at admission.\n"
        )
    if len(all_hard) > 1 and len(shown_hard) == 1:
        out.append(
            f"> **Hardness curation note (finding #6).** The {len(survivors)} "
            f"survivors shown below (top by score) all report hardness "
            f"{shown_hard[0]:.2f}, but the full set of {n_certified} certified "
            f"survivors spans hardness {{{', '.join(f'{h:.2f}' for h in all_hard)}}}. "
            f"Literal +-1 integer-literal perturbation measures numeric brittleness, "
            f"not explanatory depth; see "
            f"[`docs/findings/hardness_distribution.md`](findings/hardness_distribution.md).\n"
        )

    for i, e in enumerate(survivors, 1):
        sig = e.get("significance", {})
        out.append(f"## {i}. {e.get('nl_gloss','(survivor)')}\n")
        out.append(f"**Statement.** {e['statement']}\n")
        out.append(_proof_block(e, art) + "\n")
        out.append(
            f"**Significance.** novelty {sig.get('novelty',0):.2f} · breadth "
            f"{sig.get('breadth',0):.2f} · hardness {sig.get('hardness',0):.2f} → "
            f"score {sig.get('score',0):.2f} (is_trivial = {sig.get('is_trivial')}).\n"
        )
        out.append(
            f"**Certified novel.** yes — no corpus restatement, not closed by "
            f"automation alone, retrieval-distance {sig.get('novelty',0):.2f} ≥ delta.\n"
        )
        sibs = by_round.get(e.get("round", 0), [])
        if sibs:
            out.append("**Failed siblings from the genealogy (same round — why they didn't survive):**\n")
            for s in sibs:
                stmt = (s.get("statement") or "").strip()
                stmt = stmt if len(stmt) <= 160 else stmt[:157] + "..."
                out.append(f"- `{stmt}` — {_why_died(s)}")
            out.append("")
        out.append("")

    out.append("---\n")
    out.append(
        "_Generated by `experiments/make_survivors.py` from the run's "
        "`ledger.jsonl` + `artifacts.json`. Re-run `make demo` then "
        "`python -m experiments.make_survivors` to regenerate against a fresh "
        "real run._\n"
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render SURVIVORS.md from a real run (§12.3).")
    ap.add_argument("--run", default=None, help="run dir; default = latest non-smoke run with certified survivors")
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--out", default="SURVIVORS.md")
    args = ap.parse_args(argv)

    run = args.run or _latest_run_with_certified(args.results_dir)
    if not run:
        Path(args.out).write_text(
            "# Certified-novel survivors (real critic)\n\n"
            "No certified-novel survivors were found in any non-mock run under "
            "`results/`. Run `make demo` (code-exec or Lean) first; this file is "
            "generated only from a real critic run and is never hand-authored.\n",
            encoding="utf-8",
        )
        print("[make_survivors] no certified run found — wrote honest placeholder.")
        return 0

    Path(args.out).write_text(render(run, top=args.top), encoding="utf-8")
    print(f"[make_survivors] wrote {args.out} from {run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
