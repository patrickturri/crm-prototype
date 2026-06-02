"""Tests for the rounds-scaling / compounding experiment.

Covers (a) the pure per-round helper, (b) the embedder process-cache (Task 1),
(c) the breadth-now-fires wiring in the shared harness (Task 3), and (d) an
end-to-end DETERMINISTIC offline smoke of rounds_scaling.main, including the
silent-fallback guard. No network, no LLM-as-judge: the offline proposer +
hash embedder make the whole thing free and reproducible.
"""

from __future__ import annotations

import json

import pytest

import crm.embedding as embedding
from experiments.rounds_scaling import (
    FallbackError,
    cumulative_to_new,
    main,
)


# --------------------------------------------------------------------------
# (a) pure helper: cumulative -> per-round-new
# --------------------------------------------------------------------------
def test_cumulative_to_new_basic():
    assert cumulative_to_new([0, 1, 1, 3]) == [0, 1, 0, 2]


def test_cumulative_to_new_monotone_plateau():
    # A plateau (cumulative flat) => all-zero tail in `new`, the saturation sig.
    assert cumulative_to_new([2, 4, 4, 4]) == [2, 2, 0, 0]


def test_cumulative_to_new_empty_and_singleton():
    assert cumulative_to_new([]) == []
    assert cumulative_to_new([5]) == [5]


def test_cumulative_to_new_sum_equals_final():
    cum = [0, 2, 3, 7, 9]
    new = cumulative_to_new(cum)
    assert sum(new) == cum[-1]
    # cum is reconstructable by prefix-summing new.
    acc, rebuilt = 0, []
    for x in new:
        acc += x
        rebuilt.append(acc)
    assert rebuilt == cum


# --------------------------------------------------------------------------
# (b) Task 1: embedder is memoised per backend key (no reload per build)
# --------------------------------------------------------------------------
def test_embedder_cache_returns_same_instance():
    embedding._EMBEDDER_CACHE.clear()
    a = embedding.get_embedder("hash")
    b = embedding.get_embedder("hash")
    assert a is b  # same process-lifetime instance, not a fresh build
    assert "hash" in embedding._EMBEDDER_CACHE


def test_embedder_cache_distinct_keys():
    embedding._EMBEDDER_CACHE.clear()
    h = embedding.get_embedder(None)  # forced hash
    h2 = embedding.get_embedder("hash-fallback")
    assert h is h2  # all hash aliases collapse to one cached instance


def test_embedder_cache_counts_one_construction(monkeypatch):
    """Repeated get_embedder calls build the backend at most once."""
    embedding._EMBEDDER_CACHE.clear()
    calls = {"n": 0}
    real_init = embedding.HashEmbedder.__init__

    def counting_init(self, *a, **k):
        calls["n"] += 1
        real_init(self, *a, **k)

    monkeypatch.setattr(embedding.HashEmbedder, "__init__", counting_init)
    for _ in range(5):
        embedding.get_embedder("hash")
    assert calls["n"] == 1


# --------------------------------------------------------------------------
# (c) Task 3: breadth wiring — the shared harness now passes enablement specs
# --------------------------------------------------------------------------
def test_harness_passes_breadth_specs():
    from experiments._harness import _build_components

    cfg = {
        "proposer": {"kind": "offline_code"},
        "critic": "code_exec",
        "corpus_path": "data/code_corpus.jsonl",
        "breadth_targets_path": "data/code_breadth_targets.jsonl",
        "offline_embedder": True,
        "proof_budget_s": 5.0,
    }
    _, _, sig, _ = _build_components(cfg)
    # The enablement specs (rows carrying `solve`) must be loaded, otherwise the
    # code-exec breadth hook silently never fires.
    assert sig.breadth_target_specs, "breadth enablement specs not wired into harness"
    assert all("solve" in s for s in sig.breadth_target_specs)


# --------------------------------------------------------------------------
# (d) end-to-end DETERMINISTIC offline smoke of main()
# --------------------------------------------------------------------------
def _offline_cfg(tmp_path):
    """Write a tiny offline (no-API) config so main() is free + deterministic."""
    import yaml

    cfg = {
        "name": "rounds_smoke",
        "topic": "elementary number theory (Python-verifiable)",
        "rounds": 3,
        "k": 4,
        "seed": 0,
        "critic": "code_exec",
        "proof_budget_s": 5.0,
        "n_adversarial": 8,
        "proposer": {"kind": "offline_code"},  # deterministic, ignores context
        "weights": {"novelty": 0.3, "breadth": 0.3, "hardness": 0.4},
        "tau": 0.25,
        "delta": 0.35,
        "perturbations": 6,
        "embedder": "hash",
        "offline_embedder": True,
        "corpus_path": "data/code_corpus.jsonl",
        "breadth_targets_path": "data/code_breadth_targets.jsonl",
    }
    p = tmp_path / "offline_rounds.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def test_main_offline_smoke_writes_per_round_series(tmp_path):
    cfg_path = _offline_cfg(tmp_path)
    out = tmp_path / "out"
    # offline_code is NOT an API kind, so the fallback guard is inert; the run
    # must complete and write the per-round series for all three arms.
    rc = main([
        "--config", str(cfg_path), "--rounds", "3", "--seeds", "2",
        "--results-dir", str(out),
    ])
    assert rc == 0

    summary = json.loads((out / "summary.json").read_text())
    assert summary["rounds"] == 3
    assert set(summary["by_arm"]) == {"genealogy", "control", "best_of_N"}
    assert summary["api"] is False

    # CSV carries per-round rows: 3 arms x 2 seeds x 3 rounds = 18 data rows.
    import csv as _csv

    with (out / "rounds_scaling.csv").open() as f:
        data = list(_csv.DictReader(f))
    assert len(data) == 18
    # cum_certified is monotone non-decreasing within each (arm, seed).
    by_run: dict = {}
    for row in data:
        by_run.setdefault((row["arm"], row["seed"]), []).append(
            (int(row["round"]), int(row["cum_certified"]), int(row["new_certified"]))
        )
    for series in by_run.values():
        series.sort()
        cums = [c for _, c, _ in series]
        assert cums == sorted(cums)
        # new_certified must reconstruct cum via prefix sum.
        news = [n for _, _, n in series]
        acc, rebuilt = 0, []
        for x in news:
            acc += x
            rebuilt.append(acc)
        assert rebuilt == cums


def test_fallback_guard_fires_on_api_config_offline(tmp_path):
    """An API config that degrades offline (no usable key here) must FAIL LOUD."""
    import yaml

    cfg = {
        "name": "rounds_api_smoke",
        "topic": "elementary number theory",
        "rounds": 2,
        "k": 3,
        "seed": 0,
        "critic": "code_exec",
        "proof_budget_s": 5.0,
        "n_adversarial": 6,
        # api_code: real LLM kind. With provider forced to a non-anthropic value
        # it degrades to the offline generator => fallback guard MUST fire.
        "proposer": {"kind": "api_code"},
        "weights": {"novelty": 0.3, "breadth": 0.3, "hardness": 0.4},
        "tau": 0.25,
        "delta": 0.35,
        "perturbations": 4,
        "embedder": "hash",
        "offline_embedder": True,
        "corpus_path": "data/code_corpus.jsonl",
        "breadth_targets_path": "data/code_breadth_targets.jsonl",
    }
    p = tmp_path / "api_rounds.yaml"
    p.write_text(yaml.safe_dump(cfg))
    out = tmp_path / "out_api"

    # Force the API proposer to degrade deterministically (no real key path).
    import os

    prev = os.environ.get("CRM_PROPOSER_PROVIDER")
    os.environ["CRM_PROPOSER_PROVIDER"] = "none"
    try:
        with pytest.raises(FallbackError):
            main([
                "--config", str(p), "--rounds", "2", "--seeds", "1",
                "--results-dir", str(out),
            ])
        # With --allow-fallback the SAME run completes (smoke escape hatch).
        rc = main([
            "--config", str(p), "--rounds", "2", "--seeds", "1",
            "--results-dir", str(out), "--allow-fallback",
        ])
        assert rc == 0
        summary = json.loads((out / "summary.json").read_text())
        assert summary["any_fallback"] is True
    finally:
        if prev is None:
            os.environ.pop("CRM_PROPOSER_PROVIDER", None)
        else:
            os.environ["CRM_PROPOSER_PROVIDER"] = prev
