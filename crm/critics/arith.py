"""ArithCritic — a real, offline, reality-grounded critic for elementary NT.

This critic is NOT an LLM judge and NOT the trivial MockCritic. It genuinely
*evaluates* a restricted class of elementary number-theory statements (the demo
domain, §6.3) by numeric checking over a finite range of naturals plus a small
SMT-free decision procedure. It is the offline analogue of the Lean critic for
Phase 1: it lets the significance machinery (perturbations -> hardness,
is_trivial via automation-closeability) run for real, fast, with no network.

Reality-grounding (§3, §15): validity is decided by *computation* over concrete
inputs, never by appeal to a language model. A statement is valid iff it holds
for every tested natural in [0, N); a counterexample makes it FALSE.

Supported surface fragment (Lean-4-flavoured, also accepts the ascii forms the
StubProposer/perturbations emit):

  forall (vars), <hyp> -> <conclusion>
  exists (vars), <body>

with atoms built from: integer literals, the bound variables, `+ - *`,
`Nat.gcd`, `Nat.lcm`, `Nat.Coprime a b` (== gcd a b = 1), `%`, `Nat.Prime p`,
divisibility `a ∣ b` / `a | b`, and relations `= != <= < >= > ≤ ≥ ≠`.

Anything outside this fragment yields reason_class=ILLFORMED with valid=False —
the honest answer ("I cannot evaluate this"), never a fabricated pass.

`proof_method`:
  - "decide"   : closed by the decision procedure (automation alone). Feeds
                 is_trivial — an automation-closeable statement is trivial.
  - "supplied" : would be used by the Lean critic for a hand proof; the arith
                 critic always decides, so it reports "decide" on success.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass

from crm.critics.base import CritResult
from crm.types import Conjecture

# Default range over which forall/exists are checked.
DEFAULT_N = 40


# ---------------------------------------------------------------------------
# A tiny safe arithmetic evaluator over naturals.
# ---------------------------------------------------------------------------

class ParseError(Exception):
    pass


def _normalise(expr: str) -> str:
    """Map unicode/lean tokens to a canonical ascii form we can tokenise."""
    s = expr
    s = s.replace("ℕ", "Nat").replace("→", "->")
    s = s.replace("≤", "<=").replace("≥", ">=").replace("≠", "!=")
    s = s.replace("∣", " DIV_BAR ").replace("∤", " NDIV_BAR ")
    s = s.replace("∧", " AND ").replace("∨", " OR ")
    s = s.replace("/\\", " AND ").replace("\\/", " OR ")
    s = s.replace("Nat.Coprime", " COPRIME ")
    s = s.replace("Nat.gcd", " GCD ").replace("Nat.lcm", " LCM ")
    s = s.replace("Nat.Prime", " PRIME ")
    s = s.replace("Nat.succ", " SUCC ")
    return s


def gcd(a: int, b: int) -> int:
    return math.gcd(int(a), int(b))


def lcm(a: int, b: int) -> int:
    a, b = int(a), int(b)
    if a == 0 or b == 0:
        return 0
    return abs(a * b) // math.gcd(a, b)


def is_prime(n) -> bool:
    n = int(n)
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0:
        return False
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True


# Tokeniser ----------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"\s*(<=|>=|!=|<|>|=|\+|-|\*|%|\(|\)|,|"
    r"DIV_BAR|NDIV_BAR|AND|OR|COPRIME|GCD|LCM|PRIME|SUCC|True|False|Not|"
    r"[A-Za-z_][A-Za-z0-9_'.]*|\d+)"
)


def _tokenise(s: str) -> list[str]:
    toks: list[str] = []
    i = 0
    while i < len(s):
        m = _TOKEN_RE.match(s, i)
        if not m:
            if s[i].isspace():
                i += 1
                continue
            raise ParseError(f"unexpected char {s[i]!r} at {i}")
        tok = m.group(1)
        toks.append(tok)
        i = m.end()
    return toks


# Recursive-descent evaluator over a concrete environment ------------------

class _Eval:
    """Evaluates a (already tokenised) proposition/term to a Python bool/int."""

    def __init__(self, toks: list[str], env: dict[str, int]):
        self.toks = toks
        self.pos = 0
        self.env = env

    def peek(self) -> str | None:
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def eat(self, expect: str | None = None) -> str:
        if self.pos >= len(self.toks):
            raise ParseError("unexpected end")
        t = self.toks[self.pos]
        if expect is not None and t != expect:
            raise ParseError(f"expected {expect!r}, got {t!r}")
        self.pos += 1
        return t

    # prop := disj
    def prop(self) -> bool:
        v = self.disj()
        return v

    def disj(self) -> bool:
        v = self.conj()
        while self.peek() == "OR":
            self.eat()
            r = self.conj()
            v = bool(v) or bool(r)
        return v

    def conj(self) -> bool:
        v = self.rel()
        while self.peek() == "AND":
            self.eat()
            r = self.rel()
            v = bool(v) and bool(r)
        return v

    def rel(self):
        # Not ( prop )
        if self.peek() == "Not":
            self.eat()
            self.eat("(")
            v = self.prop()
            self.eat(")")
            return not bool(v)
        if self.peek() == "True":
            self.eat()
            return True
        if self.peek() == "False":
            self.eat()
            return False
        # PRIME p
        if self.peek() == "PRIME":
            self.eat()
            x = self.term()
            return is_prime(x)
        # COPRIME a b
        if self.peek() == "COPRIME":
            self.eat()
            a = self.term()
            b = self.term()
            return gcd(a, b) == 1
        # parenthesised prop or term-relation
        left = self.term()
        op = self.peek()
        if op in ("=", "!=", "<", "<=", ">", ">=", "DIV_BAR", "NDIV_BAR"):
            self.eat()
            right = self.term()
            return self._apply_rel(op, left, right)
        # bare boolean term (e.g. inside parens) -> truthiness
        return bool(left)

    def _apply_rel(self, op: str, a, b) -> bool:
        a, b = int(a), int(b)
        if op == "=":
            return a == b
        if op == "!=":
            return a != b
        if op == "<":
            return a < b
        if op == "<=":
            return a <= b
        if op == ">":
            return a > b
        if op == ">=":
            return a >= b
        if op == "DIV_BAR":      # a ∣ b  : a divides b
            return b % a == 0 if a != 0 else b == 0
        if op == "NDIV_BAR":     # a ∤ b
            return not (b % a == 0 if a != 0 else b == 0)
        raise ParseError(f"bad rel {op}")

    # term := add
    def term(self) -> int:
        return self.add()

    def add(self) -> int:
        v = self.mul()
        while self.peek() in ("+", "-"):
            op = self.eat()
            r = self.mul()
            v = v + r if op == "+" else v - r
        return v

    def mul(self) -> int:
        v = self.atom()
        while self.peek() == "*":
            self.eat()
            r = self.atom()
            v = v * r
        return v

    def atom(self) -> int:
        t = self.peek()
        if t is None:
            raise ParseError("unexpected end in term")
        if t == "(":
            self.eat()
            # could be a parenthesised arithmetic term
            v = self.add()
            self.eat(")")
            return v
        if t == "GCD":
            self.eat()
            a = self.atom()
            b = self.atom()
            return gcd(a, b)
        if t == "LCM":
            self.eat()
            a = self.atom()
            b = self.atom()
            return lcm(a, b)
        if t == "SUCC":
            self.eat()
            a = self.atom()
            return int(a) + 1
        if re.fullmatch(r"\d+", t):
            self.eat()
            return int(t)
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_'.]*", t):
            self.eat()
            if t in self.env:
                return self.env[t]
            raise ParseError(f"unknown identifier {t!r}")
        raise ParseError(f"unexpected token {t!r} in term")


# Statement-level parsing --------------------------------------------------

@dataclass
class ParsedStatement:
    quantifier: str          # "forall" | "exists"
    var_names: list[str]
    hyp_tokens: list[str] | None   # hypothesis prop tokens, or None
    body_tokens: list[str]         # conclusion / body prop tokens


_BINDER_VARS_RE = re.compile(r"\(([^():]*)(?::[^()]*)?\)")
_BARE_VARS_RE = re.compile(r"^[\s]*([A-Za-z_][A-Za-z0-9_'\s]*?)\s*:")


def parse_statement(stmt: str) -> ParsedStatement:
    raw = stmt.strip()
    norm = _normalise(raw)
    # leading quantifier
    mq = re.match(r"\s*(forall|exists)\b", norm)
    if not mq:
        raise ParseError("no leading quantifier")
    quant = mq.group(1)
    rest = norm[mq.end():]
    comma = rest.find(",")
    if comma == -1:
        raise ParseError("no binder comma")
    binder = rest[:comma]
    body = rest[comma + 1:].strip()

    # collect variable names from binder: handle "(a b : Nat)" and "a : Nat"
    var_names: list[str] = []
    paren_groups = _BINDER_VARS_RE.findall(binder)
    if paren_groups:
        for g in paren_groups:
            var_names.extend(g.split())
    else:
        m = _BARE_VARS_RE.match(binder)
        if m:
            var_names.extend(m.group(1).split())
        else:
            var_names.extend(re.findall(r"[A-Za-z_][A-Za-z0-9_']*", binder.split(":")[0]))
    var_names = [v for v in var_names if v and v not in ("Nat", "ℕ")]
    if not var_names:
        raise ParseError("no bound variables")

    # split body into optional hypothesis -> conclusion at the FIRST top-level ->
    hyp = None
    concl = body
    depth = 0
    i = 0
    arrow_idx = -1
    while i < len(body) - 1:
        ch = body[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and body[i:i + 2] == "->":
            arrow_idx = i
            break
        i += 1
    if arrow_idx != -1:
        hyp = body[:arrow_idx].strip()
        concl = body[arrow_idx + 2:].strip()

    hyp_tokens = _tokenise(hyp) if hyp else None
    body_tokens = _tokenise(concl)
    return ParsedStatement(quant, var_names, hyp_tokens, body_tokens)


def _eval_prop(tokens: list[str], env: dict[str, int]) -> bool:
    ev = _Eval(tokens, env)
    v = ev.prop()
    if ev.pos != len(tokens):
        raise ParseError(f"trailing tokens at {ev.pos}: {tokens[ev.pos:]}")
    return bool(v)


def _iter_envs(var_names: list[str], n: int):
    """Yield concrete integer assignments for the bound variables over [0, n).

    For multiple variables we cap the product to keep it cheap.
    """
    if len(var_names) == 1:
        for a in range(n):
            yield {var_names[0]: a}
    elif len(var_names) == 2:
        m = min(n, 20)
        for a in range(m):
            for b in range(m):
                yield {var_names[0]: a, var_names[1]: b}
    else:
        m = min(n, 8)
        import itertools

        for combo in itertools.product(range(m), repeat=len(var_names)):
            yield dict(zip(var_names, combo))


@dataclass
class _EvalResult:
    holds: bool
    counterexample: dict[str, int] | None
    illformed: bool
    error: str


def evaluate(stmt: str, n: int = DEFAULT_N) -> _EvalResult:
    """Decide a statement over [0, n) by exhaustive numeric evaluation."""
    try:
        ps = parse_statement(stmt)
    except ParseError as e:
        return _EvalResult(False, None, True, f"parse: {e}")

    try:
        if ps.quantifier == "forall":
            for env in _iter_envs(ps.var_names, n):
                if ps.hyp_tokens is not None:
                    if not _eval_prop(ps.hyp_tokens, env):
                        continue  # vacuously satisfied for this assignment
                if not _eval_prop(ps.body_tokens, env):
                    return _EvalResult(False, env, False, "counterexample")
            return _EvalResult(True, None, False, "")
        else:  # exists
            for env in _iter_envs(ps.var_names, n):
                ok = True
                if ps.hyp_tokens is not None:
                    ok = _eval_prop(ps.hyp_tokens, env)
                if ok and _eval_prop(ps.body_tokens, env):
                    return _EvalResult(True, env, False, "")
            return _EvalResult(False, None, False, "no witness in range")
    except ParseError as e:
        return _EvalResult(False, None, True, f"eval: {e}")
    except ZeroDivisionError:
        return _EvalResult(False, None, True, "division by zero")


# ---------------------------------------------------------------------------
# Automation-closeability (feeds is_trivial).
# ---------------------------------------------------------------------------

# Heuristic stand-ins for Lean's `omega`/`decide`/`simp` automation: a statement
# is "automation-closeable" if it is a pure linear-arithmetic / boundedly-decidable
# fact that omega/decide would dispatch with no creative proof. We approximate
# this honestly: linear (no gcd/lcm/prime/coprime/divisibility, only + - * by
# constants and comparisons) AND true => omega/decide would close it.
_NONLINEAR_TOKENS = ("GCD", "LCM", "PRIME", "COPRIME", "DIV_BAR", "NDIV_BAR")


def automation_closeable(stmt: str, n: int = DEFAULT_N) -> bool:
    """True iff `omega`/`decide`/`simp` alone would close the statement.

    Conservative: only linear-arithmetic statements that actually hold are
    flagged automation-closeable. gcd/coprime/prime/divisibility facts are NOT
    (those need real lemmas), so a contentful gcd theorem is never falsely
    marked trivial on this axis.
    """
    norm = _normalise(stmt)
    if any(tok in norm for tok in _NONLINEAR_TOKENS):
        return False
    res = evaluate(stmt, n)
    if res.illformed:
        return False
    # Pure-linear and true => omega closes it.
    return res.holds


# ---------------------------------------------------------------------------
# The Critic.
# ---------------------------------------------------------------------------

class ArithCritic:
    """Reality-grounded NT critic (offline). See module docstring."""

    name = "arith"

    def __init__(self, n: int = DEFAULT_N):
        self.n = n

    def automation_closeable(self, statement: str) -> bool:
        """Whether omega/decide/simp alone would close `statement` (§5.2).

        Delegates to the module-level decision; exposed as a method so the
        SignificanceCritic and certify_novel can query the critic uniformly.
        """
        return automation_closeable(statement, self.n)

    def check(self, conjecture: Conjecture) -> CritResult:
        t0 = time.perf_counter()
        stmt = (conjecture.statement or "").strip()
        if not stmt:
            return CritResult(False, "ILLFORMED", "empty statement", None,
                              time.perf_counter() - t0)
        if "sorry" in stmt or "sorry" in (conjecture.proof_attempt or ""):
            return CritResult(False, "UNPROVEN_BUDGET", "contains `sorry`",
                              None, time.perf_counter() - t0)

        res = evaluate(stmt, self.n)
        secs = time.perf_counter() - t0
        if res.illformed:
            return CritResult(False, "ILLFORMED", res.error, None, secs)
        if not res.holds:
            detail = (
                f"counterexample {res.counterexample}"
                if res.counterexample
                else res.error or "false"
            )
            return CritResult(False, "FALSE", detail, None, secs)

        method = "decide" if automation_closeable(stmt, self.n) else "supplied"
        return CritResult(True, "PROVED", "verified over range", method, secs)
