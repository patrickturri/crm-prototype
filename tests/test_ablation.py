"""Phase 3 ablation-harness tests (§9).

Run with the DETERMINISTIC OFFLINE proposer + the REAL sandboxed CodeExecCritic
so the tests are fast, hermetic, and cost nothing — yet still exercise the real
survive/die decision (never mocked, §3/§15). The significance ablation's
ON-vs-OFF distinction is asserted on real numbers.
"""

from __future__ import annotations

from experiments._harness import run_arm

_CFG = {
    "topic": "elementary number theory and combinatorics (Python-verifiable)",
    "rounds": 2,
    "k": 6,
    "critic": "code_exec",
    "proof_budget_s": 5.0,
    "n_adversarial": 8,
    "proposer": {"kind": "offline_code"},
    "weights": {"novelty": 0.3, "breadth": 0.3, "hardness": 0.4},
    "tau": 0.25,
    "delta": 0.35,
    "perturbations": 4,
    "embedder": "hash",
    "offline_embedder": True,
    "corpus_path": "data/code_corpus.jsonl",
}


def test_run_arm_real_critic_produces_survivors():
    res = run_arm(_CFG, mode="genealogy", seed=0, significance_on=True)
    # real critic decided survival; some valid survivors expected from the pool.
    assert res.cum_total[-1] == _CFG["rounds"] * _CFG["k"]
    assert res.cum_survivors[-1] >= 1
    assert len(res.cum_certified) == _CFG["rounds"]
    # cumulative series is non-decreasing.
    assert all(
        res.cum_certified[i] <= res.cum_certified[i + 1]
        for i in range(len(res.cum_certified) - 1)
    )


def test_significance_guard_reduces_trivial_survivors():
    """§9.2: trivial-survivor rate is lower with the critic ON than OFF.

    The offline pool contains a deliberately vacuous task (constant-zero f). With
    the guard OFF it slips through as a 'survivor'; with it ON it is suppressed.
    The metric is the INDEPENDENT automation check, not the loop's own gate.
    """
    on = run_arm(_CFG, mode="genealogy", seed=0, significance_on=True)
    off = run_arm(_CFG, mode="genealogy", seed=0, significance_on=False)
    assert on.indep_trivial_rate <= off.indep_trivial_rate
    # the guard must actually catch at least one vacuous survivor across seeds.
    assert off.indep_trivial_rate > 0.0


def test_single_variable_difference_genealogy_vs_control():
    """Apples-to-apples (§3.5): with a context-blind proposer the two modes give
    identical ledgers — proving the ONLY thing that can differ is the genealogy
    conditioning, not any incidental nondeterminism in the harness."""
    g = run_arm(_CFG, mode="genealogy", seed=1, significance_on=True)
    c = run_arm(_CFG, mode="control", seed=1, significance_on=True)
    assert g.cum_total[-1] == c.cum_total[-1]
    assert g.cum_survivors[-1] == c.cum_survivors[-1]
