# Finding: Significance Score Measures Hardness + Correctness Gate, Not Mathematical Depth

**Date:** 2026-06-01
**Sources:** `results/code-20260531-225343/ledger.jsonl`, `results/findings/hard_domain_n10/{genealogy,control,best_of_N}_seed[0-9]/ledger.jsonl`
**Data file:** `results/findings/significance_depth.json`

---

## Setup

558 conjecture records drawn from all committed ledgers (main code run + 30 hard-domain seeds). 183 have a significance score (these are the valid conjectures that reached the scoring stage). Of these:

| Category | n |
|---|---|
| Certified novel | 76 |
| Rejected valid (trivial by automation gate) | 74 |
| Rejected valid (low hardness gate) | 0 |
| Rejected valid (non-trivial, but failed dedup/corpus gate) | 33 |

---

## Signal Distributions

| Signal | Certified (n=76) | Rejected-valid-all (n=107) |
|---|---|---|
| novelty mean (std) | 0.545 (0.069) | 0.576 (0.089) |
| breadth mean (std) | 0.005 (0.024) | 0.000 (0.000) |
| hardness mean (std) | 0.865 (0.137) | 0.847 (0.149) |
| score mean (std) | 0.511 (0.057) | 0.153 (0.233) |

**Hardness at ceiling (1.0):** 35.5% of certified, 33.6% of all rejected-valid.
**Breadth = 0.0:** 96.1% of certified, 100% of rejected-valid.

---

## Can Score Separate Certified From Rejected?

### Certified vs ALL rejected-valid (Mann-Whitney U)

| Signal | U | p |
|---|---|---|
| novelty | 3421.5 | 0.068 |
| breadth | 4226.5 | 0.039 |
| hardness | 4336.5 | 0.424 |
| score | 6985.5 | 1.2e-17 |

Score has massive separation (p=1.2e-17), but this is **entirely explained by the trivial-automation gate**: 74/107 rejected conjectures were automation-closeable and received score=0 by construction. The discrimination is from the binary gate, not from graded signal quality.

### Certified vs NOT-TRIVIAL rejected (n=33, Mann-Whitney U)

These 33 are conjectures that were non-trivial and had significance computed, but were rejected by the **intra-run dedup gate** (embedding distance < 0.35 from an already-accepted survivor in the same run).

| Signal | U | p |
|---|---|---|
| novelty | 1408.5 | 0.310 |
| hardness | 1305.5 | 0.724 |
| score | 1361.5 | 0.480 |

**Score does NOT separate certified from non-trivial-rejected (p=0.480).** Novelty (0.528 vs 0.545) and hardness (0.848 vs 0.865) are indistinguishable. These rejected conjectures are statistically identical to certified ones on all three signals; the dedup gate is doing the work, not the score.

---

## Score Dominance: Hardness

Within the certified set, Pearson correlations:

| Pair | r | p |
|---|---|---|
| hardness vs score | 0.905 | 3.99e-29 |
| novelty vs score | 0.313 | 0.006 |

Rough variance decomposition of score std:

| Component | Contribution |
|---|---|
| 0.4 × hardness | ~91.5% |
| 0.3 × novelty | ~13.1% |
| 0.3 × breadth | ~1.6% |

Score is effectively a monotone function of hardness once the trivial gate is passed. Novelty adds a small secondary signal. Breadth is structurally inert for this corpus.

---

## Meta-Analysis: LLM Depth Ratings (n=7 Headline Survivors)

**This is meta-analysis only. Does NOT affect certification. Survival decisions are from sandbox execution.**

The 7 certified-novel survivors from `code-20260531-225343` were rated by `claude-sonnet-4-6` on mathematical depth (1=trivial definition, 2=standard textbook, 3=non-obvious with real argument, 4=deep/cross-area, 5=surprising/publishable).

| ID | Depth | Significance Score | Novelty | Hardness | Statement (abbreviated) |
|---|---|---|---|---|---|
| c_0015 | 1 | 0.540 | 0.634 | 0.875 | Proper divisors = sigma(n)-n (definitional) |
| c_0002 | 2 | 0.572 | 0.613 | 0.875 | Euler totient + sum_{d\|n} phi(d)=n |
| c_0004 | 2 | 0.521 | 0.778 | 0.625 | Legendre symbol QR count |
| c_0008 | 2 | 0.509 | 0.697 | 0.750 | Sum sigma(k) = sum k*floor(n/k) |
| c_0010 | 2 | 0.543 | 0.644 | 0.875 | d(n) hyperbolic sum |
| c_0001 | 3 | 0.534 | 0.613 | 0.875 | Hyperbola method divisor-sum identity |
| c_0017 | 3 | 0.586 | 0.661 | 0.875 | Mobius inversion of phi(n) |

**Spearman correlations with significance signals:**

| Pair | r | p |
|---|---|---|
| depth vs score | 0.239 | 0.606 |
| depth vs novelty | -0.139 | 0.766 |
| depth vs breadth | 0.242 | 0.602 |
| depth vs hardness | 0.174 | 0.709 |

All near-zero and non-significant (n=7, underpowered; treat as exploratory). The depth-1 survivor (c_0015, definitional) receives score=0.540, indistinguishable from depth-3 survivors (0.534–0.586). The score does not separate depth.

---

## Verdict

**What the score measures:** Whether a conjecture is (a) not automation-closeable, (b) has high perturbation-hardness (neighborhood is mostly false), and (c) is retrieval-distant from corpus (novelty >= 0.35). This is a correctness + non-triviality + novelty-threshold certificate.

**What the score does NOT measure:** Mathematical depth, importance, or surprise. A definitional perfect-number fact and a Mobius-inversion identity receive nearly identical scores (0.540 vs 0.586). The score range for all 7 certified headline survivors is 0.509–0.586 with std=0.028 — essentially flat from a depth perspective.

**Breadth is near-zero in practice:** 96.1% of certified conjectures have breadth=0.0. The downstream-enablement signal fires only when a survivor's verified function directly supplies a building block for one of the 8 held-out breadth targets. With the current code-domain corpus, this is rare. The 0.3 weight on breadth has essentially no effect on ordering.

**The dedup gate does the heavy lifting for certified/rejected discrimination** among non-trivial conjectures. Score does not predict whether an otherwise-valid conjecture will be certified; position in the run (relative to earlier accepted survivors) determines it.

**Honest reading:** The significance score is a well-calibrated gate for filtering automation-closeable noise, but it does not stratify mathematical depth within the survivors it accepts. Improving depth-sensitivity would require either structured depth probes (e.g., connections to other open problems), external oracle depth ratings, or a breadth corpus specifically designed to reward enabling harder downstream lemmas.
