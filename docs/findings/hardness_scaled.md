# Scaled hardness separation: does a richer operator make hardness discriminate?

Settles **review finding #4/#6**. The first pass had only 2 trivial candidates;
this uses **8 contentful** vs **11 trivial** (6 over-permissive *family A*, 5 degenerate-but-pinned *family B*),
P=32 perturbations/strategy, seed=42, real sandbox execution (no API).

Three hardness variants: **literal_any** (old: integer +-1, broken = not valid),
**rich_any** (new operators/boundaries, broken = not valid), and **rich_false**
(rich, broken = reason_class FALSE only — excludes syntactically-broken/ILLFORMED mutations).

## Mean hardness by group

| Variant | Group | Mean | Std | Min | Max | N |
|---|---|---|---|---|---|---|
| literal_any | contentful | 0.971 | 0.038 | 0.909 | 1.000 | 8 |
| literal_any | trivial (all) | 0.727 | 0.445 | 0.000 | 1.000 | 11 |
| literal_any | trivial A (over-permissive) | 0.667 | 0.471 | 0.000 | 1.000 | 6 |
| literal_any | trivial B (pinned) | 0.800 | 0.400 | 0.000 | 1.000 | 5 |
| rich_any | contentful | 0.980 | 0.035 | 0.906 | 1.000 | 8 |
| rich_any | trivial (all) | 0.886 | 0.099 | 0.722 | 1.000 | 11 |
| rich_any | trivial A (over-permissive) | 0.889 | 0.101 | 0.722 | 1.000 | 6 |
| rich_any | trivial B (pinned) | 0.883 | 0.097 | 0.778 | 1.000 | 5 |
| rich_false | contentful | 0.737 | 0.105 | 0.500 | 0.840 | 8 |
| rich_false | trivial (all) | 0.545 | 0.130 | 0.333 | 0.765 | 11 |
| rich_false | trivial A (over-permissive) | 0.568 | 0.120 | 0.444 | 0.765 | 6 |
| rich_false | trivial B (pinned) | 0.517 | 0.135 | 0.333 | 0.706 | 5 |

## Separation test (one-sided Mann-Whitney: contentful > trivial)

| Variant | vs all trivial: gap | p | separates | vs family-A: gap | p | separates |
|---|---|---|---|---|---|---|
| literal_any | +0.244 | 0.52 | False | +0.304 | 0.4106 | False |
| rich_any | +0.094 | 0.0272 | False | +0.091 | 0.0501 | False |
| rich_false | +0.193 | 0.0031 | True | +0.170 | 0.0192 | True |

## Per-candidate

| id | group | family | literal_any | rich_any | rich_false |
|---|---|---|---|---|---|
| pool_00 | contentful | - | 0.941 | 0.906 | 0.656 |
| pool_01 | contentful | - | 1.000 | 1.000 | 0.750 |
| pool_02 | contentful | - | 1.000 | 1.000 | 0.812 |
| pool_03 | contentful | - | 1.000 | 1.000 | 0.840 |
| pool_04 | contentful | - | 1.000 | 1.000 | 0.500 |
| pool_05 | contentful | - | 1.000 | 1.000 | 0.727 |
| pool_08 | contentful | - | 0.909 | 0.933 | 0.800 |
| pool_09 | contentful | - | 0.917 | 1.000 | 0.812 |
| triv_always_true | trivial | A | 0.000 | 1.000 | 0.556 |
| triv_tautology | trivial | A | 1.000 | 1.000 | 0.765 |
| triv_nonneg | trivial | A | 1.000 | 0.857 | 0.500 |
| triv_typeonly | trivial | A | 1.000 | 0.818 | 0.455 |
| triv_plus0 | trivial | A | 1.000 | 0.938 | 0.688 |
| triv_ge_self_minus1 | trivial | A | 0.000 | 0.722 | 0.444 |
| triv_const0 | trivial | B | 1.000 | 0.778 | 0.333 |
| triv_const1 | trivial | B | 1.000 | 0.818 | 0.455 |
| triv_const7 | trivial | B | 1.000 | 0.818 | 0.455 |
| triv_identity | trivial | B | 0.000 | 1.000 | 0.636 |
| triv_double | trivial | B | 1.000 | 1.000 | 0.706 |

---
*Produced by `experiments/run_hardness_scaled.py`. Real sandbox execution, no fabrication.*
