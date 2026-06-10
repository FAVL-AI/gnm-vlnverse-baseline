#!/usr/bin/env bash
# scripts/setup_iamgoodnavigator.sh
# ─────────────────────────────────────────────────────────────────────────────
# Clone IAmGoodNavigator into external/IAmGoodNavigator, verify required files,
# and write datasets/vlnverse/iamgoodnavigator_status.json.
#
# Does NOT silently skip downloads.  If download.sh is not run, prints the
# exact command.  Fails loudly if required files are missing.
#
# Usage:
#   bash scripts/setup_iamgoodnavigator.sh            # clone + inspect
#   bash scripts/setup_iamgoodnavigator.sh --download # clone + run download.sh
#   bash scripts/setup_iamgoodnavigator.sh --skip-clone  # inspect only
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IANG_TARGET="${REPO_ROOT}/external/IAmGoodNavigator"
IANG_LEGACY="${REPO_ROOT}/third_party/IAmGoodNavigator"
IANG_URL="https://github.com/william13077/IAmGoodNavigator.git"
STATUS_OUT="${REPO_ROOT}/datasets/vlnverse/iamgoodnavigator_status.json"
SKIP_CLONE=false
DO_DOWNLOAD=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-clone) SKIP_CLONE=true;  shift ;;
    --download)   DO_DOWNLOAD=true; shift ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

echo "========================================"
echo "  FleetSafe — IAmGoodNavigator Setup"
echo "========================================"
echo "  Target: ${IANG_TARGET}"
echo ""

# ── Clone / link ───────────────────────────────────────────────────────────
IANG_ROOT="${IANG_TARGET}"
CLONE_OK=false

if [[ -d "${IANG_TARGET}" ]] && [[ -f "${IANG_TARGET}/demo.py" ]]; then
  echo "[OK]  IAmGoodNavigator already present at ${IANG_TARGET}"
  CLONE_OK=true

elif [[ -d "${IANG_LEGACY}" ]] && [[ -f "${IANG_LEGACY}/demo.py" ]]; then
  echo "[OK]  Found at legacy path ${IANG_LEGACY}"
  echo "  Symlinking to external/IAmGoodNavigator..."
  mkdir -p "${REPO_ROOT}/external"
  ln -sfn "${IANG_LEGACY}" "${IANG_TARGET}" 2>/dev/null || cp -r "${IANG_LEGACY}" "${IANG_TARGET}"
  echo "[OK]  Linked."
  CLONE_OK=true

elif $SKIP_CLONE; then
  echo "[SKIP] --skip-clone: IAmGoodNavigator not present."

else
  echo "  Cloning IAmGoodNavigator from ${IANG_URL}..."
  mkdir -p "${REPO_ROOT}/external"
  if git clone "${IANG_URL}" "${IANG_TARGET}" 2>&1; then
    echo "[OK]  Cloned."
    CLONE_OK=true
  else
    echo "[WARN] Clone failed — repo may be unavailable."
    echo "  IAmGoodNavigator will operate in missing-dependency mode."
  fi
fi

echo ""

# ── Verify required files ──────────────────────────────────────────────────
echo "--- Verifying required files ---"
REQUIRED_FILES=("demo.py" "download.sh" "fine_grained_demo.json" "coarse_grained_demo.json")

ALL_OK=true
MISSING=()
for f in "${REQUIRED_FILES[@]}"; do
  if [[ -f "${IANG_ROOT}/${f}" ]]; then
    printf "  [OK]  %s\n" "${f}"
  else
    printf "  [--]  %s  (missing)\n" "${f}"
    MISSING+=("${f}")
    ALL_OK=false
  fi
done

if ! $ALL_OK; then
  echo ""
  echo "[WARN] Missing required files: ${MISSING[*]}"
  if $CLONE_OK; then
    echo "  Clone succeeded but files are missing — check IAmGoodNavigator README."
  else
    echo "  Clone did not succeed.  Re-run without --skip-clone."
  fi
fi

echo ""

# ── Run download.sh ────────────────────────────────────────────────────────
if $DO_DOWNLOAD; then
  DOWNLOAD_SCRIPT="${IANG_ROOT}/download.sh"
  if [[ -f "${DOWNLOAD_SCRIPT}" ]]; then
    echo "--- Running download.sh (scene USD/data) ---"
    bash "${DOWNLOAD_SCRIPT}" 2>&1
    echo "[OK]  download.sh complete."
  else
    echo "[FAIL] --download requested but ${DOWNLOAD_SCRIPT} not found."
    echo "  Cannot download scene data. Check IAmGoodNavigator README."
  fi
else
  if [[ -f "${IANG_ROOT}/download.sh" ]]; then
    echo "--- Scene data (NOT downloaded automatically) ---"
    echo "  Isaac Sim USD scenes are NOT downloaded unless --download is passed."
    echo "  To download:"
    echo "    bash scripts/setup_iamgoodnavigator.sh --download"
    echo "  Or run directly:"
    echo "    bash ${IANG_ROOT}/download.sh"
  fi
fi

echo ""

# ── Inspect demo task files ────────────────────────────────────────────────
echo "--- Demo task episode counts ---"
for jf in "fine_grained_demo.json" "coarse_grained_demo.json"; do
  jpath="${IANG_ROOT}/${jf}"
  if [[ -f "${jpath}" ]]; then
    count=$(python3 -c "
import json
try:
    d=json.loads(open('${jpath}').read())
    v=d if isinstance(d,list) else d.get('episodes',d.get('data',[]))
    print(len(v))
except: print('?')
" 2>/dev/null || echo "?")
    printf "  %-35s  %s episodes\n" "${jf}" "${count}"
  else
    printf "  %-35s  (missing)\n" "${jf}"
  fi
done

echo ""

# ── Write status JSON ──────────────────────────────────────────────────────
mkdir -p "$(dirname "${STATUS_OUT}")"

python3 - <<PYEOF
import json
from datetime import datetime, timezone
from pathlib import Path

root = Path("${IANG_ROOT}")

def count_episodes(fname):
    p = root / fname
    if not p.exists():
        return 0
    try:
        d = json.loads(p.read_text())
        v = d if isinstance(d, list) else d.get("episodes", d.get("data", []))
        return len(v)
    except Exception:
        return 0

fine_count   = count_episodes("fine_grained_demo.json")
coarse_count = count_episodes("coarse_grained_demo.json")
demo_py      = (root / "demo.py").exists()
dl_sh        = (root / "download.sh").exists()
root_exists  = root.exists()

missing = [f for f, v in [
    ("demo.py",               demo_py),
    ("download.sh",           dl_sh),
    ("fine_grained_demo.json",   fine_count > 0),
    ("coarse_grained_demo.json", coarse_count > 0),
] if not v]

status = {
    "source": "IAmGoodNavigator",
    "indexed_at": datetime.now(timezone.utc).isoformat(),
    "root": str(root),
    "root_exists": root_exists,
    "demo_py_exists": demo_py,
    "download_sh_exists": dl_sh,
    "fine_episodes": fine_count,
    "coarse_episodes": coarse_count,
    "ready": demo_py and (fine_count > 0 or coarse_count > 0),
    "data_downloaded": fine_count > 0 or coarse_count > 0,
    "download_command": f"bash {root}/download.sh",
    "run_episode_command": "bash scripts/run_iamgoodnavigator_episode.sh fine 0",
    "missing": missing,
    "camera_note": "In Isaac Sim: Perspective → Cameras → FloatingCamera for first-person view",
}
Path("${STATUS_OUT}").write_text(json.dumps(status, indent=2))
print(f"[OK]  Status written: ${STATUS_OUT}")
print(f"  root_exists={root_exists}  demo_py={demo_py}  fine={fine_count}  coarse={coarse_count}")
print(f"  ready={status['ready']}  missing={missing}")
PYEOF

echo ""
echo "Setup complete."
if [[ -f "${IANG_ROOT}/demo.py" ]]; then
  echo "  Run an episode (requires Isaac Sim):"
  echo "    bash scripts/run_iamgoodnavigator_episode.sh fine 0"
else
  echo "  [BLOCKED] demo.py not found. Clone must succeed before running episodes."
fi
