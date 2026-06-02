# Hypothesis test: certify_novel is essentially the hash-embedder novelty gate (H-novelty-is-score)

**Verdict: SUPPORTED.**

## Hypothesis

H-novelty-is-score: Because `breadth ~ 0` and `hardness` saturates (finding #6),
the `certified_novel` verdict is driven almost entirely by the novelty `>= 0.35`
gate. `certify_novel` is then essentially "embedding-distant from the ~20-row
corpus / from already-accepted survivors", **not** a measure of being interesting
or hard-to-vary. This would explain why best-of-N wins (more independent samples
hit more distinct embedding-distant points) and why genealogy's "build on
survivors" anchoring loses (it pulls samples into already-occupied embedding
neighbourhoods).

**Predicted observable (if true):** among valid + non-trivial conjectures,
`certified_novel` is ~perfectly predicted by `(novelty>=0.35)`, and `hardness`
adds ~zero discriminative power (AUC of hardness for certified vs non-certified
~ 0.5). If false, hardness or breadth materially separates certified from rejected.

## Method (deterministic, no API)

Pooled **all 105 committed ledgers** under `results/**/ledger.jsonl`
(1722 records; 773 carry a `significance` block). For each scored conjecture we
have `significance.{novelty,breadth,hardness,is_trivial}` and the recorded
`certified_novel`. We restrict to non-trivial records (the gate's own triviality
suppression already removed the rest) and compute, per feature, the Mann-Whitney
AUC = P(feature higher for a certified than for a non-certified record).

Reproduce:

```
python -m experiments.analyze_certify_drivers   # writes results/findings/hyp_H-novelty-is-score.json
```

(or the one-liner in the workflow brief over the same ledgers).

## Results

Pool: 773 scored records; 536 non-trivial (408 certified, 128 non-certified).

| Feature | certified mean +/- std | non-certified mean +/- std | AUC (cert vs non-cert) |
|---|---|---|---|
| **novelty** | 0.602 +/- 0.098 | 0.498 +/- 0.158 | **0.686** |
| hardness | 0.856 +/- 0.152 | 0.869 +/- 0.138 | **0.480** |
| breadth | 0.030 +/- 0.169 | 0.029 +/- 0.118 | **0.484** |

- **Hardness AUC = 0.48** — no discriminative power, and the sign is slightly
  *negative*: certified records have, if anything, marginally **lower** mean
  hardness (0.856) than non-certified ones (0.869). Hardness is saturated/noise
  with respect to the certify decision.
- **Breadth AUC = 0.48**, and **96.8%** of gate-passers have `breadth == 0`.
  Breadth carries essentially no signal.
- **Novelty AUC = 0.69** — the only feature that separates the two classes.

### The gate is necessary, and the only thing that ever removes a certification is itself embedding/structural

- **certified records violating `(novelty>=0.35 AND non-trivial)`: 0** — the
  novelty gate is strictly *necessary*. No conjecture is ever certified below the
  novelty threshold or while trivial.
- **gate-fail but certified: 0**; **gate-pass but not certified: 90.** Those 90
  are removed by the *other* certify conditions (corpus-restatement,
  automation-closeable, near-an-already-accepted-survivor). Crucially those guards
  are **also embedding-distance / structural**, not hardness or breadth.

So `certified_novel` reduces to: `non-trivial AND novelty>=0.35 AND
(not a near-duplicate in embedding/corpus space)`. Predictive accuracy of the
plain `(novelty>=0.35 AND non-trivial)` gate against the recorded verdict is
**0.83** among non-trivial records and **0.88** over all valid records; the entire
residual is the one-directional embedding-proximity guards, never hardness/breadth.

## Interpretation

Under the default hash embedder, the certified-novel verdict is an
**embedding-distance test against a small corpus + already-accepted survivors**,
gated by triviality. It is not measuring "hard-to-vary" content: hardness is
saturated and non-discriminative (AUC 0.48), breadth is ~0. This directly
rationalises finding #8 and the genealogy null (finding #3):

- **Best-of-N wins** because more independent draws cover more distinct
  embedding-distant regions, and each clears the same novelty gate.
- **Genealogy loses** because "build on survivors" anchors new draws *near*
  already-accepted survivors — exactly the neighbourhood the
  near-survivor guard rejects — so it converts novelty into proximity-collisions.

This sharpens the central negative result: the current metric cannot reward the
mechanism genealogy is supposed to exploit (deepening/compounding on prior
content), because the metric has no content-hardness axis with discriminative
power. **A fair test of H2 requires a certify signal whose discriminative power
comes from hardness/breadth, not embedding distance** (e.g. FALSE-only
`rich_false` hardness from finding #6, or a real downstream-enablement breadth
target), and/or a real (non-hash) embedder so novelty is semantic rather than
lexical.

## Caveats

- Pools heterogeneous runs (offline + api_code proposers, hash + MiniLM
  embedders, easy + hard domains). The qualitative conclusion (hardness/breadth
  AUC ~ 0.5, novelty the sole separator, novelty gate strictly necessary) is the
  same across the pool; this is an aggregate structural claim about the gate, not
  a per-arm effect size.
- AUC here is the rank statistic, not a fitted classifier; the necessity/zero-
  violation counts are exact over the pool.
