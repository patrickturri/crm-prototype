# Dedup Collapse: Intra-Survivor Semantic Deduplication (Finding #7)

**Run:** `code-20260531-225343`
**Embedder:** `sentence-transformers/all-MiniLM-L6-v2` (same backend used in the run itself, per `configs/code.yaml`)
**Delta (distance threshold):** 0.35
**Method:** `crm.novelty.dedup_survivors` — greedy, order-preserving collapse; distance = 1 - cosine_sim; no model run, only the embedder.

## Summary

| Metric | Count |
|---|---|
| Raw certified-novel (as reported by this run) | 7 |
| Deduped certified-novel (after intra-survivor collapse) | 4 |
| Near-duplicate pairs (distance < 0.35) | 6 |
| Groups after collapse | 4 |
| Statements collapsed (duplicates removed) | 3 |

The 7 survivors before intra-run dedup collapse to **4 distinct clusters** under MiniLM at delta=0.35. Three of the seven certified-novel statements are semantic near-duplicates of an already-accepted survivor from the same run.

## Groups After Dedup

### Group 1 — divisor/floor sums (3 members, 2 collapsed)

**Representative (c_0001):**
> For n>=1, the sum of floor(n/k) for k=1..n equals 2*sum_{k=1}^{floor(sqrt(n))} floor(n/k) - floor(sqrt(n))^2, the classic divisor-sum identity

**Collapsed into this group:**
- **c_0008** (dist=0.224): "For n>=1, sum of sigma(k) for k=1..n equals sum_{k=1}^{n} k * floor(n/k), where sigma(k) is the sum of divisors of k"
- **c_0010** (dist=0.281): "For n>=1, the number of integers k in [1,n] such that k divides n equals the number of divisors of n, d(n), and sum_{n=1}^{N} d(n) = sum_{k=1}^{N} floor(N/k)"

All three are variations on the hyperbola-method / divisor-sum-floor identity family.

### Group 2 — totient / Mobius inversion (2 members, 1 collapsed)

**Representative (c_0002):**
> The number of integers in [1,n] coprime to n equals Euler's totient phi(n), and sum_{d|n} phi(d) == n for all n>=1

**Collapsed into this group:**
- **c_0017** (dist=0.313): "For n>=1, sum_{d|n} mu(d)*floor(n/d) equals phi(n), where mu is the Mobius function and phi is Euler's totient — this is the Mobius inversion of n = sum_{d|n} phi(d)"

Both express the Mobius-inversion relationship between phi and n; c_0017 is the Dirichlet-series dual of c_0002.

### Group 3 — Legendre symbol / quadratic residues (1 member, distinct)

**Representative (c_0004):**
> For prime p, the number of solutions to x^2 ≡ a (mod p) is 1 + Legendre(a,p) for a not divisible by p, so summing over a=1..p-1 gives p-1 solutions total across all residues

Geometrically isolated from all other survivors (min distance to any other: 0.648).

### Group 4 — perfect numbers / sigma (1 member, distinct)

**Representative (c_0015):**
> For n>=2, the sum of all proper divisors of n (divisors < n) equals sigma(n) - n, and a number is perfect iff this equals n; the count of perfect numbers up to 1000 is 3

Min distance to any other survivor: 0.381 (borderline; above the 0.35 threshold).

## Pairwise Distance Matrix (near-dup pairs highlighted)

| Pair | Distance | Near-dup? |
|---|---|---|
| c_0001, c_0008 | 0.224 | YES |
| c_0008, c_0010 | 0.219 | YES |
| c_0001, c_0010 | 0.281 | YES |
| c_0002, c_0017 | 0.313 | YES |
| c_0008, c_0017 | 0.332 | YES |
| c_0010, c_0017 | 0.336 | YES |
| c_0008, c_0015 | 0.382 | no |
| c_0001, c_0017 | 0.384 | no |
| c_0002, c_0008 | 0.427 | no |
| c_0010, c_0015 | 0.442 | no |
| c_0002, c_0015 | 0.480 | no |
| c_0001, c_0002 | 0.503 | no |
| c_0015, c_0017 | 0.568 | no |
| c_0002, c_0004 | 0.648 | no |
| c_0001, c_0004 | 0.650 | no |
| c_0004, c_0015 | 0.701 | no |
| c_0004, c_0010 | 0.744 | no |
| c_0004, c_0008 | 0.760 | no |
| c_0004, c_0017 | 0.780 | no |

Note: c_0002 and c_0010 also have distance 0.264 (near-dup), but c_0010 is already collapsed into group 1 (c_0001) first by greedy order.

## Honest Caveats

1. **Embedder choice matters.** MiniLM is a general-purpose semantic embedder, not trained on number theory. Distances between formally distinct but semantically related identities may be noisy. A domain-specific embedder could give different collapse counts.

2. **Delta=0.35 is a fixed threshold** chosen for the corpus novelty gate; it may over- or under-collapse when applied to intra-survivor comparison. The result (4 of 7 survive dedup) is specific to this threshold.

3. **Greedy order-preserving collapse** means the first survivor in ledger order anchors each group. A different ordering could produce different representatives (though the same number of groups, assuming the same pairwise distances).

4. **This experiment is retrospective.** The run `code-20260531-225343` did NOT apply intra-survivor dedup at certification time (the gate was added after that run). Future runs with the updated `certify_novel` will block duplicates at admission, so the raw/deduped counts should converge.

**Source files:** `results/findings/dedup_collapse.json`, `crm/novelty.py` (`dedup_survivors`), `results/code-20260531-225343/ledger.jsonl`
