# Certified-novel survivors (real critic)

Top 5 certified-novel survivors from a **real** run (`code-20260531-213056`, critic = `code_exec`, proposer = `api_code`). Every survivor below was produced by the loop and verified by the critic — **none is hand-authored** (§3, §12.3). Each carries its verifiable proof/tests, its significance breakdown, and the failed genealogy siblings from the same run that explain WHY they didn't survive.

> Headline KPIs for this run: **6** certified-novel survivors · **0.628** per kilo-token · **26180** per critic-hour (18 conjectures over 3 rounds).

## 1. Euler's totient phi(n) is even for all n > 2, and odd only for n=1 and n=2.

**Statement.** The number of integers in [1, n] that are coprime to n equals Euler's totient phi(n), and phi(n) is always even for n > 2.

Proof method: tests_passed (verified by real sandboxed execution — 8 own + 13 adversarial tests passed)

```python
def f(n):
    import math
    phi = sum(1 for k in range(1, n + 1) if math.gcd(k, n) == 1)
    return phi % 2

# property checked over the sampled domain + adversarial inputs:
lambda n: f(n) == (1 if n <= 2 else 0)
```

**Significance.** novelty 0.56 · breadth 0.00 · hardness 1.00 → score 0.57 (is_trivial = False).

**Certified novel.** yes — no corpus restatement, not closed by automation alone, retrieval-distance 0.56 ≥ delta.

**Failed siblings from the genealogy (same round — why they didn't survive):**

- `The number of ways to write n as an ordered sum of exactly 2 positive odd integers equals n-1 when n is even, and 0 when n is odd.` — REFUTED false — test failed: assertion failed
- `For n >= 1, the sum of gcd(k, n) for k from 1 to n equals the sum of phi(d)*d over all divisors d of n, where phi is Euler's totient.` — REFUTED false — test failed: property fails at 200
- `The number of divisors of n! that are also perfect squares equals the product over primes p <= n of (floor(v_p(n!)/2) + 1), where v_p(n!) is the p-adic valua...` — REFUTED false — test failed: assertion failed
- `For n >= 1, the number of integers k in [1, n^2] such that floor(sqrt(k)) = floor(sqrt(k-1)) + 1 (i.e., k is a perfect square) equals n.` — REJECTED trivial — closeable by automation/degenerate impl alone (hardness 0.88 but the independent automation probe also passes — no genuine content); score forced to 0


## 2. The inclusion-exclusion formula for surjections from [n] to [n] counts exactly n! permutations.

**Statement.** The sum of (-1)^(n-k) * C(n,k) * k^n for k from 0 to n equals n! (the number of surjections from an n-set to an n-set, i.e., permutations).

Proof method: tests_passed (verified by real sandboxed execution — 7 own + 9 adversarial tests passed)

```python
def f(n):
    import math
    total = 0
    for k in range(n + 1):
        total += ((-1) ** (n - k)) * math.comb(n, k) * (k ** n)
    return total

# property checked over the sampled domain + adversarial inputs:
lambda n: f(n) == __import__('math').factorial(n)
```

**Significance.** novelty 0.61 · breadth 0.00 · hardness 0.80 → score 0.50 (is_trivial = False).

**Certified novel.** yes — no corpus restatement, not closed by automation alone, retrieval-distance 0.61 ≥ delta.

**Failed siblings from the genealogy (same round — why they didn't survive):**

- `The number of ways to write n as an ordered sum of exactly 2 positive odd integers equals n-1 when n is even, and 0 when n is odd.` — REFUTED false — test failed: assertion failed
- `For n >= 1, the sum of gcd(k, n) for k from 1 to n equals the sum of phi(d)*d over all divisors d of n, where phi is Euler's totient.` — REFUTED false — test failed: property fails at 200
- `The number of divisors of n! that are also perfect squares equals the product over primes p <= n of (floor(v_p(n!)/2) + 1), where v_p(n!) is the p-adic valua...` — REFUTED false — test failed: assertion failed
- `For n >= 1, the number of integers k in [1, n^2] such that floor(sqrt(k)) = floor(sqrt(k-1)) + 1 (i.e., k is a perfect square) equals n.` — REJECTED trivial — closeable by automation/degenerate impl alone (hardness 0.88 but the independent automation probe also passes — no genuine content); score forced to 0


## 3. Sum of divisor counts equals sum of floor(n/j), a classic identity.

**Statement.** For n >= 1, the sum of the number of divisors d(k) for k from 1 to n equals sum_{j=1}^{n} floor(n/j).

Proof method: tests_passed (verified by real sandboxed execution — 6 own + 13 adversarial tests passed)

```python
def f(n):
    import math
    total = 0
    for k in range(1, n+1):
        for d in range(1, k+1):
            if k % d == 0:
                total += 1
    return total

# property checked over the sampled domain + adversarial inputs:
lambda n: f(n) == sum(n // j for j in range(1, n+1))
```

**Significance.** novelty 0.67 · breadth 0.00 · hardness 0.75 → score 0.50 (is_trivial = False).

**Certified novel.** yes — no corpus restatement, not closed by automation alone, retrieval-distance 0.67 ≥ delta.

**Failed siblings from the genealogy (same round — why they didn't survive):**

- `For n >= 1, the number of ordered pairs (a, b) with 1 <= a, b <= n and gcd(a, b) = 1 equals sum_{k=1}^{n} phi(k) * 2 - 1, where phi is Euler's totient.` — REFUTED false — test failed: assertion failed
- `For n >= 0, the number of ways to tile a 2 x n board with 1x2 dominoes equals the (n+1)-th Fibonacci number F(n+1), where F(1)=1, F(2)=1, F(3)=2, ...` — ILL-FORMED — IndexError: list index out of range
- `For n >= 1, the number of integers k in [1, n] such that k is a perfect square equals floor(sqrt(n)), and sum_{k=1}^{n} floor(sqrt(k)) equals sum_{j=1}^{floo...` — REFUTED false — test failed: assertion failed
- `For n >= 0, the number of subsets of {1, 2, ..., n} with no two consecutive elements equals the (n+2)-th Fibonacci number F(n+2), where F(1)=1, F(2)=1.` — REFUTED false — test failed: property fails at 0


## 4. Integers with odd divisor count are exactly perfect squares, so there are floor(sqrt(n)) of them in [1,n].

**Statement.** For n >= 1, the number of integers in [1, n] with an odd number of divisors equals floor(sqrt(n)), since a positive integer has an odd number of divisors if and only if it is a perfect square.

Proof method: tests_passed (verified by real sandboxed execution — 7 own + 13 adversarial tests passed)

```python
def f(n):
    import math
    count = 0
    for k in range(1, n+1):
        num_divs = sum(1 for d in range(1, k+1) if k % d == 0)
        if num_divs % 2 == 1:
            count += 1
    return count

# property checked over the sampled domain + adversarial inputs:
lambda n: f(n) == __import__('math').isqrt(n)
```

**Significance.** novelty 0.56 · breadth 0.00 · hardness 0.75 → score 0.47 (is_trivial = False).

**Certified novel.** yes — no corpus restatement, not closed by automation alone, retrieval-distance 0.56 ≥ delta.

**Failed siblings from the genealogy (same round — why they didn't survive):**

- `For n >= 1, the number of ordered pairs (a, b) with 1 <= a, b <= n and gcd(a, b) = 1 equals sum_{k=1}^{n} phi(k) * 2 - 1, where phi is Euler's totient.` — REFUTED false — test failed: assertion failed
- `For n >= 0, the number of ways to tile a 2 x n board with 1x2 dominoes equals the (n+1)-th Fibonacci number F(n+1), where F(1)=1, F(2)=1, F(3)=2, ...` — ILL-FORMED — IndexError: list index out of range
- `For n >= 1, the number of integers k in [1, n] such that k is a perfect square equals floor(sqrt(n)), and sum_{k=1}^{n} floor(sqrt(k)) equals sum_{j=1}^{floo...` — REFUTED false — test failed: assertion failed
- `For n >= 0, the number of subsets of {1, 2, ..., n} with no two consecutive elements equals the (n+2)-th Fibonacci number F(n+2), where F(1)=1, F(2)=1.` — REFUTED false — test failed: property fails at 0


## 5. Binary strings of length n with no consecutive 1s are counted by Fibonacci numbers.

**Statement.** For n >= 0, the number of binary strings of length n with no two consecutive 1s equals the (n+2)-th Fibonacci number F(n+2), where F(1)=1, F(2)=1.

Proof method: tests_passed (verified by real sandboxed execution — 7 own + 12 adversarial tests passed)

```python
def f(n):
    count = 0
    for mask in range(1 << n):
        bits = bin(mask)[2:].zfill(n)
        if '11' not in bits:
            count += 1
    return count

# property checked over the sampled domain + adversarial inputs:
lambda n: f(n) == (lambda fib: fib(n+2))(lambda k: [0,1,1][k] if k<=2 else __import__('functools').reduce(lambda acc,_: (acc[1], acc[0]+acc[1]), range(k-2), (1,1))[1])
```

**Significance.** novelty 0.36 · breadth 0.00 · hardness 0.88 → score 0.46 (is_trivial = False).

**Certified novel.** yes — no corpus restatement, not closed by automation alone, retrieval-distance 0.36 ≥ delta.

**Failed siblings from the genealogy (same round — why they didn't survive):**

- `For n >= 1, the number of pairs (a,b) with 1 <= a <= b <= n and gcd(a,b) = 1 equals (1 + sum_{k=1}^{n} phi(k)) where phi is Euler's totient.` — REFUTED false — test failed: assertion failed
- `For n >= 1, the number of squarefree integers in [1, n] equals sum_{k=1}^{floor(sqrt(n))} mu(k) * floor(n / k^2), where mu is the Mobius function.` — REFUTED false — test failed: assertion failed
- `For n >= 1, the number of integers k in [1, n] such that k and k+1 are both squarefree equals sum_{d squarefree, d|lcm structure} ... more precisely it equal...` — REFUTED false — test failed: assertion failed
- `For n >= 1, the sum of phi(d) * mu(n/d) over all divisors d of n equals the Jordan totient J_2(n) / n * phi(n) — no, more precisely: sum_{d|n} phi(d) * mu(n/...` — ILL-FORMED — ModuleNotFoundError: No module named 'sympy'


---

_Generated by `experiments/make_survivors.py` from the run's `ledger.jsonl` + `artifacts.json`. Re-run `make demo` then `python -m experiments.make_survivors` to regenerate against a fresh real run._
