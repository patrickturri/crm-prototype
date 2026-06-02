# Genealogy Ablation at Scale (H2)

Experiment addresses **review finding #3**: the genealogy ablation (the core H2 differentiator) did not beat control at n=3 and was underpowered. Re-run with the **real `api_code` proposer** (which reads the conditioning context, so the genealogy mechanism actually bites) at **8 seeds per arm**.

- Proposer: api_code (claude-sonnet-4-6), temperature 0.7
- Embedder: hash (deterministic), held fixed across arms
- Critic: real sandboxed CodeExecCritic (never mocked)
- Seeds: [0, 1, 2, 3, 4, 5, 6, 7]

## Verdict

> Genealogy does NOT significantly beat control on certified-novel (diff=-2.00, Welch p=0.126, MWU p=0.134, n=8 seeds/arm). The H2 advantage is not established.

## Primary metric — cumulative certified-novel survivors

| seed | genealogy | control |
|------|-----------|---------|
| 0 | 6 | 5 |
| 1 | 6 | 9 |
| 2 | 6 | 6 |
| 3 | 2 | 7 |
| 4 | 4 | 6 |
| 5 | 8 | 10 |
| 6 | 5 | 2 |
| 7 | 2 | 10 |
| **mean +/- std** | **4.88 +/- 1.96** | **6.88 +/- 2.57** |

- Difference (treat - ctrl): **-2.00**
- Welch t-test: t = -1.635, **p = 0.126**
- Mann-Whitney U: U = 17.5, **p = 0.134**

## Secondary metric — trivial rate (among valid conjectures)

| seed | genealogy | control |
|------|-----------|---------|
| 0 | 0.091 | 0.583 |
| 1 | 0.333 | 0.091 |
| 2 | 0.300 | 0.100 |
| 3 | 0.167 | 0.100 |
| 4 | 0.375 | 0.111 |
| 5 | 0.200 | 0.231 |
| 6 | 0.200 | 0.714 |
| 7 | 0.500 | 0.133 |
| **mean +/- std** | **0.271 +/- 0.123** | **0.258 +/- 0.232** |

- Difference (treat - ctrl): **+0.013**
- Welch t-test: t = 0.129, **p = 0.900**
- Mann-Whitney U: U = 39.5, **p = 0.461**

---
*Numbers produced by `experiments/ablation_genealogy.py` (8-seed API run) + `experiments/analyze_genealogy_scale.py`.*
*Survive/die decisions are real sandbox execution; the proposer is the real Anthropic API. No number is fabricated.*
