# Finding: H-orthogonality-prompt-flips-h2 — REFUTED

## Hypothesis

The genealogy null (finding #3: a `genealogy` arm never beats `control`, and the
full loop never beats `best_of_N`, finding #8) is an artefact of the
*"generalise or build on these survivors"* line in
`crm.genealogy.build_conditioning_context`. That line is claimed to act as an
**exploration brake**, pushing the frozen proposer to re-tread the survivors'
neighbourhood. Replace it with an **orthogonality directive** — *"propose
results NOT expressible via, and dissimilar to, the listed survivors (avoid
their neighbourhood)"* — and genealogy should flip into an **accelerator**, so a
`genealogy_orthogonal` arm should beat **both** `control` **and** `best_of_N` on
distinct-certified per token.

**Predicted observable.** SUPPORTED iff `genealogy_orthogonal` certified-novel
per kilo-token > `control` **and** > `best_of_N` at matched budget. Otherwise the
*mechanism*, not the *wording*, is the problem.

## Design (cheapest decisive version)

- New mode `genealogy_orthogonal` in `build_conditioning_context`: identical
  WHY-failed block as `genealogy`, but the survivor block's directive is
  **inverted** (avoid-neighbourhood instead of build-on), and the closing
  constraint asks for a *different region of the topic*. Survivors are still
  listed (dedup parity with the other arms).
- Three arms, **identical 18-candidate budget** (rounds=3, k=6), seeds 0,1,2:
  1. `genealogy_orthogonal` — full loop (`experiments._harness.run_arm`).
  2. `control` — full loop, prior statements only, no reasons/build-on.
  3. `best_of_N` — one flat 18-candidate batch, **empty context**
     (`experiments.rounds_scaling.run_best_of_n_rounds`).
- Judge: real sandboxed `CodeExecCritic` + significance gate + intra-set dedup.
  **No LLM-as-judge** for survive/die.
- Proposer: `api_code` (claude-sonnet-4-6, real LLM). Embedder: `hash`
  (deterministic novelty), **held fixed across all arms** so it cannot confound.
- **Fallback guard:** every arm verified `using_fallback == False`, so the
  orthogonality directive was genuinely read by a real LLM. (`any_fallback:
  false` in the summary.)

Command:

```
python -m experiments.orthogonality_prompt --config configs/ablation.yaml \
    --rounds 3 --seeds 3 --results-dir results/orthogonality_prompt
```

## Results

certified-novel per kilo-token (primary), mean ± std over seeds 0,1,2:

| arm                   | cert/ktok       | raw distinct-certified | tokens (mean) |
|-----------------------|-----------------|------------------------|---------------|
| genealogy_orthogonal  | **0.672** ± 0.251 | 6.0  (7, 8, 3)        | 8987          |
| control               | 1.144 ± 0.441   | 8.33 (7, 11, 7)        | 7705          |
| best_of_N             | 1.298 ± 0.389   | 5.67 (5, 4, 8)         | 4366          |

- orthogonal − control (per ktok): **−0.472**
- orthogonal − best_of_N (per ktok): **−0.626**
- Welch t (n=3): orthogonal vs control t=−1.316, **p=0.275**; orthogonal vs
  best_of_N t=−1.911, **p=0.141**.

## Honest reading: REFUTED (directional)

The orthogonality-prompt arm **did not beat either reference; every point
estimate goes the wrong way.** It loses to control by −0.47 cert/ktok and to
best_of_N by −0.63, and trails control on raw distinct-certified (6.0 vs 8.33).
At n=3 neither individual gap reaches significance (p=0.28, p=0.14), but the
hypothesis predicted **strict beating of both** arms, and that fails on all three
point estimates — so the directional claim is **refuted**, not merely
inconclusive.

**The mechanism, not the wording, is the problem.** Inverting *"build on"* to
*"avoid the neighbourhood"* did not turn the survivor-conditioning into an
accelerator. The extra survivor lists cost prompt tokens (orthogonal used the
most tokens of any arm, ~8987 vs best_of_N's 4366) while the avoid-neighbourhood
constraint did not raise distinct-certified yield. This is consistent with
finding #3 (genealogy null) and finding #8 (best-of-N ≥ the full loop):
conditioning the frozen proposer on its own survivors — in **any** framing tried
so far (build-on or avoid) — does not buy a per-token advantage over a
memoryless flat batch. The cheapest, most token-efficient knowledge production in
this prototype remains the empty-context best-of-N + dedup baseline.

## Caveats / scope

- n=3 seeds: gaps are directional, not individually significant. The refutation
  rests on the *direction* (orthogonal underperforms both, never beats), which is
  the opposite of the SUPPORTED criterion; a larger n would be needed to *prove*
  a significant deficit, but not to reject the positive claim.
- Easy code domain, hash embedder, 3 rounds. A different domain or many more
  rounds could behave differently, but those are exactly the regimes finding #3
  already probed without support.

Artifacts: `results/orthogonality_prompt/summary.json`,
`results/findings/hyp_H-orthogonality-prompt-flips-h2.json`, per-arm ledgers
under `results/orthogonality_prompt/*_seed*/`.
