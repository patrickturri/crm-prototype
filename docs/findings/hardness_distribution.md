# Hardness Distribution: literal vs rich perturbation strategies

Experiment addresses **review finding #6**: integer-literal +-1 mutations
saturate hardness near 0.88 for all survivors, measuring syntactic
brittleness rather than explanatory depth.

- Candidates: 10 pool entries + 18 survivors = 28 total
- Perturbations per candidate per strategy: 32
- Seed: 42
- Embedder: hash (deterministic, no API)

## Aggregate Hardness

| Subset | Strategy | Mean | Std | Min | Max | N |
|--------|----------|------|-----|-----|-----|---|
| All | literal | 0.937 | 0.093 | 0.571 | 1.000 | 28 |
| All | rich | 0.947 | 0.078 | 0.688 | 1.000 | 28 |
| Pool only | literal | 0.977 | 0.036 | 0.909 | 1.000 | 10 |
| Pool only | rich | 0.962 | 0.069 | 0.778 | 1.000 | 10 |
| Survivors | literal | 0.915 | 0.107 | 0.571 | 1.000 | 18 |
| Survivors | rich | 0.939 | 0.081 | 0.688 | 1.000 | 18 |
| Pool (trivial) | literal | 1.000 | 0.000 | 1.000 | 1.000 | 2 |
| Pool (trivial) | rich | 0.889 | 0.111 | 0.778 | 1.000 | 2 |
| Pool (contentful) | literal | 0.971 | 0.039 | 0.909 | 1.000 | 8 |
| Pool (contentful) | rich | 0.980 | 0.035 | 0.906 | 1.000 | 8 |

## Separation Signal

- Literal gap (contentful minus trivial mean): **-0.029**
- Rich gap (contentful minus trivial mean): **0.091**
- **Rich separates contentful from trivial: False**
- Threshold for separation claim: gap > 0.10

Justification: rich gap = 0.091 (content mean 0.980 vs trivial mean 0.889); literal gap = -0.029; threshold for separation claim: >0.10

## Per-Candidate Hardness

| id | source | label | literal | rich |
|----|--------|-------|---------|------|
| pool_00 | pool | divisor-count via sqrt loop equals the naive count | 0.941 | 0.906 |
| pool_01 | pool | aliquot sum: sum of proper divisors | 1.000 | 1.000 |
| pool_02 | pool | Euler totient by factorisation equals the coprime-count | 1.000 | 1.000 |
| pool_03 | pool | partial-sum triangular number equals closed form | 1.000 | 1.000 |
| pool_04 | pool | popcount loop equals binary 1-count | 1.000 | 1.000 |
| pool_05 | pool | sum of first n odds is a perfect square | 1.000 | 1.000 |
| pool_06 | pool | double digit-reverse returns n (FALSE: fails on multipl | 1.000 | 1.000 |
| pool_07 | pool | constant-zero function (vacuous; should be suppressed) | 1.000 | 0.778 |
| pool_08 | pool | count of multiples of 3 up to n is floor(n/3) | 0.909 | 0.933 |
| pool_09 | pool | sum of squares closed form | 0.917 | 1.000 |
| c_0000 | survivor | c_0000 | 0.955 | 0.969 |
| c_0001 | survivor | c_0001 | 0.900 | 0.969 |
| c_0002 | survivor | c_0002 | 0.923 | 0.906 |
| c_0003 | survivor | c_0003 | 1.000 | 1.000 |
| c_0004 | survivor | c_0004 | 0.571 | 0.688 |
| c_0005 | survivor | c_0005 | 0.969 | 0.969 |
| c_0006 | survivor | c_0006 | 1.000 | 1.000 |
| c_0007 | survivor | c_0007 | 0.923 | 0.875 |
| c_0008 | survivor | c_0008 | 0.769 | 0.906 |
| c_0009 | survivor | c_0009 | 0.923 | 0.969 |
| c_0010 | survivor | c_0010 | 0.800 | 0.844 |
| c_0011 | survivor | c_0011 | 1.000 | 1.000 |
| c_0012 | survivor | c_0012 | 1.000 | 1.000 |
| c_0013 | survivor | c_0013 | 0.964 | 0.969 |
| c_0014 | survivor | c_0014 | 1.000 | 1.000 |
| c_0015 | survivor | c_0015 | 0.875 | 0.844 |
| c_0016 | survivor | c_0016 | 1.000 | 1.000 |
| c_0017 | survivor | c_0017 | 0.893 | 1.000 |

---
*Numbers produced by `experiments/run_hardness_distribution.py`.*
*All execution is real sandbox execution — no LLM-as-judge, no fabrication.*
