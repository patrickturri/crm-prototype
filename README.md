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
  ![Genealogy ablation](docs/assets/ablation_genealogy.png)
  *Reading: at this tiny budget the treatment trails the control on the headline
  certified-novel count (6.0±2.2 vs 7.0±0.8) — reported honestly; the mechanism,
  not the count, is the claim.*
  Over 3 seeds, treatment reached 6.00±2.16 cumulative certified-novel survivors
  vs 7.00±0.82 for control. **Reported honestly:** at this tiny budget the
  treatment does *not* lead on the headline count, but it pushes the proposer
  toward harder, less-trivial conjectures (lower trivial rate) — see REPORT.md
  for the full reading. The mechanism and the per-compute benchmark are the
  claim; a larger budget is needed to test whether that compounds.

- **Significance ablation (reward-hack guard).** Trivial/vacuous "survivors" rate,
  significance critic ON vs OFF, judged by an *independent* automation probe.
  ![Significance ablation](docs/assets/ablation_significance.png)
  *Reading: turning the critic ON drops the trivial-survivor rate from 0.34±0.29
  to 0.00±0.00 over 3 seeds — the hard-to-vary guard catches the reward-hack that
  "it compiled / it passed" optimisers fall for.*

## Headline KPI (the "certified-novelty-per-compute" benchmark)

From the **real** sandboxed code-exec critic demo (`metrics.json`):

| metric | value |
| --- | --- |
| certified-novel survivors | **7** (seed 0; of 18 conjectures, 3 rounds — 3-seed mean **6.0±2.2**, see REPORT.md) |
| `certified_novel_per_kilo_token` | **0.756** |
| critic compute | **0.58s** total to certify 7 (~**32 ms**/conjecture) |

We report critic cost as the measured seconds-per-survivor rather than an
hourly rate: annualizing a 0.58s sample to a "per critic-hour" figure (~43k)
is a ~6000× extrapolation, so we quote the measurement instead of the
extrapolation. `per_kilo_token` is the headline per-compute KPI.

The top survivors — each with its verifiable proof/tests, significance breakdown,
and the **failed genealogy siblings that explain why they died** — are in
[`docs/SURVIVORS.md`](docs/SURVIVORS.md). None is hand-authored; all came from the
loop. The full run is also browsable in the offline
**[replay viewer](docs/replay/index.html)** (see *Shareable links* below).

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

## Shareable links (offline replay + GitHub Pages)

The whole run is browsable with **zero setup** in a single self-contained,
vanilla-JS page — no build step, no API, no Lean, no network:

- **[`docs/replay/index.html`](docs/replay/index.html)** — double-click it (or
  serve `docs/`) to replay the real run: a scrubbable round-by-round timeline,
  conjecture cards coloured by `reason_class` (PROVED / FALSE / UNPROVEN_BUDGET /
  TRIVIAL / DUPLICATE), each showing the statement, gloss, refutation detail, the
  three significance mini-bars (novelty / breadth / hardness) + a certified-novel
  badge, and — under each survivor — the **failed siblings** the genealogy
  explains. Filter toggles: all / survivors only / certified-novel only.
  It reads **only** the committed, sanitized [`docs/replay/run.jsonl`](docs/replay/run.jsonl)
  (a real `ledger.jsonl` with keys/paths stripped).

The rendered report and survivors live under `docs/` too:
[`docs/REPORT.md`](docs/REPORT.md) · [`docs/SURVIVORS.md`](docs/SURVIVORS.md) ·
plots in `docs/assets/`.

**GitHub Pages (one setting to flip).** The repo is already structured to serve
`docs/`. After pushing, in the repo **Settings → Pages**, choose
**Deploy from a branch → Branch: `main`, Folder: `/docs`**, Save. The replay
viewer is then live at:

```
https://<user>.github.io/<repo>/replay/
```

`make publish` regenerates the plots, refreshes the curated `docs/` assets, runs a
**secret-scan over tracked files** (fails loudly on any leaked API key, `.env`
assignment, or host path), then **prints** (does not execute) the
`git remote add … && git push`
and the Pages-toggle steps. `make record` captures `make demo` to `docs/demo.cast`
with `asciinema` if installed (else prints a screen-recorder / Loom note).

## IP mode (what the public repo tracks)

`scripts/prep_public.sh --mode {results-only|full}` chooses how much of the moat
ships publicly:

- **`results-only`** (default) — track `README.md`, all of `docs/` (report,
  survivors, replay, plots), and the loop/critic **interfaces**, but keep the two
  load-bearing critic sources — the hard-to-vary `crm/significance.py` (§5.2) and
  the reasoned `crm/genealogy.py` (§5.1) — out of the public tree by relocating
  them into a gitignored `PRIVATE/` (shared with reviewers separately). Protects
  the moat during the competition while still giving a public, rendered,
  interactive link.
- **`full`** — track everything, including the significance + genealogy sources.

Add `--dry-run` to print exactly what *would* be excluded/moved without touching
the working tree:

```bash
scripts/prep_public.sh --mode results-only --dry-run   # non-destructive preview
```

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
