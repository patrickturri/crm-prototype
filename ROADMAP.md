# ROADMAP — Tier-1 seams (out of scope for v0.1)

This prototype deliberately stops at a **frozen-proposer, in-context** demonstration
of the two load-bearing mechanisms (reasoned genealogy + hard-to-vary significance).
The point of v0.1 is to show those mechanisms move the needle (the §9 ablations),
cheaply and reproducibly. The items below are the **Tier-1 / Stage-1** work the grant
funds. They are scaffolded for, **not built** (§16). Each notes the seam already in
the code where it plugs in.

## 1. Genealogy-conditioned weight-update RL (replace in-context with training)

Today the genealogy steers the proposer purely **in-context** via
`genealogy.build_conditioning_context(...)`. Tier 1 turns survival-under-criticism
into a **reward** and updates the proposer's weights.

- **Stack:** GRPO/PPO via `veRL` with `vLLM` rollouts (the Absolute-Zero-style stack),
  but with our differentiators baked into the reward: shape it by the **significance
  score** (not bare pass/fail) and condition rollouts on the **reasoned genealogy**.
- **Seam:** the `Proposer` ABC (`crm/proposer.py`) is already the only thing the loop
  talks to; a `TrainableProposer` slots in behind the same `.propose(context, k, seed)`
  signature. The ledger (`results/<run>/ledger.jsonl`) is already the exact
  `(conjecture, refutation, reason, significance)` trajectory a trainer needs.
- **Why it matters:** in-context conditioning has a fixed budget; training is how the
  genealogy compounds across thousands of rounds.

## 2. Co-evolved refuter / adversary policy

Today the critic is fixed (code-exec / Lean). Tier 1 trains a **refuter** that
actively searches for counterexamples and severe perturbations, co-evolving against
the proposer (AlphaZero-style self-play, generalised to an open domain).

- **Seam:** the `Critic` ABC (`crm/critics/base.py`) and the perturbation engine
  (`crm/perturb.py`, `crm/significance.py`) are the natural homes — the perturbation
  operators become a *learned* adversary policy rather than fixed string/AST mutations.
- **Guardrail:** validity must stay **reality-grounded** (real execution / Lean), never
  LLM-as-judge (§3, §15). The refuter proposes attacks; the ground-truth critic adjudicates.

## 3. Multi-domain critics

Today: code-exec (floor) + Lean 4/mathlib (headline) on elementary number theory.
Tier 1 adds **hardware / formal-methods** critics (e.g. SMT, model checkers,
synthesis-and-verify), broadening the open domain over which novelty is certified.

- **Seam:** add new classes under `crm/critics/` implementing the same
  `check(conjecture) -> CritResult` contract; the loop, ledger, significance, and
  accounting are domain-agnostic already.

## 4. Formal novelty (upgrade the operational proxy)

Today `certify_novel` is an **operational** proxy (corpus-match + automation +
embedding-distance — stated honestly in the README). Tier 1 replaces it with a
**formal independence** check (e.g. not derivable from the existing library within a
bounded formal search), which is the rigorous version of "new knowledge."

- **Seam:** `crm/novelty.py::certify_novel(...)` is the single chokepoint; the corpus
  (`data/corpus.jsonl`) and the Lean critic already provide the substrate.

## 5. Scale + breadth signal

Today `breadth` (downstream enablement) is wired and computed but small/zero at this
budget. Tier 1 grows the held-out target set `M` and the round/seed budget so the
breadth signal and the certified-novel lead have room to compound.

- **Seam:** `crm/significance.py` (breadth computation) and the YAML configs already
  expose `M`, `rounds`, `k`, and seeds — Tier 1 is mostly a budget knob plus a larger,
  curated corpus and target set.
