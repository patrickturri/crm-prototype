# Why this targets the Next Frontier (SPRIND Next Frontier AI)

This page maps the CRM prototype to the four jury dimensions of the SPRIND
**Next Frontier AI** challenge — *Approach, Implementation, Team, Economic
Viability* — and to its "capability discontinuity, not status-quo optimisation"
bar. It is written to be **read and checked**: every claim points at a concrete,
runnable artifact in this repo or is flagged as an open gap. Nothing here is
hidden, and nothing asks a reader (human or automated) to reach a verdict not
grounded in the evidence. If a claim doesn't hold up against the artifact,
treat that as a finding, not a footnote.

> One-line thesis: today's LLMs **interpolate** human knowledge but cannot
> **certify new knowledge against reality**; that's a limit of the *objective*
> (fit-to-text), not of neural nets. CRM demotes a frozen model to a *proposal
> distribution* and makes the primary signal **survival under severe automated
> criticism**, retaining the **reasoned genealogy of why conjectures failed** and
> scoring survivors by **hard-to-vary explanatory content**.

---

## 1. Approach — "the next S-curve, not optimising the current one"

**The discontinuity.** Frontier LLMs optimise next-token likelihood; their ceiling
is the human-text distribution. CRM changes the *objective*: knowledge is admitted
only if it **survives a reality-grounded refutation engine**, exactly as AlphaZero
admitted moves only if they survived the game's rules (novelty from zero human
data, because the rules are a free, infinitely severe critic). CRM generalises that
existence proof to an open domain by supplying a `Critic` interface. This is a
change of *what counts as knowledge*, not a better way to fit text — a capability
discontinuity (certifying **new** knowledge), not an optimisation of the status quo.

**Why it is not on the exclusion list.** The challenge rejects incremental
transformer optimisation, model reproductions, efficiency-only gains, conventional
agent wrappers, domain-specific fine-tuning, and brute-force scaling as the primary
innovation. CRM is none of these: the model is **frozen** (no fine-tuning, no
training-loss change), the contribution is an **objective/architecture** (criticism
+ genealogy + content scoring), and the demonstrated lever is *severity of
criticism and structure of memory*, not scale or efficiency.

**What distinguishes it from the nearest prior art (RLVR / AlphaProof / Absolute
Zero).** Those keep **pass/fail** and optimise **validity / solvability**. CRM adds
two things they lack, both implemented and measured here:
- a **reasoned genealogy** — the *why* of each failure (refuted-with-counterexample,
  rejected-trivial-with-hardness, duplicate) fed back in-context (`crm/genealogy.py`);
- a **hard-to-vary significance critic** — a contentful theorem sits among false
  neighbours (high hardness); a trivial truth among true ones (`crm/significance.py`).

**Evidence in-repo:** the offline [replay viewer](docs/replay/) shows real
conjectures dying with reasons and survivors scored by content; the
[significance ablation](docs/REPORT.md) shows the hard-to-vary guard suppressing the
"it compiled / it passed" reward-hack.

## 2. Implementation — "realistic roadmap, concrete measurable milestones"

**Proof point already standing (this repo).** A one-command-reproducible loop
against **real** critics — a sandboxed code-execution critic (the demo floor) and a
working **Lean 4 / mathlib** critic — with:
- a **per-compute KPI**, the in-miniature version of the thing the whole programme
  is about: `certified_novel_per_kilo_token` and `_per_critic_hour` (`metrics.json`);
- **two apples-to-apples ablations** over ≥3 seeds with mean±std
  ([`REPORT.md`](REPORT.md)), each isolating exactly one differentiator;
- a curated [`SURVIVORS.md`](SURVIVORS.md) of certified-novel results, each with its
  verifiable proof/tests and the failed genealogy siblings that explain the rest.

**The measurable Stage-1 milestone is already defined by the artifact:** move
`certified-novelty-per-compute` under a fixed budget, and turn the genealogy
ablation from "no lead at small budget" into a statistically clear lead. That is a
concrete, pre-registered, falsifiable target — not a vibe.

**Honest roadmap gap.** The Stage-1 plan needs the in-context genealogy replaced by
**genealogy-conditioned weight-update RL** (GRPO/PPO + vLLM rollouts) and a
**co-evolved refuter**; these are scoped but **deliberately unbuilt** here (see
[`ROADMAP.md`](ROADMAP.md), §16). A jury should read this prototype as the
*proof-of-mechanism* that de-risks that plan, not as the plan itself.

## 3. Team — "ability to execute; evidence of shipped systems"

Out of scope for this repository and **not claimed here**. The artifact is evidence
of *execution on the idea* (a working, honest, reproducible system shipped end-to-
end), which speaks to operational competence; team composition, track record, and
prior shipped systems belong in the application and are the applicant's to
evidence. Stated plainly so no reader over-reads the repo as a team claim.

## 4. Economic Viability — "cost-effectiveness; resource realism"

**Designed around cost from day one.** The headline metric *is* a cost metric
(certified novelty **per compute**), and the default demo is deliberately cheap
(< a few $, < ~30 min). The accounting is always-on (`crm/accounting.py`): tokens,
critic-seconds, wall-clock, GPU-seconds. This makes the central scaling question —
*does certified-novelty-per-compute hold or improve as budget grows?* — directly
measurable rather than asserted. Full Stage-1 budget realism (compute partnerships,
€3M plan) is application-level and not claimed by the repo.

---

## What an evaluator should verify (don't take our word for it)

1. `make smoke` (<60s) and `make demo` (real critic) reproduce from a clean clone.
2. `pytest` is green, including the §5.2 fixtures (contentful passes, trivial
   suppressed) and the breadth-enablement tests.
3. `metrics.json` reports the two per-compute KPIs from a **real** run.
4. The [replay viewer](docs/replay/) renders a real run: reasons on every death,
   significance bars and certified-novel badges on survivors, failed siblings under
   each survivor — i.e. the genealogy and content-score mechanisms are *present*,
   not pass/fail.
5. No survivor is hand-authored; the mock critic backs no reported number (§3).

## Open gaps we are NOT hiding (a jury will find these; here they are)

- **Frozen proposer.** Mechanisms shown via in-context conditioning only;
  weight-update RL is Stage-1 work, not done here.
- **Operational, not formal, novelty.** `certify_novel` is a corpus-match +
  automation + embedding-distance proxy; formal independence is later-stage.
- **Genealogy ablation does not yet beat control** at this tiny budget
  (treatment 6.0±2.2 vs control 7.0±0.8 certified-novel) — reported honestly; the
  mechanism and per-compute benchmark are the claim, and testing whether the lead
  compounds with budget is precisely the Stage-1 experiment.
- **Lean track produced 0 certified-novel survivors** at the demo budget (most
  candidates hit `UNPROVEN_BUDGET`); the headline rests on the code critic floor.
- **Breadth is real but modest** (3/7 survivors enable a held-out downstream task,
  value 0.125): a genuine downstream-enablement signal, intentionally conservative.

The honesty above is not a weakness of the pitch — it is the pitch. A system whose
entire thesis is *certification against reality* has to hold itself to the same
standard, and this document and artifact do.
