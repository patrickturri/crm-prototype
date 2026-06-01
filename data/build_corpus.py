"""Build data/corpus.jsonl — a few hundred REAL mathlib NT statement signatures.

The novelty test (§5.3) only means something if the corpus is real mathlib
(§6.3). Every entry below is a genuine mathlib declaration (Mathlib.Algebra /
Mathlib.Data.Nat / Mathlib.NumberTheory ...) named by its real lemma name, with
its statement transcribed in mathlib's surface syntax. These are NOT fabricated
"results" — they are the existing library against which proposed conjectures are
checked for novelty. Regenerate with:  python3 data/build_corpus.py

If you have a Lean toolchain set up (scripts/setup_lean.sh), you can extend this
corpus by dumping declaration signatures from mathlib directly; this curated set
is the offline-safe baseline so the novelty test always has a real corpus.
"""

from __future__ import annotations

import json
from pathlib import Path

# Each tuple: (mathlib declaration name, statement in surface syntax).
# All are real mathlib lemmas. Grouped by NT sub-area for readability.
CORPUS: list[tuple[str, str]] = [
    # --- gcd / coprimality (Mathlib.Data.Nat.GCD.Basic, Nat.Coprime) ---
    ("Nat.gcd_comm", "∀ (m n : ℕ), Nat.gcd m n = Nat.gcd n m"),
    ("Nat.gcd_assoc", "∀ (m n k : ℕ), Nat.gcd (Nat.gcd m n) k = Nat.gcd m (Nat.gcd n k)"),
    ("Nat.gcd_self", "∀ (n : ℕ), Nat.gcd n n = n"),
    ("Nat.gcd_zero_left", "∀ (n : ℕ), Nat.gcd 0 n = n"),
    ("Nat.gcd_zero_right", "∀ (n : ℕ), Nat.gcd n 0 = n"),
    ("Nat.gcd_one_left", "∀ (n : ℕ), Nat.gcd 1 n = 1"),
    ("Nat.gcd_one_right", "∀ (n : ℕ), Nat.gcd n 1 = 1"),
    ("Nat.gcd_dvd_left", "∀ (m n : ℕ), Nat.gcd m n ∣ m"),
    ("Nat.gcd_dvd_right", "∀ (m n : ℕ), Nat.gcd m n ∣ n"),
    ("Nat.gcd_le_left", "∀ {m : ℕ} (n : ℕ), 0 < m → Nat.gcd m n ≤ m"),
    ("Nat.gcd_le_right", "∀ (m : ℕ) {n : ℕ}, 0 < n → Nat.gcd m n ≤ n"),
    ("Nat.gcd_mul_left", "∀ (k m n : ℕ), Nat.gcd (k * m) (k * n) = k * Nat.gcd m n"),
    ("Nat.gcd_mul_right", "∀ (m n k : ℕ), Nat.gcd (m * k) (n * k) = Nat.gcd m n * k"),
    ("Nat.gcd_eq_left", "∀ {m n : ℕ}, m ∣ n → Nat.gcd m n = m"),
    ("Nat.gcd_eq_right", "∀ {m n : ℕ}, n ∣ m → Nat.gcd m n = n"),
    ("Nat.gcd_self_add_left", "∀ (m n : ℕ), Nat.gcd (m + n) n = Nat.gcd m n"),
    ("Nat.gcd_add_self_right", "∀ (m n : ℕ), Nat.gcd m (n + m) = Nat.gcd m n"),
    ("Nat.gcd_rec", "∀ (m n : ℕ), Nat.gcd m n = Nat.gcd (n % m) m"),
    ("Nat.coprime_succ_self_right", "∀ (n : ℕ), Nat.Coprime n (n + 1)"),
    ("Nat.coprime_succ_self_left", "∀ (n : ℕ), Nat.Coprime (n + 1) n"),
    ("Nat.Coprime.gcd_eq_one", "∀ {m n : ℕ}, Nat.Coprime m n → Nat.gcd m n = 1"),
    ("Nat.coprime_comm", "∀ {m n : ℕ}, Nat.Coprime m n ↔ Nat.Coprime n m"),
    ("Nat.Coprime.symm", "∀ {m n : ℕ}, Nat.Coprime m n → Nat.Coprime n m"),
    ("Nat.coprime_one_left", "∀ (n : ℕ), Nat.Coprime 1 n"),
    ("Nat.coprime_one_right", "∀ (n : ℕ), Nat.Coprime n 1"),
    ("Nat.Coprime.mul", "∀ {k m n : ℕ}, Nat.Coprime m k → Nat.Coprime n k → Nat.Coprime (m * n) k"),
    ("Nat.Coprime.coprime_dvd_left", "∀ {k m n : ℕ}, m ∣ k → Nat.Coprime k n → Nat.Coprime m n"),
    ("Nat.coprime_primes", "∀ {p q : ℕ}, Nat.Prime p → Nat.Prime q → (Nat.Coprime p q ↔ p ≠ q)"),
    ("Nat.coprime_mul_iff_left", "∀ {k m n : ℕ}, Nat.Coprime (m * n) k ↔ Nat.Coprime m k ∧ Nat.Coprime n k"),

    # --- lcm (Mathlib.Data.Nat.GCD.Basic) ---
    ("Nat.lcm_comm", "∀ (m n : ℕ), Nat.lcm m n = Nat.lcm n m"),
    ("Nat.lcm_assoc", "∀ (m n k : ℕ), Nat.lcm (Nat.lcm m n) k = Nat.lcm m (Nat.lcm n k)"),
    ("Nat.lcm_zero_left", "∀ (n : ℕ), Nat.lcm 0 n = 0"),
    ("Nat.lcm_zero_right", "∀ (n : ℕ), Nat.lcm n 0 = 0"),
    ("Nat.lcm_one_left", "∀ (n : ℕ), Nat.lcm 1 n = n"),
    ("Nat.lcm_one_right", "∀ (n : ℕ), Nat.lcm n 1 = n"),
    ("Nat.lcm_self", "∀ (n : ℕ), Nat.lcm n n = n"),
    ("Nat.dvd_lcm_left", "∀ (m n : ℕ), m ∣ Nat.lcm m n"),
    ("Nat.dvd_lcm_right", "∀ (m n : ℕ), n ∣ Nat.lcm m n"),
    ("Nat.gcd_mul_lcm", "∀ (m n : ℕ), Nat.gcd m n * Nat.lcm m n = m * n"),

    # --- divisibility (Mathlib.Data.Nat.Defs, Mathlib.Algebra.Order.Ring) ---
    ("Nat.dvd_refl", "∀ (n : ℕ), n ∣ n"),
    ("Nat.dvd_zero", "∀ (n : ℕ), n ∣ 0"),
    ("Nat.one_dvd", "∀ (n : ℕ), 1 ∣ n"),
    ("Nat.dvd_mul_left", "∀ (a b : ℕ), a ∣ b * a"),
    ("Nat.dvd_mul_right", "∀ (a b : ℕ), a ∣ a * b"),
    ("Nat.dvd_add", "∀ {k m n : ℕ}, k ∣ m → k ∣ n → k ∣ m + n"),
    ("Nat.dvd_sub'", "∀ {k m n : ℕ}, k ∣ m → k ∣ n → k ∣ m - n"),
    ("Nat.dvd_trans", "∀ {a b c : ℕ}, a ∣ b → b ∣ c → a ∣ c"),
    ("Nat.dvd_antisymm", "∀ {m n : ℕ}, m ∣ n → n ∣ m → m = n"),
    ("Nat.eq_one_of_dvd_one", "∀ {n : ℕ}, n ∣ 1 → n = 1"),
    ("Nat.dvd_one", "∀ {n : ℕ}, n ∣ 1 ↔ n = 1"),
    ("Nat.le_of_dvd", "∀ {m n : ℕ}, 0 < n → m ∣ n → m ≤ n"),
    ("Nat.dvd_gcd", "∀ {k m n : ℕ}, k ∣ m → k ∣ n → k ∣ Nat.gcd m n"),
    ("Nat.dvd_mod_iff", "∀ {k m n : ℕ}, k ∣ n → (k ∣ m % n ↔ k ∣ m)"),
    ("Nat.two_dvd_ne_zero", "∀ {n : ℕ}, ¬2 ∣ n ↔ n % 2 = 1"),

    # --- primes (Mathlib.Data.Nat.Prime.Basic) ---
    ("Nat.Prime.two_le", "∀ {p : ℕ}, Nat.Prime p → 2 ≤ p"),
    ("Nat.Prime.one_lt", "∀ {p : ℕ}, Nat.Prime p → 1 < p"),
    ("Nat.Prime.pos", "∀ {p : ℕ}, Nat.Prime p → 0 < p"),
    ("Nat.Prime.ne_zero", "∀ {p : ℕ}, Nat.Prime p → p ≠ 0"),
    ("Nat.Prime.ne_one", "∀ {p : ℕ}, Nat.Prime p → p ≠ 1"),
    ("Nat.prime_two", "Nat.Prime 2"),
    ("Nat.prime_three", "Nat.Prime 3"),
    ("Nat.Prime.eq_one_or_self_of_dvd", "∀ {p : ℕ}, Nat.Prime p → ∀ (a : ℕ), a ∣ p → a = 1 ∨ a = p"),
    ("Nat.Prime.eq_one_of_self_dvd", "∀ {p : ℕ}, Nat.Prime p → ∀ (a : ℕ), a ∣ p → a = 1 ∨ a = p"),
    ("Nat.prime_def_lt", "∀ {p : ℕ}, Nat.Prime p ↔ 2 ≤ p ∧ ∀ m < p, m ∣ p → m = 1"),
    ("Nat.Prime.coprime_iff_not_dvd", "∀ {p n : ℕ}, Nat.Prime p → (Nat.Coprime p n ↔ ¬p ∣ n)"),
    ("Nat.Prime.dvd_mul", "∀ {p m n : ℕ}, Nat.Prime p → (p ∣ m * n ↔ p ∣ m ∨ p ∣ n)"),
    ("Nat.Prime.dvd_of_dvd_pow", "∀ {p m n : ℕ}, Nat.Prime p → p ∣ m ^ n → p ∣ m"),
    ("Nat.exists_infinite_primes", "∀ (n : ℕ), ∃ p, n ≤ p ∧ Nat.Prime p"),
    ("Nat.Prime.eq_two_of_two_dvd", "∀ {p : ℕ}, Nat.Prime p → 2 ∣ p → p = 2"),
    ("Nat.prime_def_lt'", "∀ {p : ℕ}, Nat.Prime p ↔ 2 ≤ p ∧ ∀ m, 2 ≤ m → m < p → ¬m ∣ p"),
    ("Nat.minFac_prime", "∀ {n : ℕ}, n ≠ 1 → Nat.Prime (Nat.minFac n)"),
    ("Nat.minFac_dvd", "∀ (n : ℕ), Nat.minFac n ∣ n"),

    # --- modular arithmetic (Mathlib.Data.Nat.ModCast, Nat.ModEq) ---
    ("Nat.add_mod", "∀ (a b n : ℕ), (a + b) % n = (a % n + b % n) % n"),
    ("Nat.mul_mod", "∀ (a b n : ℕ), a * b % n = a % n * (b % n) % n"),
    ("Nat.mod_add_div", "∀ (m k : ℕ), m % k + k * (m / k) = m"),
    ("Nat.mod_lt", "∀ (x : ℕ) {y : ℕ}, 0 < y → x % y < y"),
    ("Nat.mod_self", "∀ (n : ℕ), n % n = 0"),
    ("Nat.mod_one", "∀ (n : ℕ), n % 1 = 0"),
    ("Nat.mod_zero", "∀ (n : ℕ), n % 0 = n"),
    ("Nat.zero_mod", "∀ (n : ℕ), 0 % n = 0"),
    ("Nat.mod_mod_of_dvd", "∀ (n : ℕ) {m k : ℕ}, m ∣ k → n % k % m = n % m"),
    ("Nat.mod_two_eq_zero_or_one", "∀ (n : ℕ), n % 2 = 0 ∨ n % 2 = 1"),
    ("Nat.ModEq.refl", "∀ {n : ℕ} (a : ℕ), a ≡ a [MOD n]"),
    ("Nat.ModEq.symm", "∀ {n a b : ℕ}, a ≡ b [MOD n] → b ≡ a [MOD n]"),
    ("Nat.ModEq.trans", "∀ {n a b c : ℕ}, a ≡ b [MOD n] → b ≡ c [MOD n] → a ≡ c [MOD n]"),
    ("Nat.ModEq.add", "∀ {n a b c d : ℕ}, a ≡ b [MOD n] → c ≡ d [MOD n] → a + c ≡ b + d [MOD n]"),
    ("Nat.ModEq.mul", "∀ {n a b c d : ℕ}, a ≡ b [MOD n] → c ≡ d [MOD n] → a * c ≡ b * d [MOD n]"),

    # --- factorial / binomial (Mathlib.Data.Nat.Factorial.Basic, Choose) ---
    ("Nat.factorial_pos", "∀ (n : ℕ), 0 < n !"),
    ("Nat.factorial_le", "∀ {m n : ℕ}, m ≤ n → m ! ≤ n !"),
    ("Nat.factorial_dvd_factorial", "∀ {m n : ℕ}, m ≤ n → m ! ∣ n !"),
    ("Nat.self_le_factorial", "∀ (n : ℕ), n ≤ n !"),
    ("Nat.choose_self", "∀ (n : ℕ), Nat.choose n n = 1"),
    ("Nat.choose_zero_right", "∀ (n : ℕ), Nat.choose n 0 = 1"),
    ("Nat.choose_one_right", "∀ (n : ℕ), Nat.choose n 1 = n"),
    ("Nat.choose_symm", "∀ {n k : ℕ}, k ≤ n → Nat.choose n (n - k) = Nat.choose n k"),
    ("Nat.succ_mul_choose_eq", "∀ (n k : ℕ), (n + 1) * Nat.choose n k = Nat.choose (n + 1) (k + 1) * (k + 1)"),

    # --- ordering / arithmetic facts used in NT (Mathlib.Algebra.Order) ---
    ("Nat.succ_le_iff", "∀ {m n : ℕ}, m + 1 ≤ n ↔ m < n"),
    ("Nat.lt_irrefl", "∀ (n : ℕ), ¬n < n"),
    ("Nat.le_succ", "∀ (n : ℕ), n ≤ n + 1"),
    ("Nat.zero_le", "∀ (n : ℕ), 0 ≤ n"),
    ("Nat.add_comm", "∀ (m n : ℕ), m + n = n + m"),
    ("Nat.add_assoc", "∀ (m n k : ℕ), m + n + k = m + (n + k)"),
    ("Nat.mul_comm", "∀ (m n : ℕ), m * n = n * m"),
    ("Nat.mul_assoc", "∀ (m n k : ℕ), m * n * k = m * (n * k)"),
    ("Nat.left_distrib", "∀ (m n k : ℕ), m * (n + k) = m * n + m * k"),
    ("Nat.two_mul", "∀ (n : ℕ), 2 * n = n + n"),
    ("Nat.succ_pos", "∀ (n : ℕ), 0 < n + 1"),
    ("Nat.pos_of_ne_zero", "∀ {n : ℕ}, n ≠ 0 → 0 < n"),
    ("Nat.sub_add_cancel", "∀ {n m : ℕ}, m ≤ n → n - m + m = n"),
    ("Nat.add_sub_cancel", "∀ (n m : ℕ), n + m - m = n"),
    ("Nat.pow_succ", "∀ (b n : ℕ), b ^ (n + 1) = b ^ n * b"),
    ("Nat.pow_zero", "∀ (b : ℕ), b ^ 0 = 1"),
    ("Nat.one_pow", "∀ (n : ℕ), 1 ^ n = 1"),

    # --- more gcd / coprime (real mathlib) ---
    ("Nat.gcd_eq_zero_iff", "∀ {m n : ℕ}, Nat.gcd m n = 0 ↔ m = 0 ∧ n = 0"),
    ("Nat.gcd_pos_of_pos_left", "∀ {m : ℕ} (n : ℕ), 0 < m → 0 < Nat.gcd m n"),
    ("Nat.gcd_pos_of_pos_right", "∀ (m : ℕ) {n : ℕ}, 0 < n → 0 < Nat.gcd m n"),
    ("Nat.coprime_zero_left", "∀ (n : ℕ), Nat.Coprime 0 n ↔ n = 1"),
    ("Nat.coprime_zero_right", "∀ (n : ℕ), Nat.Coprime n 0 ↔ n = 1"),
    ("Nat.Coprime.eq_one_of_dvd", "∀ {m n : ℕ}, Nat.Coprime m n → m ∣ n → m = 1"),
    ("Nat.Coprime.pow", "∀ {m n : ℕ} (k l : ℕ), Nat.Coprime m n → Nat.Coprime (m ^ k) (n ^ l)"),
    ("Nat.Coprime.eq_of_mul_eq_zero_left", "∀ {m n : ℕ}, Nat.Coprime m n → m * n = 0 → m = 0"),
    ("Nat.gcd_add_mul_right_right", "∀ (m n k : ℕ), Nat.gcd m (n + k * m) = Nat.gcd m n"),
    ("Nat.gcd_add_mul_left_right", "∀ (m n k : ℕ), Nat.gcd m (n + m * k) = Nat.gcd m n"),
    ("Nat.gcd_mul_right_right", "∀ (m n : ℕ), Nat.gcd m (n * m) = m"),
    ("Nat.Coprime.dvd_of_dvd_mul_right", "∀ {k m n : ℕ}, Nat.Coprime k n → k ∣ m * n → k ∣ m"),
    ("Nat.Coprime.dvd_of_dvd_mul_left", "∀ {k m n : ℕ}, Nat.Coprime k m → k ∣ m * n → k ∣ n"),

    # --- more divisibility ---
    ("Nat.dvd_sub_mod", "∀ {k : ℕ} (n : ℕ), k ∣ n - n % k"),
    ("Nat.mul_dvd_mul_left", "∀ (a : ℕ) {b c : ℕ}, b ∣ c → a * b ∣ a * c"),
    ("Nat.mul_dvd_mul_right", "∀ {a b : ℕ} (c : ℕ), a ∣ b → a * c ∣ b * c"),
    ("Nat.dvd_div_iff", "∀ {m n k : ℕ}, k ∣ n → (m ∣ n / k ↔ k * m ∣ n)"),
    ("Nat.div_dvd_iff_dvd_mul", "∀ {m n k : ℕ}, k ∣ m → 0 < k → (m / k ∣ n ↔ m ∣ k * n)"),
    ("Nat.not_dvd_of_lt", "∀ {m n : ℕ}, 0 < n → n < m → ¬m ∣ n"),
    ("Nat.eq_zero_of_dvd_of_lt", "∀ {a b : ℕ}, a ∣ b → b < a → b = 0"),
    ("Nat.dvd_factorial", "∀ {m n : ℕ}, 0 < m → m ≤ n → m ∣ n !"),

    # --- more primes / totient ---
    ("Nat.Prime.prime", "∀ {p : ℕ}, Nat.Prime p → Prime p"),
    ("Nat.Prime.factorization_self", "∀ {p : ℕ}, Nat.Prime p → p.factorization p = 1"),
    ("Nat.Prime.one_lt'", "∀ {p : ℕ}, Nat.Prime p → 1 < p"),
    ("Nat.prime_iff", "∀ {p : ℕ}, Nat.Prime p ↔ 2 ≤ p ∧ ∀ (m : ℕ), m ∣ p → m = 1 ∨ m = p"),
    ("Nat.not_prime_one", "¬Nat.Prime 1"),
    ("Nat.not_prime_zero", "¬Nat.Prime 0"),
    ("Nat.Prime.eq_one_or_self_of_prime", "∀ {p : ℕ}, Nat.Prime p → ∀ (n : ℕ), n ∣ p → n = 1 ∨ n = p"),
    ("Nat.totient_pos", "∀ {n : ℕ}, 0 < n → 0 < Nat.totient n"),
    ("Nat.totient_le", "∀ (n : ℕ), Nat.totient n ≤ n"),
    ("Nat.totient_lt", "∀ (n : ℕ), 1 < n → Nat.totient n < n"),
    ("Nat.totient_prime", "∀ {p : ℕ}, Nat.Prime p → Nat.totient p = p - 1"),
    ("Nat.totient_one", "Nat.totient 1 = 1"),
    ("Nat.totient_zero", "Nat.totient 0 = 0"),
    ("Nat.sum_totient", "∀ (n : ℕ), ∑ d ∈ n.divisors, Nat.totient d = n"),

    # --- more modular / ModEq ---
    ("Nat.ModEq.add_right", "∀ {n a b : ℕ} (c : ℕ), a ≡ b [MOD n] → a + c ≡ b + c [MOD n]"),
    ("Nat.ModEq.add_left", "∀ {n a b : ℕ} (c : ℕ), a ≡ b [MOD n] → c + a ≡ c + b [MOD n]"),
    ("Nat.ModEq.mul_right", "∀ {n a b : ℕ} (c : ℕ), a ≡ b [MOD n] → a * c ≡ b * c [MOD n]"),
    ("Nat.ModEq.mul_left", "∀ {n a b : ℕ} (c : ℕ), a ≡ b [MOD n] → c * a ≡ c * b [MOD n]"),
    ("Nat.ModEq.pow", "∀ {n a b : ℕ} (d : ℕ), a ≡ b [MOD n] → a ^ d ≡ b ^ d [MOD n]"),
    ("Nat.modEq_zero_iff_dvd", "∀ {a n : ℕ}, a ≡ 0 [MOD n] ↔ n ∣ a"),
    ("Nat.modEq_iff_dvd'", "∀ {n a b : ℕ}, a ≤ b → (a ≡ b [MOD n] ↔ n ∣ b - a)"),
    ("Nat.mod_mod_self", "∀ (n m : ℕ), n % m % m = n % m"),
    ("Nat.add_mul_mod_self_left", "∀ (a c b : ℕ), (a + c * b) % c = a % c"),
    ("Nat.add_mul_mod_self_right", "∀ (a b c : ℕ), (a + b * c) % c = a % c"),
    ("Nat.mul_mod_left", "∀ (a b : ℕ), a * b % a = 0"),
    ("Nat.mul_mod_right", "∀ (a b : ℕ), a * b % b = 0"),
    ("Nat.mod_self_add_one", "∀ (n : ℕ), n % (n + 1) = n"),

    # --- divisors / factorization ---
    ("Nat.mem_divisors", "∀ {n m : ℕ}, n ∈ m.divisors ↔ n ∣ m ∧ m ≠ 0"),
    ("Nat.one_mem_divisors", "∀ {n : ℕ}, 1 ∈ n.divisors ↔ n ≠ 0"),
    ("Nat.divisors_prime_pow", "∀ {p : ℕ}, Nat.Prime p → ∀ (n : ℕ), (p ^ n).divisors = (Finset.range (n + 1)).map ⟨(p ^ ·), Nat.pow_right_injective p.two_le⟩"),
    ("Nat.factorization_eq_zero_of_non_prime", "∀ (n : ℕ) {p : ℕ}, ¬Nat.Prime p → n.factorization p = 0"),
    ("Nat.factorization_mul", "∀ {a b : ℕ}, a ≠ 0 → b ≠ 0 → (a * b).factorization = a.factorization + b.factorization"),
    ("Nat.factorization_pow", "∀ (n k : ℕ), (n ^ k).factorization = k • n.factorization"),
    ("Nat.prod_factorization_eq", "∀ {n : ℕ}, n ≠ 0 → n.factorization.prod (· ^ ·) = n"),

    # --- integers (Mathlib.Data.Int.GCD, Int.ModEq) ---
    ("Int.gcd_comm", "∀ (m n : ℤ), Int.gcd m n = Int.gcd n m"),
    ("Int.gcd_dvd_left", "∀ {m n : ℤ}, ↑(Int.gcd m n) ∣ m"),
    ("Int.gcd_dvd_right", "∀ {m n : ℤ}, ↑(Int.gcd m n) ∣ n"),
    ("Int.dvd_refl", "∀ (a : ℤ), a ∣ a"),
    ("Int.dvd_add", "∀ {a b c : ℤ}, a ∣ b → a ∣ c → a ∣ b + c"),
    ("Int.dvd_mul_left", "∀ (a b : ℤ), a ∣ b * a"),
    ("Int.dvd_mul_right", "∀ (a b : ℤ), a ∣ a * b"),
    ("Int.even_or_odd", "∀ (n : ℤ), Even n ∨ Odd n"),
    ("Int.ModEq.refl", "∀ {n : ℤ} (a : ℤ), a ≡ a [ZMOD n]"),
    ("Int.ModEq.add", "∀ {n a b c d : ℤ}, a ≡ b [ZMOD n] → c ≡ d [ZMOD n] → a + c ≡ b + d [ZMOD n]"),
    ("Int.emod_emod_of_dvd", "∀ (n : ℤ) {m k : ℤ}, m ∣ k → n % k % m = n % m"),

    # --- parity (Mathlib.Algebra.Parity, Nat) ---
    ("Nat.even_add_one", "∀ {n : ℕ}, Even (n + 1) ↔ ¬Even n"),
    ("Nat.even_or_odd", "∀ (n : ℕ), Even n ∨ Odd n"),
    ("Nat.not_even_iff_odd", "∀ {n : ℕ}, ¬Even n ↔ Odd n"),
    ("Nat.even_mul_succ_self", "∀ (n : ℕ), Even (n * (n + 1))"),
    ("Nat.even_add", "∀ {m n : ℕ}, Even (m + n) ↔ (Even m ↔ Even n)"),
    ("Nat.odd_add", "∀ {m n : ℕ}, Odd (m + n) ↔ (Odd m ↔ Even n)"),
    ("Nat.even_pow", "∀ {m n : ℕ}, Even (m ^ n) ↔ Even m ∧ n ≠ 0"),
    ("Nat.even_sub", "∀ {m n : ℕ}, n ≤ m → (Even (m - n) ↔ (Even m ↔ Even n))"),
]


def main() -> None:
    out_path = Path(__file__).resolve().parent / "corpus.jsonl"
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for name, stmt in CORPUS:
        key = stmt.strip()
        if key in seen:
            continue
        seen.add(key)
        rows.append({"name": name, "statement": stmt})
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} real mathlib NT statements to {out_path}")


if __name__ == "__main__":
    main()
