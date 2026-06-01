# Best-of-N Baseline vs Full CRM System (Finding #8)

**Question (review finding #8):** Is the full pipeline — genealogy conditioning +
significance gate + intra-survivor embedding dedup + novelty certification —
actually worth the extra machinery *per token*, against a naive best-of-N + simple
dedup baseline?

**Module:** `experiments/baseline.py`
**Critic:** real sandboxed `CodeExecCritic` in BOTH arms (no LLM-as-judge for validity).
**Triviality metric:** `experiments._indep_oracle.independent_trivial_rate` — the
genuinely-independent oracle (finding #5) that shares no code with the significance
gate. Applied identically to both arms' kept/surviving sets, so the comparison is
apples-to-apples.

## Arms

| | Baseline ("best-of-N + simple dedup") | Full system |
|---|---|---|
| Genealogy conditioning | none (empty context every round) | yes (mode=genealogy) |
| Validity gate | real critic | real critic |
| Significance / triviality suppression | none | yes |
| Novelty embedding-distance gate | none | yes (delta=0.35) |
| Dedup | exact normalised-string match only | string + intra-survivor embedding distance |
| "kept" definition | distinct VALID statements | significance-gated, novelty-certified, deduped survivors |

## Deterministic floor — `offline_code` proposer + hash embedder (5 seeds)

Free and exactly reproducible:

```
python -m experiments.baseline --config configs/ablation.yaml --seeds 0,1,2,3,4 --proposer offline_code
```

| Metric | Baseline | Full |
|---|---|---|
| certified-per-kilo-token | **17.85 +/- 2.10** | **10.60 +/- 1.25** |
| independent trivial-rate | **0.240 +/- 0.028** | **0.151 +/- 0.081** |
| kept count (mean) | 8.4 | 10.6 |
| proposer tokens (mean) | 479 | 1007 |

Source: `results/findings/baseline.csv`, `results/findings/baseline.json`.

### Honest reading (deterministic floor)

The full system does **NOT** win on raw throughput per token. The baseline keeps
**1.68x more certified items per kilo-token** (17.85 vs 10.60). This is expected and
not spun: the full arm pays for genealogy conditioning (its context grows each round,
so it spends ~2.1x the tokens — 1007 vs 479), and it gates harder, so its yield per
token is lower by construction.

Where the full system does help is **quality**: the independent oracle flags
**0.151** of full-system survivors as trivial/vacuous versus **0.240** of baseline
keeps — a **~37% relative reduction** in independently-measured triviality. But note
the full-arm trivial rate has a large standard deviation (+/- 0.081, vs the baseline's
tight +/- 0.028) and the per-seed full-arm trivial rate ranges from 0.067 to 0.231,
so the gap is real on the mean but **noisy and not strongly separated** at n=5 on this
offline pool.

**Bottom line:** on the deterministic floor, the full pipeline trades roughly
1.7x throughput-per-token for a modest, noisy reduction in trivial survivors. It is
not a per-token win; it is a quality-vs-cost trade-off, and on the small offline pool
the quality margin is not decisive.

## Realistic comparison — `api_code` proposer (NONDETERMINISTIC, 1 seed)

Real Anthropic `claude-sonnet-4-6` proposer, MiniLM embedder. NOT reproducible
(temperature 0.7); a single seed; reported only as a realistic sanity check.

```
python -m experiments.baseline --config configs/ablation.yaml --seeds 0 --proposer api_code
```

| Metric | Baseline | Full |
|---|---|---|
| certified-per-kilo-token | 0.784 | 0.507 |
| independent trivial-rate | 0.000 | 0.000 |
| kept count | 6 | 5 |
| valid count | 6 | 7 |
| proposer tokens | 7652 | 9867 |

Source: `results/findings/baseline_api.csv`, `results/findings/baseline_api.json`.
Both arms used the real API (`using_fallback=False`).

### Honest reading (API, n=1)

Same direction as the floor: the baseline keeps more per token (0.784 vs 0.507,
1.55x), because the full arm spends more tokens (9867 vs 7652, genealogy context)
and gates harder — the full arm found 7 valid statements but kept only 5 after the
significance + intra-survivor-dedup gates removed 2; the baseline kept all 6 of its
valid statements (no exact-string duplicates to drop).

The independent oracle flagged **0.0** trivial survivors in BOTH arms on this single
API seed. With the LLM explicitly prompted for non-trivial claims and only 5-6
survivors per arm, the quality signal that separated the arms on the offline pool
does not appear here — at n=1 the trivial-rate comparison is uninformative, not a
win for either side. We report it as-is rather than over-reading one draw.

---

*Numbers above are produced by running `experiments/baseline.py`; every value is
traceable to `results/findings/baseline*.csv` / `baseline*.json`. `results/` is
gitignored but regenerable from the config + this module.*
