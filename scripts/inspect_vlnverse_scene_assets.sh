#!/usr/bin/env bash
# scripts/inspect_vlnverse_scene_assets.sh
# Reports scene asset availability for all IAmGoodNavigator episodes.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

IANG_ROOT="${REPO_ROOT}/external/IAmGoodNavigator"
REPORT="${REPO_ROOT}/datasets/vlnverse/iamgoodnavigator_scene_asset_report.json"

echo "========================================"
echo "  VLNVerse Scene Asset Inspection"
echo "========================================"

if [[ ! -d "${IANG_ROOT}" ]]; then
  echo "[FAIL] ${IANG_ROOT} not found. Run: bash scripts/setup_iamgoodnavigator.sh"
  exit 2
fi

REPO_SIZE=$(du -sh "${IANG_ROOT}" 2>/dev/null | awk '{print $1}')
USD_COUNT=$(find "${IANG_ROOT}" -iname "*.usd" -o -iname "*.usda" -o -iname "*.usdc" 2>/dev/null | wc -l)
echo "  Repo size:  ${REPO_SIZE}"
echo "  USD files:  ${USD_COUNT}"

# Find all .usda files
echo ""
echo "--- USD scenes found ---"
find "${IANG_ROOT}" -iname "*.usda" 2>/dev/null | while read -r f; do
  echo "  ${f}"
done

python3 - <<PYEOF
import json, os
from pathlib import Path

iang = Path("${IANG_ROOT}")
report_path = Path("${REPORT}")
report_path.parent.mkdir(parents=True, exist_ok=True)

# Parse episode JSON files
def parse_episodes(json_path):
    if not json_path.exists():
        return []
    d = json.loads(json_path.read_text())
    return d if isinstance(d, list) else d.get("episodes", d.get("data", []))

fine_eps   = parse_episodes(iang / "fine_grained_demo.json")
coarse_eps = parse_episodes(iang / "coarse_grained_demo.json")

all_eps = [(ep, "fine") for ep in fine_eps] + [(ep, "coarse") for ep in coarse_eps]

scenes_checked = {}
missing = []
found = []

for ep, task in all_eps:
    scan = ep.get("scan") or ep.get("scene_id","").split("/")[-1] or ""
    if not scan or scan in scenes_checked:
        continue
    usda = iang / scan / f"{scan}.usda"
    exists = usda.exists()
    scenes_checked[scan] = {
        "scan": scan,
        "expected_usda": str(usda),
        "exists": exists,
    }
    if exists:
        found.append(scan)
        size = usda.stat().st_size
        scenes_checked[scan]["size_bytes"] = size
    else:
        missing.append(scan)

# Also check imported episode_meta.json files
import_dir = Path("${REPO_ROOT}/datasets/vlnverse/imported/iamgoodnavigator")
imported = []
if import_dir.exists():
    for meta_file in sorted(import_dir.rglob("episode_meta.json")):
        try:
            m = json.loads(meta_file.read_text())
            imported.append({
                "key": meta_file.parent.name,
                "status": m.get("status"),
                "scene_exists": m.get("scene_exists"),
                "evidence_valid": m.get("evidence_valid"),
                "exit_code": m.get("exit_code"),
            })
        except Exception:
            pass

report = {
    "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    "repo_size": "${REPO_SIZE}",
    "usd_file_count": sum(1 for _ in iang.rglob("*.usd*")),
    "scenes_found": len(found),
    "scenes_missing": len(missing),
    "scenes": scenes_checked,
    "found_scenes": found,
    "missing_scenes": missing,
    "imported_episodes": imported,
}

report_path.write_text(json.dumps(report, indent=2))
print(f"\n  Scenes found:   {len(found)}")
print(f"  Scenes missing: {len(missing)}")
if missing:
    print("\n  Missing USD files:")
    for s in missing:
        usda = iang / s / f"{s}.usda"
        print(f"    {usda}")
    print("\n  Download instructions:")
    print("    cd external/IAmGoodNavigator && bash download.sh")
    print("    # Or manually place USD files at external/IAmGoodNavigator/<scene_id>/<scene_id>.usda")
else:
    print("  All required USD scene files are present.")
print(f"\n  Report: ${REPORT}")
PYEOF
