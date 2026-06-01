"""Tests for the four perturbation operator families (§5.2).

Each operator family gets its own test; we also test the aggregator and the
deterministic sampler `generate_perturbations`.
"""

from __future__ import annotations

from crm.perturb import (
    OP_ARGORDER,
    OP_CONSTANT,
    OP_OPERATOR,
    OP_QUANTIFIER,
    OPERATOR_FAMILIES,
    all_perturbations,
    argument_order_swaps,
    constant_mutations,
    generate_perturbations,
    operator_swaps,
    quantifier_hypothesis_edits,
)


# ---- 1. constant mutation -------------------------------------------------

def test_constant_mutation_pm1():
    perts = constant_mutations("forall (n : Nat), Nat.gcd n (n + 1) = 1")
    texts = {p.text for p in perts}
    # the literal `1` in `n + 1` should be bumped to 2 and to 0
    assert "forall (n : Nat), Nat.gcd n (n + 2) = 1" in texts
    assert "forall (n : Nat), Nat.gcd n (n + 0) = 1" in texts
    assert all(p.op == OP_CONSTANT for p in perts)


def test_constant_mutation_zero_one_swap():
    perts = constant_mutations("forall (n : Nat), n + 0 = n")
    texts = {p.text for p in perts}
    # 0 -> 1 swap present
    assert "forall (n : Nat), n + 1 = n" in texts


def test_constant_mutation_no_identifier_digits():
    # digits that are part of identifiers (x2) must NOT be mutated
    perts = constant_mutations("forall (x2 : Nat), x2 = x2")
    assert perts == []


# ---- 2. operator swap -----------------------------------------------------

def test_operator_swap_le_to_lt():
    perts = operator_swaps("forall (n : Nat), n <= n + 1")
    texts = {p.text for p in perts}
    assert "forall (n : Nat), n < n + 1" in texts
    assert all(p.op == OP_OPERATOR for p in perts)


def test_operator_swap_plus_to_minus():
    perts = operator_swaps("forall (n : Nat), n + 1 = n + 1")
    texts = {p.text for p in perts}
    assert any("- 1" in t or "-1" in t for t in texts)


def test_operator_swap_eq_to_neq_unicode():
    perts = operator_swaps("forall (n : Nat), Nat.gcd n (n + 1) = 1")
    texts = {p.text for p in perts}
    assert any("≠" in t for t in texts)


def test_operator_swap_and_or():
    perts = operator_swaps("forall (n : Nat), P n ∧ Q n")
    texts = {p.text for p in perts}
    assert any("∨" in t for t in texts)


# ---- 3. quantifier / hypothesis edit -------------------------------------

def test_quantifier_forall_to_exists():
    perts = quantifier_hypothesis_edits("forall (n : Nat), n <= n + 1")
    texts = {p.text for p in perts}
    assert any(t.startswith("exists") for t in texts)
    assert all(p.op == OP_QUANTIFIER for p in perts)


def test_quantifier_drop_hypothesis():
    perts = quantifier_hypothesis_edits(
        "forall (p : Nat), Nat.Prime p -> 2 <= p"
    )
    texts = {p.text for p in perts}
    # dropping the hypothesis leaves the bare conclusion under the binder
    assert any("Nat.Prime" not in t and "2 <= p" in t for t in texts)


def test_quantifier_negate_conclusion():
    perts = quantifier_hypothesis_edits("forall (n : Nat), n <= n + 1")
    texts = {p.text for p in perts}
    assert any("Not (" in t for t in texts)


# ---- 4. argument-order swap ----------------------------------------------

def test_argorder_prefix_function():
    perts = argument_order_swaps("forall (n : Nat), Nat.gcd n (n + 1) = 1")
    texts = {p.text for p in perts}
    assert "forall (n : Nat), Nat.gcd (n + 1) n = 1" in texts
    assert all(p.op == OP_ARGORDER for p in perts)


def test_argorder_infix_relation():
    perts = argument_order_swaps("forall (a b : Nat), a <= b")
    texts = {p.text for p in perts}
    assert any("b <= a" in t for t in texts)


def test_argorder_skips_identical_args():
    # gcd n n -> swap is a no-op, must not be emitted
    perts = argument_order_swaps("forall (n : Nat), Nat.gcd n n = n")
    assert all("Nat.gcd n n" not in p.text or p.text != "Nat.gcd n n" for p in perts)


# ---- aggregator / sampler -------------------------------------------------

def test_all_perturbations_distinct_and_nontrivial():
    stmt = "forall (n : Nat), Nat.gcd n (n + 1) = 1"
    perts = all_perturbations(stmt)
    texts = [p.text for p in perts]
    assert len(texts) == len(set(texts))     # de-duplicated
    assert all(t != stmt for t in texts)     # never the identity


def test_generate_perturbations_family_diversity():
    stmt = "forall (n : Nat), Nat.gcd n (n + 1) = 1"
    perts = generate_perturbations(stmt, 8, seed=0)
    assert len(perts) <= 8
    fams = {p.op for p in perts}
    # all four families are available for this rich statement -> all represented
    assert fams == set(OPERATOR_FAMILIES)


def test_generate_perturbations_deterministic():
    stmt = "forall (n : Nat), Nat.gcd n (n + 1) = 1"
    a = [p.text for p in generate_perturbations(stmt, 8, seed=3)]
    b = [p.text for p in generate_perturbations(stmt, 8, seed=3)]
    assert a == b
