"""Novelty certification (§5.3).

`certify_novel(statement)` requires ALL of:

  1. NOT a corpus restatement   — after normalisation, no exact/near string
     match to any statement in the corpus.
  2. NOT cheaply derivable      — not closed by automation alone (the critic's
     automation-closeability check; the analogue of exact?/aesop/simp/omega).
  3. retrieval-distant          — novelty >= delta (embedding distance from the
     nearest corpus statement).

This is an OPERATIONAL novelty test for a prototype (§5.3, README honest-limits):
formal independence is a Stage-1/2 deliverable, NOT claimed here. We never
fabricate a "novel" result — every clause is computed.
"""

from __future__ import annotations

import re

from crm.embedding import cosine_sim, get_embedder
from crm.significance import Significance


def _normalise(stmt: str) -> str:
    s = stmt.strip().lower()
    # canonicalise unicode/ascii synonyms and whitespace for matching
    s = s.replace("∀", "forall").replace("∃", "exists")
    s = s.replace("ℕ", "nat").replace("→", "->")
    s = s.replace("≤", "<=").replace("≥", ">=").replace("≠", "!=")
    s = re.sub(r"\s+", "", s)
    return s


def is_corpus_restatement(statement: str, corpus: list[str]) -> bool:
    target = _normalise(statement)
    return any(_normalise(c) == target for c in (corpus or []))


def _resolve_embedder(significance, embedder):
    """Pick an embedder for the intra-survivor distance.

    Prefer an explicitly supplied embedder; else reuse the SignificanceCritic's
    embedder (the SAME path `significance.novelty` uses, so the same 0.35 delta
    applies symmetrically to corpus and own-set); else the default embedder.
    """
    if embedder is not None:
        return embedder
    sig_embedder = getattr(significance, "embedder", None)
    if sig_embedder is not None:
        return sig_embedder
    return get_embedder()


def is_survivor_duplicate(
    statement: str,
    accepted_survivors: list[str],
    *,
    embedder,
    delta: float = 0.35,
) -> bool:
    """True iff `statement` is within `delta` of an already-accepted survivor.

    Symmetric to the corpus novelty gate: distance = 1 - max cosine_sim to the
    accepted set; a candidate is a duplicate when that distance < delta.
    """
    accepted = [s for s in (accepted_survivors or []) if s and s != statement]
    if not accepted:
        return False
    vecs = embedder.encode([statement] + accepted)
    v = vecs[0]
    max_sim = max(cosine_sim(v, vecs[i + 1]) for i in range(len(accepted)))
    distance = 1.0 - max_sim
    return distance < delta


def dedup_survivors(
    statements: list[str],
    *,
    embedder,
    delta: float = 0.35,
) -> tuple[list[str], list[list[str]]]:
    """PURE: collapse a list of certified-novel statements by embedding distance.

    Greedy, order-preserving: walk `statements` in order; keep one as the
    canonical representative of a group; fold any later statement within `delta`
    (distance 1 - cosine_sim) of an already-kept representative into that group.

    Returns `(deduped, groups)` where `deduped` is the list of kept
    representatives (the deduped certified-novel set) and `groups` is a parallel
    list: groups[i] is every input statement collapsed into deduped[i]
    (including deduped[i] itself as the first element).

    No model is run — only the supplied `embedder`. Experiment agents call this
    on an existing ledger's certified statements to MEASURE "raw certified count
    vs deduped certified count" without re-running the proposer.
    """
    deduped: list[str] = []
    groups: list[list[str]] = []
    for stmt in statements:
        placed = False
        for i, rep in enumerate(deduped):
            if not is_survivor_duplicate(stmt, [rep], embedder=embedder, delta=delta):
                continue
            groups[i].append(stmt)
            placed = True
            break
        if not placed:
            deduped.append(stmt)
            groups.append([stmt])
    return deduped, groups


def certify_novel(
    statement: str,
    significance: Significance | None = None,
    corpus: list[str] | None = None,
    delta: float = 0.35,
    critic=None,
    accepted_survivors: list[str] | None = None,
    embedder=None,
) -> bool:
    """Return True iff `statement` passes all §5.3 clauses (+ intra-run dedup).

    `accepted_survivors` is the list of statements THIS run has already
    certified-novel. A candidate within `delta` (embedding distance) of any of
    them is rejected, so two near-duplicate survivors from the same run cannot
    both certify — symmetric to the corpus novelty gate (review finding #7).
    `embedder` overrides which embedder measures that distance; by default it
    reuses the SignificanceCritic's embedder.
    """
    corpus = corpus or []

    # (1) not a corpus restatement
    if is_corpus_restatement(statement, corpus):
        return False

    # (2) not cheaply derivable by automation alone
    if critic is not None:
        fn = getattr(critic, "automation_closeable", None)
        if callable(fn):
            try:
                if fn(statement):
                    return False
            except Exception:
                pass

    # (3) retrieval-distant: novelty >= delta. Use the significance novelty if
    # supplied (already an embedding distance), else cannot certify.
    if significance is None:
        return False
    if significance.is_trivial:
        return False
    if significance.novelty < delta:
        return False

    # (4) NOT a near-duplicate of an already-accepted survivor from THIS run
    # (review finding #7). Symmetric to (3): reject when within `delta` of the
    # nearest accepted survivor, measured with the same embedder.
    if accepted_survivors:
        emb = _resolve_embedder(significance, embedder)
        if is_survivor_duplicate(
            statement, accepted_survivors, embedder=emb, delta=delta
        ):
            return False

    return True
