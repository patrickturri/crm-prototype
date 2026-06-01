"""Critic ABC + CritResult dataclass.

Defined EXACTLY per BUILD_SPEC §4. The real critics (code-exec, Lean) MUST be
reality-grounded: no LLM-as-judge for the survive/die decision (§3.1, §15).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crm.types import Conjecture

# The allowed values for CritResult.reason_class (§4).
REASON_CLASSES = (
    "PROVED",
    "FALSE",
    "UNPROVEN_BUDGET",
    "ILLFORMED",
    "TIMEOUT",
    "DUPLICATE",
)


@dataclass
class CritResult:
    valid: bool
    reason_class: str        # one of: PROVED, FALSE, UNPROVEN_BUDGET, ILLFORMED, TIMEOUT, DUPLICATE
    detail: str              # human-readable: error msg / counterexample / proof method used
    proof_method: str | None  # e.g. "supplied", "aesop", "omega", "tests_passed"
    critic_seconds: float


class Critic(ABC):
    name: str

    @abstractmethod
    def check(self, conjecture: "Conjecture") -> CritResult: ...
    # MUST be reality-grounded for the real critics. No LLM-as-judge for validity.
