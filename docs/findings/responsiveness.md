# Proposer-Responsiveness Diagnostic (root cause for H2)

**Question:** H2 (genealogy conditioning beats pass/fail) lost at n=8 easy and
n=10 hard (finding #3). Before spending on long-rounds compounding runs, we need
the root cause. When the **real** `APICodeProposer` is handed a *genealogy-mode*
conditioning context vs a *control-mode* context, **does its output distribution
actually change** — and if so, **does it change in the way the genealogy is
supposed to make it change** (referencing/avoiding prior failure modes,
generalising survivors)?

Two readings with very different implications:

- **IGNORE (fixable):** batches are statistically indistinguishable between
  modes -> H2's null is an implementation artefact (prompt is too weak).
- **USE-BUT-NO-HELP (deeper):** batches measurably differ, but the
  genealogy-specific content doesn't translate into better targeting -> H2's
  null is a property of the mechanism on this domain, not a prompt bug.

**Module:** `experiments/responsiveness.py`
**No LLM-as-judge:** this is a pure proposer-distribution probe; there is no
survive/die decision here. The failure-reference audit is a transparent,
LLM-free keyword probe, clearly labelled.
**Fallback guard:** the script FAILS LOUDLY (exit 2) if any proposer call
degrades to the offline (context-ignoring) generator — that would make the
comparison meaningless. This run used the real API on all calls
(`any_fallback=false`).

## Setup

A realistic mid-run ledger (`build_realistic_ledger`): **3 surviving PROVED
results** (with content scores 0.58–0.71) to "build on," and **4 REFUTED FALSE
entries** each carrying a concrete counterexample reason:

| Refuted statement | WHY (counterexample in ledger) |
|---|---|
| double digit-reverse returns n | n=120: reverse->21->12 != 120 (multiples of 10) |
| Fermat test as exact primality | n=341: 2^340 % 341 == 1 but 341=11*31 (pseudoprime) |
| Fibonacci-squared = product of neighbours | n=5: 25 vs 24 (Catalan identity has ±1 offset) |
| n perfect iff n = sum of ALL its divisors | n=6: 1+2+3+6=12 != 6 (must exclude n) |

`build_conditioning_context` renders these two ways. **Genealogy** lists the WHY
of each failure ("do not repeat these failure modes") plus the survivors to
"generalise or build on." **Control** lists the SAME statements as a flat "do not
restate" list with no reasons and no build-on guidance. So dedup pressure is
matched across arms; the ONLY difference is the reasoned content.

3 seeds, k=6, `claude-sonnet-4-6`, temperature 0.7. Hash embedder (deterministic,
free) for the relative embedding distance.

```
python -m experiments.responsiveness --seeds 0,1,2
```

## Results (3 seeds, real API)

| Metric | Value | Reading |
|---|---|---|
| matched embedding distance (genealogy vs control) | **0.467 ± 0.059** | batches differ a LOT |
| Jaccard overlap of statement sets | **0.030 ± 0.043** | almost no identical statements |
| prior-failure topics touched, genealogy (mean of 4) | **0.67** | — |
| prior-failure topics touched, control (mean of 4) | **0.67** | identical to genealogy |
| `proposals_shift` | **true** | distribution measurably changes |
| `references_failures` | **false** | genealogy does NOT target the failures |

Source: `results/findings/responsiveness.json` (full per-seed statements,
context previews, and per-seed audits are stored there).

## Reading: USE-BUT-NO-HELP (the deeper problem), not IGNORE

The proposer is **not** ignoring the context. The output distribution shifts
substantially and **interpretably** between modes (embedding distance 0.467,
Jaccard 0.03). But the shift is **not** in the direction H2 needs:

1. **Genealogy anchors the proposer to RESTATING the survivors, not
   generalising them.** Across all three seeds the genealogy batches repeatedly
   re-derive the listed survivors — `sum_{d|n} phi(d) = n`, `phi(n) = coprime
   count`, `sum of cubes`, triangular numbers. Seed 0 literally re-proposes
   survivor #1 verbatim ("number of integers k in [1,n] such that gcd(k,n)=1
   equals Euler's totient phi(n)") **despite** the explicit "(c) NOT restatements
   of the above" instruction. "Build on these" pulls the model toward the
   neighbourhood of what already survived rather than toward genuinely new
   territory.

2. **Control roams MORE freely.** With only a flat "don't restate" list, control
   produced more diverse, off-survivor topics (gcd(n,n+1)=1, subset counts,
   alternating binomial sums, divisors of n! ≤ n). If anything, the genealogy's
   "generalise/build-on" framing **reduces** topical diversity.

3. **The failure-avoidance signal is exactly null.** Genealogy touches prior
   failure topics at the SAME rate as control (0.67 vs 0.67), and the few hits
   are incidental keyword collisions ("2^", "prime", "digit"), not the proposer
   steering around the refuted Fermat / digit-reverse / Fibonacci / perfect-number
   claims. Neither mode re-proposes the refuted claims — but **control's plain
   statement list suppresses them just as well as genealogy's reasoned WHY.** The
   expensive "why it died" content buys nothing over a bare do-not-restate list
   on this axis.

4. **Genealogy sometimes degrades statement quality.** On seeds 1–2 the
   "generalise the survivors" push produced rambling, malformed run-on
   "statements" (multi-clause derivations of `sum phi(k)`), suggesting the model
   strains to produce harder generalisations and emits noise.

### Bottom line

The genealogy mechanism is **read and used** by the frozen proposer — it is not
a silent-ignore bug — but on this domain its specific content (a) duplicates the
deduplication pressure control already provides (so the failure-WHY adds no
measurable targeting), and (b) its "build on the survivors" framing **anchors**
the proposer near already-accepted results, *reducing* exploration relative to
control. That is a coherent mechanistic explanation for finding #3's null and
for why best-of-N (no conditioning) wins (finding #8): conditioning on the
genealogy moves probability mass toward restating/neighbouring survivors, not
toward new certified-novel territory.

**Implication for the compounding-regime test:** more rounds will *accumulate*
this anchoring, not dissolve it — the survivor list grows and the "build on
these" pull strengthens, so we should expect the genealogy arm to **drift
toward restatement** over many rounds rather than compound advantage. A prompt
fix that could flip the IGNORE reading does not apply here (the context is
already used); the lever, if any, is reshaping the genealogy prompt to push
*away* from the survivor neighbourhood (orthogonality / "find a result NOT
expressible via the survivors") rather than "build on" them. That is a concrete,
evidence-backed redesign — but the current genealogy text, as written, is an
exploration *brake*, not an accelerator.

---

*Numbers above are produced by `python -m experiments.responsiveness --seeds
0,1,2`; every value is traceable to `results/findings/responsiveness.json`
(`results/` is gitignored but regenerable). Real API on all calls
(`any_fallback=false`).*
