"""Genealogy ledger, Entry schema, and conditioning context (§5.1).

This is H2 — the core novelty. The ledger records every
(conjecture, refutation, reason, significance) tuple and is used to condition
the next round's prompt. Phase 0 ships the persistence (JSONL in the §5.1 shape)
and a conditioning-context skeleton with the `mode: "genealogy" | "control"`
flag; the full reasoned-genealogy prompt construction lands in Phase 1.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from crm.critics.base import CritResult
from crm.significance import Significance

if TYPE_CHECKING:
    from crm.types import Conjecture


@dataclass
class Entry:
    """One ledger row. Serialises to the JSONL shape in §5.1."""

    id: str
    round: int
    parent_ids: list[str]
    statement: str
    nl_gloss: str
    proof_attempt: str
    crit: CritResult
    significance: Significance | None = None
    surviving: bool = False
    certified_novel: bool = False

    @classmethod
    def from_conjecture(
        cls,
        conjecture: "Conjecture",
        crit: CritResult,
        surviving: bool = False,
    ) -> "Entry":
        return cls(
            id=conjecture.id,
            round=conjecture.round,
            parent_ids=list(conjecture.parent_ids),
            statement=conjecture.statement,
            nl_gloss=conjecture.nl_gloss,
            proof_attempt=conjecture.proof_attempt,
            crit=crit,
            surviving=surviving,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "round": self.round,
            "parent_ids": list(self.parent_ids),
            "statement": self.statement,
            "nl_gloss": self.nl_gloss,
            "proof_attempt": self.proof_attempt,
            "crit": asdict(self.crit),
            "significance": asdict(self.significance) if self.significance else None,
            "surviving": self.surviving,
            "certified_novel": self.certified_novel,
        }


@dataclass
class Ledger:
    """In-memory list of entries with JSONL persistence (§5.1)."""

    entries: list[Entry] = field(default_factory=list)

    def add(self, entry: Entry) -> None:
        self.entries.append(entry)

    def survivors(self) -> list[Entry]:
        return [e for e in self.entries if e.surviving]

    def certified(self) -> list[Entry]:
        return [e for e in self.entries if e.certified_novel]

    def dump(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for e in self.entries:
                f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")


# Map of reason_class -> short human label used in the conditioning block.
_REASON_LABEL = {
    "PROVED": "PROVED",
    "FALSE": "REFUTED: false",
    "UNPROVEN_BUDGET": "UNPROVEN in budget",
    "ILLFORMED": "ILL-FORMED",
    "TIMEOUT": "TIMED OUT",
    "DUPLICATE": "DUPLICATE",
}


def _failure_reason(e: "Entry") -> str:
    """Render the WHY of a failed entry (§5.1) — never just pass/fail.

    A conjecture can "fail" two ways: the critic refuted it (FALSE / ILLFORMED /
    etc.), OR it was valid-but-suppressed by the significance critic as trivial.
    Both carry a real reason: a counterexample, or the triviality with its
    hardness number.
    """
    stmt = e.statement
    # Valid-but-trivial suppression: surface the hardness number.
    if e.crit.valid and e.significance is not None and e.significance.is_trivial:
        h = e.significance.hardness
        return (
            f'"{stmt}"  — REJECTED: trivial '
            f"(automation-closeable or hardness {h:.2f})."
        )
    label = _REASON_LABEL.get(e.crit.reason_class, e.crit.reason_class)
    detail = f" — {e.crit.detail}" if e.crit.detail else ""
    return f'"{stmt}"  — {label}{detail}.'


def build_conditioning_context(
    ledger: Ledger,
    topic: str,
    k: int,
    mode: str = "genealogy",
) -> str:
    """Build the token-budgeted prompt block for the next round (§5.1).

    `mode="genealogy"` (treatment): includes WHY conjectures failed and the
    surviving high-content results to build on.
    `mode="genealogy_orthogonal"` (H-orthogonality variant): same WHY-failed
    block, but the survivor block's directive is INVERTED — instead of "generalise
    or build on these", it instructs the proposer to propose results NOT
    expressible via, and dissimilar to, the listed survivors (avoid their
    neighbourhood). Tests whether the genealogy null is an artefact of the
    build-on framing acting as an exploration brake.
    `mode="control"`: same prompt MINUS reasons/significance/build-on guidance,
    but still lists prior statements so both conditions deduplicate equally.

    Phase 0 ships a faithful-but-minimal version sufficient to drive the mock
    loop. Phase 1 fleshes out the significance-aware ranking and token budgeting.
    """
    if mode not in ("genealogy", "genealogy_orthogonal", "control"):
        raise ValueError(f"unknown conditioning mode: {mode!r}")
    genealogy_like = mode in ("genealogy", "genealogy_orthogonal")

    lines: list[str] = []
    lines.append(
        f"You are extending a body of formally verified mathematics about: {topic}."
    )
    lines.append("")

    prior = ledger.entries
    if genealogy_like:
        failed = [e for e in prior if not e.surviving]
        if failed:
            lines.append(
                "Past attempts and WHY they failed — do not repeat these failure modes:"
            )
            for e in failed[-12:]:
                lines.append(f"- {_failure_reason(e)}")
            lines.append("")

        survivors = ledger.survivors()
        if survivors:
            if mode == "genealogy_orthogonal":
                lines.append(
                    "Surviving, high-content results so far — propose NEW results "
                    "that are NOT expressible via and are DISSIMILAR to these "
                    "(avoid their neighbourhood; do not generalise or build on them):"
                )
            else:
                lines.append(
                    "Surviving, high-content results so far — generalise or build on these:"
                )
            for e in survivors[-12:]:
                sc = (
                    f" (content score {e.significance.score:.2f})"
                    if e.significance
                    else ""
                )
                lines.append(f'- "{e.statement}"{sc}')
            lines.append("")
    else:
        # control: list prior statements only (so dedup is matched), no reasons.
        if prior:
            lines.append("Statements already attempted (do not restate these):")
            for e in prior[-24:]:
                lines.append(f'- "{e.statement}"')
            lines.append("")

    lines.append(
        f"Now propose {k} NEW conjectures about {topic} that are (a) likely TRUE,"
    )
    if genealogy_like:
        lines.append(
            "(b) NON-trivial / hard-to-vary (small changes to them should make them false),"
        )
        if mode == "genealogy_orthogonal":
            lines.append(
                "(c) NOT restatements of, derivable from, or near-duplicates of the "
                "survivors above or of standard-library lemmas — pick a DIFFERENT "
                "region of the topic."
            )
        else:
            lines.append(
                "(c) NOT restatements of the above or of standard-library lemmas."
            )
    else:
        lines.append("(b) NOT restatements of the above.")
    lines.append(
        "Return strict JSON: [{statement, proof_attempt, nl_gloss, rationale}, ...]."
    )
    return "\n".join(lines)
