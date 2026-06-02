# Certified-novel survivors (real critic)

Top 5 certified-novel survivors from a **real** run (`code-20260531-225343`, critic = `code_exec`, proposer = `api_code`). Every survivor below was produced by the loop and verified by the critic — **none is hand-authored** (§3, §12.3). Each carries its verifiable proof/tests, its significance breakdown, and the failed genealogy siblings from the same run that explain WHY they didn't survive.

> Headline KPIs for this run (seed 0; 3-seed ablation means in REPORT.md): **7** certified-novel survivors · **0.756** per kilo-token · **0.58s** total critic time (~32 ms/conjecture; not annualized) (18 conjectures over 3 rounds).

> **Embedder provenance (honest correction).** The novelty gate in THIS run used the **deterministic hash-fallback** embedder, not MiniLM: `results/code-20260531-225343/metrics.json` records `embedding_calls: 0` for every round (MiniLM is requested by `configs/code.yaml` but was unavailable at run time, so `get_embedder` fell back per `crm/embedding.py`). The `delta >= 0.35` novelty distances above are therefore hash-fallback distances. Any sentence that previously implied a MiniLM-grade novelty signal for this run is corrected by this note; the dedup *re-measurement* (finding #7) is a separate offline computation whose embedder is stated in its own finding doc. `results/` is gitignored, so these headline numbers live only in a regenerable run directory — the binding run id is recorded in the repo-root `metrics.json` `_provenance.run`.

> **Read this honestly.** *Certified-novel* here means **operational** novelty: a claim that is not a corpus restatement, is not closeable by a degenerate-impl probe, and is at embedding-distance >= 0.35 from the static corpus. It is **fuzz-tested on bounded integers, not proved** — see [`docs/FINDINGS.md`](docs/FINDINGS.md). The survivors below are classical textbook number-theory identities (Mobius inversion = phi, sum phi(d) = n, sum floor(n/k) = sum d(n)); the system **rediscovers** them, it does not discover new mathematics.

> **Intra-run dedup (finding #7).** This run did not apply intra-survivor dedup at certification time. Re-measured with `crm.novelty.dedup_survivors` (MiniLM embedder, delta=0.35 — a separate re-measurement; the run itself used the hash fallback, see the embedder-provenance note above), the **7** certified survivors collapse to **4** distinct clusters (3 are intra-run near-duplicates) — see [`docs/findings/dedup_collapse.md`](docs/findings/dedup_collapse.md). The updated `certify_novel` gate now blocks such duplicates at admission.

> **Hardness curation note (finding #6).** The 5 survivors shown below (top by score) all report hardness 0.88, but the full set of 7 certified survivors spans hardness {0.62, 0.75, 0.88}. Literal +-1 integer-literal perturbation measures numeric brittleness, not explanatory depth; see [`docs/findings/hardness_distribution.md`](docs/findings/hardness_distribution.md).

## 1. Mobius inversion: sum of mu(d)*floor(n/d) over divisors d of n equals phi(n).

**Statement.** For n>=1, sum_{d|n} mu(d)*floor(n/d) equals phi(n), where mu is the Mobius function and phi is Euler's totient — this is the Mobius inversion of n = sum_{d|n} phi(d)

Proof method: tests_passed (verified by real sandboxed execution — 7 own + 13 adversarial tests passed)

```python
def f(n):
    import math
    def mobius(k):
        if k == 1: return 1
        factors = []
        temp = k
        p = 2
        while p * p <= temp:
            if temp % p == 0:
                factors.append(p)
                temp //= p
                if temp % p == 0:
                    return 0  # squared factor
            p += 1
        if temp > 1:
            factors.append(temp)
        return (-1) ** len(factors)
    divisors = [d for d in range(1, n+1) if n % d == 0]
    return sum(mobius(d) * (n // d) for d in divisors)

# property checked over the sampled domain + adversarial inputs:
lambda n: f(n) == sum(1 for k in range(1, n+1) if __import__('math').gcd(k, n) == 1)
```

**Significance.** novelty 0.66 · breadth 0.12 · hardness 0.88 → score 0.59 (is_trivial = False).

**Certified novel.** yes — no corpus restatement, not closed by automation alone, retrieval-distance 0.66 ≥ delta.

**Failed siblings from the genealogy (same round — why they didn't survive):**

- `For n>=1, the number of ordered pairs (a,b) with 1<=a<=b<=n and gcd(a,b)==1 equals (1 + sum_{k=1}^{n} phi(k)) // 1, specifically equals (1 + sum_{k=1}^{n} eu...` — REFUTED false — test failed: assertion failed
- `For n>=1, sum_{k=1}^{n} phi(k) equals the count of fractions a/b in lowest terms with 1<=b<=n and 1<=a<=b, i.e., (1 + sum_{k=1}^{n} phi(k)) // 2 counts unord...` — REFUTED false — test failed: property fails at 2
- `For n>=1, the number of divisors d of n such that d <= sqrt(n) equals ceil(d(n)/2) when n is a perfect square and floor(d(n)/2) otherwise, where d(n) is the ...` — REFUTED false — test failed: assertion failed
- `For n>=1, the number of integers k in [1, n^2] that can be expressed as a product of exactly two distinct integers both in [1,n] equals n*(n-1)//2 minus the ...` — REFUTED false — test failed: assertion failed


## 2. The sum of Euler's totient over all divisors of n equals n; this is a classical multiplicative identity.

**Statement.** The number of integers in [1,n] coprime to n equals Euler's totient phi(n), and sum_{d|n} phi(d) == n for all n>=1

Proof method: tests_passed (verified by real sandboxed execution — 7 own + 13 adversarial tests passed)

```python
def f(n):
    import math
    return sum(1 for k in range(1, n + 1) if math.gcd(k, n) == 1)

# property checked over the sampled domain + adversarial inputs:
lambda n: sum(f(d) for d in range(1, n + 1) if n % d == 0) == n
```

**Significance.** novelty 0.61 · breadth 0.12 · hardness 0.88 → score 0.57 (is_trivial = False).

**Certified novel.** yes — no corpus restatement, not closed by automation alone, retrieval-distance 0.61 ≥ delta.

**Failed siblings from the genealogy (same round — why they didn't survive):**

- `The number of ways to write n as an ordered sum of exactly 2 positive odd numbers equals floor(n/2) - (1 if n%2==0 else 0), specifically it equals (n-2)//2 f...` — REFUTED false — test failed: assertion failed
- `The number of binary strings of length n with no two consecutive 1s equals the (n+2)-th Fibonacci number F(n+2) where F(1)=F(2)=1` — REFUTED false — test failed: property fails at 1
- `The number of partitions of n into distinct parts equals the number of partitions of n into odd parts, for all n>=0` — REFUTED false — test failed: property fails at 1


## 3. Sum of floor(N/k) for k=1..N equals sum of number-of-divisors d(n) for n=1..N

**Statement.** For n>=1, the number of integers k in [1,n] such that k divides n equals the number of divisors of n, d(n), and sum_{n=1}^{N} d(n) = sum_{k=1}^{N} floor(N/k)

Proof method: tests_passed (verified by real sandboxed execution — 7 own + 13 adversarial tests passed)

```python
def f(N):
    return sum(N // k for k in range(1, N+1))

# property checked over the sampled domain + adversarial inputs:
lambda N: f(N) == sum(sum(1 for d in range(1, n+1) if n % d == 0) for n in range(1, N+1))
```

**Significance.** novelty 0.64 · breadth 0.00 · hardness 0.88 → score 0.54 (is_trivial = False).

**Certified novel.** yes — no corpus restatement, not closed by automation alone, retrieval-distance 0.64 ≥ delta.

**Failed siblings from the genealogy (same round — why they didn't survive):**

- `For n>=1, the number of ordered pairs (a,b) with a,b in [1,n] and gcd(a,b)==1 equals sum_{k=1}^{n} phi(k) * 2 - 1, where phi is Euler's totient` — REFUTED false — test failed: assertion failed
- `For n>=0, the number of compositions of n into parts each equal to 1 or 2 equals the (n+1)-th Fibonacci number F(n+1) where F(1)=1, F(2)=1` — REFUTED false — test failed: property fails at 1
- `For prime p>=2, the number of quadratic residues mod p (nonzero squares mod p) equals (p-1)//2` — REFUTED false — test failed: property fails at 2
- `For n>=0, the number of subsets of {1,...,n} with no two consecutive elements equals the (n+2)-th Fibonacci number F(n+2) where F(1)=1,F(2)=1` — ILL-FORMED — TypeError: 'function' object is not subscriptable


## 4. The sum of proper divisors of n equals sigma(n) - n.

**Statement.** For n>=2, the sum of all proper divisors of n (divisors < n) equals sigma(n) - n, and a number is perfect iff this equals n; the count of perfect numbers up to 1000 is 3

Proof method: tests_passed (verified by real sandboxed execution — 6 own + 13 adversarial tests passed)

```python
def f(n):
    # returns sum of proper divisors of n
    return sum(d for d in range(1, n) if n % d == 0)

# property checked over the sampled domain + adversarial inputs:
lambda n: f(n) == sum(d for d in range(1, n+1) if n % d == 0) - n
```

**Significance.** novelty 0.63 · breadth 0.00 · hardness 0.88 → score 0.54 (is_trivial = False).

**Certified novel.** yes — no corpus restatement, not closed by automation alone, retrieval-distance 0.63 ≥ delta.

**Failed siblings from the genealogy (same round — why they didn't survive):**

- `For n>=1, the number of ordered pairs (a,b) with 1<=a<=b<=n and gcd(a,b)==1 equals (1 + sum_{k=1}^{n} phi(k)) // 1, specifically equals (1 + sum_{k=1}^{n} eu...` — REFUTED false — test failed: assertion failed
- `For n>=1, sum_{k=1}^{n} phi(k) equals the count of fractions a/b in lowest terms with 1<=b<=n and 1<=a<=b, i.e., (1 + sum_{k=1}^{n} phi(k)) // 2 counts unord...` — REFUTED false — test failed: property fails at 2
- `For n>=1, the number of divisors d of n such that d <= sqrt(n) equals ceil(d(n)/2) when n is a perfect square and floor(d(n)/2) otherwise, where d(n) is the ...` — REFUTED false — test failed: assertion failed
- `For n>=1, the number of integers k in [1, n^2] that can be expressed as a product of exactly two distinct integers both in [1,n] equals n*(n-1)//2 minus the ...` — REFUTED false — test failed: assertion failed


## 5. The sum of floor(n/k) over k=1..n equals 2*sum_{k=1}^{sqrt(n)} floor(n/k) - floor(sqrt(n))^2 by the hyperbola method.

**Statement.** For n>=1, the sum of floor(n/k) for k=1..n equals 2*sum_{k=1}^{floor(sqrt(n))} floor(n/k) - floor(sqrt(n))^2, the classic divisor-sum identity

Proof method: tests_passed (verified by real sandboxed execution — 8 own + 13 adversarial tests passed)

```python
def f(n):
    import math
    return sum(n // k for k in range(1, n + 1))

# property checked over the sampled domain + adversarial inputs:
lambda n: (lambda s: f(n) == 2 * sum(n // k for k in range(1, s + 1)) - s * s)(int(n**0.5))
```

**Significance.** novelty 0.61 · breadth 0.00 · hardness 0.88 → score 0.53 (is_trivial = False).

**Certified novel.** yes — no corpus restatement, not closed by automation alone, retrieval-distance 0.61 ≥ delta.

**Failed siblings from the genealogy (same round — why they didn't survive):**

- `The number of ways to write n as an ordered sum of exactly 2 positive odd numbers equals floor(n/2) - (1 if n%2==0 else 0), specifically it equals (n-2)//2 f...` — REFUTED false — test failed: assertion failed
- `The number of binary strings of length n with no two consecutive 1s equals the (n+2)-th Fibonacci number F(n+2) where F(1)=F(2)=1` — REFUTED false — test failed: property fails at 1
- `The number of partitions of n into distinct parts equals the number of partitions of n into odd parts, for all n>=0` — REFUTED false — test failed: property fails at 1


---

_Generated by `experiments/make_survivors.py` from the run's `ledger.jsonl` + `artifacts.json`. Re-run `make demo` then `python -m experiments.make_survivors` to regenerate against a fresh real run._
