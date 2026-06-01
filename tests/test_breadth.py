"""Breadth = real downstream enablement for the code-exec critic (§5.2).

A survivor whose verified function IS a reusable primitive (e.g. Euler totient,
divisor count) should ENABLE the matching held-out downstream task; a one-off
property-checker should enable nothing. Nothing here is fabricated — every
enablement decision is a sandboxed re-execution.
"""

from __future__ import annotations

import json
from pathlib import Path

from crm.critics.code_exec import CodeExecCritic
from crm.significance import SignificanceCritic
from crm.types import Conjecture

TARGETS = [
    json.loads(line)
    for line in (
        Path(__file__).resolve().parents[1] / "data" / "code_breadth_targets.jsonl"
    ).read_text().splitlines()
    if line.strip()
]


def _conj(impl: str) -> Conjecture:
    return Conjecture(
        id="c_test",
        statement="test lemma",
        nl_gloss="",
        extra={
            "reference_impl": impl,
            "tests": "assert True",
            "property": "lambda n: True",
            "domain": "[1, 50]",
        },
    )


def test_enables_matching_primitive():
    """A real Euler-totient implementation enables the totient_sum target."""
    critic = CodeExecCritic(timeout_s=5.0)
    totient = (
        "def phi(n):\n"
        "    import math\n"
        "    return sum(1 for i in range(1, n + 1) if math.gcd(i, n) == 1)\n"
    )
    tgt = next(t for t in TARGETS if t["name"] == "totient_sum")
    assert critic.enables(_conj(totient), tgt) is True
    # ...and it does NOT enable an unrelated target (divisor *sum*).
    other = next(t for t in TARGETS if t["name"] == "divisor_sum_sum")
    assert critic.enables(_conj(totient), other) is False


def test_property_checker_enables_nothing():
    """A boolean one-off checker supplies no reusable building block."""
    critic = CodeExecCritic(timeout_s=5.0)
    checker = "def f(n):\n    return n == n\n"  # vacuous predicate
    assert all(not critic.enables(_conj(checker), t) for t in TARGETS)


def test_breadth_is_nonzero_and_fractional():
    """breadth() over the held-out targets is a real fraction in (0, 1]."""
    critic = CodeExecCritic(timeout_s=5.0)
    sig = SignificanceCritic(breadth_target_specs=TARGETS, breadth_targets=len(TARGETS))
    dcount = "def d(n):\n    return sum(1 for k in range(1, n + 1) if n % k == 0)\n"
    b = sig.breadth(_conj(dcount), critic)
    assert 0.0 < b <= 1.0
    # divisor-count enables exactly the divisor_count_sum task among these 8.
    assert abs(b - 1.0 / len(TARGETS)) < 1e-9
