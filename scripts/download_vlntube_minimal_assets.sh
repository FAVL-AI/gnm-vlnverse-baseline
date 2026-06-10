#!/usr/bin/env bash
# scripts/download_vlntube_minimal_assets.sh
# ─────────────────────────────────────────────────────────────────────────────
# Download minimal VLNTube/VLNVerse assets from HuggingFace.
# Does NOT download hundreds of GB by default — only small sample files.
#
# Datasets:
#   Eyz/SceneMeta      — room metadata JSON (~small)
#   Eyz/SceneSummary   — scene summaries (~small)
#   Eyz/VLNVerse_data  — episode data (~moderate)
#   Eyz/VLNVerse_scene — USD scenes (~large, lists files first, downloads 1)
#
# Output: datasets/vlntube/ subdirectories
#
# Usage:
#   bash scripts/download_vlntube_minimal_assets.sh
#   bash scripts/download_vlntube_minimal_assets.sh --no-scene  # skip USD
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_ROOT="${REPO_ROOT}/datasets/vlntube"
REPORT_FILE="${DATA_ROOT}/asset_download_report.json"
DOWNLOAD_SCENE=true
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-scene) DOWNLOAD_SCENE=false; shift ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

echo "========================================"
echo "  FleetSafe — VLNTube Minimal Asset Download"
echo "========================================"
echo "  Output: ${DATA_ROOT}"
echo ""

mkdir -p "${DATA_ROOT}/room_meta" \
         "${DATA_ROOT}/scene_graph" \
         "${DATA_ROOT}/prebuilt_data" \
         "${DATA_ROOT}/outputs"

# ── Check huggingface_hub ──────────────────────────────────────────────────
echo "--- Checking huggingface_hub ---"
if ! python3 -c "import huggingface_hub" 2>/dev/null; then
  echo "[WARN] huggingface_hub not installed."
  echo "  Install: pip install huggingface-hub"
  echo ""
  echo "  Manual download commands:"
  echo "    huggingface-cli download Eyz/SceneMeta --repo-type dataset --local-dir ${DATA_ROOT}/room_meta"
  echo "    huggingface-cli download Eyz/SceneSummary --repo-type dataset --local-dir ${DATA_ROOT}/scene_graph"
  echo "    huggingface-cli download Eyz/VLNVerse_data --repo-type dataset --local-dir ${DATA_ROOT}/prebuilt_data"
  echo ""

  # Write blocking report
  python3 - <<PYEOF
import json
from datetime import datetime, timezone
from pathlib import Path
report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "status": "blocked",
    "reason": "huggingface_hub not installed",
    "fix": "pip install huggingface-hub",
    "downloaded": {},
    "real_data_present": False,
}
Path("${REPORT_FILE}").write_text(json.dumps(report, indent=2))
print(f"Report written: ${REPORT_FILE}")
PYEOF
  exit 2
fi

echo "[OK]  huggingface_hub available."
echo ""

# ── Download datasets ──────────────────────────────────────────────────────
python3 - <<PYEOF
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from huggingface_hub import snapshot_download, list_repo_files, hf_hub_download
    from huggingface_hub.utils import RepositoryNotFoundError, EntryNotFoundError
except ImportError as e:
    print(f"[FAIL] {e}")
    sys.exit(2)

data_root   = Path("${DATA_ROOT}")
report_file = Path("${REPORT_FILE}")
downloaded  = {}
errors      = {}

def try_download(repo_id, local_dir, max_files=None):
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    try:
        if max_files:
            files = list(list_repo_files(repo_id, repo_type="dataset"))[:max_files]
            print(f"  {repo_id}: downloading {len(files)} files...")
            for f in files:
                try:
                    hf_hub_download(
                        repo_id=repo_id, filename=f, repo_type="dataset",
                        local_dir=str(local_dir),
                    )
                except Exception as e2:
                    print(f"    [skip] {f}: {e2}")
        else:
            print(f"  {repo_id}: snapshot download (sample)...")
            snapshot_download(
                repo_id=repo_id, repo_type="dataset",
                local_dir=str(local_dir),
                ignore_patterns=["*.usd", "*.usda", "*.usdc", "*.bin"],
            )
        files_after = list(local_dir.rglob("*"))
        real_files  = [f for f in files_after if f.is_file() and f.stat().st_size > 0]
        return {"status": "ok", "files": len(real_files)}
    except RepositoryNotFoundError:
        return {"status": "repo_not_found", "files": 0}
    except Exception as e:
        return {"status": f"error: {e}", "files": 0}

# Eyz/SceneMeta — room metadata (small)
print("--- Eyz/SceneMeta ---")
r = try_download("Eyz/SceneMeta", data_root / "room_meta")
downloaded["SceneMeta"] = r
print(f"  → {r}")

# Eyz/SceneSummary — scene summaries
print("--- Eyz/SceneSummary ---")
r = try_download("Eyz/SceneSummary", data_root / "scene_graph")
downloaded["SceneSummary"] = r
print(f"  → {r}")

# Eyz/VLNVerse_data — episode data (may be large)
print("--- Eyz/VLNVerse_data (first 20 files) ---")
r = try_download("Eyz/VLNVerse_data", data_root / "prebuilt_data", max_files=20)
downloaded["VLNVerse_data"] = r
print(f"  → {r}")

# Eyz/VLNVerse_scene — USD scenes (potentially very large)
if "${DOWNLOAD_SCENE}" == "true":
    print("--- Eyz/VLNVerse_scene (listing files first) ---")
    try:
        scene_files = list(list_repo_files("Eyz/VLNVerse_scene", repo_type="dataset"))
        print(f"  Available files: {len(scene_files)}")
        for f in scene_files[:15]:
            print(f"    {f}")
        # Only download a small non-USD file if available
        small_files = [f for f in scene_files
                       if not any(f.endswith(ext) for ext in [".usd",".usda",".usdc"])
                       and f.endswith((".json",".txt",".yaml",".md"))]
        if small_files:
            print(f"  Downloading {len(small_files[:3])} small metadata files...")
            r = try_download("Eyz/VLNVerse_scene", data_root / "envs", max_files=3)
        else:
            print("  No small files found — skipping automatic download of USD scenes.")
            print(f"  To download manually: huggingface-cli download Eyz/VLNVerse_scene --repo-type dataset --local-dir {data_root}/envs")
            r = {"status": "listing_only", "files": 0, "all_files": scene_files[:20]}
        downloaded["VLNVerse_scene"] = r
        print(f"  → {r}")
    except RepositoryNotFoundError:
        downloaded["VLNVerse_scene"] = {"status": "repo_not_found", "files": 0}
        print("  [WARN] Eyz/VLNVerse_scene not found on HuggingFace")
    except Exception as e:
        downloaded["VLNVerse_scene"] = {"status": f"error: {e}", "files": 0}
        print(f"  [WARN] {e}")
else:
    print("--- Eyz/VLNVerse_scene: SKIPPED (--no-scene) ---")
    downloaded["VLNVerse_scene"] = {"status": "skipped", "files": 0}

# Assess whether real data was downloaded
total_files = sum(v.get("files", 0) for v in downloaded.values())
real_data = total_files > 0

report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "status": "ok" if real_data else "no_data",
    "real_data_present": real_data,
    "total_files_downloaded": total_files,
    "downloaded": downloaded,
    "data_root": str(data_root),
}
report_file.write_text(json.dumps(report, indent=2))
print(f"\n[OK]  Report written: {report_file}")
print(f"  total_files={total_files}  real_data={real_data}")

if not real_data:
    print("\n[WARN] No real data downloaded.")
    print("  This may be due to HuggingFace repo access restrictions or network issues.")
    print("  Check: https://huggingface.co/datasets/Eyz/SceneMeta")
PYEOF

RC=$?

echo ""
echo "--- Updating VLNTube index ---"
python3 -m fleetsafe_vln.datagen.vlntube_indexer \
  --root "${DATA_ROOT}" 2>&1 | tail -5

echo ""
echo "Done."
if [[ -f "${REPORT_FILE}" ]]; then
  python3 -c "
import json
r=json.loads(open('${REPORT_FILE}').read())
print(f'  real_data_present={r[\"real_data_present\"]}  total_files={r[\"total_files_downloaded\"]}')
"
fi
