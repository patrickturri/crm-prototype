# BUILD SPEC — Critical-Rationalist Machine (CRM) Prototype

> **How to use this file:** Save it at the repo root and tell Claude Code: *"Implement BUILD_SPEC.md. Follow the phased plan in §13, run the checkpoint after each phase, commit on green, and never fabricate results."* You may also paste it as your first message. The agent has latitude on plumbing (marked **[latitude]**) and must follow the spec exactly on the three load-bearing novel components (§5), which are the point of the project.

---

## 1. Mission & context

We are building a **minimal but real, end-to-end** prototype of a Critical-Rationalist Machine: a system that *creates* certified-novel knowledge by **bold conjecture → severe automated criticism → retention of survivors and of the reasoned genealogy of failures**, rather than by predicting the human-text distribution.

The thesis (you need this to make good micro-decisions, especially in §5):

- Today's LLMs interpolate human knowledge but cannot **certify new knowledge against reality**. That is a limitation of their *objective* (fit-to-text), not of neural nets.
- We demote a pretrained model from a terminal objective to a **proposal distribution** (the "imagination"). The primary signal becomes **survival under severe criticism**.
- The existence proof is AlphaZero (superhuman, novel, zero human data — because the game's rules are a free, infinitely severe critic). We generalise that to an open domain by supplying a **Refutation Engine**.
- The two things that make this **not** just RLVR/AlphaProof/Absolute Zero: (i) we condition the proposer on a **structured genealogy of *why* conjectures failed** (those systems keep only pass/fail); (ii) we score conjectures by **explanatory content / hard-to-vary-ness** (those systems optimise mere validity or solvability).

**What "done" looks like as an artifact:** a clean, one-command-reproducible repo that runs the loop against a *real* formal critic, plus two ablation experiments with plots, a `metrics.json` with a `certified-novelty-per-compute` figure, and a `SURVIVORS.md` showcasing certified-novel results next to the failed siblings that the genealogy explains. This artifact is going into a grant application and an in-person pitch; treat polish and honesty as load-bearing.

---

## 2. What you are building (in one paragraph)

A loop in which a **Proposer** (frozen LLM, pluggable API or local open-weight) generates a batch of formal conjectures with proof attempts; a **Refutation Engine** (a `Critic` — mock → code-execution → Lean 4/mathlib) grades each as valid/invalid with a *structured reason*; a **Significance critic** scores each survivor for novelty, breadth, and hard-to-vary-ness, flagging trivial/vacuous survivors; a **Genealogy ledger** records every `(conjecture, refutation, reason, significance)` and is used to **condition the next round's prompt**; and an **Accountant** meters tokens/compute/time. The headline outputs are two ablations proving the genealogy and significance mechanisms add value, plus a curated list of certified-novel survivors.

---

## 3. Non-negotiables (read before writing code)

1. **Never fabricate results.** No hard-coded "novel theorems," no faked metrics, no mocked critic in the final demo. Every survivor in `SURVIVORS.md` must have been produced by a real critic on a real run, with its proof/tests attached. If a run is weak, report it weak.
2. **The final demo uses a real critic** (code-exec at minimum, Lean for the headline). The mock critic exists only to validate the loop architecture in seconds.
3. **Foreground the ablations.** The genealogy and significance experiments (§9) are the deliverable, not garnish. The loop alone is *not* the contribution — say so in the README.
4. **Do not let it collapse into RLVR.** If at any point the genealogy is reduced to "list of passed/failed statements" with no *reasons*, or significance is reduced to "it compiled," you've destroyed the novelty. The reasoned genealogy and the hard-to-vary score are the differentiators.
5. **Apples-to-apples experiments.** Treatment and control must differ in exactly one variable (§9). Same proposer, seeds, budgets, critic.
6. **Sandbox all model-generated code** (§6.2). Assume conjectures/proofs are adversarial.
7. **Determinism & accounting always on.** Seed everything; log tokens, critic-seconds, wall-clock, and (if local) GPU-seconds for every round.

---

## 4. Architecture & interfaces

```
critical-rationalist-machine/
  README.md  pyproject.toml  Makefile
  configs/            smoke.yaml  code.yaml  lean_nt.yaml
  crm/
    proposer.py       # Proposer ABC + APIProposer + LocalProposer
    critics/
      base.py         # Critic ABC, CritResult dataclass
      mock.py         # MockCritic (trivial, for architecture smoke test)
      code_exec.py    # sandboxed Python execution critic
      lean.py         # Lean 4 / mathlib critic  <-- headline
    significance.py   # novelty, breadth, hardness(perturbations) -> Significance
    genealogy.py      # Ledger, Entry schema, build_conditioning_context()
    novelty.py        # certify_novel(): corpus-match + automation + embedding-distance
    loop.py           # CRMLoop orchestrator
    accounting.py     # Accountant: tokens/compute/time meter
    run.py            # CLI entrypoint
  experiments/
    ablation_genealogy.py
    ablation_significance.py
    make_report.py    # renders REPORT.md + plots from results/
  scripts/setup_lean.sh
  data/               # corpus statements (jsonl), seed topics
  results/            # gitignored; metrics.json, plots/, survivors/
  tests/              # pytest
```

Core types (define these exactly; everything else is **[latitude]**):

```python
# critics/base.py
@dataclass
class CritResult:
    valid: bool
    reason_class: str        # one of: PROVED, FALSE, UNPROVEN_BUDGET, ILLFORMED, TIMEOUT, DUPLICATE
    detail: str              # human-readable: error msg / counterexample / proof method used
    proof_method: str | None # e.g. "supplied", "aesop", "omega", "tests_passed"
    critic_seconds: float

class Critic(ABC):
    name: str
    @abstractmethod
    def check(self, conjecture: "Conjecture") -> CritResult: ...
    # MUST be reality-grounded for the real critics. No LLM-as-judge for validity.

# significance.py
@dataclass
class Significance:
    novelty: float      # 0..1, distance from corpus / inverse base-model familiarity
    breadth: float      # 0..1, downstream enablement
    hardness: float     # 0..1, fraction of perturbed neighbours that break
    is_trivial: bool    # closeable by automation alone OR hardness < tau
    score: float        # weighted combo; 0 if is_trivial
```

---

## 5. THE THREE LOAD-BEARING COMPONENTS (follow exactly)

### 5.1 Genealogy ledger + conditioning  *(this is H2 — the core novelty)*

**Ledger entry** (persist as JSONL in `results/<run>/ledger.jsonl`):

```json
{
  "id": "c_0042",
  "round": 3,
  "parent_ids": ["c_0017"],
  "statement": "∀ (n : ℕ), Nat.gcd n (n + 1) = 1",
  "nl_gloss": "consecutive naturals are coprime",
  "proof_attempt": "by simp [Nat.gcd_comm, Nat.succ_eq_add_one]; omega",
  "crit": {"valid": true, "reason_class": "PROVED", "detail": "compiled", "proof_method": "supplied", "critic_seconds": 1.8},
  "significance": {"novelty": 0.74, "breadth": 0.40, "hardness": 0.86, "is_trivial": false, "score": 0.71},
  "surviving": true,
  "certified_novel": true
}
```

**Conditioning context** — `build_conditioning_context(ledger, topic, k) -> str`. This is the mechanism that distinguishes us. For the **treatment** condition it produces a token-budgeted prompt block like:

```
You are extending a body of formally verified mathematics about: {topic}.

Past attempts and WHY they failed — do not repeat these failure modes:
- "∀ n, n ≤ n + 2"  — REJECTED: trivial (closed by `omega`; hardness 0.05).
- "∀ n, Nat.gcd n (n+2) = 1"  — REFUTED: false, counterexample n = 2 (gcd = 2).
- "∀ n, Nat.gcd n (n+1) = 1"  — DUPLICATE of a result already found.

Surviving, high-content results so far — generalise or build on these:
- "∀ n, Nat.Coprime n (n+1)"  (content score 0.71)

Now propose {k} NEW conjectures about {topic} that are (a) likely TRUE,
(b) NON-trivial / hard-to-vary (small changes to them should make them false),
(c) NOT restatements of the above or of standard-library lemmas.
Return strict JSON: [{statement, proof_attempt, nl_gloss, rationale}, ...] in Lean 4 syntax.
```

For the **control** condition it produces the *same* prompt **minus the reasons, significance, and "build on / avoid" guidance** — it still lists prior *statements* (so both conditions deduplicate equally), but gives no genealogy of *why*. This isolates the value of the reasoned genealogy from mere deduplication. Implement both via a `mode: "genealogy" | "control"` flag.

### 5.2 Significance / hard-to-vary critic  *(this is the moat — operationalises Deutsch)*

Compute three signals for each **valid** conjecture; `score = w_n·novelty + w_b·breadth + w_h·hardness`, default weights `(0.3, 0.3, 0.4)`, **forced to 0 if `is_trivial`**.

- **novelty (0..1):** `1 - cosine_sim(embed(statement), nearest_corpus_statement)`. Use a local embedder (`sentence-transformers/all-MiniLM-L6-v2` by default; **[latitude]** to swap a math-aware model). If using a *local* Proposer, optionally average in `1 - normalized_logprob(statement | base_model)` as a familiarity proxy.
- **breadth (0..1):** of a held-out set of `M` *other* target conjectures (from `data/`), the fraction that become provable by automation **when this lemma is added as an available hypothesis**, normalised. This is a real, computable "downstream enablement" signal. Keep `M` small (e.g. 8) and budget-limited.
- **hardness (0..1) — THE KEY SIGNAL:** generate `P` syntactic/semantic **perturbations** of the load-bearing parts of the statement, re-run the critic on each (same proof budget, automation allowed), and set `hardness = (# perturbations that are NOT provable) / P`. A contentful theorem is surrounded by false neighbours (high hardness); a trivial/vacuous truth has many true neighbours (low hardness). Perturbation operators (implement on the parsed statement; AST if you build a parser, else careful string transforms with validation):
  - **constant mutation:** numeric literals `k → k±1`, `0 ↔ 1`.
  - **operator swap:** `≤ ↔ <`, `+ ↔ -`, `∣ ↔ ≠`, `∧ ↔ ∨`, `= ↔ ≠`.
  - **quantifier/hypothesis edit:** drop a hypothesis; `∀ ↔ ∃`; negate a conjunct.
  - **argument-order swap** on asymmetric relations.
- **is_trivial:** `True` if the statement is closed by automation **alone** (`by simp` / `by omega` / `by decide` / `by tauto`, no supplied proof) **OR** `hardness < tau` (default `tau = 0.25`). Trivial ⇒ `score = 0`.

**Worked examples** (use as test fixtures):
- *Contentful:* `∀ n, Nat.gcd n (n+1) = 1`. Perturb → `gcd n (n+2)=1` (false at n=2), `gcd n (n+1)=0` (false), `gcd (n+1) n = 1` (true, symmetric). Most break ⇒ hardness ≈ 0.8 ⇒ contentful. ✅
- *Trivial:* `∀ n, n ≤ n+1`. Closed by `omega` alone, and neighbours `n ≤ n+2` etc. also true ⇒ `is_trivial = True` ⇒ score 0. ❌ (correctly suppressed — this is the reward-hack the critic must catch.)

### 5.3 Novelty certification  *(operational, honest proxy — flag limits in README)*

`certify_novel(statement) -> bool` requires **all** of:
1. **not a corpus restatement:** after normalisation, no exact/near AST or string match to any statement in `data/corpus.jsonl` (a subset of mathlib declaration signatures).
2. **not cheaply derivable:** not closed by `exact?` / `aesop` / `simp` / `omega` within a small budget against the corpus (so it isn't a one-liner the library already implies).
3. **retrieval-distant:** `novelty ≥ delta` (default 0.35) — embedding distance from nearest corpus statement.

In the README, state plainly that this is an **operational** novelty test for a prototype; **formal independence** (the rigorous version) is a Stage-1/2 research deliverable, not claimed here.

---

## 6. Critics (build in this order)

### 6.0 MockCritic
Returns `valid` by a trivial rule (e.g. statement parses and contains no `sorry`), `reason_class` random among the enum for a few, instant. Purpose: validate the loop, ledger, accounting, and experiment harness in <60s with zero heavy deps. **Not used in any reported result.**

### 6.1 CodeExecCritic  *(first real critic — fast, no large downloads)*
Domain: the Proposer invents `{function_spec, reference_impl (Python), tests (asserts), nl_gloss}`. Validity = reference impl passes all its own tests **and** at least one independently-generated adversarial test, executed in the sandbox. `reason_class`: `PROVED` (all pass), `FALSE` (a test fails / wrong output), `ILLFORMED` (won't parse/import), `TIMEOUT`. Significance perturbations mutate the spec/constants and re-run. This gives a real end-to-end demo within minutes and exercises every interface.

**[latitude]** on the exact task schema, but keep it genuinely verifiable (real execution, not LLM judgement).

### 6.2 Sandboxing (mandatory for 6.1)
Run each candidate in a subprocess with: hard wall-clock timeout (e.g. 5s), no network, an ephemeral temp dir, restricted builtins / a fresh interpreter, memory cap. Prefer `nsjail`/`firejail` or a disposable Docker container if available; otherwise `subprocess` with `resource` limits + `timeout`. **[latitude]** on mechanism; **non-negotiable** that arbitrary generated code cannot touch the network or the host FS outside its sandbox.

### 6.3 LeanCritic  *(headline — do this once 6.1 is green)*
- **Setup (`scripts/setup_lean.sh`):** install `elan`; create a Lake project pinned to a recent stable `mathlib` (set `lean-toolchain` to match mathlib's); **`lake exe cache get`** to download the *prebuilt* mathlib oleans (this is the trick that turns hours of compilation into a ~10–20 min download — do NOT compile mathlib from source); `lake build` to confirm. If setup exceeds ~30 min or fails, **fall back to 6.1, log the reason, and continue** — do not block the whole build on Lean.
- **Check:** for each conjecture, write `Mathlib`-importing file:
  ```lean
  import Mathlib
  theorem crm_candidate : <statement> := <proof_attempt>
  ```
  Compile via `lake env lean <file>` with a per-candidate timeout. `valid = (exit 0 and no errors and no `sorry`)`. If the supplied proof fails, optionally retry once with `by aesop` / `by omega` / `by simp` / `by decide` and record `proof_method` accordingly (this distinguishes "supplied proof" from "automation-closed", which feeds `is_trivial`). Map failures: type/parse error → `ILLFORMED`; proof incomplete in budget → `UNPROVEN_BUDGET`; refuted-by-`decide`/counterexample → `FALSE`; timeout → `TIMEOUT`.
- Robust parsing of the Proposer's JSON; on malformed Lean, one reformat retry, then count as `ILLFORMED` (do not crash the loop).

Domain for the demo: **elementary number theory** (divisibility, gcd/coprimality, primes, modular arithmetic) — rich enough for non-trivial conjectures, well-covered by mathlib automation. Provide `data/seed_topics.txt` and a `data/corpus.jsonl` of a few hundred mathlib NT statement signatures (fetch a declaration list or curate; **[latitude]** on method, but the corpus must be real mathlib statements so the novelty test means something).

---

## 7. Proposer (pluggable, frozen)

```python
class Proposer(ABC):
    def propose(self, context: str, k: int, seed: int) -> list[Conjecture]: ...
```
- **APIProposer** (default for speed): OpenAI-compatible or Anthropic endpoint via env vars (`CRM_PROPOSER_PROVIDER`, `CRM_PROPOSER_MODEL`, API key from env). Strict-JSON output, temperature & seed configurable, robust JSON repair.
  - **CONFIGURED ENVIRONMENT (this build):** an Anthropic key is provided in a gitignored `.env` at the repo root (`CRM_PROPOSER_PROVIDER=anthropic`, `CRM_PROPOSER_MODEL=claude-sonnet-4-6`, `ANTHROPIC_API_KEY=...`). The APIProposer MUST load it via `python-dotenv` (`load_dotenv()` from the repo root) so the real proposer is used for the code-critic demo and ablations. **Never commit `.env` or any key** — keep `.env`, `.env.*`, `*.key` in `.gitignore` at all times; do not print the key in logs, the ledger, REPORT.md, or SURVIVORS.md. If the key is absent/invalid at runtime, fall back to the deterministic offline candidate generator so the demo still produces real-critic-verified survivors.
- **LocalProposer** (the on-thesis option): HF `transformers` (or vLLM if a GPU is present). Default suggested weights: a current strong open math/code reasoning model (e.g. `Qwen2.5-Math-7B-Instruct` or `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`; **[latitude]** — pick the latest stable). Exposes token logprobs for the familiarity proxy.

The Proposer is **frozen** in this prototype — no weight updates. We demonstrate the genealogy/significance mechanisms via *in-context* conditioning. (Weight-update RL is Tier 1, §16.) The README must state this explicitly and honestly.

---

## 8. The CRM loop (pseudocode)

```python
def run(config):
    proposer, critic, sig, ledger, acct = build(config)
    for r in range(config.rounds):
        ctx = build_conditioning_context(ledger, config.topic, config.k, mode=config.mode)
        batch = proposer.propose(ctx, k=config.k, seed=config.seed + r)   # acct logs tokens
        for c in batch:
            cr = critic.check(c)                                           # acct logs critic_seconds
            entry = Entry(c, cr, surviving=cr.valid)
            if cr.valid:
                entry.significance = sig.score(c, critic, corpus)          # perturbations -> hardness
                entry.surviving = not entry.significance.is_trivial
                entry.certified_novel = entry.surviving and certify_novel(c.statement)
            ledger.add(entry)
        acct.snapshot(round=r)
    ledger.dump(); acct.dump_metrics()                                     # -> metrics.json
    export_survivors(ledger)                                               # -> SURVIVORS.md
```

---

## 9. Experiments (the deliverable)

Both write per-seed CSVs to `results/` and are rendered by `make_report.py`.

### 9.1 Genealogy ablation (`experiments/ablation_genealogy.py`) — tests H2
- **Treatment:** `mode="genealogy"`. **Control:** `mode="control"`. Everything else identical: same proposer, model, `topic`, `k`, `rounds`, critic, proof budgets. Same total conjecture count.
- **Seeds:** ≥3 (default 5). Report **mean ± std**.
- **Primary metric:** cumulative **certified-novel survivors** vs. round. **Secondary:** mean significance of survivors; survival rate; trivial rate.
- **Plot:** cumulative certified-novel survivors per round, treatment vs control, with std bands. **Expected/target:** treatment ≥ control with a visible, pre-registered margin. If it isn't, report honestly and analyse why.

### 9.2 Significance ablation (`experiments/ablation_significance.py`) — tests the reward-hack guard
- **With critic on** (trivial survivors get score 0 and are excluded) **vs. off** (any valid statement counts).
- **Metric:** fraction of "survivors" that are trivial/vacuous (by an independent automation check). **Expected:** sharply lower with the critic on. **Plot:** trivial-survivor rate, on vs off.

---

## 10. Compute / cost accounting → the KPI

`Accountant` meters, per round and total: proposer tokens in/out (+ est. cost if API), embedding calls, **critic invocations and critic wall-seconds**, total wall-clock, GPU-seconds (local). `metrics.json` must include the headline:

```
certified_novel_per_kilo_token     = certified_novel / (proposer_tokens / 1000)
critic_seconds_per_certified_novel = critic_seconds / certified_novel  # measured cost, NOT an hourly extrapolation
```

This *is* the "certified-novelty-per-compute" benchmark, in miniature. Keep the default config cheap (< a few $, < ~30 min end-to-end).

---

## 11. Config, reproducibility, determinism

- All runs driven by a YAML config (`topic, rounds, k, proposer{...}, critic, proof_budget_s, perturbations P, weights, thresholds tau/delta, seed, embedder`).
- Seed numpy/random and the proposer (temperature+seed); log model id/version. Note the API-nondeterminism caveat in the README.
- Cache critic results by `hash(statement+proof+critic+budget)` to avoid recompiling identical candidates across seeds/rounds.
- `configs/smoke.yaml` (mock critic, 2 rounds, k=4, instant), `configs/code.yaml` (code-exec), `configs/lean_nt.yaml` (Lean, number theory — the demo).

---

## 12. Required outputs (what the human walks away with)

1. **Reproducible repo**: `make smoke` (architecture, <60s), `make demo` (real critic, produces results), `make ablation` (both experiments + plots).
2. **`REPORT.md`** with the two ablation plots and a 1-paragraph reading of each.
3. **`SURVIVORS.md`** — the pitch artifact and the grant "Existing Artifacts" content. For the top ~5 certified-novel survivors:
   ```
   ### Coprimality of consecutive naturals
   Statement (Lean): ∀ n : ℕ, Nat.Coprime n (n+1)
   Proof method: supplied (verified by lake env lean)
   Significance: novelty 0.74 · breadth 0.40 · hardness 0.86 → 0.71
   Certified novel: yes (no corpus match; not closed by aesop/omega; retrieval-distance 0.74)
   Failed siblings from the genealogy (why these didn't survive):
     - "∀ n, Nat.gcd n (n+2) = 1" — REFUTED false (n=2)
     - "∀ n, n ≤ n+1" — REJECTED trivial (omega-closed; hardness 0.05)
   ```
4. **`metrics.json`** with the per-compute KPIs.
5. **README.md**: what this is, the thesis in 3 sentences, one-command repro, the honest-limits section (frozen proposer; operational—not formal—novelty; small scale), and a short "how this differs from RLVR/AlphaProof/Absolute Zero" note.

---

## 13. Phased build plan (commit on each green checkpoint)

- **Phase 0 — Skeleton.** Repo layout, `pyproject`, `Makefile`, type stubs, MockCritic, Accountant, Ledger, loop, `configs/smoke.yaml`. **Checkpoint:** `make smoke` runs the full loop on the mock critic in <60s and writes a ledger + metrics. Commit.
- **Phase 1 — Significance + genealogy on mock.** Implement §5.1 and §5.2 (perturbations, hardness, triviality, conditioning context, treatment/control). Unit-test the perturbation operators and the worked examples (5.2). **Checkpoint:** `pytest` green; smoke run shows trivial conjectures flagged and a genealogy context string built. Commit.
- **Phase 2 — CodeExecCritic + sandbox.** §6.1–6.2. **Checkpoint:** `make demo` (code config) produces real survivors with passing tests; sandbox blocks a network/FS escape test. Commit.
- **Phase 3 — Ablations.** §9 on the code critic. **Checkpoint:** `make ablation` produces both plots over ≥3 seeds with mean±std. Commit.
- **Phase 4 — LeanCritic (headline).** §6.3 incl. `lake exe cache get`. **Checkpoint:** `make demo` (lean config) verifies real Lean theorems; `SURVIVORS.md` populated with proofs. Re-run §9 ablations on Lean if time permits. Commit. *(If Lean setup fails/oversize, fall back to Phase-3 code-critic results, document it, and ship.)*
- **Phase 5 — Report & polish.** `REPORT.md`, `SURVIVORS.md`, README, metrics, clean logs. Commit + tag `v0.1-pitch`.

Stop and ship at the highest phase reached; the artifact is valuable from Phase 3 onward.

---

## 14. Definition of done (acceptance tests)

- [ ] `make smoke` green in <60s; writes ledger + metrics.
- [ ] `pytest` green incl perturbation-operator tests and the two 5.2 fixtures (contentful passes, trivial suppressed).
- [ ] `make demo` produces ≥1 **certified-novel** survivor from a **real** critic with proof/tests attached.
- [ ] Genealogy ablation plot exists, ≥3 seeds, mean±std; treatment vs control clearly labelled.
- [ ] Significance ablation plot shows trivial-survivor rate dropping with the critic on.
- [ ] `metrics.json` reports `certified_novel_per_kilo_token` and `critic_seconds_per_certified_novel`.
- [ ] Sandbox demonstrably blocks network + out-of-sandbox FS access.
- [ ] `SURVIVORS.md` shows ≥3 survivors each with failed genealogy siblings.
- [ ] README's honest-limits section present and accurate.
- [ ] A fresh clone reproduces `make demo` from the README in one command (after `scripts/setup_lean.sh` for the Lean track).

---

## 15. Anti-patterns to avoid (will silently ruin the artifact)
- LLM-as-judge for *validity* (only for soft NL glosses, never for the survive/die decision).
- Genealogy degraded to pass/fail with no reasons → it's now RLVR.
- Significance = "it compiled" → the moat is gone; you must compute hardness.
- One seed, or treatment/control differing in more than the genealogy variable.
- Hard-coded example "novel theorems," cherry-picked metrics, or a mocked critic in any reported number.
- Blocking the whole build on Lean. Always have the code-critic result as the floor.

---

## 16. Out of scope now, scaffold for later (Tier 1 — Stage 1 of the grant)
Leave clean seams for, but **do not build**: weight-update RL (GRPO/PPO via `veRL` + `vLLM` rollouts; the AZR stack) replacing the in-context genealogy with genealogy-conditioned *training*; a co-evolved refuter policy; multi-domain critics (hardware/formal-methods). A short `ROADMAP.md` noting these is enough.

---

## 17. References (for the agent's situational awareness)
- Silver et al., AlphaZero — *Nature* 2017 / *Science* 2018 (existence proof: novelty from zero human data, free critic).
- DeepMind AlphaProof + AlphaGeometry 2 — IMO-2024 silver; *Nature* 2025 (Lean-verifier-in-the-loop; self-generated problem variations).
- Zhao et al., *Absolute Zero: Reinforced Self-play Reasoning with Zero Data*, arXiv:2505.03335, 2025 (self-proposed tasks + code-executor critic; our nearest prior art — we add reasoned genealogy + content scoring it lacks).
- DeepSeek-AI, *DeepSeek-R1*, *Nature* 645:633–638, 2025 (RLVR).
- Deutsch, *The Beginning of Infinity*, 2011 (good explanations are *hard to vary* — the basis for §5.2).
- mathlib + `lake exe cache get` (prebuilt oleans — the setup-time trick in §6.3).

---

## 18. Phase 6 — Shareability (same conventions: commit on green, never fabricate, [latitude] on plumbing, real data only)

**Goal:** turn the local artifact into clickable, reviewer-ready links with zero manual steps beyond `git push`. Runs after Phase 5 (depends on the real plots, `metrics.json`, the best run's `ledger.jsonl`, `REPORT.md`, `SURVIVORS.md`). `results/` stays gitignored — Phase 6 copies *curated, sanitized* artifacts into a tracked `docs/`. Build in this order, then update the `v0.1-pitch` tag.

**6.1 — Tracked docs assets.** Create a tracked `docs/` dir and copy into it: the two final ablation plots (`docs/assets/ablation_genealogy.png`, `docs/assets/ablation_significance.png`), a curated `docs/SURVIVORS.md` (top ~5 certified-novel results with proofs, significance breakdown, and failed genealogy siblings), and the rendered `docs/REPORT.md`. Use **relative** image paths so they embed on GitHub. (Never hand-author survivors — copy from the real run.)

**6.2 — GitHub-ready README.** Rewrite `README.md` so the repo URL alone tells the story: one-line what-it-is; the thesis in 3 sentences; the two embedded plots with one-sentence readings; one-command repro (`make demo`); a short "How this differs from RLVR / AlphaProof / Absolute Zero" note (reasoned genealogy + hard-to-vary content scoring, not pass/fail + validity); the headline KPI pulled from `metrics.json` (`certified_novel_per_kilo_token`, `critic_seconds_per_certified_novel`); links to `docs/SURVIVORS.md` and the replay viewer; and an honest-limits section (frozen proposer, operational—not formal—novelty, small scale). Verify the embedded plots actually render by checking relative paths resolve to real files.

**6.3 — Replay-from-logs viewer** (the reliable shareable demo — do NOT make it run anything live). A single self-contained `docs/replay/index.html` (vanilla JS, no build step, works offline by double-clicking the file) loads a committed, **sanitized** `docs/replay/run.jsonl` (a curated copy of a real `ledger.jsonl` from the best run — strip any keys/paths) and renders the loop as a scrubbable timeline:
- round-by-round; each conjecture a card coloured by `reason_class` (PROVED / FALSE / UNPROVEN_BUDGET / TRIVIAL / DUPLICATE);
- show statement, `nl_gloss`, the refutation detail (counterexample / error / "trivial: omega-closed"), and significance as three mini-bars (novelty / breadth / hardness) with a "certified-novel" badge where true;
- under each surviving result, list its failed siblings (via `parent_ids` / same round) so the genealogy story is visible;
- a header with the run's headline KPIs; filter toggles (all / survivors only / certified-novel only).
Clean and legible (generous whitespace, one accent colour, monospace for Lean). Reads ONLY the committed JSONL — no API, no Lean, no network. **Acceptance:** opening it offline shows a working replay of the real run.

**6.4 — GitHub Pages prep.** Structure `docs/` so Pages can serve it (Pages → deploy from `main` `/docs`). The agent can't enable Pages; add to the README the exact setting to flip and the resulting URL pattern (`https://<user>.github.io/<repo>/replay/`).

**6.5 — Recording helper.** Add a `make record` target that runs `make demo` under `asciinema rec docs/demo.cast` if `asciinema` is installed (else print a note to use a screen recorder / Loom). Embed the cast in the README or a docs page if produced. **[latitude]**.

**6.6 — `make publish` + secrets hygiene.** Add `make publish` that regenerates plots, refreshes `docs/` assets, runs a grep check for leaked secrets/keys/`.env` in tracked files (**fail loudly** if any), then prints (does NOT execute) the manual steps: `git remote add … && git push`, and the Pages toggle. Ensure `.gitignore` covers `results/`, `.env`, caches, and model weights.

**6.7 — IP mode.** `scripts/prep_public.sh --mode {results-only|full}`. `results-only` (default) tracks README, `docs/` (report, survivors, replay, plots), and the loop/critic interfaces, but keeps the moat — `crm/significance.py` and `crm/genealogy.py` — in a gitignored `PRIVATE/` path (the human shares these with reviewers separately). `full` tracks everything. Document the choice in the README. Protects the hard-to-vary critic during the competition while still giving a public, rendered, interactive link.

**Definition of done (Phase 6):** repo URL renders README with embedded plots; `docs/replay/index.html` replays a real run offline; `make publish` passes the secret-scan and prints push + Pages steps; `--mode results-only` excludes the significance/genealogy source; tag `v0.1-pitch` updated. Commit on green.
