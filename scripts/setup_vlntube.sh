#!/usr/bin/env bash
# scripts/setup_vlntube.sh
# ─────────────────────────────────────────────────────────────────────────────
# Clone VLNTube into external/VLNTube and print module/folder status.
# Does NOT modify VLNTube source code.
#
# Usage:
#   bash scripts/setup_vlntube.sh
#   bash scripts/setup_vlntube.sh --skip-clone     # inspect only
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VLNTUBE_TARGET="${REPO_ROOT}/external/VLNTube"
VLNTUBE_LEGACY="${REPO_ROOT}/third_party/VLNTube"
VLNTUBE_URL="https://github.com/william13077/VLNTube"
SKIP_CLONE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-clone) SKIP_CLONE=true; shift ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

echo "========================================"
echo "  FleetSafe — VLNTube Setup"
echo "========================================"
echo "  Target: ${VLNTUBE_TARGET}"
echo ""

# ── Clone if needed ────────────────────────────────────────────────────────
if [[ -d "${VLNTUBE_TARGET}" ]] && [[ -f "${VLNTUBE_TARGET}/README.md" ]]; then
  echo "[OK]  VLNTube already present at ${VLNTUBE_TARGET}"
elif [[ -d "${VLNTUBE_LEGACY}" ]] && [[ -f "${VLNTUBE_LEGACY}/README.md" ]]; then
  echo "[OK]  VLNTube found at legacy path ${VLNTUBE_LEGACY}"
  echo "  Symlinking to external/VLNTube..."
  mkdir -p "${REPO_ROOT}/external"
  ln -sfn "${VLNTUBE_LEGACY}" "${VLNTUBE_TARGET}" 2>/dev/null || \
    cp -r "${VLNTUBE_LEGACY}" "${VLNTUBE_TARGET}"
  echo "[OK]  Linked."
elif $SKIP_CLONE; then
  echo "[SKIP] --skip-clone: VLNTube not present."
else
  echo "  Cloning VLNTube from ${VLNTUBE_URL}..."
  mkdir -p "${REPO_ROOT}/external"
  if git clone "${VLNTUBE_URL}" "${VLNTUBE_TARGET}" 2>&1; then
    echo "[OK]  Cloned to ${VLNTUBE_TARGET}"
  else
    echo "[WARN] Clone failed — repo may be unavailable."
    echo "  VLNTube will operate in missing-dependency mode."
  fi
fi

echo ""

# ── Folder/module status ───────────────────────────────────────────────────
echo "--- Folder/module status ---"
VLNTUBE_ROOT="${VLNTUBE_TARGET}"
[[ ! -d "${VLNTUBE_TARGET}" ]] && VLNTUBE_ROOT="${VLNTUBE_LEGACY}"

for folder in scene_graph vistube instube datatube splits; do
  if [[ -d "${VLNTUBE_ROOT}/${folder}" ]]; then
    count=$(find "${VLNTUBE_ROOT}/${folder}" -type f 2>/dev/null | wc -l)
    printf "  ✓  %-15s  (%d files)\n" "${folder}" "${count}"
  else
    printf "  ✗  %-15s  (missing)\n" "${folder}"
  fi
done

echo ""

# ── Run indexer ────────────────────────────────────────────────────────────
echo "--- Running VLNTube indexer ---"
python3 -m fleetsafe_vln.datagen.vlntube_indexer \
  --repo "${VLNTUBE_TARGET}" \
  --root "${REPO_ROOT}/datasets/vlntube" 2>&1

echo ""
echo "--- HuggingFace VLN datasets (compatible with FleetSafe) ---"
python3 - <<PYEOF
import sys
sys.path.insert(0, "${REPO_ROOT}")
try:
    from fleetsafe_vln.datagen.hf_dataset_registry import list_known_datasets
    for d in list_known_datasets(fleetsafe_compatible_only=True)[:4]:
        print(f"  {d['id']:15s}  ~{d['size_gb']:5.0f} GB  hf:{d['hf_repo']}")
    print("  Run: python -m fleetsafe_vln.datagen.hf_dataset_registry for full list")
except Exception as e:
    print(f"  (registry unavailable: {e})")
PYEOF

echo ""
echo "Setup complete."
echo "  Next: python -m fleetsafe_vln.datagen.vlntube_indexer"
echo "  Then: open http://localhost:3000/dashboard/vln-hub"
