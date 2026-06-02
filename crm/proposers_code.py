"""Code-task proposers for the CodeExecCritic (§6.1, §7).

Two proposers, same `Proposer` interface (`propose(context, k, seed)`):

  * `OfflineCodeProposer` — a DETERMINISTIC, seedable, offline candidate
    generator. Required by the spec: "If no Anthropic/OpenAI API key is in env,
    make the proposer degrade to a deterministic offline candidate generator so
    the demo still produces REAL critic-verified survivors (real execution,
    never LLM-judged validity)." It emits a pool of genuine elementary
    number-theory / combinatorics code tasks, each with an INDEPENDENT property
    predicate so the critic can synthesise adversarial tests. The tasks are NOT
    "results" — they are *proposals*; only the real CodeExecCritic decides which
    survive. Some pool entries are deliberately FALSE or TRIVIAL so the critic
    and the significance guard have a real mix to grade.

  * `APICodeProposer` — the real LLM proposer (§7). Loads the gitignored `.env`
    via python-dotenv, calls the Anthropic Messages API for strict-JSON code
    tasks, and degrades to `OfflineCodeProposer` if the key is absent/invalid or
    the call fails. The LLM only PROPOSES; validity is always decided by the
    sandboxed critic (NO LLM-as-judge, §3, §15).

Each candidate packs its code task into `Conjecture.extra`:
    {reference_impl, tests, property, domain}
and uses `Conjecture.statement` for the human/embeddable spec (drives novelty).
"""

from __future__ import annotations

import random
from typing import Any

from crm.proposer import Proposer
from crm.types import Conjecture

# ---------------------------------------------------------------------------
# Offline candidate pool. Real, executable elementary-NT tasks. Each task:
#   statement      : NL spec (embeddable; drives novelty)
#   reference_impl : Python def
#   tests          : the proposer's OWN asserts
#   property       : an INDEPENDENT executable predicate of the claim
#   domain         : fuzz range "[lo, hi]"
# `property` is independent of `reference_impl` (different formula), so a wrong
# impl is genuinely caught by the critic's adversarial fuzzing.
# ---------------------------------------------------------------------------

_POOL: list[dict[str, str]] = [
    {
        "statement": "f(n) = number of positive divisors of n; equals trial-division count",
        "reference_impl": (
            "def f(n):\n"
            "    c = 0\n"
            "    d = 1\n"
            "    while d * d <= n:\n"
            "        if n % d == 0:\n"
            "            c += 1 if d * d == n else 2\n"
            "        d += 1\n"
            "    return c"
        ),
        "tests": "assert f(1) == 1\nassert f(6) == 4\nassert f(12) == 6",
        "property": "lambda n: f(n) == sum(1 for d in range(1, n + 1) if n % d == 0)",
        "domain": "[1, 200]",
        "nl_gloss": "divisor-count via sqrt loop equals the naive count",
    },
    {
        "statement": "f(n) = sum of proper divisors of n (aliquot sum)",
        "reference_impl": (
            "def f(n):\n"
            "    return sum(d for d in range(1, n) if n % d == 0)"
        ),
        "tests": "assert f(6) == 6\nassert f(12) == 16\nassert f(1) == 0",
        "property": "lambda n: f(n) == sum(d for d in range(1, n) if n % d == 0)",
        "domain": "[1, 150]",
        "nl_gloss": "aliquot sum: sum of proper divisors",
    },
    {
        "statement": "f(n) = Euler totient phi(n); equals count of k in [1,n] coprime to n",
        "reference_impl": (
            "import math\n"
            "def f(n):\n"
            "    r = n\n"
            "    m = n\n"
            "    p = 2\n"
            "    while p * p <= m:\n"
            "        if m % p == 0:\n"
            "            while m % p == 0:\n"
            "                m //= p\n"
            "            r -= r // p\n"
            "        p += 1\n"
            "    if m > 1:\n"
            "        r -= r // m\n"
            "    return r"
        ),
        "tests": "assert f(1) == 1\nassert f(9) == 6\nassert f(10) == 4",
        "property": (
            "lambda n: f(n) == sum(1 for k in range(1, n + 1) "
            "if math.gcd(k, n) == 1)"
        ),
        "domain": "[1, 120]",
        "nl_gloss": "Euler totient by factorisation equals the coprime-count",
    },
    {
        "statement": "f(n) = n-th triangular number; equals n*(n+1)/2",
        "reference_impl": (
            "def f(n):\n"
            "    return sum(range(n + 1))"
        ),
        "tests": "assert f(0) == 0\nassert f(3) == 6\nassert f(5) == 15",
        "property": "lambda n: f(n) == n * (n + 1) // 2",
        "domain": "[0, 300]",
        "nl_gloss": "partial-sum triangular number equals closed form",
    },
    {
        "statement": "f(n) = bit count (popcount) of n; equals number of 1s in binary",
        "reference_impl": (
            "def f(n):\n"
            "    c = 0\n"
            "    while n:\n"
            "        c += n & 1\n"
            "        n >>= 1\n"
            "    return c"
        ),
        "tests": "assert f(0) == 0\nassert f(7) == 3\nassert f(8) == 1",
        "property": "lambda n: f(n) == bin(n).count('1')",
        "domain": "[0, 500]",
        "nl_gloss": "popcount loop equals binary 1-count",
    },
    {
        "statement": "f(n) = sum of first n odd numbers; equals n*n",
        "reference_impl": (
            "def f(n):\n"
            "    return sum(2 * i + 1 for i in range(n))"
        ),
        "tests": "assert f(1) == 1\nassert f(4) == 16",
        "property": "lambda n: f(n) == n * n",
        "domain": "[0, 200]",
        "nl_gloss": "sum of first n odds is a perfect square",
    },
    {
        "statement": "f(n) = reverse of digits of n then reverse again; equals n (no leading zeros)",
        "reference_impl": (
            "def f(n):\n"
            "    return int(str(int(str(n)[::-1]))[::-1])"
        ),
        "tests": "assert f(123) == 123\nassert f(120) == 12",
        # NOTE: this claim is FALSE in general (120 -> 21 -> 12 != 120). The
        # critic must catch it via the independent property. A genuine refuted
        # sibling for the genealogy.
        "property": "lambda n: f(n) == n",
        "domain": "[1, 300]",
        "nl_gloss": "double digit-reverse returns n (FALSE: fails on multiples of 10)",
    },
    {
        "statement": "f(n) = always 0 regardless of input (vacuous constant)",
        "reference_impl": (
            "def f(n):\n"
            "    return 0"
        ),
        "tests": "assert f(5) == 0\nassert f(9) == 0",
        # TRIVIAL: property is satisfied by a constant impl; mutating constants
        # barely breaks it -> low hardness -> significance flags it trivial.
        "property": "lambda n: f(n) == 0",
        "domain": "[0, 100]",
        "nl_gloss": "constant-zero function (vacuous; should be suppressed)",
    },
    {
        "statement": "f(n) = number of integers in [1,n] divisible by 3; equals n//3",
        "reference_impl": (
            "def f(n):\n"
            "    return sum(1 for k in range(1, n + 1) if k % 3 == 0)"
        ),
        "tests": "assert f(3) == 1\nassert f(9) == 3\nassert f(2) == 0",
        "property": "lambda n: f(n) == n // 3",
        "domain": "[1, 250]",
        "nl_gloss": "count of multiples of 3 up to n is floor(n/3)",
    },
    {
        "statement": "f(n) = sum of squares 1..n; equals n(n+1)(2n+1)/6",
        "reference_impl": (
            "def f(n):\n"
            "    return sum(i * i for i in range(1, n + 1))"
        ),
        "tests": "assert f(1) == 1\nassert f(3) == 14",
        "property": "lambda n: 6 * f(n) == n * (n + 1) * (2 * n + 1)",
        "domain": "[0, 150]",
        "nl_gloss": "sum of squares closed form",
    },
]


class OfflineCodeProposer(Proposer):
    """Deterministic offline code-task proposer (§7 fallback, §6.1)."""

    name = "offline_code"

    def __init__(self) -> None:
        self.last_tokens_in = 0
        self.last_tokens_out = 0
        self._counter = 0

    def propose(self, context: str, k: int, seed: int) -> list[Conjecture]:
        rng = random.Random(seed)
        # Sample WITHOUT replacement within a round so a round has variety; if k
        # exceeds the pool, wrap around.
        pool = list(_POOL)
        rng.shuffle(pool)
        picks = [pool[i % len(pool)] for i in range(k)]

        batch: list[Conjecture] = []
        for item in picks:
            cid = f"c_{self._counter:04d}"
            self._counter += 1
            batch.append(
                Conjecture(
                    id=cid,
                    statement=item["statement"],
                    nl_gloss=item.get("nl_gloss", ""),
                    rationale="offline-code-proposer (deterministic fallback)",
                    extra={
                        "reference_impl": item["reference_impl"],
                        "tests": item["tests"],
                        "property": item.get("property", ""),
                        "domain": item.get("domain", "[1, 100]"),
                    },
                )
            )
        self.last_tokens_in = len(context.split())
        self.last_tokens_out = sum(
            len((c.statement + " " + c.extra.get("reference_impl", "")).split())
            for c in batch
        )
        return batch


# ---------------------------------------------------------------------------
# Real API proposer (Anthropic), with offline fallback.
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You invent SMALL, SELF-CONTAINED, VERIFIABLE Python coding conjectures in "
    "elementary number theory / combinatorics. For each, return a function "
    "`f`, your own asserts, and an INDEPENDENT property predicate (a different "
    "formula computing the same claimed quantity) so an automated critic can "
    "fuzz-test it. Never explain; return STRICT JSON only."
)


def _user_prompt(context: str, k: int) -> str:
    return (
        f"{context}\n\n"
        f"Propose {k} NEW code conjectures. Return a STRICT JSON array of "
        f"{k} objects, each with EXACTLY these keys:\n"
        '  "statement": one-line natural-language spec of f and its claim,\n'
        '  "reference_impl": a Python `def f(n): ...` (stdlib only; may '
        '`import math`),\n'
        '  "tests": newline-separated `assert f(...) == ...` lines,\n'
        '  "property": a Python lambda of one arg encoding the claim '
        "INDEPENDENTLY of reference_impl, e.g. "
        '"lambda n: f(n) == <other formula>",\n'
        '  "domain": an input range like "[1, 200]",\n'
        '  "nl_gloss": a short gloss.\n'
        "Make them non-trivial and likely-true. JSON only, no prose."
    )


class APICodeProposer(Proposer):
    """Anthropic API code-task proposer (§7) with offline fallback."""

    name = "api_code"

    def __init__(self, **kwargs: Any) -> None:
        self.config = kwargs
        self._fallback = OfflineCodeProposer()
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

            # Bound each request so a hung socket can't stall a multi-round/
            # multi-seed sweep indefinitely (observed: a single request blocking
            # at 0% CPU for tens of minutes with no client timeout). On timeout
            # the SDK retries `max_retries` times, then raises -> `propose`
            # degrades to the offline generator, which the experiments'
            # fallback guard then flags loudly rather than hanging silently.
            timeout_s = float(self.config.get("request_timeout_s", 120.0))
            max_retries = int(self.config.get("max_retries", 2))
            self._client = anthropic.Anthropic(
                api_key=key, timeout=timeout_s, max_retries=max_retries
            )
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
            # Any API/JSON failure => degrade to offline so the demo still
            # produces REAL critic-verified survivors (spec requirement). Log a
            # one-line reason to stderr (never the key) so the fallback is
            # diagnosable instead of silent.
            import sys

            print(
                f"[crm] APICodeProposer: falling back to offline generator "
                f"({type(e).__name__}: {str(e)[:160]})",
                file=sys.stderr,
            )
            self._using_fallback = True
            return self._fallback.propose(context, k, seed)

    def _propose_api(self, context: str, k: int, seed: int) -> list[Conjecture]:
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
            if not isinstance(item, dict) or "reference_impl" not in item:
                continue
            cid = f"c_{self._counter:04d}"
            self._counter += 1
            batch.append(
                Conjecture(
                    id=cid,
                    statement=str(item.get("statement", "")),
                    nl_gloss=str(item.get("nl_gloss", "")),
                    rationale="api-code-proposer (anthropic)",
                    extra={
                        "reference_impl": str(item.get("reference_impl", "")),
                        "tests": str(item.get("tests", "")),
                        "property": str(item.get("property", "")),
                        "domain": str(item.get("domain", "[1, 100]")),
                    },
                )
            )
        if not batch:
            raise ValueError("API returned no usable code tasks")

        # Real token accounting from the API usage object.
        usage = getattr(msg, "usage", None)
        self.last_tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
        self.last_tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
        return batch


def _parse_json_array(text: str) -> list[dict]:
    """Robustly extract a JSON array of objects from an LLM response.

    Handles: bare JSON, ```json fenced blocks, and surrounding prose. The
    bracket matcher is STRING-AWARE so `[1,n]` appearing inside a string value
    does not confuse the array-boundary detection.
    """
    import json
    import re

    text = (text or "").strip()
    # Strip surrounding code fences if present (``` or ```json ... ```).
    fence = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    elif text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()

    # Fast path: the whole thing is the array.
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
    except json.JSONDecodeError:
        pass

    # String-aware bracket scan from the first '['.
    start = text.find("[")
    if start == -1:
        return []
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                try:
                    obj = json.loads(blob)
                    return [x for x in obj if isinstance(x, dict)] if isinstance(obj, list) else []
                except json.JSONDecodeError:
                    break
    # Salvage path: the array was truncated (e.g. max_tokens). Pull out every
    # complete top-level {...} object we can, string-aware.
    return _salvage_objects(text[start:])


def _salvage_objects(text: str) -> list[dict]:
    import json

    out: list[dict] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        j = i
        while j < n:
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        blob = text[i : j + 1]
                        try:
                            obj = json.loads(blob)
                            if isinstance(obj, dict):
                                out.append(obj)
                        except json.JSONDecodeError:
                            pass
                        break
            j += 1
        i = j + 1
    return out
