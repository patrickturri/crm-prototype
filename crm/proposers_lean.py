"""Lean-task proposers for the LeanCritic (§6.3, §7).

Two proposers, same `Proposer` interface (`propose(context, k, seed)`):

  * `OfflineLeanProposer` — a DETERMINISTIC, seedable, offline candidate
    generator (the spec-required fallback so the Lean demo still produces
    REAL critic-verified survivors even with no API key). It emits a pool of
    genuine elementary number-theory Lean 4 conjectures with proof attempts.
    The pool deliberately mixes TRUE / FALSE / TRIVIAL statements so the Lean
    critic and the significance guard have a real spread to grade — these are
    *proposals*, never reported "results"; only the Lean kernel decides which
    survive.

  * `APILeanProposer` — the real LLM proposer (§7). Loads the gitignored `.env`
    via python-dotenv, calls the Anthropic Messages API for strict-JSON Lean 4
    conjectures, and degrades to `OfflineLeanProposer` if the key is
    absent/invalid or the call fails. The LLM only PROPOSES; validity is always
    decided by the Lean kernel (NO LLM-as-judge, §3, §15).

Each candidate uses `Conjecture.statement` (Lean 4 proposition, drives novelty/
embedding) and `Conjecture.proof_attempt` (Lean 4 tactic block). The statements
are written in the unicode Lean surface syntax that mathlib understands and that
the shared perturbation operators can mutate for the hardness signal.
"""

from __future__ import annotations

import random
from typing import Any

from crm.proposer import Proposer
from crm.types import Conjecture

# ---------------------------------------------------------------------------
# Offline candidate pool — real elementary-NT Lean 4 conjectures.
# Mix of TRUE (contentful), FALSE (refuted), and TRIVIAL (automation-closed).
# These are PROPOSALS, not results (§3); the Lean kernel + significance critic
# decide which survive. Statements use mathlib's unicode surface syntax.
# ---------------------------------------------------------------------------
_POOL: list[dict[str, str]] = [
    # --- contentful, likely-true gcd / coprimality ---
    {
        "statement": "∀ (n : ℕ), Nat.gcd n (n + 1) = 1",
        "proof_attempt": "by simp",
        "nl_gloss": "consecutive naturals are coprime",
    },
    {
        "statement": "∀ (n : ℕ), Nat.Coprime n (n + 1)",
        "proof_attempt": "by intro n; simp [Nat.Coprime]",
        "nl_gloss": "n and n+1 are coprime",
    },
    {
        "statement": "∀ (a b : ℕ), Nat.gcd a b = Nat.gcd b a",
        "proof_attempt": "by exact Nat.gcd_comm",
        "nl_gloss": "gcd is commutative",
    },
    {
        "statement": "∀ (a b : ℕ), Nat.gcd a b ∣ a",
        "proof_attempt": "by exact fun a b => Nat.gcd_dvd_left a b",
        "nl_gloss": "gcd divides its left argument",
    },
    {
        "statement": "∀ (a b : ℕ), Nat.lcm a b = Nat.lcm b a",
        "proof_attempt": "by exact Nat.lcm_comm",
        "nl_gloss": "lcm is commutative",
    },
    {
        "statement": "∀ (n : ℕ), Nat.gcd n (2 * n) = n",
        "proof_attempt": "by intro n; simp [Nat.gcd_mul_left]",
        "nl_gloss": "gcd of n and 2n is n",
    },
    # Genuinely-true, NON-corpus, NON-trivial gcd theorems (real mathlib-checked).
    {
        "statement": "∀ (n : ℕ), Nat.gcd n (n * n + 1) = 1",
        "proof_attempt": "by intro n; simp [Nat.gcd_comm, Nat.coprime_mul_left_add_right]",
        "nl_gloss": "n is coprime to n^2 + 1",
    },
    {
        "statement": "∀ (a b : ℕ), Nat.gcd a b ∣ a * b",
        "proof_attempt": "by intro a b; exact Dvd.dvd.mul_right (Nat.gcd_dvd_left a b) b",
        "nl_gloss": "gcd of a and b divides their product",
    },
    {
        "statement": "∀ (n : ℕ), Nat.Coprime n (n * n + 1)",
        "proof_attempt": "by intro n; simp [Nat.Coprime, Nat.gcd_comm, Nat.coprime_mul_left_add_right]",
        "nl_gloss": "n and n^2+1 are coprime",
    },
    # --- primes / modular ---
    {
        "statement": "∀ (p : ℕ), Nat.Prime p → 2 ≤ p",
        "proof_attempt": "by intro p hp; exact hp.two_le",
        "nl_gloss": "every prime is at least two",
    },
    {
        "statement": "∀ (p : ℕ), Nat.Prime p → p ≠ 0",
        "proof_attempt": "by intro p hp; exact hp.ne_zero",
        "nl_gloss": "no prime is zero",
    },
    {
        "statement": "∀ (n : ℕ), n % 2 = 0 ∨ n % 2 = 1",
        "proof_attempt": "by omega",
        "nl_gloss": "every natural is even or odd",
    },
    {
        "statement": "∀ (a b n : ℕ), (a + b) % n = (a % n + b % n) % n",
        "proof_attempt": "by exact Nat.add_mod a b n",
        "nl_gloss": "addition commutes with mod",
    },
    # --- FALSE proposals (genuine refuted siblings for the genealogy) ---
    {
        "statement": "∀ (n : ℕ), Nat.gcd n (n + 2) = 1",
        "proof_attempt": "by decide",
        "nl_gloss": "n and n+2 are coprime (FALSE at n=2)",
    },
    {
        "statement": "∀ (p : ℕ), Nat.Prime p → p % 2 = 1",
        "proof_attempt": "by decide",
        "nl_gloss": "every prime is odd (FALSE: p=2)",
    },
    {
        "statement": "∀ (a b : ℕ), Nat.gcd a b = a",
        "proof_attempt": "by simp",
        "nl_gloss": "gcd always equals left arg (FALSE)",
    },
    # --- TRIVIAL proposals (closed by omega/decide alone -> suppressed) ---
    {
        "statement": "∀ (n : ℕ), n ≤ n + 1",
        "proof_attempt": "by omega",
        "nl_gloss": "n is at most its successor (trivial; omega-closed)",
    },
    {
        "statement": "∀ (n : ℕ), n + 0 = n",
        "proof_attempt": "by simp",
        "nl_gloss": "right-identity of addition (trivial)",
    },
    {
        "statement": "∀ (a b : ℕ), a + b = b + a",
        "proof_attempt": "by omega",
        "nl_gloss": "addition commutes (trivial; omega-closed)",
    },
    {
        "statement": "∀ (n : ℕ), 2 * n = n + n",
        "proof_attempt": "by omega",
        "nl_gloss": "doubling is self-addition (trivial)",
    },
]


def _to_conjecture(item: dict[str, str], cid: str, rationale: str) -> Conjecture:
    return Conjecture(
        id=cid,
        statement=item["statement"],
        proof_attempt=item.get("proof_attempt", ""),
        nl_gloss=item.get("nl_gloss", ""),
        rationale=rationale,
    )


class OfflineLeanProposer(Proposer):
    """Deterministic offline Lean-task proposer (§7 fallback, §6.3)."""

    name = "offline_lean"

    def __init__(self) -> None:
        self.last_tokens_in = 0
        self.last_tokens_out = 0
        self._counter = 0

    def propose(self, context: str, k: int, seed: int) -> list[Conjecture]:
        rng = random.Random(seed)
        pool = list(_POOL)
        rng.shuffle(pool)
        picks = [pool[i % len(pool)] for i in range(k)]
        batch = [
            _to_conjecture(
                item, f"c_{self._counter + i:04d}",
                "offline-lean-proposer (deterministic fallback)",
            )
            for i, item in enumerate(picks)
        ]
        self._counter += len(batch)
        self.last_tokens_in = len(context.split())
        self.last_tokens_out = sum(
            len((c.statement + " " + c.proof_attempt).split()) for c in batch
        )
        return batch


# ---------------------------------------------------------------------------
# Real API proposer (Anthropic), with offline fallback.
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You invent SMALL, likely-TRUE, NON-trivial conjectures in elementary "
    "number theory (divisibility, gcd/coprimality, primes, modular "
    "arithmetic), stated and proved in Lean 4 / mathlib. Each must compile with "
    "`import Mathlib`. Prefer hard-to-vary statements (small changes should make "
    "them false) over automation-trivial ones. Never explain; STRICT JSON only."
)


def _user_prompt(context: str, k: int) -> str:
    return (
        f"{context}\n\n"
        f"Propose {k} NEW Lean 4 conjectures about elementary number theory. "
        f"Return a STRICT JSON array of {k} objects, each with EXACTLY these "
        "keys:\n"
        '  "statement": a Lean 4 proposition (e.g. '
        '"∀ (n : ℕ), Nat.gcd n (n + 1) = 1"),\n'
        '  "proof_attempt": a Lean 4 proof term/tactic block (e.g. '
        '"by simp [...]" or "by omega"),\n'
        '  "nl_gloss": a short natural-language gloss,\n'
        '  "rationale": one line on why it is non-trivial.\n'
        "Use mathlib lemma names. JSON only, no prose, no markdown fences."
    )


class APILeanProposer(Proposer):
    """Anthropic API Lean-task proposer (§7) with offline fallback."""

    name = "api_lean"

    def __init__(self, **kwargs: Any) -> None:
        self.config = kwargs
        self._fallback = OfflineLeanProposer()
        self.last_tokens_in = 0
        self.last_tokens_out = 0
        self._client = None
        self._model = None
        self._using_fallback = False
        self._counter = 0
        self._init_client()

    def _init_client(self) -> None:
        try:
            from dotenv import load_dotenv

            load_dotenv()  # repo-root .env (gitignored)
        except Exception:
            pass
        import os

        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        provider = os.environ.get("CRM_PROPOSER_PROVIDER", "anthropic").strip()
        self._model = self.config.get("model") or os.environ.get(
            "CRM_PROPOSER_MODEL", "claude-sonnet-4-6"
        )
        if not key or provider != "anthropic":
            self._using_fallback = True
            return
        try:
            import anthropic

            self._client = anthropic.Anthropic(api_key=key)
        except Exception:
            self._using_fallback = True

    @property
    def using_fallback(self) -> bool:
        return self._using_fallback

    def propose(self, context: str, k: int, seed: int) -> list[Conjecture]:
        if self._using_fallback or self._client is None:
            self._using_fallback = True
            return self._fallback.propose(context, k, seed)
        try:
            return self._propose_api(context, k, seed)
        except Exception as e:
            import sys

            print(
                f"[crm] APILeanProposer: falling back to offline generator "
                f"({type(e).__name__}: {str(e)[:160]})",
                file=sys.stderr,
            )
            self._using_fallback = True
            return self._fallback.propose(context, k, seed)

    def _propose_api(self, context: str, k: int, seed: int) -> list[Conjecture]:
        from crm.proposers_code import _parse_json_array

        msg = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            temperature=float(self.config.get("temperature", 0.7)),
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _user_prompt(context, k)}],
        )
        text = "".join(
            b.text for b in msg.content if getattr(b, "type", "") == "text"
        )
        items = _parse_json_array(text)
        if not items:
            raise ValueError("no JSON candidates parsed from API response")

        batch: list[Conjecture] = []
        for item in items[:k]:
            if not isinstance(item, dict) or "statement" not in item:
                continue
            cid = f"c_{self._counter:04d}"
            self._counter += 1
            batch.append(
                Conjecture(
                    id=cid,
                    statement=str(item.get("statement", "")),
                    proof_attempt=str(item.get("proof_attempt", "")),
                    nl_gloss=str(item.get("nl_gloss", "")),
                    rationale=str(item.get("rationale", "api-lean-proposer (anthropic)")),
                )
            )
        if not batch:
            raise ValueError("API returned no usable Lean tasks")

        usage = getattr(msg, "usage", None)
        self.last_tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
        self.last_tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
        return batch
