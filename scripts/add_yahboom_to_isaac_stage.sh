#!/usr/bin/env bash
# scripts/add_yahboom_to_isaac_stage.sh
# Attempt to add the Yahboom M3 Pro USD to the open Isaac Sim stage.
# Runs scripts/isaac/add_yahboom_to_current_stage.py through conda isaac Python.
# If Isaac UI stage is not accessible (normal outside Isaac), prints exact manual steps.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

SCRIPT="${REPO_ROOT}/scripts/isaac/add_yahboom_to_current_stage.py"
USD_PATH="${REPO_ROOT}/assets/robots/yahboom_m3_pro/yahboom_m3pro.usd"
REPORT_PATH="${REPO_ROOT}/runs/yahboom_stage_report.json"

echo "========================================"
echo "  FleetSafe — Yahboom USD → Isaac Stage"
echo "========================================"
echo "  USD:    ${USD_PATH}"
echo "  Target: /World/YahboomM3Pro"
echo ""

# ── Preflight: USD must exist ────────────────────────────────────────────────
if [[ ! -f "${USD_PATH}" ]]; then
    echo "[FAIL] Yahboom USD not found: ${USD_PATH}"
    echo "  Convert first:"
    echo "    bash scripts/import_yahboom_m3_urdf_to_isaac.sh"
    exit 1
fi
echo "[OK]  USD present: $(ls -lh "${USD_PATH}" | awk '{print $5}')"
echo ""

# ── Try conda isaac Python ───────────────────────────────────────────────────
CONDA_BASE="${CONDA_PREFIX_1:-$(conda info --base 2>/dev/null || echo '/home/favl/miniforge3')}"
CONDA_BASE="${CONDA_BASE%/envs/*}"
ISAAC_PYTHON="${CONDA_BASE}/envs/isaac/bin/python"

if [[ ! -f "${ISAAC_PYTHON}" ]]; then
    ISAAC_PYTHON="$(which python3)"
fi

echo "  Running: ${ISAAC_PYTHON} ${SCRIPT}"
echo "  (Will succeed only if this Python can access the open Isaac stage)"
echo ""

ROS_SETUP=""
[[ -f /opt/ros/humble/setup.bash ]] && ROS_SETUP="source /opt/ros/humble/setup.bash"

bash -c "${ROS_SETUP:+${ROS_SETUP} &&} '${ISAAC_PYTHON}' '${SCRIPT}'" 2>&1 || true

echo ""

# ── Check result ─────────────────────────────────────────────────────────────
if [[ -f "${REPORT_PATH}" ]]; then
    STATUS=$(python3 -c "import json; d=json.load(open('${REPORT_PATH}')); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
    STAGED=$(python3 -c "import json; d=json.load(open('${REPORT_PATH}')); print(str(d.get('stage_has_yahboom',False)).lower())" 2>/dev/null || echo "false")
    echo "  Report: status=${STATUS}  stage_has_yahboom=${STAGED}"
    if [[ "${STAGED}" == "true" ]]; then
        echo ""
        echo "[OK]  Yahboom M3 Pro is staged in Isaac at /World/YahboomM3Pro"
        exit 0
    fi
fi

# ── Manual fallback ──────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  MANUAL ACTION REQUIRED IN ISAAC SIM"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  Option A — Isaac Script Editor / Console:"
echo "    Open: Window → Script Editor"
echo "    Paste and run:"
echo ""
echo "      exec(open('${SCRIPT}').read())"
echo ""
echo "  Option B — Isaac menu:"
echo "    File → Add Reference"
echo "    Select:"
echo "      ${USD_PATH}"
echo "    Set stage path: /World/YahboomM3Pro"
echo ""
echo "  After staging, re-run this script to write the report:"
echo "    bash scripts/add_yahboom_to_isaac_stage.sh"
echo ""
echo "  Dashboard will show 'Yahboom staged: yes' once"
echo "  runs/yahboom_stage_report.json has stage_has_yahboom=true."
echo "═══════════════════════════════════════════════════════════"
exit 0
