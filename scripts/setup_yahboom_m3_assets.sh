#!/usr/bin/env bash
# scripts/setup_yahboom_m3_assets.sh
# ─────────────────────────────────────────────────────────────────────────────
# Locate Yahboom ROSMASTER M3 Pro URDF/mesh assets.
# Searches: public GitHub clone, local Fleet-Safe-VLA-OS repo, and local
# asset directories.  If found, syncs into assets/robots/yahboom_m3_pro/.
#
# Usage:
#   bash scripts/setup_yahboom_m3_assets.sh
#   bash scripts/setup_yahboom_m3_assets.sh --skip-clone
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
YAHBOOM_CLONE="${REPO_ROOT}/external/yahboom/ROSMASTER-M3"
YAHBOOM_URL="https://github.com/YahboomTechnology/ROSMASTER-M3"
ASSET_DIR="${REPO_ROOT}/assets/robots/yahboom_m3_pro"
ASSET_REPORT="${ASSET_DIR}/asset_report.json"
SOURCE_DEST="${ASSET_DIR}/source_m3pro"
SKIP_CLONE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-clone) SKIP_CLONE=true; shift ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

echo "========================================"
echo "  FleetSafe — Yahboom M3 Pro Assets"
echo "========================================"
echo "  Asset dir: ${ASSET_DIR}"
echo ""

mkdir -p "${ASSET_DIR}"

# ── Clone public GitHub repo (optional — often has no URDF) ─────────────────
if [[ -d "${YAHBOOM_CLONE}" ]] && [[ -f "${YAHBOOM_CLONE}/README.md" ]]; then
  echo "[OK]  Public ROSMASTER-M3 repo already cloned."
elif $SKIP_CLONE; then
  echo "[SKIP] --skip-clone: skipping git clone."
else
  echo "  Cloning ${YAHBOOM_URL}..."
  mkdir -p "${REPO_ROOT}/external/yahboom"
  git clone "${YAHBOOM_URL}" "${YAHBOOM_CLONE}" 2>&1 || \
    echo "[WARN] Clone failed — continuing with local path search."
fi

echo ""

# ── Search roots ─────────────────────────────────────────────────────────────
echo "--- Searching for URDF/mesh/USD assets ---"

SEARCH_ROOTS=(
  "${YAHBOOM_CLONE}"
  "/home/favl/robotics/Fleet-Safe-VLA-OS/fleet_safe_vla/robots/yahboom/m3pro"
  "/home/favl/robotics/Fleet-Safe-VLA-OS/fleet_safe_vla/robots/yahboom"
  "/home/favl/robotics/Fleet-Safe-VLA-OS/ros2_ws/src"
  "${REPO_ROOT}/external/yahboom/local_assets"
  "${ASSET_DIR}"
)

URDF_FILES=()
XACRO_FILES=()
MESH_STL=()
MESH_DAE=()
MESH_OBJ=()
USD_FILES=()

for search_root in "${SEARCH_ROOTS[@]}"; do
  if [[ -d "${search_root}" ]]; then
    while IFS= read -r -d '' f; do URDF_FILES+=("$f"); done \
      < <(find "${search_root}" -iname "*.urdf" -print0 2>/dev/null)
    while IFS= read -r -d '' f; do XACRO_FILES+=("$f"); done \
      < <(find "${search_root}" -iname "*.xacro" -print0 2>/dev/null)
    while IFS= read -r -d '' f; do MESH_STL+=("$f"); done \
      < <(find "${search_root}" -iname "*.stl" -print0 2>/dev/null)
    while IFS= read -r -d '' f; do MESH_DAE+=("$f"); done \
      < <(find "${search_root}" -iname "*.dae" -print0 2>/dev/null)
    while IFS= read -r -d '' f; do MESH_OBJ+=("$f"); done \
      < <(find "${search_root}" -iname "*.obj" -print0 2>/dev/null)
    while IFS= read -r -d '' f; do USD_FILES+=("$f"); done \
      < <(find "${search_root}" \( -iname "*.usd" -o -iname "*.usda" -o -iname "*.usdc" \) -print0 2>/dev/null)
  fi
done

# Remove source_m3pro from URDF list to avoid self-referencing
CLEAN_URDF=()
for f in "${URDF_FILES[@]}"; do
  [[ "${f}" == "${SOURCE_DEST}/"* ]] || CLEAN_URDF+=("$f")
done
URDF_FILES=("${CLEAN_URDF[@]+"${CLEAN_URDF[@]}"}")

printf "  URDF files:   %d\n" "${#URDF_FILES[@]}"
printf "  Xacro files:  %d\n" "${#XACRO_FILES[@]}"
printf "  STL meshes:   %d\n" "${#MESH_STL[@]}"
printf "  DAE meshes:   %d\n" "${#MESH_DAE[@]}"
printf "  OBJ meshes:   %d\n" "${#MESH_OBJ[@]}"
printf "  USD files:    %d\n" "${#USD_FILES[@]}"

for f in "${URDF_FILES[@]:0:3}" "${XACRO_FILES[@]:0:2}" "${USD_FILES[@]:0:2}"; do
  echo "    → ${f}"
done

echo ""

# ── Determine best URDF ───────────────────────────────────────────────────────
HAS_URDF="false"
HAS_MESH="false"
HAS_USD="false"
BEST_URDF=""
SOURCE_LABEL="none"

# Prefer named m3pro URDF
for f in "${URDF_FILES[@]}"; do
  fname="$(basename "${f}")"
  if [[ "${fname,,}" == *"m3pro"* ]] || [[ "${fname,,}" == *"m3_pro"* ]]; then
    BEST_URDF="${f}"
    HAS_URDF="true"
    SOURCE_LABEL="local Fleet-Safe-VLA-OS assets"
    break
  fi
done

# Fall back to any URDF with "yahboom" in path
if [[ -z "${BEST_URDF}" ]]; then
  for f in "${URDF_FILES[@]}"; do
    if [[ "${f,,}" == *"yahboom"* ]]; then
      BEST_URDF="${f}"
      HAS_URDF="true"
      SOURCE_LABEL="local yahboom URDF"
      break
    fi
  done
fi

# Fall back to first URDF found
if [[ -z "${BEST_URDF}" ]] && [[ ${#URDF_FILES[@]} -gt 0 ]]; then
  BEST_URDF="${URDF_FILES[0]}"
  HAS_URDF="true"
  SOURCE_LABEL="first URDF found"
fi

# Xacro fallback
if [[ -z "${BEST_URDF}" ]] && [[ ${#XACRO_FILES[@]} -gt 0 ]]; then
  BEST_URDF="${XACRO_FILES[0]}"
  HAS_URDF="true"
  SOURCE_LABEL="xacro"
fi

[[ $(( ${#MESH_STL[@]} + ${#MESH_DAE[@]} + ${#MESH_OBJ[@]} )) -gt 0 ]] && HAS_MESH="true"
[[ ${#USD_FILES[@]} -gt 0 ]] && HAS_USD="true"

# ── Copy assets if URDF found ────────────────────────────────────────────────
CANONICAL_URDF=""
if [[ "${HAS_URDF}" == "true" ]] && [[ -n "${BEST_URDF}" ]]; then
  SOURCE_DIR="$(dirname "${BEST_URDF}")"

  # Sync the whole m3pro asset folder
  echo "--- Syncing assets to ${SOURCE_DEST}/ ---"
  mkdir -p "${SOURCE_DEST}"
  rsync -av --exclude='*.pyc' --exclude='__pycache__' \
    "${SOURCE_DIR}/" "${SOURCE_DEST}/" 2>&1 | tail -5
  echo "[OK]  Asset folder synced."

  # Copy canonical URDF
  CANONICAL_URDF="${ASSET_DIR}/yahboom_m3pro.urdf"
  cp "${BEST_URDF}" "${CANONICAL_URDF}"
  echo "[OK]  Canonical URDF: ${CANONICAL_URDF}"
fi

# Safe first-element helpers
FIRST_URDF="${URDF_FILES[0]+${URDF_FILES[0]}}"
FIRST_XACRO="${XACRO_FILES[0]+${XACRO_FILES[0]}}"
FIRST_USD="${USD_FILES[0]+${USD_FILES[0]}}"

# USD note: yahboom_x3.usd is a debug asset, not M3 Pro evidence
X3_USD=""
for f in "${USD_FILES[@]}"; do
  [[ "${f,,}" == *"x3"* ]] && X3_USD="${f}" && break
done

# ── Write asset report ────────────────────────────────────────────────────────
python3 - <<PYEOF
import json
from datetime import datetime, timezone
from pathlib import Path

has_urdf = "${HAS_URDF}" == "true"
canonical = "${CANONICAL_URDF}"
source_label = "${SOURCE_LABEL}"
x3_usd = "${X3_USD}"

report = {
    "robot": "Yahboom ROSMASTER M3 Pro",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "clone_root": "${YAHBOOM_CLONE}",
    "clone_exists": Path("${YAHBOOM_CLONE}").exists(),
    "assets": {
        "urdf_count": ${#URDF_FILES[@]},
        "xacro_count": ${#XACRO_FILES[@]},
        "stl_count": ${#MESH_STL[@]},
        "dae_count": ${#MESH_DAE[@]},
        "obj_count": ${#MESH_OBJ[@]},
        "usd_count": ${#USD_FILES[@]},
    },
    "has_urdf": has_urdf,
    "has_mesh": "${HAS_MESH}" == "true",
    "has_usd":  "${HAS_USD}" == "true",
    "best_urdf": "${BEST_URDF}" if "${BEST_URDF}" else None,
    "canonical_urdf": canonical if canonical else None,
    "source": source_label if has_urdf else "urdf_not_found",
    "source_m3pro_dir": "${SOURCE_DEST}" if has_urdf else None,
    "generated_usd": None,
    "status": "urdf_found" if has_urdf else "urdf_missing",
    "urdf_files":  ["${FIRST_URDF}"]  if "${FIRST_URDF}"  else [],
    "xacro_files": ["${FIRST_XACRO}"] if "${FIRST_XACRO}" else [],
    "usd_files":   ["${FIRST_USD}"]   if "${FIRST_USD}"   else [],
    "debug_assets": {
        "yahboom_x3_usd": x3_usd if x3_usd else None,
        "note": "yahboom_x3.usd is a related/debug asset — not M3 Pro final evidence",
    },
}

out = Path("${ASSET_REPORT}")
out.write_text(json.dumps(report, indent=2))
print(f"[OK]  Asset report: {out}")
print(f"      has_urdf={has_urdf}  source={source_label}")
if canonical:
    print(f"      canonical_urdf={canonical}")
PYEOF

echo ""

# ── Outcome ───────────────────────────────────────────────────────────────────
if [[ "${HAS_URDF}" == "true" ]]; then
  echo "[OK]  Yahboom M3 Pro URDF found."
  echo "  Best URDF:       ${BEST_URDF}"
  [[ -n "${CANONICAL_URDF}" ]] && echo "  Canonical copy:  ${CANONICAL_URDF}"
  echo ""
  echo "  To import into Isaac Sim:"
  echo "    bash scripts/import_yahboom_m3_urdf_to_isaac.sh \"${CANONICAL_URDF:-${BEST_URDF}}\""
else
  echo "╔══════════════════════════════════════════════════════════════════════╗"
  echo "║  [BLOCKED] Yahboom M3 URDF/mesh NOT found in any search path.      ║"
  echo "║                                                                      ║"
  echo "║  Searched:                                                           ║"
  echo "║    external/yahboom/ROSMASTER-M3  (public GitHub)                   ║"
  echo "║    Fleet-Safe-VLA-OS/fleet_safe_vla/robots/yahboom/m3pro            ║"
  echo "║    Fleet-Safe-VLA-OS/ros2_ws/src                                    ║"
  echo "║                                                                      ║"
  echo "║  Options:                                                            ║"
  echo "║  1. Pull from real robot:                                            ║"
  echo "║       bash scripts/pull_yahboom_assets_from_robot.sh yahboom@<IP>   ║"
  echo "║  2. Download from Yahboom vendor resources / documentation page.    ║"
  echo "║  3. Use the ROS 2 package yahboom_ros2 if available on the robot.   ║"
  echo "╚══════════════════════════════════════════════════════════════════════╝"
  echo ""
  echo "  Will NOT import a generic TurtleBot/JetBot/Carter as a substitute."
fi

echo ""
echo "Done."
