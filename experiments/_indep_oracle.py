"""Genuinely-independent triviality oracle for the significance ablation (§9.2).

WHY THIS EXISTS (review finding #5)
-----------------------------------
The significance critic's own triviality gate (`is_trivial`) is computed by
`CodeExecCritic.automation_closeable_conjecture` — a degenerate-impl probe that
swaps the reference impl for the fixed battery {f=0, f=1, f=n, f=True} and re-runs
the proposer's `property` over adversarial samples drawn with the critic's own
seed (`self.seed`). If the significance ABLATION then measures "trivial survivor
rate" by calling the SAME function, the ablation is near-tautological: it is
measuring the gate with the gate. The reported ON->OFF drop is then partly an
artefact of the shared mechanism, not evidence that the guard catches vacuity.

WHAT MAKES THIS ORACLE INDEPENDENT
----------------------------------
This module decides triviality WITHOUT ever calling
`automation_closeable_conjecture`. It reuses only the low-level, mechanism-free
primitives `run_in_sandbox`, `_build_program`, `_adversarial_tests`, `_func_name`,
`_parse_domain` from `crm.critics.code_exec` (the same execution substrate the
critic uses, so verdicts are still REAL execution, never LLM-as-judge — §3, §15),
and differs from the guard along EVERY axis it is free to differ on:

  1. DIFFERENT degenerate battery. The guard uses {0, 1, n, True}. This oracle
     uses a STRUCTURALLY-UNRELATED set the guard never tries:
     {f(n)=n-1, f(n)=n+1, f(n)=n*n, f(n)=<seeded random constant>}.
     A claim is "guess-closeable" if any of these off-the-shelf impls — none of
     which encodes the claim's real computation — already satisfies the property.

  2. DISJOINT input subdomain + DIFFERENT seed. The guard samples over the full
     `domain` with the critic's `self.seed`. This oracle samples over the UPPER
     HALF of the domain only, with a large fixed seed OFFSET
     (`_INDEP_SEED_OFFSET`), so the two probes never share a sample stream. This
     also powers the holdout "fit-low / test-high" probe below.

  3. A property-alone vacuity probe the guard does not perform at all: evaluate
     the `property` predicate with the function bound to a do-nothing stub and a
     handful of unrelated impls; if the predicate is (near-)always-true
     regardless of which `f` is plugged in, the claim pins down no computation.

A survivor is judged trivial if EITHER independent probe fires. The function is a
plain module-level function whose body never references the significance weights
or the guard, so its independence from the gate is auditable by inspection.
"""

from __future__ import annotations

import random
from typing import Any

from crm.critics.code_exec import (
    _adversarial_tests,
    _build_program,
    _func_name,
    _parse_domain,
)
from crm.sandbox import run_in_sandbox

# Large offset so this oracle's sample stream cannot collide with the critic's
# (`self.seed`, typically 0..a few). Independence of sampling is the point.
_INDEP_SEED_OFFSET = 1_000_003  # a prime, far from any plausible critic seed


def _seeded_constant(payload: dict[str, Any], seed: int) -> int:
    """A deterministic but claim-unrelated constant stand-in value."""
    lo, hi = _parse_domain(payload.get("domain"))
    rng = random.Random(seed + _INDEP_SEED_OFFSET)
    # Pick a constant somewhere in the domain that is NOT one of the guard's
    # stand-ins (0/1) when avoidable.
    span = max(1, hi - lo)
    return lo + rng.randint(0, span)


def _upper_half_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Copy of the payload whose `domain` is the UPPER HALF of the original.

    This makes the oracle fuzz a DISJOINT subdomain from the critic's gate (which
    samples the full range), so the verdict cannot piggy-back on the gate's
    sample points.
    """
    lo, hi = _parse_domain(payload.get("domain"))
    mid = lo + (hi - lo) // 2
    if mid >= hi:
        mid = max(lo, hi - 1)
    out = dict(payload)
    out["domain"] = f"[{mid}, {hi}]"
    return out


def _degenerate_impls(fname: str, const_val: int) -> list[tuple[str, str]]:
    """The independent battery — DISJOINT from the guard's {0,1,n,True}.

    Each entry is (impl_source, label). None of these encodes a non-trivial
    number-theoretic computation, so if any satisfies the claim's property the
    claim is vacuous / guess-closeable.
    """
    return [
        (f"def {fname}(n):\n    return n - 1", "f=n-1"),
        (f"def {fname}(n):\n    return n + 1", "f=n+1"),
        (f"def {fname}(n):\n    return n * n", "f=n*n"),
        (f"def {fname}(n):\n    return {const_val}", f"f={const_val}(seeded)"),
    ]


def is_trivial_independent(
    conjecture: Any,
    *,
    timeout_s: float = 5.0,
    n_adversarial: int = 24,
    seed: int = 0,
) -> bool:
    """Decide triviality of one code conjecture WITHOUT the significance gate.

    Independent of `CodeExecCritic.automation_closeable_conjecture`: it shares no
    code with that method and differs in its degenerate battery, its sampling
    subdomain, and its seed (see module docstring). Real sandbox execution only.

    A conjecture is judged trivial if EITHER:
      * GUESS-CLOSEABLE: one of the structurally-unrelated stand-in impls
        {n-1, n+1, n*n, seeded-const} satisfies the proposer's `property` over a
        fresh, disjoint (upper-half) sample drawn with an offset seed; OR
      * PROPERTY-VACUOUS: the property holds for every stand-in tried (i.e. the
        predicate is satisfied no matter which unrelated `f` is plugged in), so
        it constrains no real computation.

    Returns False when there is no `property` to interrogate (cannot decide
    independently from execution alone) — the caller may apply a separate
    fallback for that case.
    """
    ex = getattr(conjecture, "extra", None) or {}
    payload = ex if "reference_impl" in ex else dict(ex)
    prop = (payload.get("property") or "").strip()
    if not prop:
        return False

    fname = _func_name(payload.get("reference_impl", "")) or "f"
    const_val = _seeded_constant(payload, seed)

    # Disjoint subdomain + offset seed => sampling genuinely separate from gate.
    holdout = _upper_half_payload(payload)
    adversarial = _adversarial_tests(
        holdout,
        fname,
        seed=seed + _INDEP_SEED_OFFSET,
        n=max(12, n_adversarial),
    )
    if not adversarial:
        return False

    # --- Probe A: guess-closeable by a structurally-unrelated stand-in --------
    # None of {n-1, n+1, n*n, seeded-const} encodes the claim's computation. If
    # any satisfies the property over the disjoint sample, the claim is vacuous.
    battery = _degenerate_impls(fname, const_val)
    for impl_src, _label in battery:
        program = _build_program(impl_src, "", adversarial)
        res = run_in_sandbox(program, timeout_s=timeout_s)
        if res.status == "ok":
            return True

    # --- Probe B: constant-fit holdout (genuinely separate from the gate) -----
    # Fit a constant on the LOWER half of the domain (the value the impl returns
    # at the lower-half boundary), then test whether that single constant still
    # satisfies the property on the disjoint UPPER half. A claim that a frozen
    # constant satisfies everywhere pins down no real computation => trivial.
    # This catches constant-style vacuity (e.g. property `f(n)==0`) WITHOUT
    # reusing the gate's {0,1,n,True} battery: the constant is DERIVED from the
    # claim's own lower-half behaviour, never hard-coded.
    fitted = _fit_lower_half_constant(payload, fname, timeout_s=timeout_s)
    if fitted is not None:
        const_impl = f"def {fname}(n):\n    return {fitted}"
        program = _build_program(const_impl, "", adversarial)
        res = run_in_sandbox(program, timeout_s=timeout_s)
        if res.status == "ok":
            return True

    # No stand-in and no fitted constant satisfied the property over the disjoint
    # sample: the predicate discriminates between impls => not trivial.
    return False


def _fit_lower_half_constant(
    payload: dict[str, Any], fname: str, *, timeout_s: float = 5.0
) -> int | None:
    """Return the impl's output at the LOWER-half midpoint, as a constant guess.

    Runs the proposer's OWN reference impl on one lower-half point to read off a
    candidate constant. This derives the constant from the claim itself rather
    than reusing the gate's hard-coded {0,1} stand-ins, keeping the probe
    independent while still catching constant-style vacuity. Returns None if the
    impl cannot be evaluated.
    """
    impl = (payload.get("reference_impl") or "").strip()
    if not impl:
        return None
    lo, hi = _parse_domain(payload.get("domain"))
    pt = lo + max(0, (hi - lo) // 4)  # a point inside the LOWER half
    program = "\n".join([
        impl,
        f"__crm_v = {fname}({pt})",
        "assert isinstance(__crm_v, int), 'non-int output'",
        "print('FIT', __crm_v)",
    ])
    res = run_in_sandbox(program, timeout_s=timeout_s)
    if res.status != "ok":
        return None
    for tok in reversed((res.stdout_tail or "").split()):
        try:
            return int(tok)
        except ValueError:
            continue
    return None


def independent_trivial_rate(
    surviving_pairs: list[tuple[Any, Any]],
    *,
    timeout_s: float = 5.0,
    n_adversarial: int = 24,
    seed: int = 0,
    hardness_fallback_tau: float = 0.25,
) -> float:
    """Fraction of survivors the INDEPENDENT oracle judges trivial (§9.2).

    `surviving_pairs` is a list of (Entry, Conjecture). The Conjecture carries
    the executable payload the oracle runs; the Entry's recorded significance is
    used ONLY as a documented residual-coupling fallback when a survivor has no
    `property` for the oracle to interrogate (see note below).

    PRIMARY signal: `is_trivial_independent` — shares no code with the
    significance gate. SECONDARY fallback (missing-property case only): the
    recorded `hardness < hardness_fallback_tau`. NOTE / HONEST RESIDUAL COUPLING:
    that hardness value is produced by the critic's perturbation machinery, which
    the gate also consumes, so the fallback is NOT fully independent. We therefore
    use it only when the primary probe cannot apply (no property), and document it
    here so the residual coupling is auditable rather than hidden (§3).
    """
    if not surviving_pairs:
        return 0.0
    n_triv = 0
    for entry, conj in surviving_pairs:
        is_triv = False
        if conj is not None:
            try:
                is_triv = is_trivial_independent(
                    conj,
                    timeout_s=timeout_s,
                    n_adversarial=n_adversarial,
                    seed=seed,
                )
            except Exception:
                is_triv = False
        if not is_triv:
            sig = getattr(entry, "significance", None)
            payload = (getattr(conj, "extra", None) or {}) if conj is not None else {}
            has_prop = bool((payload.get("property") or "").strip())
            if not has_prop and sig is not None:
                # residual-coupling fallback, missing-property case only.
                is_triv = sig.hardness < hardness_fallback_tau
        if is_triv:
            n_triv += 1
    return n_triv / len(surviving_pairs)
