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

## 2. Hardness: literal vs rich perturbation — finding #6 (SETTLED at scale)

[`docs/findings/hardness_scaled.md`](findings/hardness_scaled.md) ·
sources: `results/findings/hardness_scaled.json`,
`experiments/run_hardness_scaled.py`
(first pass with n=2 trivials: [`hardness_distribution.md`](findings/hardness_distribution.md))

The first pass had only **2 trivial candidates**, so separation could not be
tested. The scaled experiment uses **8 contentful vs 11 trivial** candidates
(all with fair own-tests — without them every perturbed neighbour is ILLFORMED,
which confounds the signal) and P=32 perturbations, with a one-sided
Mann-Whitney test. The decisive insight: **the richer operator alone does not
fix hardness — the scoring change does.**

| hardness variant | contentful mean | trivial mean | gap | MWU p (1-sided) | separates? |
|---|---|---|---|---|---|
| `literal_any` (old: ±1 literals, broken = invalid) | 0.96 | 0.72 | +0.24 | 0.52 | **no** |
| `rich_any` (rich operators, broken = invalid) | 0.99 | 0.90 | +0.09 | — | **no** |
| `rich_false` (rich, broken = FALSE counterexample only) | 0.74 | 0.55 | **+0.19** | **0.003** | **yes** |

- `literal_any`: high but bimodal on trivials (some 0.0, some 1.0) → no
  separation (p=0.52). Confirms #6.
- `rich_any`: the operator swaps produce **ILLFORMED** (syntactically broken)
  neighbours that count as "broken", inflating *every* candidate toward 1.0 →
  separation actually **worsens**. So a richer operator is not the fix.
- `rich_false`: counting only neighbours the critic refutes with a genuine
  **FALSE counterexample** (excluding ILLFORMED/TIMEOUT) yields a **significant**
  separation (0.74 vs 0.55, p=0.003; vs over-permissive "family A" trivials
  p=0.019). **The fix that matters is the metric (FALSE-only), not the operator.**

Even so the separation is **modest, not clean**: degenerate-but-pinned trivials
(constant/identity impls whose property pins the constant) still score
rich_false 0.33–0.71, because their own-tests pin them — hardness cannot flag
that family. **Conclusion: hardness is at best a weak, partial triviality signal;
the automation-closeable probe (finding #5) remains the real guard, and the
0.4 hardness weight in the significance score is hard to justify on this
evidence.** Note: production configs still default `perturb_strategy="literal"`
(only `configs/hard_domain.yaml` sets `rich`); the `rich_false` metric is not yet
wired into the live `is_trivial` gate — that remains future work.

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

## 6. Hard domain — discovery, not recall — finding #9 (SETTLED at n=10)

[`docs/findings/hard_domain_scaled.md`](findings/hard_domain_scaled.md) ·
sources: `results/findings/hard_domain_n10/summary.json`,
`results/findings/hard_domain_n10/hard_domain.csv`, per-arm `ledger.jsonl`
(first pass n=3: [`hard_domain.md`](findings/hard_domain.md))

On a freshly-defined sequence `g(n)=3g(n-1)-g(n-2)+(n mod 3)` the model cannot
look up, survivors are genuinely *discovered* properties (not recalled textbook
facts) — so this is a fair test of the mechanism. The n=3 first pass showed the
genealogy-vs-control delta **flip sign to +1.33**, which was suggestive but
underpowered. **Scaled to n=10, the flip disappears — it was noise:**

| arm | certified-novel (mean ± std, n=10) | cert / kilo-token | indep-trivial rate |
|---|---|---|---|
| genealogy | **1.90 ± 0.70** | 0.240 | **0.00** (all seeds) |
| control | **2.00 ± 0.63** | 0.271 | ~0.125 (noisy) |
| best_of_N | **3.00 ± 0.63** | **0.927** | — |

| comparison | diff | Welch p | Mann-Whitney p |
|---|---|---|---|
| genealogy − control | **−0.10** | **0.754** | **0.769** |
| best_of_N − genealogy | **+1.10** | **0.003** | **0.006** |

- **H2 is not supported even here.** Genealogy − control = **−0.10** (p=0.75) —
  indistinguishable from zero. With the n=8 easy-domain result (−2.00, p=0.13,
  section 3), the reasoned-genealogy mechanism shows **no certified-novel
  advantage on either domain**. The +1.33 from n=3 was sampling noise.
- **Best-of-N wins decisively here too**: +1.10 certified (p=0.003) and **3.9×
  per-token** (0.927 vs 0.240). Finding #8 holds.
- The full system's only measurable edge is **gate-driven triviality
  suppression** (indep-trivial 0.00 vs control ~0.125 across all 10 seeds) — that
  is the significance gate (finding #5), not the genealogy conditioning, since
  both arms run the gate and differ only in conditioning.

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
