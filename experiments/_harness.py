"""Shared ablation harness (§9).

Runs the real CRM loop in-process so the ablations can extract round-by-round
cumulative metrics and per-entry signals from the live ledger. The critic is
ALWAYS the real sandboxed CodeExecCritic — never mocked (§3, §15). The proposer
is the real Anthropic LLM (reads the conditioning context, so the genealogy
mechanism genuinely bites) with the deterministic offline fallback if no key.

Two knobs the ablations flip, EXACTLY one at a time:
  * `mode`            : "genealogy" | "control"   (genealogy ablation, §9.1)
  * `significance_on` : True | False              (significance ablation, §9.2)

When `significance_on=False` the significance critic still RUNS (so we can later
apply an INDEPENDENT triviality check), but its triviality verdict is NOT used
to suppress survivors: ANY valid statement counts as a survivor (the "off"
arm of §9.2). When True, trivial survivors get score 0 and are excluded, exactly
as the loop does in production.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from crm.accounting import Accountant
from crm.genealogy import Entry, Ledger, build_conditioning_context
from crm.novelty import certify_novel
from crm.run import (
    _build_critic,
    _build_proposer,
    _load_jsonl_objects,
    _load_jsonl_statements,
)
from crm.significance import SignificanceCritic
from experiments._indep_oracle import independent_trivial_rate


@dataclass
class RunResult:
    """Outcome of one ablation arm-run (one mode/sig-flag at one seed)."""

    ledger: Ledger
    metrics: dict
    # cumulative-by-round series (len == rounds)
    cum_certified: list[int] = field(default_factory=list)
    cum_survivors: list[int] = field(default_factory=list)
    cum_total: list[int] = field(default_factory=list)
    # per-run scalars
    mean_significance: float = 0.0
    survival_rate: float = 0.0
    trivial_rate: float = 0.0
    # independent triviality check (§9.2): fraction of survivors that an
    # INDEPENDENT automation oracle judges trivial/vacuous.
    indep_trivial_rate: float = 0.0
    critic: Any = None
    # True if the (API) proposer silently degraded to the offline,
    # context-IGNORING generator — which INVALIDATES any genealogy claim, so
    # callers must check this and fail loudly (review hard rule).
    using_fallback: bool = False
    proposer_name: str = "?"


def _build_components(cfg: dict[str, Any]):
    proposer = _build_proposer(cfg.get("proposer", {}))
    critic = _build_critic(cfg.get("critic", "code_exec"), cfg)

    sig_cfg = cfg.get("significance", {})
    weights = cfg.get("weights", {})
    corpus_path = cfg.get("corpus_path", "data/corpus.jsonl")
    corpus = _load_jsonl_statements(corpus_path)
    breadth_path = cfg.get("breadth_targets_path", corpus_path)
    breadth = _load_jsonl_statements(breadth_path)
    # Structured downstream-enablement targets (rows with a `solve`), mirroring
    # crm.run.run_from_config. WITHOUT these the code-exec critic's real
    # `enables` hook never fires and breadth silently collapses to 0 for the
    # code domain (review recon: breadth=0 for all api_code scored entries).
    breadth_specs = [o for o in _load_jsonl_objects(breadth_path) if "solve" in o]

    embedder = cfg.get("embedder")
    if cfg.get("offline_embedder", False):
        embedder = "hash"

    significance = SignificanceCritic(
        w_novelty=weights.get("novelty", 0.3),
        w_breadth=weights.get("breadth", 0.3),
        w_hardness=weights.get("hardness", 0.4),
        tau=cfg.get("tau", 0.25),
        perturbations=cfg.get("perturbations", 8),
        breadth_targets=sig_cfg.get("breadth_targets", 8),
        embedder=embedder,
        corpus_statements=corpus,
        breadth_target_statements=breadth,
        breadth_target_specs=breadth_specs,
        seed=int(cfg.get("seed", 0)),
        perturb_strategy=cfg.get("perturb_strategy", "literal"),
    )
    return proposer, critic, significance, corpus


def run_arm(
    cfg: dict[str, Any],
    *,
    mode: str,
    seed: int,
    significance_on: bool,
    out_dir: str | Path | None = None,
) -> RunResult:
    """Run one arm of an ablation: a full CRM loop with the real critic.

    Mirrors crm.loop.CRMLoop.run (§8) but records cumulative-by-round series and
    the per-entry signals the ablations report. The ONLY behavioural difference
    from production is the `significance_on` switch (§9.2).
    """
    rounds = int(cfg.get("rounds", 3))
    k = int(cfg.get("k", 6))
    topic = cfg.get("topic", "elementary number theory")
    delta = float(cfg.get("delta", 0.35))

    proposer, critic, sig, corpus = _build_components(cfg)
    ledger = Ledger()
    acct = Accountant(
        est_cost_per_1k_in=cfg.get("est_cost_per_1k_in", 0.0),
        est_cost_per_1k_out=cfg.get("est_cost_per_1k_out", 0.0),
    )

    random.seed(seed)
    np.random.seed(seed % (2**32))

    cum_certified: list[int] = []
    cum_survivors: list[int] = []
    cum_total: list[int] = []

    # Keep the live Conjecture next to its Entry so the INDEPENDENT triviality
    # oracle (which needs the executable payload) can run on survivors later.
    pairs: list[tuple[Entry, Any]] = []

    # Running set of statements THIS arm has already certified-novel, so a later
    # near-duplicate of an earlier survivor is blocked (review finding #7).
    accepted: list[str] = []

    for r in range(rounds):
        ctx = build_conditioning_context(ledger, topic, k, mode=mode)
        batch = proposer.propose(ctx, k=k, seed=seed + r)
        acct.log_proposer(
            getattr(proposer, "last_tokens_in", 0),
            getattr(proposer, "last_tokens_out", 0),
        )
        for c in batch:
            c.round = r
            cr = critic.check(c)
            acct.log_critic(cr.critic_seconds)
            entry = Entry.from_conjecture(c, cr, surviving=cr.valid)
            pairs.append((entry, c))
            if cr.valid:
                s = sig.score(c, critic, corpus)
                entry.significance = s
                if significance_on:
                    # production behaviour: trivial -> suppressed, score 0.
                    entry.surviving = not s.is_trivial
                    entry.certified_novel = entry.surviving and certify_novel(
                        c.statement,
                        s,
                        corpus,
                        delta=delta,
                        critic=critic,
                        accepted_survivors=accepted,
                    )
                else:
                    # "off" arm (§9.2): ANY valid statement counts; no triviality
                    # suppression and no content gate on certification.
                    entry.surviving = True
                    entry.certified_novel = certify_novel(
                        c.statement,
                        s,
                        corpus,
                        delta=delta,
                        critic=critic,
                        accepted_survivors=accepted,
                    )
                if entry.certified_novel:
                    accepted.append(c.statement)
            ledger.add(entry)
        acct.snapshot(round=r)
        cum_certified.append(len(ledger.certified()))
        cum_survivors.append(len(ledger.survivors()))
        cum_total.append(len(ledger.entries))

    metrics = acct.metrics(
        certified_novel=len(ledger.certified()),
        surviving=len(ledger.survivors()),
        total_conjectures=len(ledger.entries),
    )
    metrics.update(
        {
            "mode": mode,
            "seed": seed,
            "significance_on": significance_on,
            "topic": topic,
            "k": k,
            "n_rounds": rounds,
            "critic": getattr(critic, "name", "?"),
            "proposer": getattr(proposer, "name", "?"),
        }
    )

    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        ledger.dump(out / "ledger.jsonl")

    # ----- per-run scalars (secondary metrics, §9.1 / §9.2) -----------------
    survivors = ledger.survivors()
    valid = [e for e in ledger.entries if e.crit.valid]
    sig_scores = [
        e.significance.score for e in survivors if e.significance is not None
    ]
    mean_sig = float(np.mean(sig_scores)) if sig_scores else 0.0
    survival_rate = len(survivors) / len(ledger.entries) if ledger.entries else 0.0

    # In-loop trivial rate among valid conjectures (uses the loop's own verdict).
    n_trivial = sum(
        1
        for e in valid
        if e.significance is not None and e.significance.is_trivial
    )
    trivial_rate = n_trivial / len(valid) if valid else 0.0

    # INDEPENDENT triviality check over the SURVIVORS of THIS arm (§9.2 metric):
    # a SEPARATELY-IMPLEMENTED oracle (experiments._indep_oracle) decides
    # triviality, sharing NO code with the significance gate's
    # `automation_closeable_conjecture` (review finding #5). We use the live
    # Conjecture payloads captured during the run.
    surviving_pairs = [(e, c) for (e, c) in pairs if e.surviving]
    indep_trivial = _independent_trivial_rate(surviving_pairs, critic)

    return RunResult(
        ledger=ledger,
        metrics=metrics,
        cum_certified=cum_certified,
        cum_survivors=cum_survivors,
        cum_total=cum_total,
        mean_significance=mean_sig,
        survival_rate=survival_rate,
        trivial_rate=trivial_rate,
        indep_trivial_rate=indep_trivial,
        critic=critic,
        using_fallback=bool(getattr(proposer, "using_fallback", False)),
        proposer_name=getattr(proposer, "name", "?"),
    )


def _independent_trivial_rate(surviving_pairs: list[tuple[Entry, Any]], critic) -> float:
    """Fraction of survivors a GENUINELY-INDEPENDENT oracle calls trivial (§9.2).

    Review finding #5: the previous implementation called
    `critic.automation_closeable_conjecture` — the SAME degenerate-impl probe the
    significance critic uses to compute `is_trivial` — so the significance
    ablation was measuring the gate with itself (near-tautological).

    The verdict now comes from `experiments._indep_oracle`, a separately
    implemented oracle that shares NO code with the gate: it uses a different
    degenerate battery ({n-1, n+1, n*n, seeded-const} vs the gate's {0, 1, n,
    True}), a DISJOINT (upper-half) sampling subdomain, and a large seed offset,
    so its sample stream cannot collide with the critic's. It still decides by
    REAL sandbox execution (no LLM-as-judge, §3, §15). A documented residual
    fallback to the recorded hardness signal applies ONLY when a survivor has no
    `property` for the oracle to interrogate (see `_indep_oracle`).
    """
    return independent_trivial_rate(
        surviving_pairs,
        timeout_s=getattr(critic, "timeout_s", 5.0),
        n_adversarial=max(24, 2 * getattr(critic, "n_adversarial", 12)),
        seed=getattr(critic, "seed", 0),
    )
