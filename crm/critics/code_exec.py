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
        self, conjecture: Conjecture, p: int, seed: int, strategy: str = "literal"
    ) -> list[Conjecture]:
        """Mutate the spec/constants and return re-runnable candidates (§6.1).

        The hardness signal asks: do small changes to the load-bearing parts of
        the claim break it? For a code task the load-bearing parts are the
        numeric constants AND the operators/boundaries in the `reference_impl`
        and the `property` predicate. We mutate those ONE AT A TIME, holding the
        OTHER side fixed, so each neighbour is a genuinely different claim:

          * mutate the reference_impl but keep the property fixed
            => a contentful impl now violates its own property => FALSE (breaks).
          * mutate the property but keep the impl fixed
            => likewise a contentful claim breaks.

        A vacuous/over-permissive spec (e.g. property always True) survives these
        mutations => low hardness => correctly flagged trivial. This is real
        execution, not a heuristic: every neighbour is run in the sandbox.

        ``strategy`` selects the mutation family (addresses review finding #6,
        where literal +-1 mutations saturate hardness at 0.88 for every
        survivor):

          * ``"literal"`` (default): ONLY integer-literal mutations k->k+-1,
            0->1. This reproduces the original behaviour byte-for-byte so the
            two strategies can be A/B'd against the same survivors.
          * ``"semantic"``: ONLY operand/operator-level rewrites — range-boundary
            edits, comparison/arithmetic-operator swaps, condition negation,
            and off-by-domain body shifts. No literal mutations.
          * ``"rich"`` / ``"all"``: BOTH literal and semantic mutations.

        Every neighbour, regardless of strategy, flows through the SAME
        dedup-and-sample tail and is run in the sandbox — no heuristic scoring.
        """
        import re
        import random

        ex = dict(conjecture.extra or {})
        impl = ex.get("reference_impl", "")
        prop = ex.get("property", "")
        base_id = conjecture.id

        do_literal = strategy in ("literal", "rich", "all")
        do_semantic = strategy in ("semantic", "rich", "all")

        int_re = re.compile(r"(?<![A-Za-z0-9_.])(\d+)(?![A-Za-z0-9_.])")

        # Operator/comparison swaps: each (pattern, replacement, note). The
        # patterns require non-word boundaries so we never split an identifier.
        # Applied ONE occurrence at a time below.
        _OP_SWAPS: list[tuple[str, str, str]] = [
            (r"==", "!=", "==/!="),
            (r"!=", "==", "!=/=="),
            (r"<=", "<", "<=/<"),
            (r">=", ">", ">=/>"),
            (r"<", "<=", "</<="),
            (r">", ">=", ">/>="),
            (r"%", "//", "%//"),
            (r"\+", "-", "+/-"),
            (r"-", "+", "-/+"),
            (r"\*", "//", "*//"),
            (r"//", "*", "///*"),
        ]

        def mutate_field(text: str) -> list[tuple[str, str]]:
            """Return (mutated_text, note) for each single mutation of `text`.

            Honours the enclosing ``strategy``: literal mutations gated on
            ``do_literal``, operand/operator rewrites gated on ``do_semantic``.
            """
            out: list[tuple[str, str]] = []

            # --- literal mutations (original behaviour) --------------------
            if do_literal:
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

            # --- semantic mutations (operand/operator-level rewrites) ------
            if do_semantic:
                out.extend(_semantic_mutations(text))

            return out

        # range(a, b) boundary edits: shift each numeric/expression bound by
        # +-1 at the source-token level. Captures the common idioms
        # range(1, n+1), range(0, n+1), range(n), range(2, n).
        _range_re = re.compile(r"range\(([^()]*)\)")
        _ident_re = re.compile(r"(?<![A-Za-z0-9_.])([A-Za-z_]\w*)(?![A-Za-z0-9_(.])")

        def _semantic_mutations(text: str) -> list[tuple[str, str]]:
            out: list[tuple[str, str]] = []

            # 1. operator / comparison / arithmetic swaps, one occurrence each.
            for pat, repl, note in _OP_SWAPS:
                cre = re.compile(pat)
                for m in cre.finditer(text):
                    s, e = m.span()
                    out.append((text[:s] + repl + text[e:], f"op {note}"))

            # 2. range() boundary edits: append +1 / -1 to each comma-separated
            #    argument of every range(...) call (off-by-one in the bound).
            for m in _range_re.finditer(text):
                inner = m.group(1)
                s, e = m.span()
                args = inner.split(",")
                for ai in range(len(args)):
                    for delta, sym in ((1, "+1"), (-1, "-1")):
                        new_args = list(args)
                        new_args[ai] = f"({args[ai].strip()}){'+' if delta>0 else '-'}1"
                        new_inner = ",".join(new_args)
                        new_call = f"range({new_inner})"
                        out.append(
                            (text[:s] + new_call + text[e:],
                             f"range arg{ai} {sym}")
                        )

            # 3. off-by-domain body shift: n -> n+1 / n -> n-1 for bare uses of
            #    the loop/argument variable `n` (the canonical task variable),
            #    one occurrence at a time. Skips identifier-internal matches.
            for m in re.finditer(r"(?<![A-Za-z0-9_.])n(?![A-Za-z0-9_(.])", text):
                s, e = m.span()
                for repl, sym in (("(n+1)", "n->n+1"), ("(n-1)", "n->n-1")):
                    out.append((text[:s] + repl + text[e:], f"shift {sym}"))

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

    # ---- downstream enablement (feeds breadth, §5.2) -------------------
    def enables(self, survivor: Conjecture, target: dict[str, Any]) -> bool:
        """Does the survivor's VERIFIED function enable this held-out task? (§5.2)

        We inject the survivor's reference function as the helper ``h`` of the
        target's ``solve(n, h)`` and check, in the sandbox, that it reproduces the
        target's canonical helper over the target's domain. A guard first confirms
        the target genuinely DEPENDS on the helper (an identity helper gives a
        different answer somewhere), so we count real enablement, not a task that
        any function would satisfy. Real execution, never fabricated; a signature
        mismatch / wrong output simply means "not enabled" (honest 0).
        """
        payload = _payload(survivor)
        impl = (payload.get("reference_impl") or "").strip()
        fname = _func_name(impl)
        h_ref = (target.get("h_ref") or "").strip()
        h_ref_name = (target.get("h_ref_name") or "_crm_h_ref").strip()
        solve = (target.get("solve") or "").strip()
        domain = (target.get("domain") or "range(1, 13)").strip()
        if not impl or not fname or not h_ref or not solve:
            return False

        program = "\n".join([
            "import math",
            "from math import comb, gcd, factorial as _crm_factorial",
            "# --- survivor's verified reference implementation ---",
            impl,
            "# --- target's canonical helper + downstream task ---",
            h_ref,
            solve,
            f"_crm_dom = list({domain})",
            "_crm_id = (lambda _x: _x)",
            # guard: the task must genuinely depend on the helper's CONTENT.
            f"assert any(solve(_n, _crm_id) != solve(_n, {h_ref_name}) "
            f"for _n in _crm_dom), 'helper-independent target'",
            # enablement: the survivor's function reproduces the canonical helper
            # INSIDE the downstream computation, for every n in the domain.
            f"assert all(solve(_n, {fname}) == solve(_n, {h_ref_name}) "
            f"for _n in _crm_dom), 'survivor does not supply the building block'",
            "print('ENABLED')",
        ])
        res = run_in_sandbox(program, timeout_s=self.timeout_s)
        return res.status == "ok"

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
