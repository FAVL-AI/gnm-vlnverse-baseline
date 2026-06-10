#!/usr/bin/env bash
# scripts/isaaclab/replay_intervention.sh
#
# Intervention Evidence Replay Viewer — Isaac Sim launcher.
#
# Usage:
#   ./scripts/isaaclab/replay_intervention.sh --episode-dir <path>
#   ./scripts/isaaclab/replay_intervention.sh --episode-dir <path> --jump-to-interventions
#   ./scripts/isaaclab/replay_intervention.sh --episode-dir <path> --speed 0.5
#
# Requires:
#   conda activate isaac
#   export OMNI_KIT_ACCEPT_EULA=Y  (set automatically below if not set)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ── Check conda environment ───────────────────────────────────────────────────
if [[ -z "${CONDA_DEFAULT_ENV}" ]] || [[ "${CONDA_DEFAULT_ENV}" != "isaac" ]]; then
    echo ""
    echo "[replay_intervention.sh] ERROR: Isaac conda environment not active."
    echo "  Run: conda activate isaac"
    echo "  Then re-run: ./scripts/isaaclab/replay_intervention.sh --episode-dir <path>"
    echo ""
    exit 1
fi

# ── Check --episode-dir provided ─────────────────────────────────────────────
if [[ "$*" != *"--episode-dir"* ]]; then
    echo ""
    echo "[replay_intervention.sh] ERROR: --episode-dir is required."
    echo ""
    echo "  Usage:"
    echo "    ./scripts/isaaclab/replay_intervention.sh --episode-dir <path>"
    echo ""
    echo "  Example (after a mock run):"
    echo "    ./scripts/isaaclab/replay_intervention.sh \\"
    echo "      --episode-dir benchmarks/visualnav/results/<run_id>/episodes/episode_0001"
    echo ""
    exit 1
fi

export OMNI_KIT_ACCEPT_EULA=Y

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  FleetSafe VisualNav  |  Intervention Evidence Replay Viewer"
echo "════════════════════════════════════════════════════════════════"
echo "  Isaac  : $(python -c 'import isaaclab; print(isaaclab.__version__)' 2>/dev/null || echo 'version unknown')"
echo "  Conda  : ${CONDA_DEFAULT_ENV}"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "  Evidence contract:"
echo "    Every visual element = a field in intervention_evidence.jsonl"
echo "    Missing files → explicit warning overlay, no silent fallback"
echo "    Mock backend  → MOCK COUNTERFACTUAL overlay always shown"
echo "════════════════════════════════════════════════════════════════"
echo ""

cd "${REPO_ROOT}"
python scripts/isaaclab/replay_intervention.py "$@"
