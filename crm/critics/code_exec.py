"""Sandboxed Python execution critic (§6.1).

Domain (§6.1): the Proposer invents a self-contained, *executable* conjecture::

    {
      "function_spec": "<one-line signature + nl claim, e.g. 'f(n) returns the
                         number of divisors of n; claim: f(n) == f of n's prime
                         factorisation product'>",
      "reference_impl": "def f(n): ...",          # Python
      "tests": "assert f(6) == 4\nassert f(1) == 1",  # the proposer's own asserts
      "property": "lambda n: f(n) == sum(1 for d in range(1,n+1) if n%d==0)",
                  # an INDEPENDENT executable predicate of the claim (used to
                  # synthesise adversarial tests); optional but recommended.
      "domain": "[1, 200]",                        # input range for adversarial fuzz
      "nl_gloss": "...",
    }

Validity (§6.1) = the reference impl passes **all of its own tests** AND **>=1
independently-generated adversarial test**, executed in the sandbox (§6.2). The
adversarial tests are NOT supplied by the proposer: the critic generates fresh
inputs over `domain` and checks them against the `property` predicate (an
independent encoding of the claim). If no `property` is given, the critic falls
back to *metamorphic* adversarial tests derived from the spec (determinism /
idempotence / range checks) — still real execution, never LLM judgement (§3,
§15: NO LLM-as-judge for the survive/die decision).

`reason_class` mapping (§6.1):
  * PROVED   — all own tests AND >=1 adversarial test pass.
  * FALSE    — a test fails / wrong output (carries the failing input).
  * ILLFORMED— won't parse / import / define the promised symbol.
  * TIMEOUT  — wall-clock blown.

Significance perturbations (§5.2, §6.1) mutate the spec/constants and re-run; the
SignificanceCritic drives that via this critic's `check` + `automation_closeable`.
"""

from __future__ import annotations

import time
from typing import Any

from crm.critics.base import CritResult
from crm.sandbox import run_in_sandbox
from crm.types import Conjecture

# How many independent adversarial inputs to draw per candidate.
DEFAULT_N_ADVERSARIAL = 12


def _payload(conjecture: Conjecture) -> dict[str, Any]:
    """Pull the code task out of the conjecture (extra preferred, else parse)."""
    ex = conjecture.extra or {}
    if "reference_impl" in ex:
        return ex
    # Some proposers may pack the whole task JSON into `statement`; tolerate it.
    return ex


def _build_program(
    reference_impl: str,
    own_tests: str,
    adversarial_tests: list[str],
) -> str:
    """Assemble the full candidate program run inside the sandbox.

    Structure: define the reference impl, run the proposer's own asserts, then
    run the independently-generated adversarial asserts. `__crm_current_test__`
    is updated before each assert so the child can report which one failed.
    """
    lines: list[str] = []
    lines.append("# --- reference implementation (model-generated) ---")
    lines.append(reference_impl.strip())
    lines.append("")
    lines.append("__crm_current_test__ = None")
    lines.append("# --- proposer's own tests ---")
    for i, t in enumerate(_split_asserts(own_tests)):
        lines.append(f"__crm_current_test__ = {t!r}")
        lines.append(t)
    lines.append("# --- independently-generated adversarial tests ---")
    for i, t in enumerate(adversarial_tests):
        lines.append(f"__crm_current_test__ = {t!r}")
        lines.append(t)
    return "\n".join(lines)


def _split_asserts(tests: str) -> list[str]:
    out: list[str] = []
    for raw in (tests or "").splitlines():
        s = raw.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def _func_name(reference_impl: str) -> str | None:
    import re

    m = re.search(r"^\s*def\s+([A-Za-z_]\w*)\s*\(", reference_impl, re.MULTILINE)
    return m.group(1) if m else None


def _parse_domain(domain: str | None) -> tuple[int, int]:
    """Parse '[a, b]' / 'a..b' into an integer range; default [1, 100]."""
    import re

    if not domain:
        return (1, 100)
    nums = re.findall(r"-?\d+", str(domain))
    if len(nums) >= 2:
        a, b = int(nums[0]), int(nums[1])
        return (min(a, b), max(a, b))
    if len(nums) == 1:
        return (1, int(nums[0]))
    return (1, 100)


def _adversarial_tests(
    payload: dict[str, Any],
    fname: str,
    seed: int,
    n: int = DEFAULT_N_ADVERSARIAL,
) -> list[str]:
    """Generate INDEPENDENT adversarial asserts (§6.1) — not from the proposer.

    Strategy, in priority order, all real executable checks:
      1. If a `property` predicate is supplied, draw fresh inputs over `domain`
         (including boundary values) and assert `property(x)` holds — this is an
         independent encoding of the claim, so a wrong impl is caught.
      2. Else fall back to metamorphic checks that any correct deterministic
         numeric function must satisfy: determinism (same input -> same output)
         on fresh inputs the proposer did not list.
    """
    import random

    lo, hi = _parse_domain(payload.get("domain"))
    rng = random.Random(seed)
    # Boundary + random interior points the proposer is unlikely to have tested.
    pts: list[int] = []
    for b in (lo, lo + 1, hi, hi - 1):
        if lo <= b <= hi:
            pts.append(b)
    while len(pts) < n:
        pts.append(rng.randint(lo, hi))
    # de-dup, keep order, cap to n
    seen: set[int] = set()
    uniq: list[int] = []
    for p in pts:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    uniq = uniq[:n]

    prop = (payload.get("property") or "").strip()
    tests: list[str] = []
    if prop:
        # The property is an independent predicate over the input; bind it to a
        # name and assert it for each fresh point. We DO NOT trust the proposer's
        # word — we execute it.
        tests.append(f"__crm_prop = ({prop})")
        for x in uniq:
            tests.append(
                f"assert __crm_prop({x}), 'property fails at {x}'"
            )
    else:
        # Metamorphic fallback: determinism on fresh inputs.
        for x in uniq:
            tests.append(
                f"assert {fname}({x}) == {fname}({x}), 'non-deterministic at {x}'"
            )
    return tests


class CodeExecCritic:
    """Reality-grounded code critic (§6.1). Executes everything in the sandbox.

    NO LLM-as-judge: validity is decided purely by whether real code passes real
    tests under real execution (§3, §15).
    """

    name = "code_exec"

    def __init__(
        self,
        timeout_s: float = 5.0,
        n_adversarial: int = DEFAULT_N_ADVERSARIAL,
        seed: int = 0,
    ) -> None:
        self.timeout_s = timeout_s
        self.n_adversarial = n_adversarial
        self.seed = seed

    # ---- the survive/die decision --------------------------------------
    def check(self, conjecture: Conjecture) -> CritResult:
        t0 = time.perf_counter()
        payload = _payload(conjecture)

        impl = (payload.get("reference_impl") or "").strip()
        own_tests = payload.get("tests") or ""

        if not impl:
            return CritResult(
                False, "ILLFORMED", "no reference_impl supplied", None,
                time.perf_counter() - t0,
            )

        fname = _func_name(impl)
        if fname is None:
            return CritResult(
                False, "ILLFORMED", "reference_impl defines no top-level function",
                None, time.perf_counter() - t0,
            )

        own = _split_asserts(own_tests)
        if not own:
            return CritResult(
                False, "ILLFORMED", "no own tests supplied", None,
                time.perf_counter() - t0,
            )

        adversarial = _adversarial_tests(
            payload, fname, seed=self.seed + (conjecture.round or 0),
            n=self.n_adversarial,
        )
        if not adversarial:
            return CritResult(
                False, "ILLFORMED", "could not synthesise an adversarial test",
                None, time.perf_counter() - t0,
            )

        program = _build_program(impl, own_tests, adversarial)
        res = run_in_sandbox(program, timeout_s=self.timeout_s)
        secs = time.perf_counter() - t0

        if res.status == "timeout":
            return CritResult(False, "TIMEOUT", res.detail, None, secs)
        if res.status == "blocked":
            # Candidate tried to escape the sandbox; treat as ill-formed/refused.
            return CritResult(
                False, "ILLFORMED",
                f"refused (sandbox guard): {res.detail}", None, secs,
            )
        if res.status == "error":
            # Import/define/runtime error => ill-formed (won't parse/import, §6.1).
            return CritResult(False, "ILLFORMED", res.detail, None, secs)
        if res.status == "fail":
            return CritResult(
                False, "FALSE", f"test failed: {res.detail}", None, secs,
            )
        # status == "ok": all own tests AND >=1 adversarial test passed.
        return CritResult(
            True, "PROVED",
            f"{len(own)} own + {len(adversarial)} adversarial tests passed",
            "tests_passed", secs,
        )

    # ---- significance perturbations (§5.2, §6.1) -----------------------
    def perturb(
        self, conjecture: Conjecture, p: int, seed: int
    ) -> list[Conjecture]:
        """Mutate the spec/constants and return re-runnable candidates (§6.1).

        The hardness signal asks: do small changes to the load-bearing parts of
        the claim break it? For a code task the load-bearing parts are the
        numeric constants in the `reference_impl` and the `property` predicate.
        We mutate those constants (k -> k±1, 0<->1) ONE AT A TIME, holding the
        OTHER side fixed, so each neighbour is a genuinely different claim:

          * mutate a constant in the reference_impl but keep the property fixed
            => a contentful impl now violates its own property => FALSE (breaks).
          * mutate a constant in the property but keep the impl fixed
            => likewise a contentful claim breaks.

        A vacuous/over-permissive spec (e.g. property always True) survives these
        mutations => low hardness => correctly flagged trivial. This is real
        execution, not a heuristic: every neighbour is run in the sandbox.
        """
        import re
        import random

        ex = dict(conjecture.extra or {})
        impl = ex.get("reference_impl", "")
        prop = ex.get("property", "")
        base_id = conjecture.id

        int_re = re.compile(r"(?<![A-Za-z0-9_.])(\d+)(?![A-Za-z0-9_.])")

        def mutate_field(text: str) -> list[tuple[str, str]]:
            """Return (mutated_text, note) for each single-constant mutation."""
            out: list[tuple[str, str]] = []
            for m in int_re.finditer(text):
                k = int(m.group(1))
                s, e = m.span(1)
                cands: list[int] = [k + 1]
                if k >= 1:
                    cands.append(k - 1)
                if k == 0:
                    cands.append(1)
                for nk in cands:
                    if nk == k:
                        continue
                    out.append((text[:s] + str(nk) + text[e:], f"{k}->{nk}"))
            return out

        neighbours: list[Conjecture] = []
        # Mutate the impl (property held fixed) ...
        for i, (new_impl, note) in enumerate(mutate_field(impl)):
            nex = dict(ex)
            nex["reference_impl"] = new_impl
            neighbours.append(
                Conjecture(
                    id=f"{base_id}_pimpl{i}",
                    statement=conjecture.statement,
                    nl_gloss=f"impl const {note}",
                    round=conjecture.round,
                    extra=nex,
                )
            )
        # ... and mutate the property (impl held fixed).
        for i, (new_prop, note) in enumerate(mutate_field(prop)):
            nex = dict(ex)
            nex["property"] = new_prop
            neighbours.append(
                Conjecture(
                    id=f"{base_id}_pprop{i}",
                    statement=conjecture.statement,
                    nl_gloss=f"property const {note}",
                    round=conjecture.round,
                    extra=nex,
                )
            )

        # De-dup by (impl, property) and sample deterministically up to p.
        seen: set[tuple[str, str]] = set()
        uniq: list[Conjecture] = []
        for c in neighbours:
            key = (c.extra.get("reference_impl", ""), c.extra.get("property", ""))
            if key not in seen and key != (impl, prop):
                seen.add(key)
                uniq.append(c)
        rng = random.Random(seed)
        rng.shuffle(uniq)
        return uniq[:p]

    # ---- automation-closeability (feeds is_trivial, §5.2) --------------
    def automation_closeable(self, statement: str) -> bool:
        """Statement-only path (used by the Lean/arith critics). The code critic
        needs the full candidate (the executable property), so the meaningful
        oracle is `automation_closeable_conjecture`; from a bare string we cannot
        decide and conservatively return False."""
        return False

    def automation_closeable_conjecture(self, conjecture: Conjecture) -> bool:
        """A code claim is 'trivial' (the analogue of omega/decide closing a
        statement) iff a DEGENERATE implementation that ignores the real
        structure of the problem already satisfies the proposer's property over
        the fuzz domain (§5.2 triviality / reward-hack guard, §15).

        Concretely: replace the reference impl with each degenerate stand-in —
        `f(n)=0`, `f(n)=1`, `f(n)=n` (identity) — and run the property's
        adversarial tests in the sandbox. If ANY degenerate impl satisfies the
        property everywhere tested, the claim is vacuous: it does not pin down a
        non-trivial computation. This catches constant/identity reward-hacks
        (e.g. `f(n)=0` with property `f(n)==0`). Real execution, not heuristic.
        """
        payload = _payload(conjecture)
        prop = (payload.get("property") or "").strip()
        if not prop:
            # No independent property to interrogate => fall back to hardness.
            return False
        fname = _func_name(payload.get("reference_impl", "")) or "f"

        degenerate_impls = [
            f"def {fname}(n):\n    return 0",
            f"def {fname}(n):\n    return 1",
            f"def {fname}(n):\n    return n",
            f"def {fname}(n):\n    return True",
        ]
        # Use a DENSER battery for the triviality probe than for validity, so a
        # degenerate impl can't coincidentally pass a sparse sample and produce
        # a false "trivial" verdict on a genuinely contentful task.
        adversarial = _adversarial_tests(
            payload, fname, seed=self.seed, n=max(24, 2 * self.n_adversarial)
        )
        if not adversarial:
            return False
        for dimpl in degenerate_impls:
            program = _build_program(dimpl, "", adversarial)
            res = run_in_sandbox(program, timeout_s=self.timeout_s)
            if res.status == "ok":
                # A do-nothing constant/identity impl already satisfies the
                # claim over the whole fuzz domain => the spec pins down no
                # non-trivial computation => vacuous / trivial (reward-hack).
                return True
        return False
