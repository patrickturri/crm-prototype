"""CRMLoop orchestrator (§8).

Implements the §8 pseudocode faithfully:

    for r in rounds:
        ctx   = build_conditioning_context(ledger, topic, k, mode)
        batch = proposer.propose(ctx, k, seed+r)         # acct logs tokens
        for c in batch:
            cr = critic.check(c)                         # acct logs critic_seconds
            entry = Entry(c, cr, surviving=cr.valid)
            if cr.valid:
                entry.significance   = sig.score(c, critic, corpus)
                entry.surviving      = not significance.is_trivial
                entry.certified_novel = surviving and certify_novel(...)
            ledger.add(entry)
        acct.snapshot(round=r)
    ledger.dump(); acct.dump_metrics()
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from crm.accounting import Accountant
from crm.critics.base import Critic
from crm.genealogy import Entry, Ledger, build_conditioning_context
from crm.novelty import certify_novel
from crm.proposer import Proposer
from crm.significance import SignificanceCritic


@dataclass
class LoopConfig:
    topic: str = "elementary number theory"
    rounds: int = 2
    k: int = 4
    seed: int = 0
    mode: str = "genealogy"  # "genealogy" | "control"
    proof_budget_s: float = 5.0
    extra: dict[str, Any] = field(default_factory=dict)


class CRMLoop:
    def __init__(
        self,
        proposer: Proposer,
        critic: Critic,
        significance: SignificanceCritic,
        ledger: Ledger,
        accountant: Accountant,
        config: LoopConfig,
        corpus: list[str] | None = None,
    ) -> None:
        self.proposer = proposer
        self.critic = critic
        self.sig = significance
        self.ledger = ledger
        self.acct = accountant
        self.config = config
        self.corpus = corpus or []

    def run(self, out_dir: str | Path) -> dict:
        cfg = self.config
        # Determinism: seed everything (§3.7, §11).
        random.seed(cfg.seed)
        np.random.seed(cfg.seed % (2**32))

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)

        # Verifiable artifacts per conjecture (e.g. code-exec reference_impl +
        # tests). Kept OUT of the §5.1 ledger schema (which stays stable) but
        # persisted alongside it so REPORT/SURVIVORS can attach the REAL proof
        # or tests the critic actually ran. Never fabricated — copied verbatim
        # from the conjecture the critic graded.
        artifacts: dict[str, dict] = {}

        # Running set of statements already certified-novel THIS run, so a later
        # near-duplicate of an earlier survivor is blocked (review finding #7).
        accepted: list[str] = []

        for r in range(cfg.rounds):
            ctx = build_conditioning_context(
                self.ledger, cfg.topic, cfg.k, mode=cfg.mode
            )
            batch = self.proposer.propose(ctx, k=cfg.k, seed=cfg.seed + r)

            # Token accounting from the proposer (real strings, not fabricated).
            self.acct.log_proposer(
                getattr(self.proposer, "last_tokens_in", 0),
                getattr(self.proposer, "last_tokens_out", 0),
            )

            for c in batch:
                c.round = r
                cr = self.critic.check(c)
                self.acct.log_critic(cr.critic_seconds)

                entry = Entry.from_conjecture(c, cr, surviving=cr.valid)
                if cr.valid:
                    sig = self.sig.score(c, self.critic, self.corpus)
                    entry.significance = sig
                    entry.surviving = not sig.is_trivial
                    entry.certified_novel = entry.surviving and certify_novel(
                        c.statement,
                        sig,
                        self.corpus,
                        critic=self.critic,
                        accepted_survivors=accepted,
                    )
                    if entry.certified_novel:
                        accepted.append(c.statement)
                self.ledger.add(entry)

                ex = dict(c.extra or {})
                if ex:
                    artifacts[c.id] = {
                        "reference_impl": ex.get("reference_impl", ""),
                        "tests": ex.get("tests", ""),
                        "property": ex.get("property", ""),
                        "domain": ex.get("domain", ""),
                        "lean_statement": ex.get("lean_statement", ""),
                    }

            self.acct.snapshot(round=r)

        ledger_path = out / "ledger.jsonl"
        metrics_path = out / "metrics.json"
        self.ledger.dump(ledger_path)
        if artifacts:
            import json as _json

            with open(out / "artifacts.json", "w", encoding="utf-8") as f:
                _json.dump(artifacts, f, ensure_ascii=False, indent=2)
        metrics = self.acct.dump_metrics(
            metrics_path,
            certified_novel=len(self.ledger.certified()),
            surviving=len(self.ledger.survivors()),
            total_conjectures=len(self.ledger.entries),
            extra={
                "topic": cfg.topic,
                "n_rounds": cfg.rounds,
                "k": cfg.k,
                "seed": cfg.seed,
                "mode": cfg.mode,
                "critic": getattr(self.critic, "name", "?"),
                "proposer": getattr(self.proposer, "name", "?"),
            },
        )
        return metrics
