"""MockCritic (§6.0).

Validates by a trivial rule (statement non-empty and contains no `sorry`),
assigns a reason_class deterministically so runs are reproducible, and returns
instantly. Purpose: validate the loop, ledger, accounting, and experiment
harness in <60s with zero heavy deps.

NOT USED IN ANY REPORTED RESULT (§3, §6.0).
"""

from __future__ import annotations

import hashlib

from crm.critics.base import CritResult
from crm.types import Conjecture

# Reason classes the mock may emit for *valid* candidates. The mock is a
# stand-in only; it never feeds a reported number.
_VALID_REASONS = ("PROVED",)
_INVALID_REASONS = ("FALSE", "UNPROVEN_BUDGET", "TIMEOUT", "DUPLICATE")


def _stable_pick(seed_str: str, options: tuple[str, ...]) -> str:
    h = hashlib.sha256(seed_str.encode("utf-8")).digest()
    return options[h[0] % len(options)]


class MockCritic:
    name = "mock"

    def check(self, conjecture: Conjecture) -> CritResult:
        stmt = (conjecture.statement or "").strip()

        # Ill-formed: empty statement.
        if not stmt:
            return CritResult(
                valid=False,
                reason_class="ILLFORMED",
                detail="empty statement",
                proof_method=None,
                critic_seconds=0.0,
            )

        # Trivial "refutation": presence of `sorry` => not valid.
        if "sorry" in stmt or "sorry" in (conjecture.proof_attempt or ""):
            reason = _stable_pick(conjecture.id + stmt, _INVALID_REASONS)
            return CritResult(
                valid=False,
                reason_class=reason,
                detail="contains `sorry` (mock-refuted)",
                proof_method=None,
                critic_seconds=0.0,
            )

        # Otherwise: deterministically valid via the trivial parse rule.
        reason = _stable_pick(conjecture.id + stmt, _VALID_REASONS)
        return CritResult(
            valid=True,
            reason_class=reason,
            detail="mock: parses, no `sorry`",
            proof_method="supplied",
            critic_seconds=0.0,
        )
