"""Proposer-responsiveness diagnostic (root-cause for H2).

The genealogy thesis (H2) lost at n=8 easy and n=10 hard (finding #3). Before
spending more on long-rounds compounding runs, we need the ROOT CAUSE: when the
REAL APICodeProposer is handed a genealogy-mode conditioning context vs a
control-mode one, does its OUTPUT DISTRIBUTION actually change at all?

Two failure modes, very different implications:

  * The proposer IGNORES the genealogy entirely -> the proposal batches are
    statistically indistinguishable between modes. Then H2's null is an
    *implementation* artefact (fixable: stronger prompt, examples, etc.).

  * The proposer USES the genealogy (batches measurably differ, proposals
    reference/avoid the listed failure modes) but it still doesn't yield more
    certified-novel knowledge. Then H2's null is a *deeper* property of the
    mechanism on this domain (not fixable by prompt tweaks).

Method (modest API cost — 2 modes x N seeds x 1 call each, default 3 seeds = 6
real calls, plus an optional empty-context arm):

  1. Build a realistic NON-EMPTY ledger: a few PROVED survivors (with content
     scores) and a few FALSE/REFUTED entries (with their counterexample
     reasons), shaped exactly as crm.genealogy.Entry so
     build_conditioning_context renders the real genealogy/control blocks.
  2. For each seed, call the REAL APICodeProposer.propose with
     (a) genealogy context, (b) control context, (optionally c) empty context.
  3. Measure, per seed:
       - embedding distance between MATCHED proposals (greedy nearest-neighbour
         match of genealogy<->control statements, mean 1-cosine over matches),
         using crm.embedding;
       - Jaccard overlap of normalised statement sets;
       - whether genealogy proposals textually reference/avoid the prior failure
         modes (keyword probe over the FALSE statements + an LLM-free heuristic).
  4. Aggregate, decide proposals_shift (is the distribution measurably
     different?), and write results/findings/responsiveness.json +
     docs/findings/responsiveness.md.

HARD RULES respected: no fabricated numbers (everything traces to the JSON);
detects silent offline fallback and FAILS LOUDLY (a fallback proposer ignores
context by construction, so the diagnostic would be meaningless); no
LLM-as-judge for any survive/die decision (there is none here — this is a
pure proposer-distribution probe).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

from crm.critics.base import CritResult
from crm.embedding import get_embedder
from crm.genealogy import Entry, Ledger, build_conditioning_context
from crm.run import _build_proposer

TOPIC = "elementary number theory and combinatorics (Python-verifiable)"


def _proved(idx: int, stmt: str, score: float) -> Entry:
    """A surviving, high-content PROVED entry (genealogy 'build on these')."""
    from crm.significance import Significance

    e = Entry(
        id=f"p_{idx:02d}",
        round=0,
        parent_ids=[],
        statement=stmt,
        nl_gloss="",
        proof_attempt="",
        crit=CritResult(
            valid=True,
            reason_class="PROVED",
            detail="all adversarial tests passed",
            proof_method="tests_passed",
            critic_seconds=0.01,
        ),
        surviving=True,
    )
    e.significance = Significance(
        novelty=0.5,
        breadth=0.5,
        hardness=0.7,
        is_trivial=False,
        score=score,
    )
    return e


def _false(idx: int, stmt: str, detail: str) -> Entry:
    """A REFUTED entry with a real counterexample reason (genealogy 'why it died')."""
    return Entry(
        id=f"f_{idx:02d}",
        round=0,
        parent_ids=[],
        statement=stmt,
        nl_gloss="",
        proof_attempt="",
        crit=CritResult(
            valid=False,
            reason_class="FALSE",
            detail=detail,
            proof_method=None,
            critic_seconds=0.01,
        ),
        surviving=False,
    )


def build_realistic_ledger() -> Ledger:
    """A plausible mid-run ledger: 3 surviving results + 4 refuted attempts.

    The FALSE entries carry concrete, distinctive failure modes a responsive
    proposer could plausibly steer around (digit-reversal on multiples of 10, a
    false primality shortcut, an off-by-one Fibonacci identity, a wrong
    perfect-number characterisation). The survivors are genuine, content-bearing
    NT facts to 'build on'.
    """
    ledger = Ledger()
    # Surviving, high-content results to build on.
    for e in [
        _proved(0, "f(n) = sum of squares 1..n; equals n(n+1)(2n+1)/6", 0.71),
        _proved(1, "f(n) = Euler totient phi(n); equals count of k in [1,n] coprime to n", 0.66),
        _proved(2, "f(n) = number of positive divisors of n; equals trial-division count", 0.58),
    ]:
        ledger.add(e)
    # Refuted attempts with WHY (counterexamples).
    for e in [
        _false(
            0,
            "f(n) = double digit-reverse of n returns n for all n",
            "counterexample n=120: reverse->21, reverse->12 != 120 (fails on multiples of 10)",
        ),
        _false(
            1,
            "f(n) = n is prime iff 2^(n-1) % n == 1 (Fermat test as exact primality)",
            "counterexample n=341: 2^340 % 341 == 1 but 341 = 11*31 is composite (pseudoprime)",
        ),
        _false(
            2,
            "f(n) = n-th Fibonacci squared equals product of its two neighbours",
            "counterexample n=5: F(5)^2=25 but F(4)*F(6)=3*8=24 (Catalan identity has +/-1 offset)",
        ),
        _false(
            3,
            "f(n) = n is perfect iff n equals sum of all its divisors",
            "counterexample n=6: sum of ALL divisors 1+2+3+6=12 != 6 (must exclude n itself)",
        ),
    ]:
        ledger.add(e)
    return ledger


# --- distribution-shift metrics -------------------------------------------

def _norm_stmt(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _matched_embedding_distance(emb, stmts_a: list[str], stmts_b: list[str]) -> float:
    """Mean (1 - cosine) over a greedy nearest-neighbour matching A->B.

    For each genealogy statement we find its closest control statement and take
    the embedding distance to that nearest neighbour, then average. 0 means the
    two batches contain (near-)identical statements; larger means the batches
    drift apart. Uses crm.embedding (L2-normalised rows -> dot == cosine).
    """
    if not stmts_a or not stmts_b:
        return float("nan")
    va = emb.encode(stmts_a)
    vb = emb.encode(stmts_b)
    sims = va @ vb.T  # (|a|, |b|) cosine matrix
    nearest = sims.max(axis=1)  # best control match per genealogy stmt
    dists = 1.0 - nearest
    return float(np.mean(dists))


def _jaccard(stmts_a: list[str], stmts_b: list[str]) -> float:
    a = {_norm_stmt(s) for s in stmts_a if _norm_stmt(s)}
    b = {_norm_stmt(s) for s in stmts_b if _norm_stmt(s)}
    if not a and not b:
        return float("nan")
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else float("nan")


# Distinctive content tokens from each FALSE statement / reason. A responsive
# proposer told "do not repeat these failure modes" would either (a) avoid these
# topics, or (b) explicitly reference / correct them. Either is evidence of use.
_FAILURE_TOPICS = {
    "digit-reverse / palindrome": ["revers", "palindrom", "digit"],
    "fermat pseudoprime / primality shortcut": ["fermat", "pseudoprime", "2^", "prime"],
    "fibonacci neighbour identity": ["fibonacci", "fib(", "catalan", "neighbour", "neighbor"],
    "perfect-number / divisor-sum characterisation": ["perfect", "aliquot", "proper divisor", "sum of all its divisors"],
}


def _failure_reference_audit(stmts: list[str]) -> dict:
    """Heuristic, LLM-free audit: does the batch touch the prior failure topics?

    NOT a survive/die decision and NOT an LLM judgement — a transparent keyword
    probe over the proposed statements, so the qualitative claim is traceable.
    """
    blob = " \n ".join(_norm_stmt(s) for s in stmts)
    hits: dict[str, list[str]] = {}
    for topic, kws in _FAILURE_TOPICS.items():
        found = [kw for kw in kws if kw in blob]
        if found:
            hits[topic] = found
    return {"topics_touched": hits, "n_topics_touched": len(hits)}


def run(seeds: list[int], with_empty: bool, out_dir: Path) -> dict:
    ledger = build_realistic_ledger()
    geneal_ctx = build_conditioning_context(ledger, TOPIC, k=6, mode="genealogy")
    control_ctx = build_conditioning_context(ledger, TOPIC, k=6, mode="control")
    empty_ctx = (
        f"You are extending a body of formally verified mathematics about: {TOPIC}.\n"
    )

    # Real API proposer. A fresh instance per call so the proposer's internal
    # id counter does not leak state across modes (statements are what matter).
    spec = {"kind": "api_code", "model": "claude-sonnet-4-6", "temperature": 0.7}

    per_seed: list[dict] = []
    any_fallback = False
    emb = get_embedder("hash")  # deterministic, free, sufficient for relative dist

    for seed in seeds:
        rec: dict = {"seed": seed}
        batches: dict[str, list[str]] = {}
        mode_ctx = [("genealogy", geneal_ctx), ("control", control_ctx)]
        if with_empty:
            mode_ctx.append(("empty", empty_ctx))
        for mode, ctx in mode_ctx:
            prop = _build_proposer(spec)
            conjs = prop.propose(ctx, k=6, seed=seed)
            fell_back = getattr(prop, "using_fallback", False)
            any_fallback = any_fallback or fell_back
            stmts = [c.statement for c in conjs]
            batches[mode] = stmts
            rec[f"{mode}_statements"] = stmts
            rec[f"{mode}_using_fallback"] = bool(fell_back)
            rec[f"{mode}_tokens_in"] = getattr(prop, "last_tokens_in", 0)
            rec[f"{mode}_tokens_out"] = getattr(prop, "last_tokens_out", 0)

        g, c = batches["genealogy"], batches["control"]
        rec["embedding_distance_matched"] = _matched_embedding_distance(emb, g, c)
        rec["jaccard_overlap"] = _jaccard(g, c)
        rec["genealogy_failure_audit"] = _failure_reference_audit(g)
        rec["control_failure_audit"] = _failure_reference_audit(c)
        if with_empty:
            e = batches["empty"]
            rec["embedding_distance_genealogy_vs_empty"] = _matched_embedding_distance(emb, g, e)
            rec["jaccard_genealogy_vs_empty"] = _jaccard(g, e)
        per_seed.append(rec)

    def _agg(key: str) -> dict:
        vals = [r[key] for r in per_seed if not np.isnan(r.get(key, float("nan")))]
        if not vals:
            return {"mean": float("nan"), "std": float("nan"), "n": 0}
        return {"mean": float(np.mean(vals)), "std": float(np.std(vals)), "n": len(vals)}

    emb_agg = _agg("embedding_distance_matched")
    jac_agg = _agg("jaccard_overlap")

    # genealogy proposals reference/avoid prior failure modes? True if, on
    # average, the genealogy batch touches >=1 prior failure topic.
    geneal_touch = float(np.mean([r["genealogy_failure_audit"]["n_topics_touched"] for r in per_seed]))
    control_touch = float(np.mean([r["control_failure_audit"]["n_topics_touched"] for r in per_seed]))
    references_failures = bool(geneal_touch >= 1.0)

    # proposals_shift: do batches measurably differ between modes? We require a
    # non-trivial embedding drift OR clearly-imperfect overlap. Identical batches
    # would give embedding_distance ~ 0 and jaccard ~ 1.
    proposals_shift = bool(
        (not np.isnan(emb_agg["mean"]) and emb_agg["mean"] >= 0.10)
        or (not np.isnan(jac_agg["mean"]) and jac_agg["mean"] <= 0.90)
    )

    summary = {
        "config": "experiments/responsiveness.py",
        "topic": TOPIC,
        "k": 6,
        "seeds": seeds,
        "n_seeds": len(seeds),
        "any_fallback": any_fallback,
        "embedding_distance_matched": emb_agg,
        "jaccard_overlap": jac_agg,
        "genealogy_topics_touched_mean": geneal_touch,
        "control_topics_touched_mean": control_touch,
        "references_failures": references_failures,
        "proposals_shift": proposals_shift,
        "ledger_failure_modes": [
            {"statement": e.statement, "detail": e.crit.detail}
            for e in ledger.entries if not e.surviving
        ],
        "ledger_survivors": [e.statement for e in ledger.survivors()],
        "per_seed": per_seed,
        "genealogy_context_preview": geneal_ctx,
        "control_context_preview": control_ctx,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "responsiveness.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="0,1,2", help="comma-separated seeds")
    ap.add_argument("--with-empty", action="store_true", help="also probe empty-context arm")
    ap.add_argument("--out", default="results/findings", help="output dir")
    args = ap.parse_args()
    seeds = [int(s) for s in args.seeds.split(",") if s.strip() != ""]
    summary = run(seeds, args.with_empty, Path(args.out))

    if summary["any_fallback"]:
        print(
            "[responsiveness] FATAL: a proposer call fell back to the OFFLINE "
            "generator (context-ignoring). The genealogy/control comparison is "
            "INVALID. Check ANTHROPIC_API_KEY / model. Aborting non-zero.",
        )
        raise SystemExit(2)

    print(json.dumps({
        "embedding_distance_matched": summary["embedding_distance_matched"],
        "jaccard_overlap": summary["jaccard_overlap"],
        "references_failures": summary["references_failures"],
        "proposals_shift": summary["proposals_shift"],
        "genealogy_topics_touched_mean": summary["genealogy_topics_touched_mean"],
        "control_topics_touched_mean": summary["control_topics_touched_mean"],
    }, indent=2))


if __name__ == "__main__":
    main()
