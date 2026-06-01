#!/usr/bin/env python3
"""Phase 6 (§18 6.6) — secret-scan over TRACKED files.

Fails LOUDLY (non-zero exit) if any tracked / about-to-be-shared file contains
an API key, an Anthropic key, an `.env` assignment, or a host path. This guards
the `make publish` path so we can never push a leaked secret.

Scans:
  - every git-tracked file (`git ls-files`), if this is a git repo, plus
  - the curated shared artifacts under docs/ and the top-level README/REPORT/
    SURVIVORS, whether or not they are committed yet.

Also asserts `.env` itself is NOT tracked.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Patterns that must never appear in a shared/tracked file.
PATTERNS = [
    re.compile(r"sk-ant-"),
    re.compile(r"ANTHROPIC_API_KEY\s*="),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),          # generic OpenAI-style key
    re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    re.compile(r"/home/[A-Za-z0-9._-]+/"),
]

# Files we must never even *read* into a shared context.
NEVER_TRACK = {".env"}

# This scanner and the build spec legitimately mention the variable name / the
# `sk-ant-` prefix as documentation; exclude them from the scan.
SELF_EXCLUDE = {
    "scripts/secret_scan.py",
    "experiments/make_docs.py",
    "BUILD_SPEC.md",
    "Makefile",
}

BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".cast", ".ico", ".woff", ".woff2"}


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
        files = [ROOT / line for line in out.splitlines() if line.strip()]
    except Exception:
        files = []
    # Always also scan the curated shared artifacts (may be staged/untracked).
    extra = [
        ROOT / "README.md",
        ROOT / "REPORT.md",
        ROOT / "SURVIVORS.md",
        *(ROOT / "docs").rglob("*"),
    ]
    seen = set()
    result = []
    for f in files + extra:
        if f.is_file() and f not in seen:
            seen.add(f)
            result.append(f)
    return result


def main() -> int:
    # 1. .env must not be tracked.
    try:
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.splitlines()
    except Exception:
        tracked = []
    for nt in NEVER_TRACK:
        if nt in tracked:
            print(f"[secret-scan] FAIL: {nt} is tracked by git — it must be gitignored.")
            return 1

    # 2. content scan.
    violations = []
    for f in tracked_files():
        rel = f.relative_to(ROOT).as_posix()
        if rel in SELF_EXCLUDE:
            continue
        if f.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in PATTERNS:
            for m in pat.finditer(text):
                line_no = text[: m.start()].count("\n") + 1
                violations.append(f"  {rel}:{line_no}  matched /{pat.pattern}/")

    if violations:
        print("[secret-scan] FAIL — leaked secret/path in tracked/shared files:")
        for v in violations:
            print(v)
        return 1

    print(f"[secret-scan] OK — scanned tracked + shared files, no keys/.env/host-paths leaked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
