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
from crm.run import _build_critic, _build_proposer, _load_jsonl_statements
from crm.significance import SignificanceCritic


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


def _build_components(cfg: dict[str, Any]):
    proposer = _build_proposer(cfg.get("proposer", {}))
    critic = _build_critic(cfg.get("critic", "code_exec"), cfg)

    sig_cfg = cfg.get("significance", {})
    weights = cfg.get("weights", {})
    corpus_path = cfg.get("corpus_path", "data/corpus.jsonl")
    corpus = _load_jsonl_statements(corpus_path)
    breadth_path = cfg.get("breadth_targets_path", corpus_path)
    breadth = _load_jsonl_statements(breadth_path)

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
        seed=int(cfg.get("seed", 0)),
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
                        c.statement, s, corpus, delta=delta, critic=critic
                    )
                else:
                    # "off" arm (§9.2): ANY valid statement counts; no triviality
                    # suppression and no content gate on certification.
                    entry.surviving = True
                    entry.certified_novel = certify_novel(
                        c.statement, s, corpus, delta=delta, critic=critic
                    )
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
    # a fresh automation oracle (the critic's degenerate-impl probe) decides
    # triviality, independent of whatever the loop used to gate survival. We use
    # the live Conjecture payloads captured during the run.
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
    )


def _independent_trivial_rate(surviving_pairs: list[tuple[Entry, Any]], critic) -> float:
    """Fraction of survivors an INDEPENDENT automation oracle calls trivial.

    The oracle is the critic's `automation_closeable_conjecture` — a real
    execution probe that replaces the impl with degenerate stand-ins (f=0/1/n)
    and checks whether the proposer's property is still satisfied. This is
    independent of the significance critic's own gating (it does not look at the
    novelty/breadth/hardness *weights*), so it is a fair, automation-only check
    of whether a "survivor" is vacuous (§9.2). When the property is missing we
    fall back to the recorded hardness<0.25 signal.
    """
    if not surviving_pairs:
        return 0.0
    oracle = getattr(critic, "automation_closeable_conjecture", None)
    n_triv = 0
    for e, c in surviving_pairs:
        is_triv = False
        if callable(oracle) and c is not None:
            try:
                is_triv = bool(oracle(c))
            except Exception:
                is_triv = False
        if not is_triv and e.significance is not None:
            # secondary independent signal: a near-zero-hardness statement is
            # vacuous regardless of the gating used.
            is_triv = e.significance.hardness < 0.25
        if is_triv:
            n_triv += 1
    return n_triv / len(surviving_pairs)
