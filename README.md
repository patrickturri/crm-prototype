# Critical-Rationalist Machine (CRM) — prototype

A minimal but **real, end-to-end** prototype of a machine that *creates*
certified-novel knowledge by **bold conjecture → severe automated criticism →
retention of survivors and of the reasoned genealogy of failures**, rather than
by predicting the human-text distribution.

## Thesis (3 sentences)

Today's LLMs interpolate human knowledge but cannot **certify new knowledge
against reality** — a limitation of their fit-to-text *objective*, not of neural
nets. We demote a **frozen** model from a terminal objective to a **proposal
distribution** ("imagination") and make the primary signal **survival under
severe automated criticism** (a Refutation Engine; AlphaZero generalised to an
open domain). The two things that make this **not** RLVR / AlphaProof / Absolute
Zero: we condition the proposer on a **structured genealogy of *why* conjectures
failed** (those systems keep only pass/fail), and we score conjectures by
**explanatory content / hard-to-vary-ness** (those systems optimise mere
validity or solvability).

## The contribution is the ablations (not the loop)

The loop alone is **not** the point. The deliverable is the two apples-to-apples
experiments in [`REPORT.md`](REPORT.md), each isolating one of the two
differentiators against an otherwise-identical control (same proposer, model,
topic, k, rounds, critic, budgets, seed list — differing in exactly one variable):

- **Genealogy ablation (H2).** Treatment (`mode=genealogy`, the proposer sees
  *why* past conjectures died and which survivors to build on) vs control
  (`mode=control`, prior statements listed for dedup only, no reasons).
  ![Genealogy ablation](results/plots/ablation_genealogy.png)
  Over 3 seeds, treatment reached 6.00±2.16 cumulative certified-novel survivors
  vs 7.00±0.82 for control. **Reported honestly:** at this tiny budget the
  treatment does *not* lead on the headline count, but it pushes the proposer
  toward harder, less-trivial conjectures (lower trivial rate) — see REPORT.md
  for the full reading. The mechanism and the per-compute benchmark are the
  claim; a larger budget is needed to test whether that compounds.

- **Significance ablation (reward-hack guard).** Trivial/vacuous "survivors" rate,
  significance critic ON vs OFF, judged by an *independent* automation probe.
  ![Significance ablation](results/plots/ablation_significance.png)
  Turning the critic ON drops the trivial-survivor rate from 0.34±0.29 to
  0.00±0.00 over 3 seeds — the hard-to-vary guard catches the reward-hack that
  "it compiled / it passed" optimisers fall for.

## Headline KPI (the "certified-novelty-per-compute" benchmark)

From the **real** sandboxed code-exec critic demo (`metrics.json`):

| metric | value |
| --- | --- |
| certified-novel survivors | **6** (of 18 conjectures, 3 rounds) |
| `certified_novel_per_kilo_token` | **0.628** |
| `certified_novel_per_critic_hour` | **26,180** |

The top survivors — each with its verifiable proof/tests, significance breakdown,
and the **failed genealogy siblings that explain why they died** — are in
[`SURVIVORS.md`](SURVIVORS.md). None is hand-authored; all came from the loop.

## One-command reproduction

```bash
make install        # editable install (numpy, pyyaml, matplotlib, anthropic, dotenv, sentence-transformers)
make demo           # REAL sandboxed code-exec critic -> results/<run>/{ledger.jsonl,metrics.json,artifacts.json}
```

Then regenerate the curated artifacts from that run:

```bash
make ablation                              # both experiments (>=3 seeds) + plots + REPORT.md
python -m experiments.make_survivors       # SURVIVORS.md from the latest real run
```

Other targets: `make smoke` (full loop on the **mock** critic in <60s — for
architecture validation only, never a reported result), `make test` (pytest incl.
the §5.2 perturbation/triviality fixtures).

The proposer uses a real Anthropic model when a key is present in a gitignored
`.env` (`CRM_PROPOSER_PROVIDER`, `CRM_PROPOSER_MODEL`, `ANTHROPIC_API_KEY`); with
no/invalid key it degrades to a **deterministic offline candidate generator**, so
`make demo` still produces real-critic-verified survivors offline.

### Lean headline track (optional)

`scripts/setup_lean.sh` installs `elan`, pins a Lake project to a stable mathlib,
and runs `lake exe cache get` (prebuilt oleans — the setup-time trick). Then:

```bash
make demo CONFIG=configs/lean_nt.yaml      # Lean 4 / mathlib critic, number theory
```

**Status (honest):** the Lean toolchain is wired and works (it really compiles
candidates via `lake env lean`), but at the demo budget it produced **0
certified-novel survivors** (most candidates hit `UNPROVEN_BUDGET`; the one that
proved did not survive the significance critic). **The headline therefore rests on
the code-exec critic**, exactly as the build plan permits as the floor (§13/§14).
Lean is the path to the formal-novelty headline; closing it needs more proof
budget and proof-search retries (see [`ROADMAP.md`](ROADMAP.md)).

## How this differs from RLVR / AlphaProof / Absolute Zero

Those systems keep only **pass/fail** and optimise **validity / solvability**. We
keep a **reasoned genealogy** (*why* each conjecture failed — refuted-with-
counterexample, rejected-trivial-with-hardness) and feed it back in-context, and
we add a **significance critic** that computes **hard-to-vary-ness**: a contentful
theorem is surrounded by false neighbours (high hardness), a trivial truth is not
(low hardness). That is what suppresses the "it compiled" reward-hack and is what
the §9 ablations measure. If the genealogy ever degraded to pass/fail, or
significance to "it compiled," the novelty would be gone (§15).

## Honest limits (read this)

- **Frozen proposer.** No weight updates in this prototype; the genealogy and
  significance mechanisms are demonstrated via **in-context** conditioning only.
  Weight-update RL is Tier-1 future work — see [`ROADMAP.md`](ROADMAP.md).
- **Operational — not formal — novelty.** `certify_novel` is a corpus-match +
  automation + embedding-distance **proxy** for a prototype. **Formal
  independence** (the rigorous version) is a Stage-1/2 deliverable, not claimed here.
- **Small scale.** A miniature artifact: ~18 conjectures over 3 rounds, 3 seeds.
  The headline is the **mechanism** and the **per-compute benchmark**, not raw
  output volume. The genealogy ablation does not yet show a certified-novel lead
  at this budget; we report that plainly.
- **The mock critic is never a result.** `MockCritic` validates the
  loop/ledger/accounting/harness in seconds; no reported number uses it (§3).
- **API non-determinism.** With the API proposer, sampling is seeded but the
  endpoint is not bit-reproducible; the offline generator is fully deterministic.

## Layout

See [`BUILD_SPEC.md`](BUILD_SPEC.md) §4. The three load-bearing components (§5):
the genealogy ledger + conditioning (`crm/genealogy.py`), the hard-to-vary
significance critic (`crm/significance.py`, `crm/perturb.py`), and operational
novelty certification (`crm/novelty.py`). Critics live in `crm/critics/`
(`mock.py`, `code_exec.py` + `sandbox.py`, `lean.py`); the loop is `crm/loop.py`;
accounting is `crm/accounting.py`; experiments + report/survivors generators are
in `experiments/`.
