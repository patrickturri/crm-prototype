# Deep rounds-scaling — does iteration compound? (finding: NO)

Config `configs/ablation.yaml` (api_code proposer + hash embedder), **25 rounds**, genealogy vs control. Parsed from `results/rounds_scaling_run.log`; **fallback-contaminated seeds excluded** (intermittent APIConnectionError silently dropped some seeds to the context-ignoring offline proposer — those are not valid and are removed). The `best_of_N` arm is omitted: at R·k=150 candidates in one call it exceeds the proposer's max_tokens and is not viable (the sane-budget best-of-N comparison is in `baseline.md` / `hard_domain_scaled.md`).

## Compounding test (new-certified, early third vs late third)

| arm | clean seeds | final certified (mean±std) | new (early⅓) | new (late⅓) | late/early | plateau round (median) |
|---|---|---|---|---|---|---|
| genealogy | 7 | 13±4.7809 | 9.4286 | 0.5714 | 0.0606 | 14 |
| control | 4 | 18.5±3.9051 | 14.5 | 1.25 | 0.0862 | 20.0 |

**Reading.** New certified-novel is concentrated in the EARLY rounds and collapses toward zero in the LATE rounds for both arms (late/early ratio well below 1, median plateau round in the low-to-mid teens out of 25). **Iteration does not compound — it saturates.** Once the proposer has surfaced the small set of operationally-novel claims it can find for this domain, more rounds add almost nothing, regardless of genealogy conditioning.

## Endpoint: genealogy vs control (clean seeds)

- genealogy − control (final certified) = **-5.5**
- Welch p = **0.1067**, Mann-Whitney p = **0.1066**

Even at 25 rounds, genealogy does **not** significantly beat control — consistent with the n=8 (easy) and n=10 (hard) ablations. Scaling rounds does not rescue H2.

---
*Produced by `experiments/analyze_rounds_scaling_clean.py` from the run log; fallback seeds excluded. No fabrication.*
