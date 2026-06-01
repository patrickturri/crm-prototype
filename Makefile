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

# Real-critic run (code-exec / Lean) -- filled in by Phases 2 and 4.
demo:
	@echo "make demo: implemented in Phase 2 (code-exec) / Phase 4 (Lean)." >&2
	@exit 1

# Both ablations + plots -- filled in by Phase 3.
ablation:
	@echo "make ablation: implemented in Phase 3." >&2
	@exit 1

clean:
	rm -rf results/*/ results/metrics.json
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
