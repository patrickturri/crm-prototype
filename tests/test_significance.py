"""Tests for the significance / hard-to-vary critic (§5.2).

Includes the two WORKED-EXAMPLE fixtures from §5.2:
  - contentful  "∀ n, Nat.gcd n (n+1) = 1"  -> high hardness, NOT trivial, score>0
  - trivial     "∀ n, n ≤ n+1"               -> is_trivial, score == 0

The critic used is the real, offline ArithCritic so hardness is computed by
genuinely re-running the critic on perturbations (not mocked).
"""

from __future__ import annotations

import pytest

from crm.critics.arith import ArithCritic, automation_closeable
from crm.embedding import get_embedder
from crm.novelty import (
    certify_novel,
    dedup_survivors,
    is_survivor_duplicate,
)
from crm.significance import SignificanceCritic
from crm.types import Conjecture

CONTENTFUL = "forall (n : Nat), Nat.gcd n (n + 1) = 1"
TRIVIAL = "forall (n : Nat), n <= n + 1"

# small corpus so novelty is computed against something real
CORPUS = [
    "forall (n : Nat), Nat.gcd n n = n",
    "forall (a b : Nat), a + b = b + a",
    "forall (p : Nat), Nat.Prime p -> 2 <= p",
]


@pytest.fixture
def critic():
    return ArithCritic()


@pytest.fixture
def sig():
    return SignificanceCritic(
        embedder="hash",          # offline deterministic embedder
        perturbations=8,
        tau=0.25,
        corpus_statements=CORPUS,
    )


def test_contentful_example_passes(sig, critic):
    """§5.2 worked example: contentful theorem is high-hardness, not trivial."""
    s = sig.score(Conjecture(id="c", statement=CONTENTFUL), critic)
    assert s.hardness >= 0.5, f"expected high hardness, got {s.hardness}"
    assert not s.is_trivial
    assert s.score > 0.0


def test_trivial_example_suppressed(sig, critic):
    """§5.2 worked example: trivial truth is suppressed (is_trivial, score 0)."""
    s = sig.score(Conjecture(id="t", statement=TRIVIAL), critic)
    assert s.is_trivial
    assert s.score == 0.0


def test_trivial_is_automation_closeable(critic):
    """n <= n+1 is closed by omega/decide alone -> automation-closeable."""
    assert automation_closeable(TRIVIAL) is True
    # gcd theorem is NOT closed by linear automation alone
    assert automation_closeable(CONTENTFUL) is False


def test_hardness_uses_real_perturbations(sig, critic):
    """hardness re-runs the SAME critic on perturbations (not mocked)."""
    h, results = sig.hardness(CONTENTFUL, critic)
    assert results, "expected some perturbations"
    # at least the false neighbour gcd n (n+2)=1 must appear and BREAK
    broke = {t for t, prov in results if not prov}
    assert any("n + 2" in t for t in broke)
    assert 0.0 <= h <= 1.0


def test_score_forced_zero_when_trivial(sig, critic):
    """score is forced to 0 whenever is_trivial (§5.2)."""
    s = sig.score(Conjecture(id="t", statement=TRIVIAL), critic)
    assert s.is_trivial and s.score == 0.0


def test_hardness_below_tau_marks_trivial(critic):
    """Even a non-automation statement is trivial if hardness < tau."""
    # Force a high tau so the contentful example is below threshold.
    sig = SignificanceCritic(
        embedder="hash", perturbations=8, tau=0.99, corpus_statements=CORPUS
    )
    s = sig.score(Conjecture(id="c", statement=CONTENTFUL), critic)
    assert s.is_trivial
    assert s.score == 0.0


def test_novelty_in_range(sig, critic):
    s = sig.score(Conjecture(id="c", statement=CONTENTFUL), critic)
    assert 0.0 <= s.novelty <= 1.0


def test_certify_novel_rejects_corpus_restatement(sig, critic):
    """A corpus restatement is never certified novel (§5.3 clause 1)."""
    restated = CORPUS[0]
    s = sig.score(Conjecture(id="r", statement=restated), critic)
    assert not certify_novel(restated, s, CORPUS, critic=critic)


def test_certify_novel_rejects_automation_closeable(critic):
    """A trivial/automation-closeable statement is not certified (§5.3 clause 2)."""
    sig = SignificanceCritic(embedder="hash", perturbations=8, corpus_statements=CORPUS)
    s = sig.score(Conjecture(id="t", statement=TRIVIAL), critic)
    assert not certify_novel(TRIVIAL, s, CORPUS, critic=critic)


# --- intra-survivor dedup (§5.3 clause 4, review finding #7) ----------------

# A dedicated corpus with NO gcd/lcm statement nearby, so the gcd survivor and
# the lcm survivor both clear the delta=0.35 novelty gate under the (weak) hash
# embedder. CONTENTFUL is the corpus-distant, non-trivial survivor; CONTENTFUL_DUP
# is a whitespace rewording of it (distance 0 -> within delta); DISTINCT is far
# from BOTH this corpus and CONTENTFUL.
DEDUP_CORPUS = ["forall (a b : Nat), a + b = b + a"]
CONTENTFUL_DUP = "forall (n : Nat),  Nat.gcd  n  (n + 1)  =  1"
DISTINCT = "forall (m : Nat), Nat.lcm m (m + 13) = m * (m + 13)"


@pytest.fixture
def dedup_sig():
    return SignificanceCritic(
        embedder="hash",
        perturbations=8,
        tau=0.25,
        corpus_statements=DEDUP_CORPUS,
    )


def test_certify_novel_passes_without_accepted_survivors(dedup_sig, critic):
    """Baseline: a corpus-distant, non-trivial statement certifies on its own."""
    s = dedup_sig.score(Conjecture(id="a", statement=CONTENTFUL), critic)
    assert certify_novel(CONTENTFUL, s, DEDUP_CORPUS, critic=critic)


def test_certify_novel_rejects_intra_run_duplicate(dedup_sig, critic):
    """A near-duplicate of an ALREADY-accepted survivor is not certified again."""
    # Without the accepted set, the (corpus-distant) duplicate WOULD certify...
    s = dedup_sig.score(Conjecture(id="dup", statement=CONTENTFUL_DUP), critic)
    assert certify_novel(CONTENTFUL_DUP, s, DEDUP_CORPUS, critic=critic)
    # ...but once CONTENTFUL is an accepted survivor, the dup is blocked (#7).
    assert not certify_novel(
        CONTENTFUL_DUP, s, DEDUP_CORPUS, critic=critic,
        accepted_survivors=[CONTENTFUL],
    )


def test_certify_novel_distinct_survivor_still_certifies(dedup_sig, critic):
    """A genuinely different survivor is NOT blocked by the accepted set."""
    s = dedup_sig.score(Conjecture(id="d", statement=DISTINCT), critic)
    assert certify_novel(
        DISTINCT, s, DEDUP_CORPUS, critic=critic, accepted_survivors=[CONTENTFUL]
    )


def test_is_survivor_duplicate_pure():
    """Pure distance check: identical/near-identical -> dup; distinct -> not."""
    emb = get_embedder("hash")
    assert is_survivor_duplicate(
        CONTENTFUL_DUP, [CONTENTFUL], embedder=emb, delta=0.35
    )
    assert not is_survivor_duplicate(
        DISTINCT, [CONTENTFUL], embedder=emb, delta=0.35
    )
    # empty / self-only accepted set is never a duplicate
    assert not is_survivor_duplicate(CONTENTFUL, [], embedder=emb, delta=0.35)
    assert not is_survivor_duplicate(
        CONTENTFUL, [CONTENTFUL], embedder=emb, delta=0.35
    )


def test_dedup_survivors_collapses_near_duplicates():
    """PURE measurement on an existing list: raw count vs deduped count."""
    emb = get_embedder("hash")
    raw = [CONTENTFUL, CONTENTFUL_DUP, DISTINCT]
    deduped, groups = dedup_survivors(raw, embedder=emb, delta=0.35)
    # CONTENTFUL and its dup collapse into one group; DISTINCT stands alone.
    assert deduped == [CONTENTFUL, DISTINCT]
    assert groups[0] == [CONTENTFUL, CONTENTFUL_DUP]
    assert groups[1] == [DISTINCT]
    # every input is accounted for in exactly one group
    assert sum(len(g) for g in groups) == len(raw)


def test_dedup_survivors_order_preserving_no_duplicates():
    """All-distinct input is returned unchanged, order preserved."""
    emb = get_embedder("hash")
    raw = [CONTENTFUL, DISTINCT, DEDUP_CORPUS[0]]
    deduped, groups = dedup_survivors(raw, embedder=emb, delta=0.35)
    assert deduped == raw
    assert all(len(g) == 1 for g in groups)
