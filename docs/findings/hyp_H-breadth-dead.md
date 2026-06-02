# Finding: H-breadth-dead — breadth is near-dead in the reported ablations, but not for the claimed reason

**Verdict: the hypothesis's PREDICTED OBSERVABLE is CONFIRMED, but its stated MECHANISM is REFUTED.**

- Tested against git HEAD `e3e82e7`, config `configs/ablation.yaml`, zero API calls (reused committed ledgers + instrumented the live critics).
- `make test` green: **82 passed**.

## Hypothesis (as stated)

> In the genealogy/control/best-of-N ablations the breadth signal is structurally near-dead:
> `code_corpus.jsonl` rows carry only `{name, statement}` (0 have a `solve` key), so
> `breadth_target_specs` is always empty and the code-exec `enables()` path never runs;
> breadth falls back to `_breadth_structural`, whose `_shares_structure` only matches Lean
> tokens (`Nat.gcd`, `|`, `%`). Therefore significance score collapses to
> `~0.3*novelty + 0.4*hardness` with breadth pinned at 0 — a 2-signal score in every
> reported genealogy result.

## What the evidence says

### 1. The PREDICTED OBSERVABLE holds (effect is real)

On the reported genealogy/control ablation ledgers (`results/ablation_genealogy/**/ledger.jsonl`):

```
n 117
breadth==0 frac 1.0
max|score-(.3nov+.4hard)| 5.00000000069889e-07
```

Every surviving conjecture has `breadth == 0.0`, and for non-trivial survivors
`score == 0.3*novelty + 0.4*hardness` to within 5e-7 (rounding). So in the **reported
H2 numbers the 3-signal moat is effectively a 2-signal (novelty + hardness) score.**
That much of the hypothesis is correct and worth recording.

### 2. The stated MECHANISM is wrong (REFUTED)

The hypothesis assumes breadth specs come from `code_corpus.jsonl`. They do not.

- `code_corpus.jsonl`: 20 rows, 0 with a `solve` key (premise's corpus fact is true)...
- ...but `configs/ablation.yaml` sets `breadth_targets_path: data/code_breadth_targets.jsonl`,
  a **dedicated** targets file: **8 rows, all 8 with a `solve` key**.
- `experiments/_harness.py:75-81` loads `breadth_specs = [o for o in objects(breadth_path) if "solve" in o]`
  — this is the "Task 3" breadth wiring referenced in the briefing.

Instrumenting the live components built from the ablation config:

```
proposer: APICodeProposer
critic:   CodeExecCritic
has enables hook: True
breadth_target_specs n: 8
spec names: ['totient_sum','divisor_count_sum','divisor_sum_sum','prime_count',
             'perfect_square_count','fibonacci_sum','factorial_sum','catalan_sum']
```

So `breadth_target_specs` is **NOT empty**, the critic **does** expose `enables`, and the
`enables()` branch in `crm/significance.py:220-232` **is** the one that runs. The
`_breadth_structural` / `_shares_structure` Lean-token fallback is **never reached** on this
config. The claimed causal chain is false.

### 3. The enables() path is LIVE and CAN return >0 (positive/negative control)

Running the real sandboxed `enables()` on hand-built survivors:

```
breadth(totient survivor) = 0.125   <-- Euler-totient impl enables target 'totient_sum'
breadth(n^2 survivor)     = 0.0
totient enables: ['totient_sum']
```

A survivor whose verified function reproduces Euler's totient scores breadth = 1/8 = 0.125
through actual sandbox execution. Breadth is not pinned to 0 by structure.

### 4. Corroboration across all ledgers

Across **all** committed ledgers (545 surviving-with-sig entries), 24 (4.4%) have
`breadth > 0`, with observed nonzero values {0.125, 0.333, 1.0} and a max score deviation
of exactly **0.3 = w_breadth(0.3) * breadth(1.0)**. All 24 come from
`results/hard_dryrun_offline` and old smoke/code runs — **none from any genealogy / control /
best_of_N ablation arm.**

## Corrected diagnosis (what is actually true)

Breadth is **near-dead in practice for the reported H2 ablations**, but the cause is
**behavioural, not structural**: the `enables()` path is fully wired and capable of nonzero
output, yet the FROZEN proposer's Python-domain claims essentially never reproduce one of the
8 held-out number-theory primitives (totient, divisor-count/sum, prime-count, perfect-square
count, Fibonacci/factorial/Catalan sums). So `enables()` runs and honestly returns 0 for
nearly every survivor. The reported significance score is therefore effectively
`0.3*novelty + 0.4*hardness` — confirming the hypothesis's *symptom* while refuting its
*explanation*.

Implication: to make breadth a live third signal in the H2 ablations you must change the
**generation/target overlap** (steer proposals toward reusable primitives, or pick breadth
targets that match the domain the proposer actually explores), not "fix an empty-specs /
structural-fallback bug" — there is no such bug to fix.

## Reproduce

```bash
# (a) Premise + corpus facts
python -c "import json; r=[json.loads(l) for l in open('data/code_corpus.jsonl')]; print('corpus rows',len(r),'with solve',sum('solve' in x for x in r))"
python -c "import json; r=[json.loads(l) for l in open('data/code_breadth_targets.jsonl')]; print('target rows',len(r),'with solve',sum('solve' in x for x in r))"

# (b) Live path probe + controls (no API)
python -c "
import yaml; from experiments._harness import _build_components; from crm.types import Conjecture
cfg=yaml.safe_load(open('configs/ablation.yaml')); _,crit,sig,_=_build_components(cfg)
print('specs', len(sig.breadth_target_specs), 'enables hook', callable(getattr(crit,'enables',None)))
impl='def f(k):\n    import math\n    return sum(1 for i in range(1,k+1) if math.gcd(i,k)==1)'
g=Conjecture(id='p',statement='totient',proof_attempt='',extra={'reference_impl':impl,'tests':'assert f(6)==2','property':'t','domain':'range(1,11)'})
print('breadth(totient)=', sig.breadth(g,crit))
"

# (c) Predicted observable on reported ablations
python -c "import json,glob; e=[json.loads(l) for f in glob.glob('results/ablation_genealogy/**/ledger.jsonl',recursive=True) for l in open(f)]; s=[r['significance'] for r in e if r.get('significance') and r['surviving']]; print('n',len(s)); print('breadth==0 frac', sum(x['breadth']==0 for x in s)/len(s)); print('max|score-(.3nov+.4hard)|', max(abs(x['score']-(0.3*x['novelty']+0.4*x['hardness'])) for x in s if not x['is_trivial']))"
```
