"""Tests for the genealogy ledger + conditioning context (§5.1).

Verifies the load-bearing property: treatment ("genealogy") carries WHY
(reasons, significance, build-on guidance); control lists prior STATEMENTS only
(equal dedup, no reasoned genealogy). This isolates the reasoned-genealogy value
from mere deduplication.
"""

from __future__ import annotations

import pytest

from crm.critics.base import CritResult
from crm.genealogy import (
    Entry,
    Ledger,
    build_conditioning_context,
)
from crm.significance import Significance


def _entry(cid, stmt, valid, reason, detail, surviving, sig=None):
    return Entry(
        id=cid,
        round=0,
        parent_ids=[],
        statement=stmt,
        nl_gloss="",
        proof_attempt="",
        crit=CritResult(valid, reason, detail, "supplied", 0.0),
        significance=sig,
        surviving=surviving,
    )


@pytest.fixture
def ledger():
    lg = Ledger()
    # a refuted-false conjecture (carries a counterexample reason)
    lg.add(_entry(
        "c0", "forall (n : Nat), Nat.gcd n (n + 2) = 1",
        False, "FALSE", "counterexample {'n': 0}", False,
    ))
    # a valid-but-trivial conjecture (carries hardness in its WHY)
    lg.add(_entry(
        "c1", "forall (n : Nat), n <= n + 1",
        True, "PROVED", "verified over range", False,
        sig=Significance(0.3, 0.0, 0.05, True, 0.0),
    ))
    # a surviving high-content conjecture
    lg.add(_entry(
        "c2", "forall (n : Nat), Nat.gcd n (n + 1) = 1",
        True, "PROVED", "verified over range", True,
        sig=Significance(0.74, 0.40, 0.86, False, 0.71),
    ))
    return lg


def test_treatment_carries_why_and_significance(ledger):
    treat = build_conditioning_context(ledger, "gcd", 4, mode="genealogy")
    # reasons present
    assert "WHY they failed" in treat
    assert "counterexample" in treat                 # refutation reason
    assert "trivial" in treat                         # triviality reason
    assert "hardness" in treat                        # the hardness number
    # build-on guidance + content score for survivors
    assert "generalise or build on" in treat
    assert "content score 0.71" in treat
    assert "hard-to-vary" in treat


def test_control_lists_statements_only(ledger):
    ctrl = build_conditioning_context(ledger, "gcd", 4, mode="control")
    # all prior STATEMENTS listed (so dedup is matched across conditions)
    assert "Nat.gcd n (n + 2)" in ctrl
    assert "n <= n + 1" in ctrl
    assert "Nat.gcd n (n + 1)" in ctrl
    # but NO reasons / significance / build-on guidance
    assert "counterexample" not in ctrl
    assert "WHY they failed" not in ctrl
    assert "content score" not in ctrl
    assert "build on" not in ctrl
    assert "hard-to-vary" not in ctrl


def test_dedup_parity_statements_in_both(ledger):
    """Both conditions list every prior statement -> dedup is equal (§5.1)."""
    treat = build_conditioning_context(ledger, "gcd", 4, mode="genealogy")
    ctrl = build_conditioning_context(ledger, "gcd", 4, mode="control")
    for stmt in [
        "forall (n : Nat), Nat.gcd n (n + 2) = 1",
        "forall (n : Nat), n <= n + 1",
        "forall (n : Nat), Nat.gcd n (n + 1) = 1",
    ]:
        assert stmt in treat
        assert stmt in ctrl


def test_orthogonal_mode_inverts_build_on(ledger):
    """genealogy_orthogonal keeps the WHY-failed block but inverts the survivor
    directive: avoid the survivors' neighbourhood instead of building on them."""
    orth = build_conditioning_context(ledger, "gcd", 4, mode="genealogy_orthogonal")
    # same failure-reason block as genealogy
    assert "WHY they failed" in orth
    assert "counterexample" in orth
    # survivors STILL listed (dedup parity) with their content score
    assert "Nat.gcd n (n + 1)" in orth
    assert "content score 0.71" in orth
    # but the directive is the INVERSE of build-on
    assert "build on" not in orth or "do not generalise or build on" in orth
    assert "DISSIMILAR" in orth or "dissimilar" in orth.lower()
    assert "generalise or build on these:" not in orth
    assert "hard-to-vary" in orth


def test_unknown_mode_raises(ledger):
    with pytest.raises(ValueError):
        build_conditioning_context(ledger, "gcd", 4, mode="bogus")
