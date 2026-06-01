"""Novelty certification (§5.3).

`certify_novel(statement)` requires ALL of: not a corpus restatement, not
cheaply derivable by automation, and retrieval-distant (novelty >= delta).

Phase 0 ships a conservative stub that returns False. This is the HONEST floor
(§3.1): we never certify a result as novel on a faked check. The real
corpus-match + automation + embedding-distance logic lands with the Lean/code
critics in later phases.
"""

from __future__ import annotations

from crm.significance import Significance


def certify_novel(
    statement: str,
    significance: Significance | None = None,
    corpus: list[str] | None = None,
    delta: float = 0.35,
) -> bool:
    # PHASE 0 STUB: no real corpus/embedding check yet => not certified.
    # Returning False here is the honest default; nothing is reported as novel
    # until a real critic + corpus are wired in.
    return False
