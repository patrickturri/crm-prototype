# Findings — review-pass experiments (honest, number-by-number)

This file consolidates the follow-up experiments run to address an external
review of the CRM prototype. Each section links to a standalone finding doc
under [`docs/findings/`](findings/) and to the raw result files it was computed
from. **Every number here is produced by running code and is traceable to a
named result file. Null and unfavorable results are reported as such.**

## What "certified-novel" actually means (read first)

`certify_novel` is an **operational** novelty proxy, not a proof of new
mathematics:

1. not a verbatim corpus restatement,
2. not closeable by a degenerate-impl automation probe, and
3. at embedding-distance >= **0.35** from the static novelty corpus.

Survival is decided by **fuzz-testing on bounded integers** in a sandbox — not a
formal proof. The headline run's survivors are **classical textbook number-theory
identities** (Mobius inversion = phi, sum_{d|n} phi(d) = n, sum floor(n/k) =
sum d(n)). The system **rediscovers** them under criticism; it does not discover
new mathematics. The **Lean** (formal-proof) track produced **0** certified-novel
survivors at the demo budget — testing is not proving, and that is the honest
tell. See [`docs/SURVIVORS.md`](SURVIVORS.md) and the README "Honest limits".

---

## 1. Intra-survivor dedup — finding #7

[`docs/findings/dedup_collapse.md`](findings/dedup_collapse.md) ·
sources: `results/findings/dedup_collapse.json`,
`results/code-20260531-225343/ledger.jsonl`

The 7 certified-novel survivors of run `code-20260531-225343`, re-measured with
`crm.novelty.dedup_survivors` (the run's own MiniLM embedder, delta=0.35),
collapse to **4** distinct clusters — **3 of 7 (43%)** are intra-run semantic
near-duplicates (the divisor/floor-sum family c_0001/c_0008/c_0010, and the
totient/Mobius pair c_0002/c_0017). The two remaining survivors (Legendre,
perfect-numbers) are genuinely distant. **Fix shipped:** `certify_novel` now
applies a fourth gate that rejects a candidate within delta of an
already-accepted survivor from the same run, so future runs block these at
admission.

| metric | value |
|---|---|
| raw certified | 7 |
| deduped certified | 4 |
| collapsed (near-dups) | 3 |
| delta | 0.35 |

## 2. Hardness: literal vs rich perturbation — finding #6

[`docs/findings/hardness_distribution.md`](findings/hardness_distribution.md) ·
sources: `results/findings/hardness_distribution.json`,
`experiments/run_hardness_distribution.py`

Literal +-1 integer-literal mutation measures numeric brittleness, not depth: it
rates the **vacuous constant-zero** task at hardness **1.000** (as hard as a
contentful identity). The new **rich** strategy (operator/boundary/operand
rewrites) moves it in the correct direction (constant-zero -> **0.778**). But the
overall separation is weak: rich gap (contentful minus trivial) = **0.091**,
just below the 0.10 "separates" threshold, and the trivial pool is only n=2.
Mean hardness stays high under both strategies (literal **0.937**, rich
**0.947** over 28 candidates). The review's "0.88 for ALL survivors" is not
exactly borne out (survivor literal mean 0.915, std 0.107), but the qualitative
defect — literal can't tell trivial from contentful — is confirmed. Rich is
qualitatively better; the quantitative gain is modest.

## 3. Genealogy ablation at scale (H2) — finding #3

[`docs/findings/genealogy_scale.md`](findings/genealogy_scale.md) ·
sources: `results/ablation_genealogy.csv`,
`results/findings/genealogy_scale.json`

Scaled to **n=8 seeds** with the real `api_code` proposer (the setup where the
genealogy mechanism actually bites). Genealogy does **NOT** beat control — control
is higher:

| metric | genealogy | control |
|---|---|---|
| certified-novel (mean +/- std) | **4.88 +/- 1.96** | **6.88 +/- 2.57** |
| trivial rate | 0.271 | 0.258 |

Difference (treat - ctrl) = **-2.00**; Welch **p=0.126**, Mann-Whitney
**p=0.134** (not significant); trivial-rate difference is a near-tie (Welch
**p=0.90**). **The H2 advantage is not established on the easy recall domain; the
review's call to demote the claim is supported.** (See section 6 for the one
domain where the sign flips.)

## 4. Significance guard with an independent oracle — finding #5

source paragraph in [`docs/REPORT.md`](REPORT.md) section 9.2 ·
module `experiments/_indep_oracle.py` ·
data `results/ablation_significance_indep_offline/ablation_significance.csv`

The old significance ablation was near-tautological: its "independent" trivial
probe reused the gate's own degenerate-impl oracle. A genuinely independent
oracle (`is_trivial_independent`) was built that shares **no code** with the
gate — structurally-unrelated degenerate battery, disjoint sampling subdomain,
constant-fit holdout. Re-run on the deterministic floor (offline_code + hash
embedder, 5 seeds), the guard still helps but by a smaller, noisier margin than
the tautological probe claimed:

| trivial-survivor rate | guard ON | guard OFF |
|---|---|---|
| independent oracle (5 seeds) | **0.15 +/- 0.07** | **0.27 +/- 0.08** |

Even with the guard ON, the independent oracle still flags ~15% of survivors as
guess-closeable. (The old self-measuring probe reported 0.00 vs 0.34 — that
number is retired.)

## 5. Best-of-N baseline vs full system — finding #8

[`docs/findings/baseline.md`](findings/baseline.md) ·
sources: `results/findings/baseline.csv`/`.json`,
`results/findings/baseline_api.csv`/`.json`, `experiments/baseline.py`

The full pipeline does **NOT** win per token. On the deterministic floor
(offline_code + hash embedder, 5 seeds):

| metric | baseline | full |
|---|---|---|
| certified per kilo-token | **17.85 +/- 2.10** | **10.60 +/- 1.25** |
| independent trivial-rate | 0.240 +/- 0.028 | 0.151 +/- 0.081 |

The baseline keeps **1.68x more** certified items per token (the full arm spends
~2.1x the tokens on growing genealogy context and gates harder). The full
system's only edge is a modest, noisy **~37% relative** reduction in
independently-measured triviality (0.240 -> 0.151), which **vanishes** on the
single API seed (0.0 in both arms). Frame the loop as a **cost/quality
trade-off**, not a per-token win.

## 6. Hard domain — discovery, not recall — finding #9

[`docs/findings/hard_domain.md`](findings/hard_domain.md) ·
sources: `results/findings/hard_domain/summary.json`,
`results/findings/hard_domain/hard_domain.csv`, per-arm `ledger.jsonl`

On a freshly-defined sequence `g(n)=3g(n-1)-g(n-2)+(n mod 3)` the model cannot
look up, the system produces **10/10 genuinely discovered** (non-recalled,
non-restatement) certified survivors. The genealogy-vs-control delta **flips
sign** between domains:

| domain | genealogy | control | delta |
|---|---|---|---|
| easy (recall) | 6.00 +/- 2.16 | 7.00 +/- 0.82 | **-1.00** (no help) |
| hard (discovery) | 2.33 +/- 0.47 | 1.00 +/- 0.82 | **+1.33** (helps) |

Note: the easy-domain row here is the original **n=3** ablation
(`results/ablation_genealogy.csv` was since rerun at n=8 — see section 3, where
the delta is -2.00; both are unfavorable to H2 on the easy domain). The hard-domain
flip is the thesis-relevant signal, but it is **underpowered (n=3, overlapping
error bars)** — suggestive, not significant. best-of-N still certified the most
(3.67) and dominates per-token (4.7x), so finding #8 holds here too.

---

## Reproduction

- Deterministic / free (offline proposer + hash embedder): dedup, hardness,
  baseline-floor, and the independent-oracle significance ablation are exactly
  reproducible.
- API (nondeterministic, costs money, temperature 0.7): the n=8 genealogy scale
  run, the API baseline seed, and the hard-domain run use the real Anthropic
  proposer and are not bit-reproducible.

`results/` is gitignored but regenerable from the configs + modules named above.
Full test suite: **71 passed** (`python -m pytest -q`).
