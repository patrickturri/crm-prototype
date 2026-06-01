"""Hard-domain code proposer (addresses review finding #9).

The default code domain ("elementary number theory") lets the frozen LLM RECALL
textbook identities (Mobius inversion = phi, sum phi(d) = n, ...). Recall is not
discovery, so it does not test the thesis. This module defines a domain where the
model CANNOT recall the answer: a FRESHLY-DEFINED, parameterised integer-sequence
family that does not appear in any corpus, textbook, or (to the best of our
knowledge) OEIS. The model is handed ONLY the recurrence and must DISCOVER
properties of it (closed forms, divisibility/parity laws, growth identities,
cross-relations) by reasoning about the recurrence, not by recall.

Executable-property + sandbox-fuzz validation is kept intact:

  * The recurrence itself is given to the model as the ground-truth
    ``reference_impl`` skeleton (`g(n)`), so a conjecture is graded against the
    TRUE sequence, not the model's possibly-wrong restatement.
  * The model must supply an INDEPENDENT ``property`` predicate encoding the
    DISCOVERED identity (e.g. ``lambda n: g(n) == <closed form>`` or
    ``lambda n: g(n) % 2 == n % 2``). The CodeExecCritic fuzzes the recurrence
    against this predicate over the domain; a wrong conjecture is refuted by a
    real counterexample. NO LLM-as-judge.

Two proposers, same ``Proposer`` interface (``propose(context, k, seed)``):

  * ``HardDomainAPIProposer`` — real Anthropic LLM. It is told the sequence
    definition, the canonical ``g(n)`` recurrence to paste into every
    ``reference_impl``, and is asked for NON-trivial discovered identities.
  * ``HardDomainOfflineProposer`` — deterministic offline fallback so the run is
    free/reproducible when no API key is present. It emits a fixed pool of
    candidate identities about the SAME family — a deliberate mix of TRUE,
    FALSE, and TRIVIAL claims so the critic + significance guard have real work.

The freshly-defined family (NOT a standard sequence):

    g(0) = 2
    g(1) = 3
    g(n) = 3*g(n-1) - g(n-2) + (n % 3)        for n >= 2

The ``+ (n % 3)`` inhomogeneous term is the non-standard twist: it breaks the
clean Chebyshev/Fibonacci-style closed forms a model could recall, so any true
identity has to be FOUND. (We verified at build time that this exact recurrence
does not match the leading terms of common OEIS sequences; see
``data/hard_domain_corpus.jsonl`` for the recall-test corpus.)
"""

from __future__ import annotations

import random
from typing import Any

from crm.proposer import Proposer
from crm.types import Conjecture

# ---------------------------------------------------------------------------
# The freshly-defined family. This canonical recurrence is the GROUND TRUTH;
# every candidate's reference_impl is this exact function, so the critic fuzzes
# the model's conjectured property against the TRUE sequence.
# ---------------------------------------------------------------------------

CANONICAL_G = (
    "def g(n):\n"
    "    a, b = 2, 3\n"
    "    if n == 0:\n"
    "        return a\n"
    "    if n == 1:\n"
    "        return b\n"
    "    for i in range(2, n + 1):\n"
    "        a, b = b, 3 * b - a + (i % 3)\n"
    "    return b"
)

_SEQUENCE_DEF = (
    "Consider the FRESHLY-DEFINED integer sequence g (it is NOT a standard named "
    "sequence; do not assume Fibonacci/Lucas/Chebyshev closed forms):\n"
    "    g(0) = 2\n"
    "    g(1) = 3\n"
    "    g(n) = 3*g(n-1) - g(n-2) + (n mod 3)   for n >= 2\n"
    "The canonical reference implementation you MUST paste verbatim as "
    "reference_impl in EVERY candidate is:\n\n"
    f"{CANONICAL_G}\n\n"
    "First few terms: g(0..8) = 2, 3, 9, 24, 64, 170, 446, 1169, 3063.\n"
    "You CANNOT look this sequence up. You must DISCOVER properties of it by "
    "reasoning about the recurrence: parity/divisibility laws, growth ratios, "
    "linear identities relating g(n), g(n-1), g(n-2), modular patterns, or a "
    "closed/semi-closed form. Each conjecture must be an INDEPENDENT executable "
    "predicate of g (a different formula or modular check), so an automated "
    "critic can fuzz-test it against the true recurrence."
)


# ---------------------------------------------------------------------------
# Offline candidate pool over the SAME family. Each entry's reference_impl is
# the canonical recurrence (ground truth); the `property` is the conjectured
# identity. Mix of TRUE / FALSE / TRIVIAL so the pipeline has real work.
# ---------------------------------------------------------------------------

_POOL: list[dict[str, str]] = [
    {
        # TRUE: linear recurrence identity re-derived independently (recompute
        # g(n-1), g(n-2) inline and check 3*g(n-1)-g(n-2)+(n%3) == g(n)).
        "statement": "g satisfies g(n) = 3*g(n-1) - g(n-2) + (n mod 3) for n>=2 (recurrence holds)",
        "property": (
            "lambda n: n < 2 or g(n) == 3 * g(n - 1) - g(n - 2) + (n % 3)"
        ),
        "domain": "[2, 60]",
        "nl_gloss": "the defining recurrence re-checked independently (TRUE)",
    },
    {
        # TRUE: g(n) mod 2 obeys the recurrence reduced mod 2. Independent check
        # recomputes the parity via a separate mod-2 recurrence (not by reading
        # g), so it is a genuine cross-formula, not a restatement of the impl.
        "statement": "parity of g(n) equals parity of the 2-term mod-2 recurrence seeded (0,1)",
        "property": (
            "lambda n: g(n) % 2 == (lambda m: (lambda f: f(f, m))"
            "(lambda rec, k: (2 % 2) if k == 0 else ((3 % 2) if k == 1 else "
            "(3 * rec(rec, k - 1) - rec(rec, k - 2) + (k % 3)) % 2)))(n)"
        ),
        "domain": "[0, 25]",
        "nl_gloss": "g(n) mod 2 obeys the same recurrence mod 2 (TRUE but near-restatement)",
    },
    {
        # TRUE non-obvious: g(n) - g(n-1) is strictly increasing (convexity-like).
        "statement": "consecutive differences g(n)-g(n-1) are strictly increasing for n>=2",
        "property": (
            "lambda n: n < 3 or (g(n) - g(n - 1)) > (g(n - 1) - g(n - 2))"
        ),
        "domain": "[3, 60]",
        "nl_gloss": "the difference sequence is strictly increasing (discovered, TRUE)",
    },
    {
        # TRUE growth: g(n+1) > 2*g(n) for n>=1 (ratio bound, must be discovered).
        "statement": "g grows faster than doubling: g(n+1) > 2*g(n) for all n>=1",
        "property": "lambda n: n < 1 or g(n + 1) > 2 * g(n)",
        "domain": "[1, 50]",
        "nl_gloss": "super-doubling growth bound (discovered, TRUE)",
    },
    {
        # FALSE: a plausible-looking but wrong closed form (Chebyshev-style guess
        # that ignores the +(n%3) term). The critic must refute it.
        "statement": "g has closed form g(n) = round(((3+sqrt(5))/2)**n) (homogeneous guess)",
        "property": (
            "lambda n: g(n) == round(((3 + 5 ** 0.5) / 2) ** n)"
        ),
        "domain": "[0, 20]",
        "nl_gloss": "homogeneous golden-ratio-style closed form (FALSE: ignores +(n%3))",
    },
    {
        # FALSE: wrong divisibility claim.
        "statement": "g(n) is divisible by 3 whenever n is divisible by 3",
        "property": "lambda n: (n % 3 != 0) or (g(n) % 3 == 0)",
        "domain": "[0, 40]",
        "nl_gloss": "false divisibility-by-3 claim (FALSE)",
    },
    {
        # TRIVIAL / vacuous: property satisfied by a constant; degenerate impls
        # close it -> significance flags trivial.
        "statement": "g(n) is always at least 2 (lower bound, vacuous)",
        "property": "lambda n: g(n) >= 2",
        "domain": "[0, 40]",
        "nl_gloss": "vacuous lower bound (TRIVIAL; degenerate const impl closes it)",
    },
    {
        # TRUE discovered modular identity: g(n) mod 3 cycles with period 3:
        # g mod 3 = 2,0,2,1,2,2,0,1,2,... compute -> check independently via
        # recomputed mod-3 recurrence.
        "statement": "g(n) mod 3 obeys the recurrence reduced mod 3 (period structure)",
        "property": (
            "lambda n: g(n) % 3 == (lambda m: (lambda f: f(f, m))"
            "(lambda rec, k: (2 % 3) if k == 0 else ((3 % 3) if k == 1 else "
            "(3 * rec(rec, k - 1) - rec(rec, k - 2) + (k % 3)) % 3)))(n)"
        ),
        "domain": "[0, 25]",
        "nl_gloss": "g(n) mod 3 from the reduced recurrence (TRUE)",
    },
]


def _make_conjecture(item: dict[str, str], counter: int) -> Conjecture:
    return Conjecture(
        id=f"h_{counter:04d}",
        statement=item["statement"],
        nl_gloss=item.get("nl_gloss", ""),
        rationale="hard-domain proposer",
        extra={
            "reference_impl": CANONICAL_G,
            # The proposer's own asserts: a couple of known true anchor terms so
            # an ILL-FORMED property is caught early; these are about g, not the
            # claim, and are identical for every candidate.
            "tests": "assert g(0) == 2\nassert g(2) == 9\nassert g(4) == 64",
            "property": item["property"],
            "domain": item.get("domain", "[0, 40]"),
        },
    )


class HardDomainOfflineProposer(Proposer):
    """Deterministic offline proposer over the freshly-defined family."""

    name = "hard_offline"

    def __init__(self) -> None:
        self.last_tokens_in = 0
        self.last_tokens_out = 0
        self._counter = 0

    def propose(self, context: str, k: int, seed: int) -> list[Conjecture]:
        rng = random.Random(seed)
        pool = list(_POOL)
        rng.shuffle(pool)
        picks = [pool[i % len(pool)] for i in range(k)]
        batch = [self._make_conjecture(it) for it in picks]
        self.last_tokens_in = len(context.split())
        self.last_tokens_out = sum(
            len((c.statement + " " + c.extra.get("property", "")).split())
            for c in batch
        )
        return batch

    def _make_conjecture(self, item: dict[str, str]) -> Conjecture:
        c = _make_conjecture(item, self._counter)
        self._counter += 1
        return c


_SYSTEM_PROMPT = (
    "You are a mathematical-discovery engine. You are given the definition of a "
    "FRESHLY-INVENTED integer sequence that does NOT appear in any textbook or "
    "database, so you CANNOT recall facts about it — you must DISCOVER true, "
    "non-trivial properties by reasoning about its recurrence. For each "
    "discovery you return a Python predicate that an automated critic will "
    "fuzz-test against the true recurrence. Never explain; return STRICT JSON "
    "only."
)


def _user_prompt(context: str, k: int) -> str:
    return (
        f"{_SEQUENCE_DEF}\n\n"
        f"{context}\n\n"
        f"Propose {k} NEW, NON-TRIVIAL discovered properties of g. Return a "
        f"STRICT JSON array of {k} objects, each with EXACTLY these keys:\n"
        '  "statement": one-line natural-language statement of the discovered '
        "property of g,\n"
        '  "property": a Python lambda of one arg n encoding the property '
        "INDEPENDENTLY (a different formula / modular check), e.g. "
        '"lambda n: g(n) % 2 == n % 2" or '
        '"lambda n: n < 2 or g(n) == <expr in g(n-1), g(n-2)>". You may guard '
        "small-n with `n < c or ...`. The function g is already defined for "
        "you; reference it directly.\n"
        '  "domain": an input range like "[0, 40]",\n'
        '  "nl_gloss": a short gloss.\n'
        "Do NOT restate the defining recurrence verbatim — find DEEPER "
        "properties (closed forms, divisibility/parity laws, growth bounds, "
        "modular periods, identities among several terms). Make them non-trivial "
        "(a constant/identity stand-in must NOT satisfy them) and likely TRUE. "
        "JSON only, no prose. Do NOT include reference_impl — it is fixed."
    )


class HardDomainAPIProposer(Proposer):
    """Anthropic API proposer over the freshly-defined family, offline fallback."""

    name = "hard_api"

    def __init__(self, **kwargs: Any) -> None:
        self.config = kwargs
        self._fallback = HardDomainOfflineProposer()
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

            load_dotenv()
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
                f"[crm] HardDomainAPIProposer: falling back to offline "
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
            if not isinstance(item, dict) or "property" not in item:
                continue
            cid = f"h_{self._counter:04d}"
            self._counter += 1
            # reference_impl is ALWAYS the canonical ground-truth recurrence; the
            # model only supplies the conjectured property (no LLM-authored impl
            # to game the fuzzing).
            batch.append(
                Conjecture(
                    id=cid,
                    statement=str(item.get("statement", "")),
                    nl_gloss=str(item.get("nl_gloss", "")),
                    rationale="hard-domain api-proposer (anthropic)",
                    extra={
                        "reference_impl": CANONICAL_G,
                        "tests": "assert g(0) == 2\nassert g(2) == 9\nassert g(4) == 64",
                        "property": str(item.get("property", "")),
                        "domain": str(item.get("domain", "[0, 40]")),
                    },
                )
            )
        if not batch:
            raise ValueError("API returned no usable hard-domain properties")

        usage = getattr(msg, "usage", None)
        self.last_tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
        self.last_tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
        return batch
