PYTHON ?= python3

.PHONY: install smoke test demo ablation clean

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

# Both ablations + plots -- filled in by Phase 3.
ablation:
	@echo "make ablation: implemented in Phase 3." >&2
	@exit 1

clean:
	rm -rf results/*/ results/metrics.json
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
