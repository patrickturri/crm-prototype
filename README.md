# Critical-Rationalist Machine (CRM) — prototype

A minimal, end-to-end prototype of a machine that *creates* certified-novel
knowledge by **bold conjecture → severe automated criticism → retention of
survivors and of the reasoned genealogy of failures**, rather than by predicting
the human-text distribution.

**Thesis (3 sentences).** Today's LLMs interpolate human knowledge but cannot
certify *new* knowledge against reality — a limitation of their fit-to-text
objective, not of neural nets. We demote a frozen model from a terminal
objective to a **proposal distribution** and make the primary signal **survival
under severe automated criticism** (a Refutation Engine). Two things make this
not RLVR/AlphaProof/Absolute Zero: we condition the proposer on a **structured
genealogy of *why* conjectures failed**, and we score conjectures by
**explanatory content / hard-to-vary-ness**, not mere validity.

## One-command reproduction

```bash
make install        # editable install (pyyaml, numpy)
make smoke          # full loop on the MockCritic in <60s -> results/<run>/
```

`make smoke` writes `results/<run>/ledger.jsonl` (the §5.1 genealogy schema) and
`results/<run>/metrics.json` (the per-compute KPIs). `make test` runs pytest.

Later phases add `make demo` (real code-exec / Lean critic) and `make ablation`
(the two experiments + plots).

## How this differs from RLVR / AlphaProof / Absolute Zero

Those systems keep only **pass/fail** and optimise **validity/solvability**. We
keep a **reasoned genealogy** (*why* each conjecture failed) and feed it back
in-context, and we add a **significance critic** that scores **hard-to-vary-ness**
(a contentful theorem is surrounded by false neighbours; a trivial truth is
not), suppressing reward-hacks like vacuous "it compiled" survivors.

## Honest limits (read this)

- **Frozen proposer.** No weight updates in this prototype; the genealogy and
  significance mechanisms are demonstrated via *in-context* conditioning only.
  Weight-update RL is future work (see `ROADMAP.md`).
- **Operational — not formal — novelty.** `certify_novel` is a corpus-match +
  automation + embedding-distance proxy for a prototype; formal independence is
  a later research deliverable, not claimed here.
- **The mock critic is NOT a result.** `MockCritic` exists only to validate the
  loop/ledger/accounting/harness in seconds. No reported number ever uses it.
- **Small scale.** This is a miniature artifact; the headline is the
  *mechanism* and the per-compute benchmark, not raw output volume.
- **Phase 0 status.** This commit is the skeleton: the significance hardness
  computation, the real critics, the corpus, and the ablations are stubbed with
  honest floors (return-False / mark-trivial) and filled in later phases. The
  `data/corpus.jsonl` here is a 3-row placeholder; the real mathlib NT corpus
  arrives with the Lean track.

## Layout

See `BUILD_SPEC.md` §4. Core types live in `crm/critics/base.py` and
`crm/significance.py`; the loop is `crm/loop.py`; the genealogy ledger is
`crm/genealogy.py`; accounting is `crm/accounting.py`.
