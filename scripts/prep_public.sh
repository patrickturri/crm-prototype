#!/usr/bin/env bash
# Phase 6 (§18 6.7) — IP mode: choose what the public repo tracks.
#
#   --mode results-only  (default)  Track README, docs/ (report, survivors,
#                                    replay, plots) and the loop/critic
#                                    INTERFACES, but keep the moat — the
#                                    hard-to-vary significance critic and the
#                                    reasoned genealogy — out of the public tree
#                                    by moving crm/significance.py and
#                                    crm/genealogy.py into a gitignored PRIVATE/
#                                    path (shared with reviewers separately).
#
#   --mode full                      Track everything (significance + genealogy
#                                    included). Use once IP protection is no
#                                    longer needed.
#
#   --dry-run                        NON-DESTRUCTIVE: print exactly what WOULD be
#                                    excluded/moved, without touching the working
#                                    tree (so the build keeps working).
#
# Examples:
#   scripts/prep_public.sh --mode results-only --dry-run
#   scripts/prep_public.sh --mode full
set -euo pipefail

MODE="results-only"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --mode) MODE="${2:-}"; shift 2 ;;
    --mode=*) MODE="${1#*=}"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ "$MODE" != "results-only" ] && [ "$MODE" != "full" ]; then
  echo "error: --mode must be 'results-only' or 'full' (got '$MODE')" >&2
  exit 2
fi

# Repo root = parent of this script's dir.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# The moat: the two load-bearing critic sources (§5.1 genealogy, §5.2 significance).
MOAT=("crm/significance.py" "crm/genealogy.py")
PRIVATE_DIR="PRIVATE"

echo "prep_public: mode=${MODE} dry_run=${DRY_RUN}"

if [ "$MODE" = "full" ]; then
  echo "  [full] Tracking EVERYTHING — significance.py and genealogy.py stay in crm/."
  if grep -qE '^/?PRIVATE/?$' .gitignore 2>/dev/null; then
    echo "  note: PRIVATE/ is gitignored; in full mode nothing is moved there."
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "  [dry-run] No changes made."
  fi
  exit 0
fi

# ---- results-only ----
echo "  [results-only] Public repo will TRACK: README.md, docs/ (REPORT, SURVIVORS,"
echo "                 replay/, assets/), and the loop/critic INTERFACES."
echo "  [results-only] The MOAT will be EXCLUDED from the public tree and moved to ${PRIVATE_DIR}/:"
for f in "${MOAT[@]}"; do
  base="$(basename "$f")"
  echo "    - ${f}  ->  ${PRIVATE_DIR}/${base}   (gitignored; share with reviewers separately)"
done
echo "  [results-only] Rationale: protects the hard-to-vary significance critic and the"
echo "                 reasoned genealogy during the competition while still giving a"
echo "                 public, rendered, interactive link."

if [ "$DRY_RUN" -eq 1 ]; then
  echo "  [dry-run] NON-DESTRUCTIVE: nothing moved, .gitignore untouched, working tree intact."
  echo "  [dry-run] Re-run without --dry-run to actually relocate the moat into ${PRIVATE_DIR}/."
  exit 0
fi

# Real (destructive) path: move the moat into a gitignored PRIVATE/ dir and
# ensure .gitignore excludes it.
mkdir -p "${PRIVATE_DIR}"
for f in "${MOAT[@]}"; do
  base="$(basename "$f")"
  if [ -f "$f" ]; then
    git mv "$f" "${PRIVATE_DIR}/${base}" 2>/dev/null || mv "$f" "${PRIVATE_DIR}/${base}"
    echo "  moved ${f} -> ${PRIVATE_DIR}/${base}"
  elif [ -f "${PRIVATE_DIR}/${base}" ]; then
    echo "  already in ${PRIVATE_DIR}/: ${base}"
  else
    echo "  warning: ${f} not found (already moved?)" >&2
  fi
done

if ! grep -qE '^/?PRIVATE/?$' .gitignore 2>/dev/null; then
  printf '\n# Phase 6 IP mode (results-only): the moat lives here, never committed.\nPRIVATE/\n' >> .gitignore
  echo "  added PRIVATE/ to .gitignore"
fi

echo "  done. The public tree no longer contains significance.py / genealogy.py."
echo "  NOTE: crm/ imports them — keep ${PRIVATE_DIR}/ on PYTHONPATH (or symlink) to run locally."
