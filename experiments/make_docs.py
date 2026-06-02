"""Phase 6 (§18) — refresh the tracked, SANITIZED docs/ artifacts from the best
REAL run.

`results/` stays gitignored (§4); this script copies *curated, sanitized* real
artifacts into a tracked `docs/`:

  - docs/assets/ablation_genealogy.png      (real plot, copied from results/plots/)
  - docs/assets/ablation_significance.png   (real plot, copied from results/plots/)
  - docs/REPORT.md                          (rendered REPORT.md, image paths rewritten
                                             to the relative docs/assets/ copies)
  - docs/SURVIVORS.md                       (curated copy of the real SURVIVORS.md)
  - docs/replay/run.jsonl                   (sanitized copy of the best run's REAL
                                             ledger.jsonl, enriched with proof/test
                                             artifacts, secrets/paths stripped)

NEVER fabricates survivors or metrics (§3). The best run is the one whose id is
recorded in the root metrics.json `_provenance.run`; its ledger.jsonl is the
single source of truth for the replay viewer.

Sanitization (§18 6.3 / 6.6): every emitted JSONL row is scanned for and
scrubbed of anything resembling an API key, an absolute host path, or an env
assignment. The build fails loudly if anything matches after scrubbing.

ROOT <-> docs/ RELATIONSHIP (drift-control, review finding "root/docs drift").
This script IS the generator for the duplicated Markdown: `docs/REPORT.md` and
`docs/SURVIVORS.md` are produced HERE from the repo-root `REPORT.md` /
`SURVIVORS.md` (the source of truth), with `docs/assets/` link prefixes
rewritten for GitHub-Pages relative resolution (see `copy_report` /
`copy_survivors`). So the correct workflow for any numbers/prose edit is:
edit the ROOT copy, then run `python -m experiments.make_docs` to regenerate the
docs/ copy — do NOT hand-edit `docs/REPORT.md` / `docs/SURVIVORS.md`.

NOT generated here (hand-maintained, edit directly): `README.md` (root only),
`docs/FINDINGS.md`, and `docs/findings/*.md`. These have no generator yet, so a
single-sided edit to them can drift; keep that in mind until a generator covers
them.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
DOCS = ROOT / "docs"

# Patterns that must NEVER appear in a tracked/shared file.
SECRET_PATTERNS = [
    re.compile(r"sk-ant-"),
    re.compile(r"ANTHROPIC_API_KEY"),
    re.compile(r"/Users/"),
    re.compile(r"/home/"),
    re.compile(r"/root/"),
]


def _best_run() -> Path:
    """The best completed run: the one named in metrics.json _provenance.run."""
    mj = ROOT / "metrics.json"
    if mj.exists():
        try:
            prov = json.loads(mj.read_text()).get("_provenance", {})
            run = prov.get("run")
            if run and (RESULTS / run / "ledger.jsonl").exists():
                return RESULTS / run
        except Exception:
            pass
    # Fallback: most recent real (non-mock) run with a ledger.
    cands = sorted(
        (p for p in RESULTS.glob("*/ledger.jsonl") if not p.parent.name.startswith("smoke")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not cands:
        raise SystemExit("no real run with a ledger.jsonl found under results/")
    return cands[0].parent


def _scrub(s: str) -> str:
    """Best-effort scrub of host paths / secrets from a free-text string."""
    s = re.sub(r"/(?:Users|home|root)/[^\s\"']*", "<path>", s)
    s = re.sub(r"sk-ant-[A-Za-z0-9_\-]+", "<redacted-key>", s)
    return s


def _assert_clean(text: str, where: str) -> None:
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            raise SystemExit(
                f"SECRET-SCAN FAILED: pattern {pat.pattern!r} found in {where}. "
                "Refusing to write a tracked file with a leaked secret/path."
            )


def build_run_jsonl(run_dir: Path) -> int:
    """Write docs/replay/run.jsonl: the REAL ledger, enriched + sanitized."""
    ledger = run_dir / "ledger.jsonl"
    artifacts_path = run_dir / "artifacts.json"
    artifacts = {}
    if artifacts_path.exists():
        artifacts = json.loads(artifacts_path.read_text())

    out_rows: list[str] = []
    for line in ledger.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        # Scrub free-text fields.
        for key in ("statement", "nl_gloss", "proof_attempt"):
            if isinstance(row.get(key), str):
                row[key] = _scrub(row[key])
        if isinstance(row.get("crit"), dict) and isinstance(row["crit"].get("detail"), str):
            row["crit"]["detail"] = _scrub(row["crit"]["detail"])
        # Attach the verifiable proof/test artifact (the WHY-it's-real evidence)
        # so the offline viewer can show it without reading results/.
        art = artifacts.get(row.get("id"))
        if art:
            row["artifact"] = {
                "reference_impl": _scrub(str(art.get("reference_impl", ""))),
                "tests": _scrub(str(art.get("tests", ""))),
                "property": _scrub(str(art.get("property", ""))),
                "lean_statement": _scrub(str(art.get("lean_statement", ""))),
            }
        emitted = json.dumps(row, ensure_ascii=False)
        _assert_clean(emitted, "docs/replay/run.jsonl")
        out_rows.append(emitted)

    if not out_rows:
        raise SystemExit(f"refusing to write an empty run.jsonl from {ledger}")

    (DOCS / "replay").mkdir(parents=True, exist_ok=True)
    (DOCS / "replay" / "run.jsonl").write_text("\n".join(out_rows) + "\n", encoding="utf-8")
    return len(out_rows)


def copy_plots() -> None:
    src = RESULTS / "plots"
    dst = DOCS / "assets"
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("ablation_genealogy.png", "ablation_significance.png"):
        s = src / name
        if not s.exists():
            raise SystemExit(f"missing real plot {s} — run `make ablation` first.")
        shutil.copyfile(s, dst / name)


def copy_report() -> None:
    """Copy REPORT.md into docs/, rewriting plot paths to the relative copies."""
    src = ROOT / "REPORT.md"
    if not src.exists():
        raise SystemExit("missing REPORT.md — run `make report` first.")
    text = src.read_text(encoding="utf-8")
    # REPORT.md references docs/assets/<x>.png (resolves on GitHub from repo root);
    # the docs/ copy sits beside assets/, so it uses the relative assets/<x>.png.
    text = text.replace("docs/assets/", "assets/")
    _assert_clean(text, "docs/REPORT.md")
    (DOCS / "REPORT.md").write_text(text, encoding="utf-8")


def copy_survivors() -> None:
    src = ROOT / "SURVIVORS.md"
    if not src.exists():
        raise SystemExit("missing SURVIVORS.md — run `make survivors` first.")
    text = src.read_text(encoding="utf-8")
    _assert_clean(text, "docs/SURVIVORS.md")
    (DOCS / "SURVIVORS.md").write_text(text, encoding="utf-8")


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)
    run_dir = _best_run()
    n = build_run_jsonl(run_dir)
    copy_plots()
    copy_report()
    copy_survivors()
    print(f"[make_docs] best run: {run_dir.name}")
    print(f"[make_docs] wrote docs/replay/run.jsonl ({n} real rows)")
    print("[make_docs] wrote docs/assets/{ablation_genealogy,ablation_significance}.png")
    print("[make_docs] wrote docs/REPORT.md, docs/SURVIVORS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
