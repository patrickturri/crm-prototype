"""Tests for the hard-domain proposer (review finding #9).

Every numeric expectation here was confirmed by executing the canonical
recurrence — none is fabricated. The point of the domain is that the sequence is
FRESHLY DEFINED, so we pin the ground-truth terms and that the offline pool's
TRUE/FALSE/TRIVIAL labels actually hold under real sandbox-style evaluation.
"""

from __future__ import annotations

import re

from crm.critics.code_exec import CodeExecCritic
from crm.proposers_hard import (
    CANONICAL_G,
    HardDomainOfflineProposer,
    _POOL,
)


def _g():
    ns: dict = {}
    exec(CANONICAL_G, ns)
    return ns["g"]


def test_canonical_terms():
    g = _g()
    # Confirmed by running the recurrence g(n)=3g(n-1)-g(n-2)+(n%3), g0=2,g1=3.
    assert [g(i) for i in range(9)] == [2, 3, 9, 24, 64, 170, 446, 1169, 3063]


def _holds(prop_src: str, domain: str, g) -> bool:
    prop = eval(prop_src, {"g": g})
    nums = re.findall(r"-?\d+", domain)
    lo, hi = int(nums[0]), int(nums[1])
    return all(prop(n) for n in range(lo, hi + 1))


def test_pool_true_claims_hold():
    g = _g()
    true_glosses = ("TRUE", "discovered, TRUE", "TRUE)")
    for it in _POOL:
        gloss = it["nl_gloss"]
        if "FALSE" in gloss or "TRIVIAL" in gloss:
            continue
        assert _holds(it["property"], it["domain"], g), it["statement"]


def test_pool_false_claims_are_false():
    g = _g()
    for it in _POOL:
        if "FALSE" in it["nl_gloss"]:
            assert not _holds(it["property"], it["domain"], g), it["statement"]


def test_offline_proposer_emits_canonical_impl():
    p = HardDomainOfflineProposer()
    batch = p.propose("", k=4, seed=0)
    assert len(batch) == 4
    for c in batch:
        # reference_impl is ALWAYS the ground-truth recurrence (model cannot
        # author the impl); only the property is conjectured.
        assert c.extra["reference_impl"] == CANONICAL_G
        assert "property" in c.extra and c.extra["property"]


def test_critic_validates_true_and_refutes_false():
    """The real sandboxed critic accepts a TRUE pool claim and refutes a FALSE
    one — no LLM-as-judge, real execution against the true recurrence."""
    p = HardDomainOfflineProposer()
    crit = CodeExecCritic(timeout_s=5.0, n_adversarial=12, seed=0)
    # Pull a known TRUE and a known FALSE entry directly from the pool.
    true_item = next(it for it in _POOL if it["nl_gloss"].endswith("(TRUE)") or "discovered, TRUE" in it["nl_gloss"])
    false_item = next(it for it in _POOL if "FALSE" in it["nl_gloss"])

    true_c = p._make_conjecture(true_item)
    false_c = p._make_conjecture(false_item)
    assert crit.check(true_c).valid is True
    assert crit.check(false_c).valid is False
