#!/usr/bin/env bash
# scripts/run_iamgoodnavigator_episode.sh
# ─────────────────────────────────────────────────────────────────────────────
# Run one IAmGoodNavigator demo episode and index the output into FleetSafe.
#
# IMPORTANT: demo.py opens fine_grained_demo.json / coarse_grained_demo.json
# using a relative path, so it must be launched from external/IAmGoodNavigator/.
# This script always cd's there before running demo.py.
#
# IMPORTANT: Isaac Sim requires numpy==1.26.0.  This script detects the 'isaac'
# conda environment and uses its Python automatically.  If that env is not
# found, it checks whether the active Python has numpy==1.26.0 and exits with
# a clear error if not.
#
# Usage:
#   bash scripts/run_iamgoodnavigator_episode.sh fine 0
#   bash scripts/run_iamgoodnavigator_episode.sh coarse 2
#
# Output:
#   runs/iamgoodnavigator/<task>_<index>/isaac_demo.log
#   datasets/vlnverse/imported/iamgoodnavigator/<task>_<index>/episode_meta.json
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IANG_ROOT="${REPO_ROOT}/external/IAmGoodNavigator"
TASK="${1:-fine}"
INDEX="${2:-0}"
WORK_DIR="${REPO_ROOT}/runs/iamgoodnavigator/${TASK}_${INDEX}"
IMPORT_DIR="${REPO_ROOT}/datasets/vlnverse/imported/iamgoodnavigator/${TASK}_${INDEX}"
CONDA_BASE="${CONDA_PREFIX_1:-$(conda info --base 2>/dev/null || echo '/home/favl/miniforge3')}"
CONDA_BASE="${CONDA_BASE%/envs/*}"   # strip env suffix if CONDA_PREFIX_1 points to an env

echo "========================================"
echo "  FleetSafe — IAmGoodNavigator Episode"
echo "  task=${TASK}  index=${INDEX}"
echo "========================================"
echo "  IAmGoodNavigator: ${IANG_ROOT}"
echo "  Work dir:         ${WORK_DIR}"
echo ""

# ── Preflight: repo structure ─────────────────────────────────────────────────
if [[ ! -d "${IANG_ROOT}" ]]; then
  echo "[FAIL] ${IANG_ROOT} not found."
  echo "  Run: bash scripts/setup_iamgoodnavigator.sh"
  exit 2
fi
if [[ ! -f "${IANG_ROOT}/demo.py" ]]; then
  echo "[FAIL] demo.py not found in ${IANG_ROOT}"
  exit 2
fi

# ── Preflight: task data file ─────────────────────────────────────────────────
TASK_FILE="${IANG_ROOT}/${TASK}_grained_demo.json"
if [[ ! -f "${TASK_FILE}" ]]; then
  echo "[FAIL] Task data file not found: ${TASK_FILE}"
  echo "  Run: bash scripts/setup_iamgoodnavigator.sh --download"
  exit 2
fi

EPISODE_COUNT=$(python3 -c "
import json
try:
    d = json.load(open('${TASK_FILE}'))
    v = d if isinstance(d, list) else d.get('episodes', d.get('data', []))
    print(len(v))
except Exception: print(0)
" 2>/dev/null || echo "0")
echo "  Available episodes: ${EPISODE_COUNT} (${TASK})"
if [[ "${EPISODE_COUNT}" == "0" ]]; then
  echo "[FAIL] No episodes in ${TASK_FILE}"
  exit 2
fi

# ── Resolve isaac Python — must have numpy==1.26.0 ───────────────────────────
echo "--- Resolving isaac Python ---"

ISAAC_PYTHON=""

# 1. Try explicit isaac conda env
_CANDIDATE="${CONDA_BASE}/envs/isaac/bin/python"
if [[ -f "${_CANDIDATE}" ]]; then
  _NP="$("${_CANDIDATE}" -c 'import numpy; print(numpy.__version__)' 2>/dev/null || echo 'missing')"
  if [[ "${_NP}" == 1.26.* ]]; then
    ISAAC_PYTHON="${_CANDIDATE}"
    echo "[OK]  isaac env Python: ${ISAAC_PYTHON}  (numpy ${_NP})"
  else
    echo "[WARN] isaac env has numpy=${_NP}, need 1.26.x — running install..."
    "${_CANDIDATE}" -m pip install "numpy==1.26.0" --quiet && \
      ISAAC_PYTHON="${_CANDIDATE}" && \
      echo "[OK]  numpy downgraded in isaac env." || \
      echo "[WARN] pip downgrade failed."
  fi
fi

# 2. Fall back to active Python if it already has the right numpy
if [[ -z "${ISAAC_PYTHON}" ]]; then
  _NP="$(python3 -c 'import numpy; print(numpy.__version__)' 2>/dev/null || echo 'missing')"
  if [[ "${_NP}" == 1.26.* ]]; then
    ISAAC_PYTHON="python3"
    echo "[OK]  Active Python has numpy ${_NP} — using python3."
  fi
fi

# 3. Hard fail if no acceptable Python found
if [[ -z "${ISAAC_PYTHON}" ]]; then
  _NP="$(python3 -c 'import numpy; print(numpy.__version__)' 2>/dev/null || echo 'missing')"
  echo ""
  echo "╔══════════════════════════════════════════════════════════════════════╗"
  echo "║  [FAIL] numpy==1.26.0 not found.                                    ║"
  echo "║                                                                      ║"
  echo "║  Active Python numpy: ${_NP:-missing}$(printf '%*s' $((44-${#_NP})) '')║"
  echo "║  Isaac Sim requires:  1.26.0                                         ║"
  echo "║                                                                      ║"
  echo "║  Fix:                                                                ║"
  echo "║    bash scripts/install_isaac_demo_deps.sh                           ║"
  echo "║    conda activate isaac                                               ║"
  echo "║    bash scripts/run_iamgoodnavigator_episode.sh ${TASK} ${INDEX}     ║"
  echo "╚══════════════════════════════════════════════════════════════════════╝"
  exit 1
fi

# ── Preflight: dependency check (using resolved Python) ──────────────────────
echo "--- Checking Python dependencies ---"
MISSING_DEPS=()
"${ISAAC_PYTHON}" -c "import numpy; v=numpy.__version__; assert v.startswith('1.26'), v" 2>/dev/null \
  || { echo "[FAIL] numpy must be 1.26.x"; exit 1; }
"${ISAAC_PYTHON}" -c "import pandas"  2>/dev/null || MISSING_DEPS+=("pandas==2.2.3")
"${ISAAC_PYTHON}" -c "import cv2"     2>/dev/null || MISSING_DEPS+=("opencv-python==4.10.0.84")
"${ISAAC_PYTHON}" -c "import PIL"     2>/dev/null || MISSING_DEPS+=("pillow")
"${ISAAC_PYTHON}" -c "import yaml"    2>/dev/null || MISSING_DEPS+=("pyyaml")
"${ISAAC_PYTHON}" -c "import tqdm"    2>/dev/null || MISSING_DEPS+=("tqdm")

if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
  echo "[WARN] Missing packages: ${MISSING_DEPS[*]}"
  echo "  Installing..."
  "${ISAAC_PYTHON}" -m pip install "${MISSING_DEPS[@]}" --quiet && \
    echo "[OK]  Installed." || echo "[WARN] Install failed — check manually."
else
  echo "[OK]  All dependencies present."
fi
echo "  numpy: $("${ISAAC_PYTHON}" -c 'import numpy; print(numpy.__version__)')"

mkdir -p "${WORK_DIR}"

# ── Launch episode ─────────────────────────────────────────────────────────────
# CRITICAL: demo.py opens fine_grained_demo.json with a bare relative path,
# so we must run it from external/IAmGoodNavigator/ (not the repo root).
LOG_FILE="${WORK_DIR}/isaac_demo.log"
echo ""
echo "--- Launching episode ---"
echo "  cwd:     ${IANG_ROOT}"
echo "  command: python demo.py --task ${TASK} --index ${INDEX} --work_dir ${WORK_DIR}"
echo "  log:     ${LOG_FILE}"
echo ""
echo "  NOTE: This demo runs inside Isaac Sim."
echo "  Camera: Perspective → Cameras → FloatingCamera  (first-person)"
echo ""

RC=0
(
  cd "${IANG_ROOT}"
  "${ISAAC_PYTHON}" demo.py \
    --task    "${TASK}" \
    --index   "${INDEX}" \
    --work_dir "${WORK_DIR}" \
    2>&1 | tee "${LOG_FILE}"
) || RC=$?

echo ""
if [[ ${RC} -eq 0 ]]; then
  echo "[OK]  Episode finished (exit 0)."
else
  echo "[WARN] Episode exited with code ${RC}."
  if grep -q "No module named 'isaacsim'" "${LOG_FILE}" 2>/dev/null; then
    echo "  Isaac Sim not running — episode requires Isaac Sim."
    echo "  Run demo.py inside the Isaac Sim Python environment."
  fi
  echo "  Log: ${LOG_FILE}"
fi

# ── Index output (always runs, even on failure) ──────────────────────────────
echo ""
echo "--- Indexing episode output ---"
mkdir -p "${IMPORT_DIR}"

python3 - <<PYEOF
import json, sys
from datetime import datetime, timezone
from pathlib import Path

work = Path("${WORK_DIR}")
dest = Path("${IMPORT_DIR}")
rc   = ${RC}

# IAmGoodNavigator writes trajectory as CSV (e.g. kujiale_0010_4_4.csv), not JSON
traj_files   = (list(work.rglob("trajectory*.json")) + list(work.rglob("*traj*.json"))
                + list(work.rglob("*.csv")))
metric_files = list(work.rglob("metrics*.json"))   + list(work.rglob("result*.json"))
image_files  = list(work.rglob("*.jpg"))           + list(work.rglob("*.png"))
log_file     = work / "isaac_demo.log"

error_msg = None
if log_file.exists():
    for line in log_file.read_text(errors="replace").splitlines():
        if any(kw in line for kw in ("Error", "error", "Traceback", "FAIL")):
            error_msg = line.strip()[:200]
            break

instruction_text = None
scan_id = None
task_path = Path("${IANG_ROOT}/${TASK}_grained_demo.json")
if task_path.exists():
    try:
        d = json.loads(task_path.read_text())
        eps = d if isinstance(d, list) else d.get("episodes", d.get("data", []))
        ep = eps[int("${INDEX}")]
        raw = ep.get("instruction") or ep.get("text") or ep.get("nl_command")
        if isinstance(raw, dict):
            instruction_text = str(raw.get("instruction_text", ""))
        elif isinstance(raw, str):
            instruction_text = raw
        elif raw is not None:
            instruction_text = str(raw)
        scan_id = ep.get("scan") or ep.get("scene_id", "").split("/")[-1] or None
    except Exception as e:
        instruction_text = f"[parse error: {e}]"

# Scene existence check
iang_root = Path("${IANG_ROOT}")
expected_scene_path = None
scene_exists = False
if scan_id:
    expected_scene_path = str(iang_root / scan_id / f"{scan_id}.usda")
    scene_exists = Path(expected_scene_path).exists()

# Determine status
if rc != 0:
    status = "failed"
elif not scene_exists:
    status = "completed_missing_scene"
elif len(traj_files) == 0 and len(image_files) == 0:
    status = "completed_no_output"
else:
    status = "completed"

# evidence_valid: only when scene is present and episode produced output
evidence_valid = (rc == 0 and scene_exists and
                  (len(traj_files) > 0 or len(image_files) > 0))

# error_summary
error_summary = None
if status == "completed_missing_scene":
    error_summary = f"Scene USD missing: {expected_scene_path}"
elif status == "completed_no_output":
    error_summary = "Episode exited 0 but produced no trajectory/image files (Isaac Sim may need interactive mode)"
elif error_msg:
    error_summary = error_msg

meta = {
    "source": "IAmGoodNavigator",
    "task": "${TASK}",
    "index": int("${INDEX}"),
    "indexed_at": datetime.now(timezone.utc).isoformat(),
    "work_dir": str(work),
    "exit_code": rc,
    "instruction": instruction_text,
    "scan_id": scan_id,
    "expected_scene_path": expected_scene_path,
    "scene_exists": scene_exists,
    "evidence_valid": evidence_valid,
    "error": error_msg,
    "error_summary": error_summary,
    "files": {
        "trajectories": [str(p.relative_to(work)) for p in traj_files[:5]],
        "metrics": [str(p.relative_to(work)) for p in metric_files[:3]],
        "images": [str(p.relative_to(work)) for p in image_files[:10]],
        "log": str(log_file.relative_to(work)) if log_file.exists() else None,
    },
    "file_counts": {
        "trajectories": len(traj_files),
        "metrics": len(metric_files),
        "images": len(image_files),
    },
    "status": status,
    "metadata_imported": True,
    "camera_note": "Set Isaac Sim camera: Perspective → Cameras → FloatingCamera",
}

out = dest / "episode_meta.json"
out.write_text(json.dumps(meta, indent=2))
print(f"  episode_meta.json: {out}")
print(f"  status={meta['status']}  exit_code={rc}  scene_exists={scene_exists}  "
      f"traj={meta['file_counts']['trajectories']}  "
      f"images={meta['file_counts']['images']}")
if instruction_text:
    print(f"  instruction: {instruction_text[:120]}")
if error_summary:
    print(f"  error_summary: {error_summary[:160]}")
PYEOF

echo ""
echo "--- Updating VLNVerse index ---"
python3 -m fleetsafe_vln.benchmark.vlnverse_indexer \
  --root "${REPO_ROOT}/datasets/vlnverse" 2>&1 | tail -5 || true

echo ""
echo "Done."
echo "  Output:   ${WORK_DIR}"
echo "  Imported: ${IMPORT_DIR}"
echo ""
echo "  Camera (IMPORTANT):"
echo "    In Isaac Sim: Perspective → Cameras → FloatingCamera"
