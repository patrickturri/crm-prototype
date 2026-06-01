"""Shared lightweight data types used across the CRM prototype.

`Conjecture` is the unit of proposal produced by a `Proposer` and consumed by a
`Critic`. It is intentionally domain-agnostic: the `statement`/`proof_attempt`
fields carry Lean for the Lean track, while a code task may pack a spec/impl/tests
into the same fields (see the code-exec critic in a later phase).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Conjecture:
    """A single proposed conjecture with its proof attempt and metadata."""

    id: str
    statement: str
    proof_attempt: str = ""
    nl_gloss: str = ""
    rationale: str = ""
    round: int = 0
    parent_ids: list[str] = field(default_factory=list)
    # Free-form domain payload (e.g. code-exec task fields). Kept out of the
    # load-bearing fields so the JSONL schema in §5.1 stays stable.
    extra: dict[str, Any] = field(default_factory=dict)
