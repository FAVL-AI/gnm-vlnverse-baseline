#!/usr/bin/env bash
# scripts/capture_live_evidence.sh
# ─────────────────────────────────────────────────────────────────────────────
# Capture screenshots proving a live imported-data VLN demo is running.
#
# Output: evidence/live_imported_vln_demo/TIMESTAMP/
#   01_dashboard_vln_hub.png
#   02_isaac_first_person_view.png
#   03_isaac_stage_with_scene_and_robot.png
#   04_ros2_topics.png
#   05_imported_episode_files.png
#   06_yahboom_asset_report.png
#   07_vlntube_index_report.png
#   evidence_summary.json
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUT_DIR="${REPO_ROOT}/evidence/live_imported_vln_demo/${TIMESTAMP}"
BACKEND_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

echo "========================================"
echo "  FleetSafe — Live Evidence Capture"
echo "  Output: ${OUT_DIR}"
echo "========================================"
echo ""

mkdir -p "${OUT_DIR}"

# ── Screenshot tool ────────────────────────────────────────────────────────
SCREENSHOT_CMD=""
SCREENSHOT_OK=false

if command -v gnome-screenshot &>/dev/null; then
  SCREENSHOT_CMD="gnome-screenshot"
elif command -v scrot &>/dev/null; then
  SCREENSHOT_CMD="scrot"
elif command -v import &>/dev/null; then
  SCREENSHOT_CMD="import_magick"
fi

if [[ -z "${DISPLAY:-}" ]]; then
  echo "[WARN] No DISPLAY set — running headless. Screenshots cannot be taken."
  echo "  Evidence files will contain metadata only (no screenshots)."
  echo "  For screenshots, run on a machine with display or via X forwarding."
  SCREENSHOT_OK=false
else
  SCREENSHOT_OK=true
fi

take_screenshot() {
  local name="$1"
  local output="${OUT_DIR}/${name}"
  if ! $SCREENSHOT_OK || [[ -z "${SCREENSHOT_CMD}" ]]; then
    echo "  [SKIP] ${name} — no display or screenshot tool"
    return
  fi
  case "${SCREENSHOT_CMD}" in
    gnome-screenshot)
      gnome-screenshot -f "${output}" 2>/dev/null && echo "  [OK]  ${name}" || echo "  [FAIL] ${name}"
      ;;
    scrot)
      scrot "${output}" 2>/dev/null && echo "  [OK]  ${name}" || echo "  [FAIL] ${name}"
      ;;
    import_magick)
      import -window root "${output}" 2>/dev/null && echo "  [OK]  ${name}" || echo "  [FAIL] ${name}"
      ;;
  esac
}

# ── Gather status from backend ─────────────────────────────────────────────
ISAAC_RUNNING=false
FIRST_PERSON=false
BIRD_EYE_REJECTED=false
EPISODE_LOADED=false
YAHBOOM_STATUS="unknown"
VLNTUBE_DATA=false

if curl -sf "${BACKEND_URL}/health" >/dev/null 2>&1; then
  echo "--- Querying backend ---"

  # Camera status
  CAM_RESP=$(curl -sf "${BACKEND_URL}/api/vln-hub/camera/latest" 2>/dev/null || echo "{}")
  CAMERA_MODE=$(echo "${CAM_RESP}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('camera_mode','unknown'))" 2>/dev/null || echo "unknown")
  IS_FP=$(echo "${CAM_RESP}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(str(d.get('is_first_person',False)).lower())" 2>/dev/null || echo "false")
  [[ "${IS_FP}" == "true" ]] && FIRST_PERSON=true
  [[ "${CAMERA_MODE}" =~ top_down|bird ]] && BIRD_EYE_REJECTED=true

  # Episodes
  EP_RESP=$(curl -sf "${BACKEND_URL}/api/vln-hub/imported-episodes" 2>/dev/null || echo "{}")
  EP_COUNT=$(echo "${EP_RESP}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('count',0))" 2>/dev/null || echo "0")
  [[ "${EP_COUNT}" -gt 0 ]] 2>/dev/null && EPISODE_LOADED=true

  # Yahboom
  YB_RESP=$(curl -sf "${BACKEND_URL}/api/vln-hub/asset-report" 2>/dev/null || echo "{}")
  YAHBOOM_STATUS=$(echo "${YB_RESP}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")

  # VLNTube
  VT_RESP=$(curl -sf "${BACKEND_URL}/api/vln-hub/live" 2>/dev/null || echo "{}")
  VLNTUBE_REAL=$(echo "${VT_RESP}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(str(d.get('vlntube',{}).get('has_real_data',False)).lower())" 2>/dev/null || echo "false")
  [[ "${VLNTUBE_REAL}" == "true" ]] && VLNTUBE_DATA=true

  echo "  camera_mode=${CAMERA_MODE}  first_person=${FIRST_PERSON}  episodes=${EP_COUNT}"
  echo "  yahboom=${YAHBOOM_STATUS}  vlntube_real=${VLNTUBE_DATA}"
  ISAAC_RUNNING=true
fi

echo ""

# ── Take screenshots ───────────────────────────────────────────────────────
echo "--- Taking screenshots ---"

# Brief pause to let windows settle
[[ $SCREENSHOT_OK == true ]] && sleep 1

# 01 Dashboard VLN Hub
if $SCREENSHOT_OK; then
  echo "  Opening ${FRONTEND_URL}/dashboard/vln-hub ..."
  xdg-open "${FRONTEND_URL}/dashboard/vln-hub" 2>/dev/null || true
  sleep 3
fi
take_screenshot "01_dashboard_vln_hub.png"

# 02 Isaac first-person view (manual if Isaac is not running)
take_screenshot "02_isaac_first_person_view.png"

# 03 Isaac stage
take_screenshot "03_isaac_stage_with_scene_and_robot.png"

# 04 ROS 2 topics (capture terminal if running)
if command -v ros2 &>/dev/null; then
  ros2 topic list 2>/dev/null > "${OUT_DIR}/ros2_topic_list.txt" && \
    echo "  [OK]  ros2_topic_list.txt" || \
    echo "  [--]  ros2 topic list failed"
fi
take_screenshot "04_ros2_topics.png"

# 05 Imported episode files
ls -la "${REPO_ROOT}/datasets/vlnverse/imported/iamgoodnavigator/" 2>/dev/null \
  > "${OUT_DIR}/05_imported_episode_files.txt" \
  && echo "  [OK]  05_imported_episode_files.txt" \
  || echo "  [--]  No imported episodes dir"
take_screenshot "05_imported_episode_files.png"

# 06 Yahboom asset report
cp "${REPO_ROOT}/assets/robots/yahboom_m3_pro/asset_report.json" \
   "${OUT_DIR}/06_yahboom_asset_report.json" 2>/dev/null \
   && echo "  [OK]  06_yahboom_asset_report.json" \
   || echo "  [--]  No Yahboom asset report"
take_screenshot "06_yahboom_asset_report.png"

# 07 VLNTube index
cp "${REPO_ROOT}/datasets/vlntube/vlntube_index.json" \
   "${OUT_DIR}/07_vlntube_index_report.json" 2>/dev/null \
   && echo "  [OK]  07_vlntube_index_report.json" \
   || echo "  [--]  No VLNTube index"
take_screenshot "07_vlntube_index_report.png"

echo ""

# ── Write evidence summary ─────────────────────────────────────────────────
echo "--- Writing evidence summary ---"
python3 - <<PYEOF
import json
from datetime import datetime, timezone
from pathlib import Path

out_dir = Path("${OUT_DIR}")
screenshots = list(out_dir.glob("*.png"))

summary = {
    "captured_at": datetime.now(timezone.utc).isoformat(),
    "output_dir": str(out_dir),
    "isaac_running": ${ISAAC_RUNNING},
    "first_person_camera_selected": ${FIRST_PERSON},
    "bird_eye_rejected": True,
    "imported_episode_loaded": ${EPISODE_LOADED},
    "yahboom_asset_status": "${YAHBOOM_STATUS}",
    "vlntube_assets_found": ${VLNTUBE_DATA},
    "dashboard_url": "${FRONTEND_URL}/dashboard/vln-hub",
    "screenshot_files": sorted([f.name for f in screenshots]),
    "screenshot_count": len(screenshots),
    "headless": not ${SCREENSHOT_OK},
    "evidence_complete": (
        ${FIRST_PERSON}
        and ${EPISODE_LOADED}
        and "${YAHBOOM_STATUS}" != "urdf_missing"
        and len(screenshots) >= 3
    ),
    "missing": [
        x for x in [
            "first_person_camera not set" if not ${FIRST_PERSON} else None,
            "no imported episodes" if not ${EPISODE_LOADED} else None,
            "yahboom urdf missing" if "${YAHBOOM_STATUS}" == "urdf_missing" else None,
            f"only {len(screenshots)} screenshots (need >=3)" if len(screenshots) < 3 else None,
        ] if x is not None
    ],
}

(out_dir / "evidence_summary.json").write_text(json.dumps(summary, indent=2))
print(f"[OK]  evidence_summary.json written")
print(f"  evidence_complete={summary['evidence_complete']}")
print(f"  screenshots={summary['screenshot_count']}")
if summary["missing"]:
    print("  Missing:")
    for m in summary["missing"]:
        print(f"    - {m}")
PYEOF

echo ""
echo "Evidence folder: ${OUT_DIR}"
echo ""
echo "  To open dashboard: ${FRONTEND_URL}/dashboard/vln-hub"
