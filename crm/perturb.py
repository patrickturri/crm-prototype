"""Perturbation operators for the hardness signal (§5.2).

The hardness signal is THE key signal (§5.2, §15): a contentful theorem is
surrounded by FALSE neighbours, a trivial/vacuous truth by TRUE ones. We
generate `P` syntactic/semantic perturbations of the load-bearing parts of a
statement, re-run the critic on each, and set::

    hardness = (# perturbations NOT provable) / P

This module implements the FOUR perturbation operator families from §5.2 as
careful, validated string transforms on Lean-4-flavoured statements:

  1. constant mutation     : numeric literals  k -> k±1,  0 <-> 1
  2. operator swap         : <= <-> < , + <-> - , | <-> != , /\\ <-> \\/ , = <-> !=
  3. quantifier/hypothesis : drop a hypothesis ; forall <-> exists ; negate a conjunct
  4. argument-order swap    : swap the two arguments of an asymmetric relation

Each operator yields a list of `Perturbation(text, op, note)` candidates. We
only emit perturbations that genuinely DIFFER from the original (so a no-op
mutation never inflates hardness), and we tag each with the operator family so
tests can assert per-family coverage.

These transforms operate on the surface string. The spec permits this ("AST if
you build a parser, else careful string transforms with validation"). We keep
the operators conservative and well-tested rather than clever.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Operator-family identifiers (used by tests for per-family coverage).
OP_CONSTANT = "constant_mutation"
OP_OPERATOR = "operator_swap"
OP_QUANTIFIER = "quantifier_hypothesis_edit"
OP_ARGORDER = "argument_order_swap"

OPERATOR_FAMILIES = (OP_CONSTANT, OP_OPERATOR, OP_QUANTIFIER, OP_ARGORDER)


@dataclass(frozen=True)
class Perturbation:
    """One perturbed neighbour of a statement."""

    text: str       # the perturbed statement
    op: str         # which operator family produced it (one of OPERATOR_FAMILIES)
    note: str       # human-readable description of the edit


# ---------------------------------------------------------------------------
# 1. constant mutation:  numeric literals k -> k±1, and 0 <-> 1
# ---------------------------------------------------------------------------

# Match standalone integer literals (not part of an identifier like `x2`).
_INT_RE = re.compile(r"(?<![A-Za-z0-9_])(\d+)(?![A-Za-z0-9_])")


def constant_mutations(stmt: str) -> list[Perturbation]:
    out: list[Perturbation] = []
    seen: set[str] = set()
    for m in _INT_RE.finditer(stmt):
        k = int(m.group(1))
        start, end = m.span(1)
        # k -> k+1, k -> k-1 (k>=1), and the 0<->1 swap.
        candidates: list[tuple[int, str]] = [(k + 1, f"{k}->{k + 1}")]
        if k >= 1:
            candidates.append((k - 1, f"{k}->{k - 1}"))
        if k == 0:
            candidates.append((1, "0<->1"))
        elif k == 1:
            candidates.append((0, "0<->1"))
        for newk, note in candidates:
            if newk == k:
                continue
            text = stmt[:start] + str(newk) + stmt[end:]
            if text != stmt and text not in seen:
                seen.add(text)
                out.append(Perturbation(text, OP_CONSTANT, f"constant {note}"))
    return out


# ---------------------------------------------------------------------------
# 2. operator swap:  <= <-> < , + <-> - , | <-> != , /\\ <-> \\/ , = <-> !=
# ---------------------------------------------------------------------------

# Ordered list of (regex, replacement, note). We use placeholders so a forward
# and backward swap don't ping-pong within a single rewrite.
_OPERATOR_SWAPS: list[tuple[str, str, str]] = [
    # multi-char relations first so `<=` isn't eaten by `<`
    (r"<=", "<", "<= -> <"),
    (r">=", ">", ">= -> >"),
    (r"!=", "=", "!= -> ="),
    # logical connectives (Lean unicode and ascii)
    (r"∧", "∨", "/\\ -> \\/"),
    (r"∨", "∧", "\\/ -> /\\"),
    (r"/\\", "\\/", "/\\ -> \\/"),
    (r"\\/", "/\\", "\\/ -> /\\"),
    # divisibility <-> inequality
    (r"∣", "≠", "| -> !="),
    # single-char relations / ops
    (r"(?<![<>=!])=(?![=])", "≠", "= -> !="),
    (r"≠", "=", "!= -> ="),
    (r"(?<![<>=!])<(?![=])", "≤", "< -> <="),
    (r"(?<![<>=!])>(?![=])", "≥", "> -> >="),
    (r"≤", "<", "<= -> <"),
    (r"≥", ">", ">= -> >"),
    (r"\+", "-", "+ -> -"),
    (r"(?<![A-Za-z0-9_])\*(?![A-Za-z0-9_])", "+", "* -> +"),
]


def operator_swaps(stmt: str) -> list[Perturbation]:
    out: list[Perturbation] = []
    seen: set[str] = set()
    for pat, repl, note in _OPERATOR_SWAPS:
        rx = re.compile(pat)
        # Swap each occurrence independently (one at a time) to maximise the
        # number of distinct, load-bearing neighbours.
        matches = list(rx.finditer(stmt))
        for m in matches:
            text = stmt[: m.start()] + repl + stmt[m.end():]
            if text != stmt and text not in seen:
                seen.add(text)
                out.append(Perturbation(text, OP_OPERATOR, f"operator {note}"))
    return out


# ---------------------------------------------------------------------------
# 3. quantifier / hypothesis edit: drop a hypothesis ; forall <-> exists ;
#    negate a conjunct
# ---------------------------------------------------------------------------

_FORALL_RE = re.compile(r"(forall|∀)")
_EXISTS_RE = re.compile(r"(exists|∃)")
# A hypothesis is the left of an implication arrow `->` / `→`.
_IMPL_RE = re.compile(r"\s*(->|→)\s*")


def quantifier_hypothesis_edits(stmt: str) -> list[Perturbation]:
    out: list[Perturbation] = []
    seen: set[str] = set()

    def _add(text: str, note: str) -> None:
        if text and text != stmt and text not in seen:
            seen.add(text)
            out.append(Perturbation(text, OP_QUANTIFIER, note))

    # (a) forall <-> exists on the leading quantifier.
    m = _FORALL_RE.search(stmt)
    if m:
        repl = "exists" if m.group(1) == "forall" else "∃"
        _add(stmt[: m.start()] + repl + stmt[m.end():], "forall -> exists")
    m = _EXISTS_RE.search(stmt)
    if m:
        repl = "forall" if m.group(1) == "exists" else "∀"
        _add(stmt[: m.start()] + repl + stmt[m.end():], "exists -> forall")

    # (b) drop a hypothesis: if there's an implication, drop the left side of the
    # FIRST arrow (turning `H -> C` into `C`). We keep the binder prefix
    # (everything up to and including the first comma) so the result stays a
    # well-formed quantified statement.
    impl = _IMPL_RE.search(stmt)
    if impl:
        prefix_end = stmt.find(",")
        body_start = prefix_end + 1 if prefix_end != -1 else 0
        prefix = stmt[:body_start]
        body = stmt[body_start:]
        bimpl = _IMPL_RE.search(body)
        if bimpl:
            conclusion = body[bimpl.end():]
            _add((prefix + " " + conclusion).strip(), "drop hypothesis")

    # (c) negate a conjunct / the conclusion: wrap the conclusion in `Not ( ... )`.
    # Find the conclusion (text after the last arrow, else the whole body after
    # the binder comma).
    comma = stmt.find(",")
    body = stmt[comma + 1:] if comma != -1 else stmt
    last_arrow = max(body.rfind("->"), body.rfind("→"))
    if last_arrow != -1:
        head = body[: last_arrow + 2]
        concl = body[last_arrow + 2:].strip()
    else:
        head = ""
        concl = body.strip()
    if concl:
        prefix = stmt[: comma + 1] if comma != -1 else ""
        negated = f"{prefix} {head} Not ({concl})".strip()
        _add(re.sub(r"\s+", " ", negated), "negate conclusion")

    return out


# ---------------------------------------------------------------------------
# 4. argument-order swap on asymmetric relations
# ---------------------------------------------------------------------------

# Function-call form:  Name a b   (e.g. Nat.gcd n (n+1))  -- swap a<->b for
# relations/functions that are NOT symmetric in general usage here. We also
# handle infix asymmetric relations (<=, <, |, % ...).
_ASYM_PREFIX = re.compile(
    r"(Nat\.gcd|Nat\.lcm|Nat\.sub|Nat\.div|Nat\.mod|Nat\.pow)\s+"
    r"(\([^()]*\)|[A-Za-z0-9_]+)\s+"
    r"(\([^()]*\)|[A-Za-z0-9_]+)"
)

_ASYM_INFIX = re.compile(
    r"(\([^()]*\)|[A-Za-z0-9_]+)\s*(<=|<|>=|>|∣|%|∤|≤|≥)\s*(\([^()]*\)|[A-Za-z0-9_]+)"
)


def argument_order_swaps(stmt: str) -> list[Perturbation]:
    out: list[Perturbation] = []
    seen: set[str] = set()

    for m in _ASYM_PREFIX.finditer(stmt):
        fn, a, b = m.group(1), m.group(2), m.group(3)
        if a == b:
            continue
        swapped = f"{fn} {b} {a}"
        text = stmt[: m.start()] + swapped + stmt[m.end():]
        if text != stmt and text not in seen:
            seen.add(text)
            out.append(
                Perturbation(text, OP_ARGORDER, f"argswap {fn} {a}<->{b}")
            )

    for m in _ASYM_INFIX.finditer(stmt):
        a, rel, b = m.group(1), m.group(2), m.group(3)
        if a == b:
            continue
        swapped = f"{a} {rel} {b}"  # placeholder; actually swap operands:
        swapped = f"{b} {rel} {a}"
        text = stmt[: m.start()] + swapped + stmt[m.end():]
        if text != stmt and text not in seen:
            seen.add(text)
            out.append(
                Perturbation(text, OP_ARGORDER, f"argswap {a} {rel} {b}")
            )

    return out


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

_ALL_OPS = (
    constant_mutations,
    operator_swaps,
    quantifier_hypothesis_edits,
    argument_order_swaps,
)


def all_perturbations(stmt: str) -> list[Perturbation]:
    """All distinct perturbations across the four families, de-duplicated."""
    out: list[Perturbation] = []
    seen: set[str] = set()
    for fn in _ALL_OPS:
        for p in fn(stmt):
            if p.text not in seen:
                seen.add(p.text)
                out.append(p)
    return out


def generate_perturbations(stmt: str, p: int, seed: int = 0) -> list[Perturbation]:
    """Return up to `p` perturbations, sampling deterministically across the
    four families so hardness is computed over a balanced, reproducible set.

    We round-robin across families first (guaranteeing family diversity when
    available) then fill from the remainder, in a stable order seeded by `seed`.
    """
    import random

    by_family: dict[str, list[Perturbation]] = {f: [] for f in OPERATOR_FAMILIES}
    for pert in all_perturbations(stmt):
        by_family[pert.op].append(pert)

    rng = random.Random(seed)
    for fam in by_family:
        rng.shuffle(by_family[fam])

    chosen: list[Perturbation] = []
    seen: set[str] = set()
    # Round-robin to guarantee family diversity.
    while len(chosen) < p and any(by_family[f] for f in OPERATOR_FAMILIES):
        for fam in OPERATOR_FAMILIES:
            if by_family[fam] and len(chosen) < p:
                cand = by_family[fam].pop()
                if cand.text not in seen:
                    seen.add(cand.text)
                    chosen.append(cand)
    return chosen[:p]
