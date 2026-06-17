#!/usr/bin/env bash
# Clone the official Yahboom ROSMASTER M3 Pro repository as a local reference.
#
# The clone is placed at:
#   external/yahboom/ROSMASTER-M3PRO
#
# This directory is gitignored and is never committed to our research repo.
# It is a read-only local reference for URDF, launch, sensor, and topic
# inspection. Do not modify files inside it.
#
# Usage:
#   bash scripts/setup/clone_yahboom_rosmaster_m3pro.sh [--update] [--dry-run]
#
# Flags:
#   --update    If the repo is already cloned, pull the latest changes.
#   --dry-run   Print what would run; do not execute. Exits 0.

set -euo pipefail

UPSTREAM_URL="https://github.com/YahboomTechnology/ROSMASTER-M3PRO"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
DEST="$ROOT/external/yahboom/ROSMASTER-M3PRO"

DO_UPDATE=false
DRY_RUN=false

for arg in "$@"; do
  case "$arg" in
    --update)   DO_UPDATE=true ;;
    --dry-run)  DRY_RUN=true ;;
  esac
done

echo "============================================================"
echo " Yahboom ROSMASTER M3 Pro Upstream Clone Script"
echo "============================================================"
echo "Upstream URL : $UPSTREAM_URL"
echo "Destination  : $DEST"
echo "Update mode  : $DO_UPDATE"
echo "Dry-run      : $DRY_RUN"
echo "============================================================"
echo ""
echo "The cloned repo is a local read-only reference."
echo "It is gitignored and will not be committed to our research repo."
echo "Do not modify files inside external/."
echo ""

if $DRY_RUN; then
  echo "[DRY-RUN] Would run:"
  if [[ -d "$DEST/.git" ]]; then
    echo "  git -C $DEST pull --ff-only"
  else
    echo "  mkdir -p $(dirname "$DEST")"
    echo "  git clone $UPSTREAM_URL $DEST"
  fi
  echo ""
  echo "[DRY-RUN] After cloning, run:"
  echo "  python3 scripts/gnm/inspect_yahboom_upstream.py"
  echo ""
  echo "[OK] Dry-run complete."
  exit 0
fi

if ! command -v git &>/dev/null; then
  echo "[FAIL] git is not installed. Cannot clone upstream repo."
  exit 1
fi

mkdir -p "$(dirname "$DEST")"

if [[ -d "$DEST/.git" ]]; then
  echo "[INFO] Upstream repo already cloned at: $DEST"
  if $DO_UPDATE; then
    echo "[INFO] Pulling latest changes..."
    git -C "$DEST" pull --ff-only
    echo "[OK] Update complete."
  else
    echo "[INFO] To pull latest changes, run with --update."
    echo "[OK] Using existing clone."
  fi
else
  echo "[INFO] Cloning upstream repo..."
  echo "[INFO] This may take a few minutes depending on connection speed."
  echo ""
  git clone "$UPSTREAM_URL" "$DEST"
  echo ""
  echo "[OK] Clone complete: $DEST"
fi

echo ""
echo "------------------------------------------------------------"
echo " Next step: inspect the upstream content"
echo "------------------------------------------------------------"
echo ""
echo "  python3 scripts/gnm/inspect_yahboom_upstream.py"
echo ""
echo "This will search for URDF, Xacro, launch files, and topic"
echo "references in the cloned repo and write an inventory report."
echo ""
echo "Reference docs:"
echo "  docs/yahboom_upstream_integration.md"
echo "  docs/yahboom_to_fleetsafe_topic_mapping.md"
