#!/usr/bin/env bash
# Lean 4 / mathlib setup (§6.3) — implemented in Phase 4.
#
# Will: install elan; create a Lake project pinned to a recent stable mathlib;
# `lake exe cache get` to download prebuilt oleans (NOT compile from source);
# `lake build` to confirm. If setup exceeds ~30 min or fails, fall back to the
# code critic, log the reason, and continue.
set -euo pipefail
echo "scripts/setup_lean.sh: implemented in Phase 4 (Lean track). No-op for now." >&2
exit 0
