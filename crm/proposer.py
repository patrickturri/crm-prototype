"""Proposer ABC + proposers (§7).

The Proposer is FROZEN in this prototype — no weight updates. We demonstrate the
genealogy/significance mechanisms via in-context conditioning only.

Phase 0 ships:
  - `Proposer` ABC,
  - `StubProposer`: a deterministic, offline, seedable proposer good enough to
    drive the mock loop without any API/model dependency,
  - `APIProposer` / `LocalProposer`: declared stubs (filled in later phases).
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from crm.types import Conjecture


class Proposer(ABC):
    @abstractmethod
    def propose(self, context: str, k: int, seed: int) -> list[Conjecture]: ...


# A small deterministic pool of toy NT-flavoured statements. These are NOT
# reported results — the StubProposer exists only to exercise the mock loop
# offline. Some intentionally contain `sorry` so the mock critic refutes them,
# giving the genealogy a mix of survivors and failures to record.
_POOL: list[dict[str, str]] = [
    {
        "statement": "forall (n : Nat), Nat.gcd n (n + 1) = 1",
        "proof_attempt": "by simp [Nat.coprime_succ_self]",
        "nl_gloss": "consecutive naturals are coprime",
    },
    {
        "statement": "forall (n : Nat), n <= n + 1",
        "proof_attempt": "by omega",
        "nl_gloss": "n is at most its successor",
    },
    {
        "statement": "forall (n : Nat), Nat.gcd n (n + 2) = 1",
        "proof_attempt": "by sorry",
        "nl_gloss": "n and n+2 are coprime (FALSE at n=2)",
    },
    {
        "statement": "forall (a b : Nat), a + b = b + a",
        "proof_attempt": "by ring",
        "nl_gloss": "addition commutes",
    },
    {
        "statement": "forall (n : Nat), 2 * n = n + n",
        "proof_attempt": "by ring",
        "nl_gloss": "doubling is self-addition",
    },
    {
        "statement": "forall (p : Nat), Nat.Prime p -> p >= 2",
        "proof_attempt": "by exact Nat.Prime.two_le",
        "nl_gloss": "primes are at least two",
    },
    {
        "statement": "forall (n : Nat), n % 2 = 0 -> sorry",
        "proof_attempt": "by sorry",
        "nl_gloss": "incomplete even-number claim",
    },
    {
        "statement": "forall (n : Nat), Nat.gcd n n = n",
        "proof_attempt": "by simp",
        "nl_gloss": "gcd of n with itself is n",
    },
]


class StubProposer(Proposer):
    """Deterministic offline proposer. Seedable; emits Conjectures from a fixed
    pool, varying selection by (seed, round) so successive rounds differ.

    Token accounting is reported via `last_tokens_in/out` so the loop can meter
    a *real* (if synthetic) token count rather than fabricating one.
    """

    name = "stub"

    def __init__(self) -> None:
        self.last_tokens_in: int = 0
        self.last_tokens_out: int = 0
        self._counter: int = 0

    def propose(self, context: str, k: int, seed: int) -> list[Conjecture]:
        rng = random.Random(seed)
        picks = [rng.choice(_POOL) for _ in range(k)]
        batch: list[Conjecture] = []
        for item in picks:
            cid = f"c_{self._counter:04d}"
            self._counter += 1
            batch.append(
                Conjecture(
                    id=cid,
                    statement=item["statement"],
                    proof_attempt=item["proof_attempt"],
                    nl_gloss=item["nl_gloss"],
                    rationale="stub-proposer (offline)",
                )
            )
        # Real-ish token accounting: count whitespace tokens of context (in) and
        # of the emitted JSON-ish payload (out). Not fabricated — derived from
        # actual strings handled this call.
        self.last_tokens_in = len(context.split())
        self.last_tokens_out = sum(
            len((c.statement + " " + c.proof_attempt + " " + c.nl_gloss).split())
            for c in batch
        )
        return batch


class APIProposer(Proposer):
    """OpenAI-compatible / Anthropic endpoint proposer (§7). Stub for Phase 0."""

    name = "api"

    def __init__(self, *args, **kwargs) -> None:  # noqa: D401
        self.config = kwargs

    def propose(self, context: str, k: int, seed: int) -> list[Conjecture]:
        raise NotImplementedError("APIProposer is implemented in a later phase.")


class LocalProposer(Proposer):
    """HF transformers / vLLM local proposer (§7). Stub for Phase 0."""

    name = "local"

    def __init__(self, *args, **kwargs) -> None:
        self.config = kwargs

    def propose(self, context: str, k: int, seed: int) -> list[Conjecture]:
        raise NotImplementedError("LocalProposer is implemented in a later phase.")
