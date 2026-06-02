PYTHON ?= python3

.PHONY: install smoke test demo ablation survivors report clean docs record publish

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

# Rounds-scaling / compounding experiment (deep-run regime). Tests whether the
# genealogy arm keeps producing NEW certified-novel survivors over MANY rounds
# (compounding) or plateaus like the memoryless best-of-N baseline. Override
# ROUNDS/SEEDS. With the api_code base config (ablation.yaml) this calls the
# real LLM and FAILS LOUDLY if any arm silently degrades to the offline
# generator. For a free deterministic smoke add `ROUNDS=4 SEEDS=1` and pass the
# offline config / --allow-fallback (see experiments/rounds_scaling.py header).
ROUNDS ?= 25
ROUNDS_SEEDS ?= 3
ROUNDS_CONFIG ?= configs/ablation.yaml
rounds:
	$(PYTHON) -m experiments.rounds_scaling --config $(ROUNDS_CONFIG) \
		--rounds $(ROUNDS) --seeds $(ROUNDS_SEEDS)

# Robustness / model-sensitivity of the genealogy null. Re-runs a SLICE of the
# genealogy-vs-best_of_N comparison under different proposer settings
# (sonnet@0.7, sonnet@0.3, haiku@4-5) to ask whether the known nulls are
# model/temperature-specific or robust. Real LLM; FAILS LOUDLY on silent
# fallback. Override ROBUST_ROUNDS/ROBUST_SEEDS.
ROBUST_ROUNDS ?= 6
ROBUST_SEEDS ?= 3
robust:
	$(PYTHON) -m experiments.robustness --rounds $(ROBUST_ROUNDS) \
		--seeds $(ROBUST_SEEDS) --results-dir results/findings/robustness

clean:
	rm -rf results/*/ results/metrics.json
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

# ---------------------------------------------------------------------------
# Phase 6 (§18) — Shareability. results/ STAYS gitignored; we copy CURATED,
# SANITIZED real artifacts into a tracked docs/. Never hand-author survivors.
# ---------------------------------------------------------------------------

# 6.1 — refresh tracked docs/ from the best REAL run (plots, REPORT, SURVIVORS,
# and the sanitized replay run.jsonl). Fails loudly on any leaked secret/path.
docs:
	$(PYTHON) -m experiments.make_docs

# 6.5 — recording helper. Records `make demo` under asciinema if installed,
# else prints a screen-recorder / Loom note. [latitude]
record:
	@if command -v asciinema >/dev/null 2>&1; then \
		echo "[record] asciinema found — recording 'make demo' to docs/demo.cast"; \
		asciinema rec docs/demo.cast --overwrite -c "$(MAKE) demo"; \
		echo "[record] wrote docs/demo.cast — embed it in the README with an asciinema player or upload to asciinema.org."; \
	else \
		echo "[record] asciinema not installed."; \
		echo "[record] Install it (brew install asciinema / pipx install asciinema) to capture docs/demo.cast,"; \
		echo "[record] or screen-record 'make demo' with QuickTime / Loom and link the video in the README."; \
	fi

# 6.6 — publish: regenerate plots, refresh docs/ assets, secret-scan TRACKED
# files (FAIL LOUDLY on any key/.env/sk-ant), then PRINT (do not execute) the
# manual push + Pages-toggle steps.
publish:
	@echo "[publish] (1/3) regenerating plots + REPORT.md from the real ablation CSVs…"
	@$(PYTHON) -m experiments.make_report
	@echo "[publish] (2/3) refreshing curated, sanitized docs/ assets from the best real run…"
	@$(PYTHON) -m experiments.make_docs
	@echo "[publish] (3/3) secret-scan over TRACKED files (keys / .env / sk-ant / host paths)…"
	@$(PYTHON) scripts/secret_scan.py
	@echo ""
	@echo "================ MANUAL STEPS (not executed) ================"
	@echo "  # 1. Add your GitHub remote and push (results/ + .env stay gitignored):"
	@echo "  git remote add origin git@github.com:<user>/<repo>.git"
	@echo "  git push -u origin main"
	@echo ""
	@echo "  # 2. Enable GitHub Pages: repo Settings -> Pages ->"
	@echo "  #    'Deploy from a branch' -> Branch: main, Folder: /docs -> Save."
	@echo "  # The replay viewer will then be live at:"
	@echo "  #    https://<user>.github.io/<repo>/replay/"
	@echo "============================================================"
