PYTHON ?= python3

.PHONY: install smoke test demo ablation survivors report clean

install:
	$(PYTHON) -m pip install -e .

# Phase 0 checkpoint: full loop on the MockCritic in <60s; writes
# results/<run>/ledger.jsonl and metrics.json.
smoke:
	$(PYTHON) -m crm.run --config configs/smoke.yaml

test:
	$(PYTHON) -m pytest

# Real-critic run. Default: the sandboxed code-exec critic (Phase 2). Override
# with `make demo CONFIG=configs/lean_nt.yaml` once Lean (Phase 4) is in.
CONFIG ?= configs/code.yaml
demo:
	$(PYTHON) -m crm.run --config $(CONFIG)

# Phase 3 checkpoint (§9): both ablations on the REAL sandboxed CodeExecCritic
# (never mocked, §3/§15) over >=3 seeds, then render both mean±std plots into
# results/plots/ and write REPORT.md with a 1-paragraph reading of each.
# Per-seed CSVs land in results/. Override seeds with `make ablation SEEDS=3`
# and the config with `make ablation ABLATION_CONFIG=...`.
SEEDS ?= 5
ABLATION_CONFIG ?= configs/ablation.yaml
ablation:
	$(PYTHON) -m experiments.ablation_genealogy --config $(ABLATION_CONFIG) --seeds $(SEEDS)
	$(PYTHON) -m experiments.ablation_significance --config $(ABLATION_CONFIG) --seeds $(SEEDS)
	$(PYTHON) -m experiments.make_report

# Phase 5 (§12): regenerate the rendered report (plots + REPORT.md) and the
# curated SURVIVORS.md from the latest REAL non-mock run. Never hand-authored.
report:
	$(PYTHON) -m experiments.make_report

survivors:
	$(PYTHON) -m experiments.make_survivors

clean:
	rm -rf results/*/ results/metrics.json
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
