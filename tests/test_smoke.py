"""Phase 0 smoke tests: the loop runs on the MockCritic and writes outputs."""

from __future__ import annotations

import json
from pathlib import Path

from crm.accounting import Accountant
from crm.critics.mock import MockCritic
from crm.genealogy import Ledger, build_conditioning_context
from crm.loop import CRMLoop, LoopConfig
from crm.proposer import StubProposer
from crm.significance import SignificanceCritic


def _run(tmp_path: Path, mode: str = "genealogy"):
    cfg = LoopConfig(rounds=2, k=4, seed=0, mode=mode)
    loop = CRMLoop(
        proposer=StubProposer(),
        critic=MockCritic(),
        significance=SignificanceCritic(),
        ledger=Ledger(),
        accountant=Accountant(),
        config=cfg,
    )
    return loop.run(tmp_path), tmp_path


def test_loop_writes_ledger_and_metrics(tmp_path):
    metrics, out = _run(tmp_path)
    ledger = out / "ledger.jsonl"
    mfile = out / "metrics.json"
    assert ledger.exists()
    assert mfile.exists()

    rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
    # 2 rounds * k=4 = 8 conjectures.
    assert len(rows) == 8

    # §5.1 schema keys present on every row.
    required = {
        "id", "round", "parent_ids", "statement", "nl_gloss",
        "proof_attempt", "crit", "significance", "surviving", "certified_novel",
    }
    for row in rows:
        assert required <= set(row.keys())
        assert set(row["crit"].keys()) == {
            "valid", "reason_class", "detail", "proof_method", "critic_seconds",
        }


def test_metrics_have_kpis(tmp_path):
    metrics, _ = _run(tmp_path)
    assert "certified_novel_per_kilo_token" in metrics
    assert "certified_novel_per_critic_hour" in metrics
    assert metrics["total_conjectures"] == 8


def test_determinism(tmp_path):
    m1, o1 = _run(tmp_path / "a")
    m2, o2 = _run(tmp_path / "b")
    assert (o1 / "ledger.jsonl").read_text() == (o2 / "ledger.jsonl").read_text()


def test_conditioning_modes_differ():
    cfg = LoopConfig(rounds=1, k=4, seed=1, mode="genealogy")
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        loop = CRMLoop(
            proposer=StubProposer(), critic=MockCritic(),
            significance=SignificanceCritic(), ledger=Ledger(),
            accountant=Accountant(), config=cfg,
        )
        loop.run(d)
        ledger = loop.ledger

    treat = build_conditioning_context(ledger, "nt", 4, mode="genealogy")
    ctrl = build_conditioning_context(ledger, "nt", 4, mode="control")
    # Treatment carries WHY (reasons); control does not.
    assert treat != ctrl
    assert "hard-to-vary" in treat
    assert "hard-to-vary" not in ctrl
