"""Tests for the genuinely-independent triviality oracle (§9.2, review #5).

These assert that experiments._indep_oracle decides triviality by REAL sandbox
execution, catches the vacuous constant-zero task, passes the contentful tasks,
and — critically — does NOT reuse the significance gate's
`automation_closeable_conjecture` mechanism (auditable independence).
"""

from __future__ import annotations

import inspect

from crm.types import Conjecture
from experiments import _indep_oracle
from experiments._indep_oracle import (
    independent_trivial_rate,
    is_trivial_independent,
)


def _conj(statement, impl, tests, prop, domain, cid="c"):
    return Conjecture(
        id=cid,
        statement=statement,
        extra={
            "reference_impl": impl,
            "tests": tests,
            "property": prop,
            "domain": domain,
        },
    )


VACUOUS_ZERO = _conj(
    "f(n) = always 0 (vacuous constant)",
    "def f(n):\n    return 0",
    "assert f(5) == 0",
    "lambda n: f(n) == 0",
    "[0, 100]",
    cid="zero",
)

DIVISOR_COUNT = _conj(
    "f(n) = number of divisors of n",
    (
        "def f(n):\n"
        "    c = 0\n"
        "    d = 1\n"
        "    while d * d <= n:\n"
        "        if n % d == 0:\n"
        "            c += 1 if d * d == n else 2\n"
        "        d += 1\n"
        "    return c"
    ),
    "assert f(6) == 4",
    "lambda n: f(n) == sum(1 for d in range(1, n + 1) if n % d == 0)",
    "[1, 200]",
    cid="dcount",
)

TRIANGULAR = _conj(
    "f(n) = n-th triangular number",
    "def f(n):\n    return sum(range(n + 1))",
    "assert f(3) == 6",
    "lambda n: f(n) == n * (n + 1) // 2",
    "[0, 300]",
    cid="tri",
)


def test_catches_vacuous_constant_zero():
    assert is_trivial_independent(VACUOUS_ZERO) is True


def test_passes_contentful_divisor_count():
    assert is_trivial_independent(DIVISOR_COUNT) is False


def test_passes_contentful_triangular():
    assert is_trivial_independent(TRIANGULAR) is False


def test_no_property_is_undecidable_returns_false():
    c = _conj(
        "no property",
        "def f(n):\n    return n",
        "assert f(1) == 1",
        "",
        "[1, 100]",
    )
    assert is_trivial_independent(c) is False


def test_rate_aggregates_over_survivors():
    class _Sig:
        hardness = 0.9

    class _Entry:
        significance = _Sig()

    pairs = [
        (_Entry(), VACUOUS_ZERO),
        (_Entry(), DIVISOR_COUNT),
        (_Entry(), TRIANGULAR),
    ]
    rate = independent_trivial_rate(pairs)
    assert abs(rate - (1.0 / 3.0)) < 1e-9


def test_does_not_reference_the_significance_gate_mechanism():
    """Auditable independence: the oracle must not CALL the gate's
    `automation_closeable_conjecture` (review finding #5).

    We strip docstrings/comments (which legitimately NAME the gate to explain
    what the oracle avoids) and assert the executable code never invokes it.
    """
    import ast

    src = inspect.getsource(_indep_oracle)
    tree = ast.parse(src)
    # Collect every attribute access / name used in executable code.
    called_attrs = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }
    assert "automation_closeable" not in called_attrs
    assert "automation_closeable_conjecture" not in called_attrs
    # The oracle must not even import the gate method by name.
    assert "automation_closeable" not in {
        a.name for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node.names
        for a in node.names
    }
    # And it must differ from the gate's degenerate battery: the gate uses
    # the literal `return n` / `return 0` / `return 1` / `return True` stand-ins;
    # this oracle's battery uses n-1 / n+1 / n*n / a seeded constant instead.
    assert "return n - 1" in src
    assert "return n * n" in src
