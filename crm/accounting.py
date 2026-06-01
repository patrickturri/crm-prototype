"""Accountant: tokens / compute / time meter (§10).

Meters, per round and total: proposer tokens in/out (+ est. cost if API),
embedding calls, critic invocations and critic wall-seconds, total wall-clock,
GPU-seconds (local). Produces the headline KPIs into metrics.json:

    certified_novel_per_kilo_token  = certified_novel / (proposer_tokens / 1000)
    certified_novel_per_critic_hour = certified_novel / (critic_seconds / 3600)
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class RoundSnapshot:
    round: int
    proposer_tokens_in: int
    proposer_tokens_out: int
    embedding_calls: int
    critic_invocations: int
    critic_seconds: float
    gpu_seconds: float
    wall_seconds: float


@dataclass
class Accountant:
    """Accumulates compute/cost meters and computes per-compute KPIs."""

    est_cost_per_1k_in: float = 0.0
    est_cost_per_1k_out: float = 0.0

    proposer_tokens_in: int = 0
    proposer_tokens_out: int = 0
    embedding_calls: int = 0
    critic_invocations: int = 0
    critic_seconds: float = 0.0
    gpu_seconds: float = 0.0

    _start: float = field(default_factory=time.monotonic)
    snapshots: list[RoundSnapshot] = field(default_factory=list)
    # internal: meters captured at last snapshot, to compute per-round deltas
    _last: dict[str, float] = field(default_factory=dict)

    # ---- metering hooks -------------------------------------------------
    def log_proposer(self, tokens_in: int, tokens_out: int) -> None:
        self.proposer_tokens_in += int(tokens_in)
        self.proposer_tokens_out += int(tokens_out)

    def log_embedding(self, n: int = 1) -> None:
        self.embedding_calls += int(n)

    def log_critic(self, critic_seconds: float, invocations: int = 1) -> None:
        self.critic_seconds += float(critic_seconds)
        self.critic_invocations += int(invocations)

    def log_gpu(self, gpu_seconds: float) -> None:
        self.gpu_seconds += float(gpu_seconds)

    # ---- snapshots ------------------------------------------------------
    def snapshot(self, round: int) -> RoundSnapshot:
        last = self._last
        snap = RoundSnapshot(
            round=round,
            proposer_tokens_in=self.proposer_tokens_in - int(last.get("ti", 0)),
            proposer_tokens_out=self.proposer_tokens_out - int(last.get("to", 0)),
            embedding_calls=self.embedding_calls - int(last.get("emb", 0)),
            critic_invocations=self.critic_invocations - int(last.get("ci", 0)),
            critic_seconds=self.critic_seconds - last.get("cs", 0.0),
            gpu_seconds=self.gpu_seconds - last.get("gpu", 0.0),
            wall_seconds=time.monotonic() - self._start - last.get("wall", 0.0),
        )
        self.snapshots.append(snap)
        self._last = {
            "ti": self.proposer_tokens_in,
            "to": self.proposer_tokens_out,
            "emb": self.embedding_calls,
            "ci": self.critic_invocations,
            "cs": self.critic_seconds,
            "gpu": self.gpu_seconds,
            "wall": time.monotonic() - self._start,
        }
        return snap

    # ---- KPIs / dump ----------------------------------------------------
    @property
    def total_tokens(self) -> int:
        return self.proposer_tokens_in + self.proposer_tokens_out

    @property
    def est_cost_usd(self) -> float:
        return (
            self.proposer_tokens_in / 1000.0 * self.est_cost_per_1k_in
            + self.proposer_tokens_out / 1000.0 * self.est_cost_per_1k_out
        )

    def metrics(self, certified_novel: int, surviving: int, total_conjectures: int) -> dict:
        tokens = self.total_tokens
        per_kilo_token = (
            certified_novel / (tokens / 1000.0) if tokens > 0 else 0.0
        )
        per_critic_hour = (
            certified_novel / (self.critic_seconds / 3600.0)
            if self.critic_seconds > 0
            else 0.0
        )
        return {
            "certified_novel": certified_novel,
            "surviving": surviving,
            "total_conjectures": total_conjectures,
            "proposer_tokens_in": self.proposer_tokens_in,
            "proposer_tokens_out": self.proposer_tokens_out,
            "proposer_tokens_total": tokens,
            "embedding_calls": self.embedding_calls,
            "critic_invocations": self.critic_invocations,
            "critic_seconds": round(self.critic_seconds, 6),
            "gpu_seconds": round(self.gpu_seconds, 6),
            "wall_seconds": round(time.monotonic() - self._start, 6),
            "est_cost_usd": round(self.est_cost_usd, 6),
            "certified_novel_per_kilo_token": per_kilo_token,
            "certified_novel_per_critic_hour": per_critic_hour,
            "rounds": [asdict(s) for s in self.snapshots],
        }

    def dump_metrics(
        self,
        path: str | Path,
        certified_novel: int,
        surviving: int,
        total_conjectures: int,
        extra: dict | None = None,
    ) -> dict:
        m = self.metrics(certified_novel, surviving, total_conjectures)
        if extra:
            m.update(extra)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(m, indent=2, sort_keys=True), encoding="utf-8")
        return m
