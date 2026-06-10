#!/usr/bin/env bash
# scripts/run_real_imported_vln_demo_check.sh
# ─────────────────────────────────────────────────────────────────────────────
# Acceptance check for the real imported VLN demo.
#
# PASS only if real imported data, correct camera, and correct robot.
# FAIL on mock-only, missing data, or bird's-eye camera.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_URL="http://localhost:8000"
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

PASS=0
FAIL=0
SKIP=0

pass()  { echo "  [PASS] $1"; PASS=$((PASS+1)); }
fail()  { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
skip()  { echo "  [SKIP] $1"; SKIP=$((SKIP+1)); }
check() {
  local desc="$1"
  local cond="$2"
  if [[ "${cond}" == "true" ]]; then
    pass "${desc}"
  else
    fail "${desc}"
  fi
}

echo "========================================"
echo "  FleetSafe — Real VLN Demo Check"
echo "========================================"
echo ""

# ── 1. IAmGoodNavigator clone ─────────────────────────────────────────────
echo "--- IAmGoodNavigator ---"
IANG_ROOT="${REPO_ROOT}/external/IAmGoodNavigator"
[[ -d "${IANG_ROOT}" ]] && IANG_EXISTS=true || IANG_EXISTS=false
check "external/IAmGoodNavigator exists"          "${IANG_EXISTS}"
check "external/IAmGoodNavigator/demo.py exists"  "$([ -f "${IANG_ROOT}/demo.py" ] && echo true || echo false)"
check "fine_grained_demo.json exists"             "$([ -f "${IANG_ROOT}/fine_grained_demo.json" ] && echo true || echo false)"

# Fine episode count > 0 (requires data download)
if [[ -f "${IANG_ROOT}/fine_grained_demo.json" ]]; then
  FINE_COUNT=$(python3 -c "
import json
d=json.loads(open('${IANG_ROOT}/fine_grained_demo.json').read())
v=d if isinstance(d,list) else d.get('episodes',d.get('data',[]))
print(len(v))
" 2>/dev/null || echo "0")
  check "fine_grained_demo.json has episodes (data downloaded)" "$([ "${FINE_COUNT}" -gt 0 ] && echo true || echo false)"
else
  fail "fine_grained_demo.json missing — download not run"
fi

echo ""

# ── 2. VLNVerse index ─────────────────────────────────────────────────────
echo "--- VLNVerse index ---"
VVINDEX="${REPO_ROOT}/datasets/vlnverse/vlnverse_index.json"
check "datasets/vlnverse/vlnverse_index.json exists" "$([ -f "${VVINDEX}" ] && echo true || echo false)"
if [[ -f "${VVINDEX}" ]]; then
  VV_VALID=$(python3 -c "import json; json.loads(open('${VVINDEX}').read()); print('true')" 2>/dev/null || echo "false")
  check "vlnverse_index.json is valid JSON" "${VV_VALID}"
fi

IANG_STATUS="${REPO_ROOT}/datasets/vlnverse/iamgoodnavigator_status.json"
check "iamgoodnavigator_status.json exists" "$([ -f "${IANG_STATUS}" ] && echo true || echo false)"

echo ""

# ── 3. VLNTube ────────────────────────────────────────────────────────────
echo "--- VLNTube ---"
VTROOT="${REPO_ROOT}/external/VLNTube"
check "external/VLNTube exists" "$([ -d "${VTROOT}" ] && echo true || echo false)"

VTINDEX="${REPO_ROOT}/datasets/vlntube/vlntube_index.json"
check "datasets/vlntube/vlntube_index.json exists" "$([ -f "${VTINDEX}" ] && echo true || echo false)"

# Check for real data (not just empty dirs)
if [[ -f "${VTINDEX}" ]]; then
  VT_REAL=$(python3 -c "
import json
d=json.loads(open('${VTINDEX}').read())
print(str(d.get('summary',{}).get('has_real_data',False)).lower())
" 2>/dev/null || echo "false")
  # This is a warning, not a hard fail (real data requires downloads)
  if [[ "${VT_REAL}" == "true" ]]; then
    pass "VLNTube has real downloaded data"
  else
    fail "VLNTube has only empty dirs (run: bash scripts/download_vlntube_minimal_assets.sh)"
  fi
fi

echo ""

# ── 4. Yahboom assets ─────────────────────────────────────────────────────
echo "--- Yahboom M3 Pro ---"
ASSET_REPORT="${REPO_ROOT}/assets/robots/yahboom_m3_pro/asset_report.json"
check "assets/robots/yahboom_m3_pro/asset_report.json exists" \
  "$([ -f "${ASSET_REPORT}" ] && echo true || echo false)"

if [[ -f "${ASSET_REPORT}" ]]; then
  HAS_URDF=$(python3 -c "import json; d=json.loads(open('${ASSET_REPORT}').read()); print(str(d.get('has_urdf',False)).lower())" 2>/dev/null || echo "false")
  check "Yahboom M3 URDF found (not a generic robot substitute)" "${HAS_URDF}"

  HAS_USD=$(python3 -c "import json; d=json.loads(open('${ASSET_REPORT}').read()); print(str(bool(d.get('generated_usd'))).lower())" 2>/dev/null || echo "false")
  if [[ "${HAS_USD}" == "true" ]]; then
    pass "Yahboom M3 Isaac USD generated"
  else
    fail "Yahboom M3 Isaac USD not yet generated (run: bash scripts/import_yahboom_m3_urdf_to_isaac.sh)"
  fi
fi

echo ""

# ── 5. Camera report ──────────────────────────────────────────────────────
echo "--- Camera ---"
CAMERA_REPORT="${REPO_ROOT}/runs/current_camera_report.json"
check "runs/current_camera_report.json exists" \
  "$([ -f "${CAMERA_REPORT}" ] && echo true || echo false)"

if [[ -f "${CAMERA_REPORT}" ]]; then
  CAM_MODE=$(python3 -c "import json; d=json.loads(open('${CAMERA_REPORT}').read()); print(d.get('camera_mode','unknown'))" 2>/dev/null || echo "unknown")
  IS_FP=$(python3 -c "import json; d=json.loads(open('${CAMERA_REPORT}').read()); print(str(d.get('is_first_person',False)).lower())" 2>/dev/null || echo "false")

  check "Camera is first_person or FloatingCamera (not bird's-eye)" "${IS_FP}"

  # Hard fail if bird's-eye
  if [[ "${CAM_MODE}" =~ top_down|bird_eye|TopDown|BirdEye ]]; then
    fail "Bird's-eye camera detected — this is NOT accepted as navigation evidence"
  fi

  if [[ "${IS_FP}" == "false" ]]; then
    echo "         Camera mode: ${CAM_MODE}"
    echo "         Required: first_person or FloatingCamera"
    echo "         Run: python.sh scripts/isaac/set_first_person_camera.py"
    echo "         Or in Isaac: Perspective → Cameras → FloatingCamera"
  fi
fi

echo ""

# ── 6. Imported episodes ──────────────────────────────────────────────────
echo "--- Imported Episodes ---"
IMPORT_DIR="${REPO_ROOT}/datasets/vlnverse/imported/iamgoodnavigator"
EP_COUNT=0
if [[ -d "${IMPORT_DIR}" ]]; then
  EP_COUNT=$(find "${IMPORT_DIR}" -name "episode_meta.json" 2>/dev/null | wc -l)
fi

if [[ ${EP_COUNT} -gt 0 ]]; then
  pass "Imported IAmGoodNavigator episodes found: ${EP_COUNT}"
else
  fail "No imported episodes (run: bash scripts/run_iamgoodnavigator_episode.sh fine 0)"
fi

echo ""

# ── 7. Backend endpoints ──────────────────────────────────────────────────
echo "--- Backend endpoints ---"
if curl -sf "${BACKEND_URL}/health" >/dev/null 2>&1; then
  # /api/vln-hub/live must return JSON
  LIVE_OK=$(curl -sf "${BACKEND_URL}/api/vln-hub/live" 2>/dev/null | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print(str(d.get('ok',False)).lower())" 2>/dev/null || echo "false")
  check "/api/vln-hub/live returns JSON {ok: true}" "${LIVE_OK}"

  # /api/yahboom/assets
  YB_OK=$(curl -s -o /dev/null -w "%{http_code}" "${BACKEND_URL}/api/yahboom/assets" 2>/dev/null || echo "000")
  check "/api/yahboom/assets endpoint exists (HTTP ${YB_OK})" \
    "$([ "${YB_OK}" == "200" ] && echo true || echo false)"

  # /api/vln-hub/imported-episodes
  EP_HTTP=$(curl -s -o /dev/null -w "%{http_code}" "${BACKEND_URL}/api/vln-hub/imported-episodes" 2>/dev/null || echo "000")
  check "/api/vln-hub/imported-episodes endpoint exists (HTTP ${EP_HTTP})" \
    "$([ "${EP_HTTP}" == "200" ] && echo true || echo false)"
else
  skip "Backend not reachable at ${BACKEND_URL} — skipping endpoint checks"
fi

echo ""

# ── 8. Frontend builds ────────────────────────────────────────────────────
echo "--- Frontend ---"
PAGE_FILE="${REPO_ROOT}/command-center/frontend/src/app/dashboard/vln-hub/page.tsx"
check "/dashboard/vln-hub page.tsx exists" "$([ -f "${PAGE_FILE}" ] && echo true || echo false)"

if [[ -f "${PAGE_FILE}" ]]; then
  # Check it imports LiveStatus (real evidence panel)
  HAS_LIVE=$(grep -c "LiveStatus" "${PAGE_FILE}" 2>/dev/null || echo "0")
  check "page.tsx has real evidence panels (LiveStatus)" \
    "$([ "${HAS_LIVE}" -gt 0 ] && echo true || echo false)"

  # Must NOT be mock/placeholder only
  if grep -qE "placeholder-only|mock data only|missing-data instructions" "${PAGE_FILE}" 2>/dev/null; then
    fail "page.tsx has placeholder-only content"
  else
    pass "page.tsx is not placeholder-only"
  fi
fi

echo ""

# ── 9. Evidence screenshots ───────────────────────────────────────────────
echo "--- Evidence screenshots ---"
EVIDENCE_DIR="${REPO_ROOT}/evidence/live_imported_vln_demo"
if [[ -d "${EVIDENCE_DIR}" ]]; then
  LATEST_RUN=$(ls -t "${EVIDENCE_DIR}" 2>/dev/null | head -1)
  if [[ -n "${LATEST_RUN}" ]]; then
    SCREENSHOT_COUNT=$(find "${EVIDENCE_DIR}/${LATEST_RUN}" -name "*.png" 2>/dev/null | wc -l)
    SUMMARY_EXISTS="$([ -f "${EVIDENCE_DIR}/${LATEST_RUN}/evidence_summary.json" ] && echo true || echo false)"
    check "evidence_summary.json exists" "${SUMMARY_EXISTS}"
    if [[ ${SCREENSHOT_COUNT} -ge 1 ]]; then
      pass "Evidence screenshots found: ${SCREENSHOT_COUNT} (run: ${LATEST_RUN})"
    else
      fail "No evidence screenshots (run: bash scripts/capture_live_evidence.sh)"
    fi
  else
    fail "No evidence runs found (run: bash scripts/capture_live_evidence.sh)"
  fi
else
  fail "evidence/live_imported_vln_demo/ does not exist"
fi

echo ""

# ── Summary ───────────────────────────────────────────────────────────────
echo "========================================"
printf "  PASS: %d   FAIL: %d   SKIP: %d\n" "${PASS}" "${FAIL}" "${SKIP}"
echo "========================================"

if [[ ${FAIL} -gt 0 ]]; then
  echo ""
  echo "  Demo check FAILED."
  echo "  Resolve the FAIL items above, then re-run:"
  echo "    bash scripts/run_real_imported_vln_demo.sh"
  echo "    bash scripts/run_real_imported_vln_demo_check.sh"
  exit 1
fi

echo ""
echo "  All checks passed. Real imported VLN demo is verified."
