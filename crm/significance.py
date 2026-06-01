"""Significance / hard-to-vary critic (§5.2).

Phase 0 ships only the `Significance` dataclass (defined EXACTLY per §4) and a
`SignificanceCritic` stub interface. The real perturbation/hardness machinery is
implemented in Phase 1; the stub here lets the loop run end-to-end on the mock
critic WITHOUT fabricating a hardness number (it returns hardness=0.0 and marks
nothing as contentful, so nothing trivial is ever falsely promoted).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crm.critics.base import Critic
    from crm.types import Conjecture


@dataclass
class Significance:
    novelty: float      # 0..1, distance from corpus / inverse base-model familiarity
    breadth: float      # 0..1, downstream enablement
    hardness: float     # 0..1, fraction of perturbed neighbours that break
    is_trivial: bool    # closeable by automation alone OR hardness < tau
    score: float        # weighted combo; 0 if is_trivial


class SignificanceCritic:
    """Computes a `Significance` for a VALID conjecture.

    Phase 0 stub: returns a zeroed Significance flagged trivial. This is a
    deliberate *floor*, not a fabricated result — it never promotes a conjecture
    on a faked hardness number. Phase 1 replaces `score()` with the real
    perturbation-based hardness computation (§5.2).
    """

    def __init__(
        self,
        w_novelty: float = 0.3,
        w_breadth: float = 0.3,
        w_hardness: float = 0.4,
        tau: float = 0.25,
        perturbations: int = 8,
        breadth_targets: int = 8,
        embedder: str | None = None,
    ) -> None:
        self.w_novelty = w_novelty
        self.w_breadth = w_breadth
        self.w_hardness = w_hardness
        self.tau = tau
        self.perturbations = perturbations
        self.breadth_targets = breadth_targets
        self.embedder = embedder

    def score(
        self,
        conjecture: "Conjecture",
        critic: "Critic",
        corpus: list[str] | None = None,
    ) -> Significance:
        # PHASE 0 STUB. No real hardness computed yet => mark trivial so the
        # loop is honest about not knowing significance. Phase 1 overrides this.
        return Significance(
            novelty=0.0,
            breadth=0.0,
            hardness=0.0,
            is_trivial=True,
            score=0.0,
        )
