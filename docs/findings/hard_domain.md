# Hard Domain: Discovery, Not Recall (Finding #9)

**Question (review finding #9):** The default code domain ("elementary number
theory") lets the frozen LLM *recall* textbook identities (Mobius inversion = phi,
sum phi(d) = n, ...). Recall is not discovery, so it does not test the thesis.
Does the system still produce certified survivors when the answer **cannot be
recalled**, and — the core differentiator (finding #3) — does **genealogy
conditioning help MORE** in a domain where there is nothing to recall?

**Module:** `experiments/hard_domain.py`
**Config:** `configs/hard_domain.yaml`
**Proposer:** real Anthropic `claude-sonnet-4-6` (`hard_api`), `using_fallback=False`
on every arm of this run (verified per-row in the CSV).
**Critic:** real sandboxed `CodeExecCritic` in all arms — no LLM-as-judge for the
survive/die decision.
**Embedder:** `sentence-transformers/all-MiniLM-L6-v2`.
**Perturbation family:** `rich` (operator/boundary mutations, finding #6), not just
integer-literal +-1.

## The domain — a freshly-defined sequence the model cannot look up

```
g(0) = 2,  g(1) = 3,  g(n) = 3*g(n-1) - g(n-2) + (n mod 3)   for n >= 2
g(0..8) = 2, 3, 9, 24, 64, 170, 446, 1169, 3063
```

The `+ (n mod 3)` inhomogeneous term breaks the clean Chebyshev/Fibonacci/Pell-style
closed forms a model could recall. The canonical `g(n)` is pinned as the
`reference_impl` of **every** candidate (the model cannot author the impl); the
model supplies only a conjectured executable `property`, which the sandboxed critic
fuzz-tests against the **true** recurrence. A wrong conjecture is refuted by a real
counterexample. The novelty corpus (`data/hard_domain_corpus.jsonl`) is the set of
*recallable* standard sequences/identities (Fibonacci, Lucas, Chebyshev, Pell,
Binet, homogeneous-recurrence theory, ...), so embedding-distance novelty measures
distance from what the model **could** recall.

## Results (api_code, 3 seeds, NONDETERMINISTIC — temperature 0.7)

```
python -m experiments.hard_domain --config configs/hard_domain.yaml --seeds 3 \
    --results-dir results/findings/hard_domain
```

| Arm | certified_novel (mean +/- std) | survival_rate | mean_significance | cert / kilo-token |
|---|---|---|---|---|
| **genealogy** | **2.33 +/- 0.47** | 0.241 | 0.503 | 0.260 |
| **control** | **1.00 +/- 0.82** | 0.093 | 0.345 | 0.152 |
| **best_of_N** | **3.67 +/- 1.89** | 0.278 | 0.537 | 1.213 |

Per-seed certified counts: genealogy {3, 2, 2}; control {0, 2, 1}; best_of_N {5, 1, 5}.
Source: `results/findings/hard_domain/hard_domain.csv`, `summary.json`.

## Do survivors survive, and are they genuinely non-recalled?

**Yes.** Across the genealogy + control arms, **10/10** certified survivors are
genuinely *discovered* properties of `g`, not verbatim restatements of the defining
recurrence (checked by pattern-matching the property source against the literal
`3*g(n-1)-g(n-2)+(n%3)` form). Representative certified survivors:

- `g(n) mod 3` is periodic with period 3: `[2,0,0][n mod 3]` for all n >= 0.
- The ratio `g(n+1)/g(n)` converges to `(3+sqrt(5))/2 ~= 2.618`, so `g(n) > 2*g(n-1)`
  for n >= 4 and `g(n) < 3*g(n-1) - 1` for n >= 2.
- Parity law: `g(n)` is even iff `n mod 3 != 1`.
- Recurrence shift identity: `g(n+3) = 3*g(n+2) - g(n+1) + ((n+3) mod 3)`.
- (best_of_N) `g(n)` mod 2 has period 6: `[0,1,1,0,0,0]`; higher-order relation
  `g(n+6) - 18*g(n+3) + g(n)` collapses.

None of these is a recallable textbook fact: the sequence does not exist in any
corpus. The model had to reason about the recurrence to find growth ratios, modular
periods, parity laws, and higher-order shift identities. This is the behaviour the
thesis predicts, on a domain where pure recall is impossible.

**Honest caveat on "non-recalled".** The growth-ratio claim `(3+sqrt(5))/2` is the
dominant characteristic root of the *homogeneous* part `x^2 = 3x - 1` — a model that
recognises the recurrence shape can *derive* it quickly. So "cannot recall the
sequence" does not mean "cannot reason from the recurrence's structure"; several
survivors are exactly that kind of structural derivation. They are still discovery
(the constant, period, and bounds are about THIS sequence and are critic-verified),
but they are not deep — see hardness below.

## Does genealogy help MORE here than on the easy domain?

This is the central comparison. The genealogy-vs-control certified delta flips sign
between domains:

| Domain | genealogy | control | genealogy - control |
|---|---|---|---|
| Easy (`results/ablation_genealogy.csv`) | 6.00 +/- 2.16 | 7.00 +/- 0.82 | **-1.00** (no help) |
| Hard (this run) | 2.33 +/- 0.47 | 1.00 +/- 0.82 | **+1.33** (helps) |

**Directionally, genealogy helps on the hard domain where it did not on the easy
one** — consistent with the thesis that *reasoned* conditioning (the WHY of prior
survivors) matters more when the model cannot fall back on recall. Control seed 0
certified **zero** survivors (trivial_rate 1.00 — the significance guard suppressed
every valid claim), whereas genealogy never collapsed to zero. Genealogy also won on
survival_rate (0.241 vs 0.093) and mean_significance (0.503 vs 0.345).

**But this is underpowered and must not be oversold.** n = 3 seeds per arm. The
error bars overlap: genealogy 2.33 +/- 0.47 vs control 1.00 +/- 0.82. The +1.33
delta is one to two survivors per run, driven partly by the single control-seed-0
zero. This is a **suggestive directional flip, not a significant effect.** A
defensible claim needs more seeds; at n = 3 we report the direction and decline to
claim significance.

## Did the model trivialize the domain? (honest tell)

Partly, and the guard caught it. The in-loop `trivial_rate` among valid conjectures
is high — genealogy {0.14, 0.43, 0.40}, control {1.00, 0.40, 0.33} — i.e. the model
frequently proposed vacuous or degenerate-closeable claims (lower bounds, sign
facts) that the significance guard zeroed before certification. The independent
oracle (finding #5) flagged certified survivors as trivial at rate 0.0 in 5 of 6
genealogy/control seeds, and 0.33 in one control seed (1 of 3 survivors). So the
domain is *not* immune to trivialization — the model still reaches for easy claims —
but the guard is doing real work, and what survives is mostly contentful.

## The per-token story still favours best-of-N (finding #8 holds here)

`best_of_N` certified the most on average (3.67) and dominates per-token
(1.21 cert/kilo-token vs genealogy's 0.26 — about **4.7x**), because the genealogy
arm spends ~3x the tokens on growing conditioning context (8.9k vs 3.0k mean
proposer tokens). This replicates the baseline finding on the hard domain: the
iterative loop is **not** a per-token win. Its advantage, if any, is the
genealogy-vs-control quality/robustness margin above (no zero-survivor collapse,
higher significance) — not raw throughput.

## Bottom line (honest)

1. The system **does** produce critic-verified, genuinely non-recalled survivors on
   a freshly-defined sequence — the domain tests discovery, not recall.
2. Genealogy conditioning **helps directionally here** (+1.33 certified) where it
   **hurt on the easy domain** (-1.00) — the sign flip is the thesis-relevant
   signal. But at n = 3 with overlapping error bars it is **suggestive, not
   significant**; do not report it as a confirmed effect.
3. The model still proposes many trivial claims (high in-loop trivial_rate); the
   significance guard suppresses them, and the survivors that remain are real but
   mostly *shallow* structural derivations (characteristic-root growth, modular
   periods), not deep theorems.
4. best-of-N still wins on raw count and decisively on per-token (finding #8 is
   not overturned by the hard domain).

---

*Numbers above are produced by `experiments/hard_domain.py`; every value is
traceable to `results/findings/hard_domain/hard_domain.csv` and `summary.json`, and
survivor statements to the per-arm `ledger.jsonl`. `results/` is gitignored but
regenerable from `configs/hard_domain.yaml` + this module (modulo API
nondeterminism at temperature 0.7). The easy-domain comparison row is from
`results/ablation_genealogy.csv`.*
