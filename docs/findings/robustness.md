# Robustness / Model-Sensitivity of the Genealogy Null (Finding #10)

**Question.** Every prior CRM null — H2 not supported, best-of-N >= genealogy
(findings #3, #8, responsiveness) — was measured with ONE proposer config:
`claude-sonnet-4-6` at temperature 0.7. Are those conclusions a property of the
MECHANISM, or an artefact of that particular model/temperature? This experiment
re-runs a SLICE of the genealogy-vs-best_of_N comparison under three proposer
settings and asks whether the sign/size of the gap moves.

**Module:** `experiments/robustness.py` (Make target: `make robust`).
**Critic:** real sandboxed `CodeExecCritic` in BOTH arms — no LLM-as-judge for
survive/die (§3, §15). LLM is the proposer only.
**Fallback guard (hard rule):** both arms use the real LLM proposer; if ANY arm
silently degraded to the offline context-IGNORING generator the comparison would
be invalid, so the run raises `FallbackError` and writes no summary unless
`--allow-fallback`. **This run used the real API on every call:
`any_fallback=false`.**

## Setup

Two arms per setting (the task's genealogy-vs-best_of_N slice; the `control` arm
is dropped to keep the API budget bounded):

- **genealogy** — full loop, `mode="genealogy"` (`experiments._harness.run_arm`):
  each round's prompt carries WHY past conjectures died + which survivors to
  build on. The mechanism under test.
- **best_of_N** — one flat batch of `R*k` candidates with EMPTY context, then the
  SAME critic + significance gate + intra-set dedup
  (`experiments.rounds_scaling.run_best_of_n_rounds`). The memoryless reference.

Held fixed across settings (so the comparison isolates the proposer config): hash
embedder (deterministic novelty), `CodeExecCritic`, weights, corpus, breadth
targets, `R = 6` rounds, `k = 6`, 3 seeds. Metric: distinct certified-novel
survivors after 6 rounds, mean over seeds; Welch's t-test on the per-seed finals.

Three settings:

| label | model | temperature | role |
|---|---|---|---|
| `sonnet_t07` | claude-sonnet-4-6 | 0.7 | the prior-findings baseline |
| `sonnet_t03` | claude-sonnet-4-6 | 0.3 | same model, lower temperature |
| `haiku_t07`  | claude-haiku-4-5  | 0.7 | a different (smaller/faster) model |

```
python -m experiments.robustness --rounds 6 --seeds 3 --results-dir results/findings/robustness
```

## Results (real API, 3 seeds/arm, no fallback)

| setting | genealogy (mean +/- std) | best_of_N (mean +/- std) | delta (gen - bON) | Welch t | Welch p |
|---|---|---|---|---|---|
| `sonnet_t07` (baseline) | **6.0 +/- 0.82** | **6.33 +/- 1.25** | **-0.33** | -0.32 | **0.77** |
| `sonnet_t03` (temp 0.3) | **7.0 +/- 0.82** | **6.33 +/- 0.47** | **+0.67** | +1.00 | **0.39** |
| `haiku_t07` (different model) | **2.0 +/- 0.82** | **4.67 +/- 1.70** | **-2.67** | -2.00 | **0.14** |

Per-seed finals (so the spread is auditable):

| setting | genealogy finals | best_of_N finals |
|---|---|---|
| `sonnet_t07` | [7, 6, 5] | [6, 5, 8] |
| `sonnet_t03` | [6, 8, 7] | [6, 6, 7] |
| `haiku_t07`  | [2, 3, 1] | [3, 4, 7] |

Source: `results/findings/robustness/summary.json`, `robustness.csv`, and the
per-arm per-seed ledgers under `results/findings/robustness/<label>/`.
Machine summary flags: `all_deltas_nonpositive=false`,
`any_significant_positive=false`.

## Honest reading: the null is ROBUST, not baseline-specific

**Genealogy does not significantly beat best-of-N in ANY of the three settings.**
The conclusion of findings #3/#8 holds across model and temperature:

1. **Baseline reproduces.** `sonnet_t07` gives delta = -0.33 (p = 0.77) — best-of-N
   is, if anything, slightly ahead, exactly as before. The known null is not a
   one-off.

2. **Lower temperature nudges the point estimate positive but not significantly.**
   At `sonnet_t03` the genealogy mean (7.0) edges above best-of-N (6.33),
   delta = +0.67, but p = 0.39 at n = 3 — well short of significance, and best-of-N
   also gets *tighter* (std 0.47). So `all_deltas_nonpositive` is `false` only
   because of this one small, non-significant positive point estimate; it is NOT
   evidence for H2. If there is any real effect of lowering temperature, it is at
   most a small narrowing of the gap, not a reversal of the verdict.

3. **The smaller model makes best-of-N win by MORE, and craters absolute yield.**
   `haiku_t07` is the largest gap, delta = -2.67 (p = 0.14, the closest to
   significance of the three, and in favour of best-of-N). Haiku also produces far
   fewer certified-novel survivors overall (genealogy mean 2.0 vs sonnet's 6-7;
   per-seed genealogy finals as low as [2,3,1]). On a weaker proposer the
   genealogy conditioning does not rescue yield — it under-performs the memoryless
   batch, consistent with the responsiveness finding that "build on the survivors"
   anchors the proposer rather than expanding it.

### Bottom line

Across a 3x change in temperature and a model swap, **no setting shows a
significant genealogy advantage**, the baseline result reproduces, and the only
setting where genealogy's *point estimate* leads (sonnet @ 0.3) is not
significant. The nulls are a property of the mechanism on this domain, not an
artefact of `claude-sonnet-4-6 @ 0.7`. The temperature knob is the one place
worth a larger-n follow-up (the +0.67 at temp 0.3 is the only non-adverse
signal), but on the present evidence the verdict is unchanged: conditioning on a
reasoned genealogy does not produce more certified-novel knowledge than a
deduped best-of-N.

---

*Numbers above are produced by `python -m experiments.robustness --rounds 6
--seeds 3` against the live Anthropic API; every value is traceable to
`results/findings/robustness/summary.json` + `robustness.csv` (`results/` is
gitignored but regenerable). Real API on all calls (`any_fallback=false`).
Per-request timeout + retries were added to the API proposer so a hung socket
cannot stall the sweep; on exhaustion the proposer would fall back to offline,
which the guard then flags loudly.*
