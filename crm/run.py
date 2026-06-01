"""CLI entrypoint (§4).

    python -m crm.run --config configs/smoke.yaml

Loads a YAML config, builds the proposer/critic/significance/ledger/accountant,
runs the CRMLoop, and writes results/<run>/ledger.jsonl + metrics.json.
"""

from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path
from typing import Any

import yaml

from crm.accounting import Accountant
from crm.genealogy import Ledger
from crm.loop import CRMLoop, LoopConfig
from crm.proposer import APIProposer, LocalProposer, StubProposer
from crm.significance import SignificanceCritic


def _build_critic(name: str):
    name = (name or "mock").lower()
    if name == "mock":
        from crm.critics.mock import MockCritic

        return MockCritic()
    # code_exec / lean land in later phases.
    raise ValueError(f"unknown / not-yet-implemented critic: {name!r}")


def _build_proposer(spec: dict[str, Any]):
    kind = (spec.get("kind") or "stub").lower()
    if kind == "stub":
        return StubProposer()
    if kind == "api":
        return APIProposer(**spec)
    if kind == "local":
        return LocalProposer(**spec)
    raise ValueError(f"unknown proposer kind: {kind!r}")


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def run_from_config(cfg: dict[str, Any], run_name: str | None = None) -> dict:
    results_root = Path(cfg.get("results_dir", "results"))
    if run_name is None:
        ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        run_name = f"{cfg.get('name', 'run')}-{ts}"
    out_dir = results_root / run_name

    proposer = _build_proposer(cfg.get("proposer", {}))
    critic = _build_critic(cfg.get("critic", "mock"))

    sig_cfg = cfg.get("significance", {})
    weights = cfg.get("weights", {})
    significance = SignificanceCritic(
        w_novelty=weights.get("novelty", 0.3),
        w_breadth=weights.get("breadth", 0.3),
        w_hardness=weights.get("hardness", 0.4),
        tau=cfg.get("tau", 0.25),
        perturbations=cfg.get("perturbations", 8),
        breadth_targets=sig_cfg.get("breadth_targets", 8),
        embedder=cfg.get("embedder"),
    )

    accountant = Accountant(
        est_cost_per_1k_in=cfg.get("est_cost_per_1k_in", 0.0),
        est_cost_per_1k_out=cfg.get("est_cost_per_1k_out", 0.0),
    )

    loop_config = LoopConfig(
        topic=cfg.get("topic", "elementary number theory"),
        rounds=int(cfg.get("rounds", 2)),
        k=int(cfg.get("k", 4)),
        seed=int(cfg.get("seed", 0)),
        mode=cfg.get("mode", "genealogy"),
        proof_budget_s=float(cfg.get("proof_budget_s", 5.0)),
    )

    loop = CRMLoop(
        proposer=proposer,
        critic=critic,
        significance=significance,
        ledger=Ledger(),
        accountant=accountant,
        config=loop_config,
        corpus=[],
    )
    metrics = loop.run(out_dir)
    print(f"[crm] run complete: {out_dir}")
    print(f"[crm]   ledger:  {out_dir / 'ledger.jsonl'}")
    print(f"[crm]   metrics: {out_dir / 'metrics.json'}")
    print(
        f"[crm]   conjectures={metrics['total_conjectures']} "
        f"surviving={metrics['surviving']} certified_novel={metrics['certified_novel']}"
    )
    return metrics


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the CRM loop from a YAML config.")
    ap.add_argument("--config", required=True, help="path to a YAML config")
    ap.add_argument("--run-name", default=None, help="explicit results/<run> name")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    run_from_config(cfg, run_name=args.run_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
