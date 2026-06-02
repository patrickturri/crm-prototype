# Hard domain at scale (n=10) — settles finding #3 / #9

The first-pass hard-domain run (n=3) showed the genealogy-vs-control delta
**flip sign** to **+1.33** on a non-recallable sequence, which was *suggestive*
of the thesis (genealogy helps where recall is impossible) but underpowered.
This run scales to **n=10 seeds** with the real `api_code` proposer to settle it.

Domain: the freshly-defined sequence `g(n) = 3·g(n-1) − g(n-2) + (n mod 3)`
(`configs/hard_domain.yaml`, `crm/proposers_hard.py`); `reference_impl` is fixed
to the ground-truth recurrence so the model can only conjecture *properties*.

Sources: `results/findings/hard_domain_n10/summary.json`,
`results/findings/hard_domain_n10/hard_domain.csv` (per-arm ledgers alongside).

## Result — the n=3 sign-flip was noise

| arm | certified-novel (mean ± std, n=10) | survival rate | cert / kilo-token | indep-trivial rate |
|---|---|---|---|---|
| genealogy | **1.90 ± 0.70** | 0.150 | 0.240 | **0.00** (all 10 seeds) |
| control | **2.00 ± 0.63** | 0.139 | 0.271 | ~0.125 (noisy 0–0.67) |
| best_of_N | **3.00 ± 0.63** | 0.278 | **0.927** | — |

Per-seed certified-novel:
- genealogy: `[1, 2, 1, 2, 2, 2, 3, 2, 1, 3]`
- control: `[2, 3, 1, 3, 2, 2, 2, 1, 2, 2]`
- best_of_N: `[3, 3, 3, 2, 2, 3, 4, 4, 3, 3]`

Significance tests (two-sided):

| comparison | diff | Welch t | Welch p | Mann-Whitney p |
|---|---|---|---|---|
| genealogy − control | **−0.10** | −0.318 | **0.754** | **0.769** |
| best_of_N − genealogy | **+1.10** | 3.498 | **0.003** | **0.006** |

## Honest reading

- **H2 is not supported, even on the recall-resistant domain.** At n=10 the
  genealogy–control delta is **−0.10** (p=0.75 / MWU p=0.77) — indistinguishable
  from zero. The encouraging **+1.33** from n=3 did **not** survive scaling; it
  was sampling noise on three seeds. Combined with the n=8 easy-domain result
  (−2.00, p=0.13, [genealogy_scale](genealogy_scale.md)), the reasoned-genealogy
  mechanism shows **no certified-novel advantage on either domain**.
- **Best-of-N still wins**, decisively, even here: +1.10 certified vs genealogy
  (p=0.003) and **3.9× per-token** (0.927 vs 0.240). Finding #8 holds on the
  hard domain.
- **The one genuine edge for the full system is triviality suppression, not
  genealogy.** Genealogy's independent-trivial-rate is **0.00 across all 10
  seeds** vs control's noisy mean ~0.125 — but that is the **significance gate**
  doing the work (both arms run it; they differ only in conditioning), so it is
  not evidence for H2. It is evidence the gate is useful (cf. finding #5).
- The domain itself worked as intended: survivors are genuinely discovered
  properties of `g` (parity/divisibility/growth identities), not recalled
  textbook facts — so the null is a fair test of the mechanism, not an artifact
  of the model refusing to engage.

**Verdict:** scaling settles #3 against the thesis. The full CRM loop's machinery
(genealogy conditioning) is not justified by certified-novel yield on either the
easy or the hard domain; its only measurable benefit is gate-driven triviality
suppression, and a naive best-of-N baseline beats it on count and per-token in
every condition tested.
