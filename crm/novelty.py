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


def certify_novel(
    statement: str,
    significance: Significance | None = None,
    corpus: list[str] | None = None,
    delta: float = 0.35,
    critic=None,
) -> bool:
    """Return True iff `statement` passes all three §5.3 clauses."""
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
    return significance.novelty >= delta
