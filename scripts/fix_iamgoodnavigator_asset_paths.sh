#!/usr/bin/env bash
# scripts/fix_iamgoodnavigator_asset_paths.sh
# Search for missing VLNVerse USD scene files and link/copy them into place.
# Never claims final evidence if only metadata is present.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

IANG_ROOT="${REPO_ROOT}/external/IAmGoodNavigator"
STATUS_FILE="${REPO_ROOT}/datasets/vlnverse/asset_path_fix_status.json"

echo "========================================"
echo "  IAmGoodNavigator Asset Path Fix"
echo "========================================"

if [[ ! -d "${IANG_ROOT}" ]]; then
  echo "[FAIL] ${IANG_ROOT} not found."
  exit 2
fi

# Get list of expected scene IDs from episode JSON
SCENE_IDS=()
while IFS= read -r scene; do
  SCENE_IDS+=("${scene}")
done < <(python3 -c "
import json
from pathlib import Path
iang = Path('${IANG_ROOT}')
ids = set()
for f in ['fine_grained_demo.json', 'coarse_grained_demo.json']:
    fp = iang / f
    if fp.exists():
        d = json.loads(fp.read_text())
        eps = d if isinstance(d, list) else d.get('episodes', [])
        for ep in eps:
            s = ep.get('scan') or ep.get('scene_id','').split('/')[-1]
            if s:
                ids.add(s)
for s in sorted(ids):
    print(s)
" 2>/dev/null)

echo "  Expected scenes: ${#SCENE_IDS[@]}"
for s in "${SCENE_IDS[@]}"; do
  echo "    ${s}"
done
echo ""

FOUND_STATUS=()
MISSING_STATUS=()

for SCENE_ID in "${SCENE_IDS[@]}"; do
  TARGET="${IANG_ROOT}/${SCENE_ID}/${SCENE_ID}.usda"
  if [[ -f "${TARGET}" ]]; then
    echo "[OK]  ${SCENE_ID}: ${TARGET}"
    FOUND_STATUS+=("${SCENE_ID}")
    continue
  fi

  echo "[SEARCH] Looking for ${SCENE_ID}.usda ..."
  FOUND_PATH=""

  # Search common local paths
  while IFS= read -r -d '' candidate; do
    [[ -n "${candidate}" ]] && FOUND_PATH="${candidate}" && break
  done < <(find /home/favl /mnt /media /opt \
      -iname "${SCENE_ID}.usda" -print0 2>/dev/null || true)

  if [[ -n "${FOUND_PATH}" ]]; then
    echo "[FOUND] ${FOUND_PATH}"
    SRC_DIR="$(dirname "${FOUND_PATH}")"
    DEST_DIR="${IANG_ROOT}/${SCENE_ID}"
    mkdir -p "${DEST_DIR}"
    echo "  Copying ${SRC_DIR}/ → ${DEST_DIR}/"
    rsync -av "${SRC_DIR}/" "${DEST_DIR}/" 2>&1 | tail -3
    echo "[OK]  Copied to ${TARGET}"
    FOUND_STATUS+=("${SCENE_ID}")
  else
    echo "[MISSING] ${SCENE_ID}.usda not found in any search path."
    echo "  Expected: ${TARGET}"
    echo "  Fix: cd external/IAmGoodNavigator && bash download.sh"
    MISSING_STATUS+=("${SCENE_ID}")
  fi
  echo ""
done

python3 - <<PYEOF
import json
from datetime import datetime, timezone
from pathlib import Path

found  = "${FOUND_STATUS[*]+${FOUND_STATUS[*]}}"
missing = "${MISSING_STATUS[*]+${MISSING_STATUS[*]}}"

found_list  = [s for s in found.split()  if s] if found  else []
missing_list = [s for s in missing.split() if s] if missing else []

status = "all_scenes_present" if not missing_list else (
    "partial_scenes" if found_list else "missing_full_dataset"
)

report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "status": status,
    "scenes_found": found_list,
    "scenes_missing": missing_list,
    "final_evidence_valid": len(missing_list) == 0,
    "note": (
        "All required scene USD files present." if not missing_list else
        "Some scenes missing. Metadata only — not final scene evidence. "
        "Run: cd external/IAmGoodNavigator && bash download.sh"
    ),
}
Path("${STATUS_FILE}").write_text(json.dumps(report, indent=2))
print(f"\n  Status: {status}")
print(f"  Found:  {len(found_list)}  Missing: {len(missing_list)}")
print(f"  final_evidence_valid: {report['final_evidence_valid']}")
print(f"  Report: ${STATUS_FILE}")
PYEOF
