#!/usr/bin/env bash
# Lean 4 / mathlib setup (§6.3) — the headline real critic's toolchain.
#
# What this does, in order:
#   1. install `elan` (the Lean toolchain manager) if absent;
#   2. create a Lake project at .lean/crm_lean pinned to a RECENT STABLE mathlib,
#      with `lean-toolchain` set to MATCH that mathlib release;
#   3. `lake exe cache get` to download the PREBUILT mathlib oleans — the trick
#      that turns hours of source compilation into a ~10-20 min download
#      (we NEVER compile mathlib from source, §6.3);
#   4. `lake build` to confirm the project + cached oleans are usable.
#
# NON-FATAL (§6.3, §15): this phase must NOT block the whole build. If any step
# fails or the wall-clock budget (~30 min) is exceeded, we log the reason
# clearly, leave the code-exec critic as the floor, and exit 0 so downstream
# `make demo`/`make ablation` still run. The LeanCritic itself detects an
# unavailable toolchain and returns labelled ILLFORMED results rather than
# crashing — so a non-green Lean outcome is acceptable and reported honestly.
#
# Usage:  bash scripts/setup_lean.sh
# Env:    CRM_LEAN_BUDGET_S   overall budget in seconds (default 1800 = 30 min)
#         MATHLIB_REV         override the pinned mathlib git ref

set -uo pipefail   # NOT -e: we handle failures ourselves and stay non-fatal.

# --- locate repo root and the project dir ---------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_DIR="${REPO_ROOT}/.lean/crm_lean"
LOG_DIR="${REPO_ROOT}/.lean"
mkdir -p "${LOG_DIR}"
SETUP_LOG="${LOG_DIR}/setup.log"

BUDGET_S="${CRM_LEAN_BUDGET_S:-1800}"
# A recent stable mathlib release tag and its MATCHING Lean toolchain (§6.3:
# lean-toolchain must match mathlib's). mathlib release tags vN.M.K ship with
# the leanprover/lean4:vN.M.K toolchain, so we pin both in lockstep up front so
# `lake update` has a toolchain to run under (elan auto-installs it on use).
MATHLIB_REV="${MATHLIB_REV:-v4.15.0}"
LEAN_TOOLCHAIN="${LEAN_TOOLCHAIN:-leanprover/lean4:${MATHLIB_REV}}"

START_TS="$(date +%s)"

log()  { echo "[setup_lean] $*" | tee -a "${SETUP_LOG}" >&2; }
note_fallback() {
  log "FALLBACK: $*"
  log "Lean track unavailable -> the sandboxed code-exec critic (configs/code.yaml)"
  log "remains the real-critic floor. Run: make demo CONFIG=configs/code.yaml"
  log "The LeanCritic will return labelled ILLFORMED results until setup succeeds."
  exit 0   # NON-FATAL: never block the build (§6.3).
}

budget_left() {
  local now; now="$(date +%s)"
  local used=$(( now - START_TS ))
  echo $(( BUDGET_S - used ))
}
check_budget() {
  local left; left="$(budget_left)"
  if [ "${left}" -le 0 ]; then
    note_fallback "exceeded the ~$((BUDGET_S/60))-min setup budget at step: $1"
  fi
}

log "starting Lean/mathlib setup (budget ${BUDGET_S}s, mathlib ${MATHLIB_REV})"
log "repo=${REPO_ROOT} project=${PROJECT_DIR}"

# --- 1. install elan ------------------------------------------------------
export PATH="${HOME}/.elan/bin:${PATH}"
if ! command -v elan >/dev/null 2>&1; then
  log "elan not found; installing via elan-init ..."
  if command -v curl >/dev/null 2>&1; then
    FETCH=(curl -fsSL "https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh")
  elif command -v wget >/dev/null 2>&1; then
    FETCH=(wget -qO- "https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh")
  else
    note_fallback "neither curl nor wget available to fetch elan-init"
  fi
  if ! timeout "$(budget_left)" bash -c '"$@"' _ "${FETCH[@]}" 2>>"${SETUP_LOG}" | \
       timeout "$(budget_left)" sh -s -- -y --default-toolchain none >>"${SETUP_LOG}" 2>&1; then
    note_fallback "elan installation failed (see ${SETUP_LOG}); likely no network access"
  fi
  export PATH="${HOME}/.elan/bin:${PATH}"
fi
if ! command -v elan >/dev/null 2>&1; then
  note_fallback "elan still not on PATH after install attempt"
fi
log "elan: $(command -v elan) ($(elan --version 2>/dev/null || echo '?'))"
check_budget "after elan"

# --- 2. create the Lake project pinned to recent stable mathlib -----------
if [ ! -f "${PROJECT_DIR}/lakefile.toml" ] && [ ! -f "${PROJECT_DIR}/lakefile.lean" ]; then
  mkdir -p "$(dirname "${PROJECT_DIR}")"
  log "creating Lake project at ${PROJECT_DIR}"
  mkdir -p "${PROJECT_DIR}"

  # lakefile.toml requiring mathlib at a pinned, recent-stable revision.
  cat > "${PROJECT_DIR}/lakefile.toml" <<EOF
name = "crm_lean"
defaultTargets = ["CrmLean"]

[[require]]
name = "mathlib"
scope = "leanprover-community"
rev = "${MATHLIB_REV}"

[[lean_lib]]
name = "CrmLean"
EOF

  mkdir -p "${PROJECT_DIR}/CrmLean"
  cat > "${PROJECT_DIR}/CrmLean.lean" <<'EOF'
-- CRM Lean project root. Imports Mathlib so `lake env lean` on a candidate file
-- (import Mathlib; theorem crm_candidate : ... := ...) resolves against the
-- prebuilt oleans pulled by `lake exe cache get`.
import Mathlib
EOF
fi

# Pin lean-toolchain to match the mathlib release BEFORE `lake update` so Lake
# has a toolchain to run under (elan auto-installs it on first use in this dir).
if [ ! -f "${PROJECT_DIR}/lean-toolchain" ]; then
  echo "${LEAN_TOOLCHAIN}" > "${PROJECT_DIR}/lean-toolchain"
  log "pinned lean-toolchain = ${LEAN_TOOLCHAIN} (matches mathlib ${MATHLIB_REV})"
fi

cd "${PROJECT_DIR}" || note_fallback "could not cd into ${PROJECT_DIR}"

# Trigger toolchain install (elan fetches ${LEAN_TOOLCHAIN} on first use here).
log "ensuring Lean toolchain ${LEAN_TOOLCHAIN} is installed ..."
if ! timeout "$(budget_left)" elan toolchain install "${LEAN_TOOLCHAIN}" >>"${SETUP_LOG}" 2>&1; then
  log "elan toolchain install returned non-zero (may already be present); continuing"
fi
check_budget "after toolchain install"

# `lake update mathlib` resolves the dependency and (crucially) writes the
# matching `lean-toolchain` so elan downloads the exact Lean used by this
# mathlib release — keeping toolchain and mathlib in lockstep (§6.3).
log "resolving mathlib dependency (lake update) ..."
if ! timeout "$(budget_left)" lake update mathlib >>"${SETUP_LOG}" 2>&1; then
  note_fallback "lake update failed (see ${SETUP_LOG}); likely no network access"
fi
check_budget "after lake update"

if [ -f "${PROJECT_DIR}/lean-toolchain" ]; then
  log "pinned lean-toolchain: $(cat "${PROJECT_DIR}/lean-toolchain")"
fi

# --- 3. download PREBUILT mathlib oleans (NOT a source compile) -----------
log "downloading prebuilt mathlib oleans (lake exe cache get) ..."
if ! timeout "$(budget_left)" lake exe cache get >>"${SETUP_LOG}" 2>&1; then
  note_fallback "lake exe cache get failed (see ${SETUP_LOG}); prebuilt oleans unavailable"
fi
check_budget "after cache get"

# --- 4. confirm with lake build (uses the cached oleans) ------------------
log "confirming with lake build ..."
if ! timeout "$(budget_left)" lake build >>"${SETUP_LOG}" 2>&1; then
  note_fallback "lake build failed (see ${SETUP_LOG})"
fi

# --- smoke-compile a known-true theorem to prove the kernel path works -----
SMOKE_FILE="${PROJECT_DIR}/_crm_smoke.lean"
cat > "${SMOKE_FILE}" <<'EOF'
import Mathlib
theorem crm_candidate : ∀ (n : ℕ), Nat.gcd n (n + 1) = 1 := by simp
EOF
if timeout "$(budget_left)" lake env lean "${SMOKE_FILE}" >>"${SETUP_LOG}" 2>&1; then
  log "SUCCESS: Lean toolchain + mathlib ready; smoke theorem compiled."
  log "Run the headline demo: make demo CONFIG=configs/lean_nt.yaml"
  rm -f "${SMOKE_FILE}"
  exit 0
else
  rm -f "${SMOKE_FILE}"
  note_fallback "smoke theorem failed to compile (see ${SETUP_LOG})"
fi
