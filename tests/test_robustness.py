"""Tests for the robustness / model-sensitivity sweep.

Covers (a) the pure Welch helper's degenerate-input contract, (b) the SETTINGS
table shape, and (c) an end-to-end DETERMINISTIC offline smoke of main() with
the fallback guard — both that it FIRES on an API-degrade and that
--allow-fallback lets the same run complete. No network, no LLM-as-judge.
"""

from __future__ import annotations

import json
import os

import pytest

from experiments.robustness import SETTINGS, _welch, main
from experiments.rounds_scaling import FallbackError


def test_welch_degenerate_returns_nan():
    # <2 samples per side, or zero variance both sides -> (nan, nan).
    t, p = _welch([1.0], [2.0])
    assert t != t and p != p  # NaN
    t, p = _welch([3.0, 3.0], [3.0, 3.0])
    assert t != t and p != p


def test_welch_real_difference_is_finite():
    t, p = _welch([5.0, 6.0, 7.0], [1.0, 2.0, 3.0])
    assert t == t and p == p  # finite
    assert 0.0 <= p <= 1.0
    assert t > 0  # first group larger


def test_settings_table_shape():
    labels = {s[2] for s in SETTINGS}
    assert {"sonnet_t07", "sonnet_t03", "haiku_t07"} <= labels
    for model, temp, label in SETTINGS:
        assert isinstance(model, str) and model
        assert 0.0 <= float(temp) <= 1.0
        assert isinstance(label, str) and label


def test_main_offline_fallback_guard(tmp_path):
    """API config degraded offline must FAIL LOUD; --allow-fallback completes."""
    out = tmp_path / "out"
    prev = os.environ.get("CRM_PROPOSER_PROVIDER")
    os.environ["CRM_PROPOSER_PROVIDER"] = "none"  # force offline degrade
    try:
        with pytest.raises(FallbackError):
            main([
                "--config", "configs/ablation.yaml",
                "--rounds", "1", "--seeds", "1", "--results-dir", str(out),
            ])
        # No summary on the failed (guarded) run.
        assert not (out / "summary.json").exists()

        # Escape hatch: same run completes and records the fallback honestly.
        rc = main([
            "--config", "configs/ablation.yaml",
            "--rounds", "1", "--seeds", "1", "--results-dir", str(out),
            "--allow-fallback",
        ])
        assert rc == 0
        summary = json.loads((out / "summary.json").read_text())
        assert summary["any_fallback"] is True
        # Every setting present; two arms each.
        assert len(summary["settings"]) == len(SETTINGS)
        assert summary["arms"] == ["genealogy", "best_of_N"]
    finally:
        if prev is None:
            os.environ.pop("CRM_PROPOSER_PROVIDER", None)
        else:
            os.environ["CRM_PROPOSER_PROVIDER"] = prev
