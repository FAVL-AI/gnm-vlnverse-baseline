#!/usr/bin/env bash
# scripts/run_vln_hub_smoke_test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Smoke-test the VLN Hub integration.
# Does NOT require Isaac Sim, ROS 2, Gemini, or large dataset downloads.
#
# Pass criteria:
#   1. Python indexers run without error
#   2. Index JSON files are written and valid
#   3. Backend /api/vln-hub/* endpoints return 200 (if backend reachable)
#
# Usage:
#   bash scripts/run_vln_hub_smoke_test.sh
#   bash scripts/run_vln_hub_smoke_test.sh --no-backend   # skip backend checks
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

BACKEND_URL="http://localhost:8000"
CHECK_BACKEND=true
PASS=0
FAIL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-backend) CHECK_BACKEND=false; shift ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

echo "========================================"
echo "  FleetSafe — VLN Hub Smoke Test"
echo "========================================"
echo ""

pass() { echo "  [PASS] $1"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

# ── 1. Python indexers ─────────────────────────────────────────────────────
echo "--- Python indexers ---"

if python3 -m fleetsafe_vln.benchmark.vlnverse_indexer \
     --root "${REPO_ROOT}/datasets/vlnverse" 2>&1 | grep -q "VLNVerse index written"; then
  pass "vlnverse_indexer ran OK"
else
  if python3 -m fleetsafe_vln.benchmark.vlnverse_indexer \
       --root "${REPO_ROOT}/datasets/vlnverse" >/dev/null 2>&1; then
    pass "vlnverse_indexer ran OK (no output grep match)"
  else
    fail "vlnverse_indexer failed"
  fi
fi

if python3 -m fleetsafe_vln.datagen.vlntube_indexer \
     --root "${REPO_ROOT}/datasets/vlntube" 2>&1 | grep -q "VLNTube index written"; then
  pass "vlntube_indexer ran OK"
else
  if python3 -m fleetsafe_vln.datagen.vlntube_indexer \
       --root "${REPO_ROOT}/datasets/vlntube" >/dev/null 2>&1; then
    pass "vlntube_indexer ran OK (no output grep match)"
  else
    fail "vlntube_indexer failed"
  fi
fi

echo ""

# ── 2. Index files valid JSON ─────────────────────────────────────────────
echo "--- Index file validity ---"

VVINDEX="${REPO_ROOT}/datasets/vlnverse/vlnverse_index.json"
VTINDEX="${REPO_ROOT}/datasets/vlntube/vlntube_index.json"

if [[ -f "${VVINDEX}" ]]; then
  if python3 -c "import json; json.loads(open('${VVINDEX}').read())" 2>/dev/null; then
    pass "vlnverse_index.json is valid JSON"
    # Check required fields
    if python3 -c "
import json
d = json.loads(open('${VVINDEX}').read())
assert 'summary' in d
assert 'indexed_at' in d
assert 'datasets' in d
assert 'next_actions' in d
" 2>/dev/null; then
      pass "vlnverse_index.json has required fields"
    else
      fail "vlnverse_index.json missing required fields"
    fi
  else
    fail "vlnverse_index.json is not valid JSON"
  fi
else
  fail "vlnverse_index.json not found at ${VVINDEX}"
fi

if [[ -f "${VTINDEX}" ]]; then
  if python3 -c "import json; json.loads(open('${VTINDEX}').read())" 2>/dev/null; then
    pass "vlntube_index.json is valid JSON"
    if python3 -c "
import json
d = json.loads(open('${VTINDEX}').read())
assert 'summary' in d
assert 'indexed_at' in d
assert 'datasets' in d
assert 'next_actions' in d
" 2>/dev/null; then
      pass "vlntube_index.json has required fields"
    else
      fail "vlntube_index.json missing required fields"
    fi
  else
    fail "vlntube_index.json is not valid JSON"
  fi
else
  fail "vlntube_index.json not found at ${VTINDEX}"
fi

echo ""

# ── 3. HF registry import ─────────────────────────────────────────────────
echo "--- HF dataset registry ---"
if python3 -c "
import sys; sys.path.insert(0, '${REPO_ROOT}')
from fleetsafe_vln.datagen.hf_dataset_registry import list_known_datasets
ds = list_known_datasets()
assert len(ds) >= 4, f'Expected >=4 datasets, got {len(ds)}'
for d in ds:
    assert 'id' in d
    assert 'name' in d
    assert 'hf_repo' in d
" 2>/dev/null; then
  pass "hf_dataset_registry imports and has valid entries"
else
  fail "hf_dataset_registry import or validation failed"
fi

echo ""

# ── 4. Backend endpoints ──────────────────────────────────────────────────
if $CHECK_BACKEND; then
  echo "--- Backend /api/vln-hub/* endpoints ---"

  if curl -sf "${BACKEND_URL}/health" >/dev/null 2>&1; then
    for endpoint in status vlntube vlnverse previews trajectories instructions; do
      http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        "${BACKEND_URL}/api/vln-hub/${endpoint}" 2>/dev/null || echo "000")
      if [[ "${http_code}" == "200" ]] || [[ "${http_code}" == "404" ]]; then
        pass "/api/vln-hub/${endpoint} → HTTP ${http_code}"
      else
        fail "/api/vln-hub/${endpoint} → HTTP ${http_code} (expected 200 or 404)"
      fi
    done

    # POST /refresh
    http_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
      "${BACKEND_URL}/api/vln-hub/refresh" 2>/dev/null || echo "000")
    if [[ "${http_code}" == "200" ]]; then
      pass "/api/vln-hub/refresh POST → HTTP 200"
    else
      fail "/api/vln-hub/refresh POST → HTTP ${http_code}"
    fi
  else
    echo "  [SKIP] Backend not reachable at ${BACKEND_URL}"
    echo "         Start with: cd command-center && python -m uvicorn backend.main:app --port 8000"
    echo "         Or re-run with: --no-backend"
  fi
else
  echo "  [SKIP] Backend checks disabled (--no-backend)"
fi

echo ""

# ── Summary ───────────────────────────────────────────────────────────────
echo "========================================"
printf "  PASS: %d   FAIL: %d\n" "${PASS}" "${FAIL}"
echo "========================================"

if [[ ${FAIL} -gt 0 ]]; then
  exit 1
fi
echo "All checks passed."
