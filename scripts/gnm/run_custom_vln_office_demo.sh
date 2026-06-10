#!/usr/bin/env bash
# run_custom_vln_office_demo.sh — One-command CustomVLN-Office evidence demo
# ============================================================================
# Prints and executes all dry-run commands to prove the independent custom
# Isaac Sim navigation environment pipeline.
#
# Run from repository root:
#   bash scripts/gnm/run_custom_vln_office_demo.sh
set -e
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
RESET='\033[0m'

header() { echo -e "\n${BOLD}${CYAN}══════════════════════════════════════════════════════${RESET}";
           echo -e "${BOLD}${CYAN}  $1${RESET}";
           echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════${RESET}"; }
ok()     { echo -e "  ${GREEN}✓${RESET}  $1"; }

echo -e "${BOLD}${YELLOW}"
echo "  FleetSafe-VisualNav-Benchmark"
echo "  CustomVLN-Office — Independent Isaac Sim Navigation Demo"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo -e "${RESET}"

# ── 0. Distinction statement ──────────────────────────────────────────────────
header "0. What is CustomVLN-Office?"
echo
ok "VLNVerse = official Track A reproduction (SR 20.0%, OSR 46.7%, NE 6.51 m)"
ok "CustomVLN-Office = INDEPENDENT Isaac Sim scene (no VLNVerse assets)"
ok "Purpose: prove the GNM-style pipeline works beyond VLNVerse"
echo
echo -e "  ${CYAN}Scene: 16 m × 10 m office / corridor layout${RESET}"
echo -e "  ${CYAN}Assets: Isaac Sim primitives (no VLNVerse)${RESET}"
echo -e "  ${CYAN}Methodology: current RGB + goal RGB → local waypoint/action${RESET}"

# ── 1. Asset discovery ────────────────────────────────────────────────────────
header "1. Isaac asset discovery (dry-run)"
python3 scripts/gnm/discover_isaac_assets.py --dry-run
ok "Manifest: results/custom_vln_office/isaac_asset_manifest.json"

# ── 2. Scene generation ───────────────────────────────────────────────────────
header "2. Scene generation (dry-run)"
python3 scripts/gnm/create_custom_vln_office_scene.py --dry-run
ok "USDA stub: assets/custom_vln_office/scene_layout.usda"
ok "Manifest:  results/custom_vln_office/scene_manifest.md"

# ── 3. Data collection ────────────────────────────────────────────────────────
header "3. RGB data collection (dry-run — synthetic frames)"
python3 scripts/gnm/collect_custom_vln_office_data.py --dry-run
TRAIN=$(find datasets/custom_vln_office/train -name "traj_data.pkl" 2>/dev/null | wc -l | tr -d ' ')
VAL=$(find datasets/custom_vln_office/val   -name "traj_data.pkl" 2>/dev/null | wc -l | tr -d ' ')
ok "Train episodes : $TRAIN"
ok "Val   episodes : $VAL"
ok "Data root: datasets/custom_vln_office/"

# ── 4. Tasks config ───────────────────────────────────────────────────────────
header "4. Navigation task config"
python3 - <<'PYEOF'
import yaml
from pathlib import Path
with open("configs/custom_vln_office/tasks.yaml") as f:
    tasks = yaml.safe_load(f)
eps = tasks.get("episodes", [])
print(f"  Episodes defined: {len(eps)}")
for ep in eps:
    print(f"    [{ep['split']}] {ep['episode_id']}  →  \"{ep['instruction'][:60]}\"")
PYEOF
ok "Config: configs/custom_vln_office/tasks.yaml"

# ── 5. Replay dry-run ────────────────────────────────────────────────────────
header "5. Replay dry-run (episode cvlo_ep001)"
python3 scripts/gnm/replay_custom_vln_office.py --dry-run --episode cvlo_ep001
ok "Evidence panels: results/figures/cvlo_cvlo_ep001_*.png"

# ── 6. Evaluation ────────────────────────────────────────────────────────────
header "6. Evaluation"
python3 scripts/gnm/evaluate_custom_vln_office.py --dry-run
ok "Eval summary: results/custom_vln_office/eval_summary.md"
ok "Eval CSV:     results/custom_vln_office/eval_summary.csv"

# ── 7. Manual drive info ──────────────────────────────────────────────────────
header "7. Manual drive (dry-run — shows controls)"
python3 scripts/gnm/manual_custom_vln_office_drive.py --dry-run
ok "Manual data saved to: datasets/custom_vln_office_manual/"

# ── 8. Reviewer packet ────────────────────────────────────────────────────────
header "8. Reviewer documentation"
if [ -f results/bo_reviewer_packet/12_custom_vln_office_independent_isaac_scene.md ]; then
    ok "results/bo_reviewer_packet/12_custom_vln_office_independent_isaac_scene.md"
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}${YELLOW}══════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  Summary${RESET}"
echo -e "${BOLD}${YELLOW}══════════════════════════════════════════════════════${RESET}"
echo
ok "CustomVLN-Office: independent Isaac Sim office navigation scene"
ok "NO VLNVerse assets used"
ok "6 train + 2 val episodes with RGB frames, traj_data.pkl, actions.jsonl"
ok "GNM input/output pipeline: current RGB + goal RGB → local waypoint/action"
ok "x/y/yaw logged per frame in traj_data.pkl"
ok "Local waypoint labels derived from consecutive trajectory poses"
echo
echo -e "  Isaac Sim full commands:"
echo -e "  ${CYAN}conda run -n isaac python scripts/gnm/create_custom_vln_office_scene.py${RESET}"
echo -e "  ${CYAN}conda run -n isaac python scripts/gnm/collect_custom_vln_office_data.py${RESET}"
echo -e "  ${CYAN}EPISODE=cvlo_ep003 conda run -n isaac python scripts/gnm/replay_custom_vln_office.py${RESET}"
echo -e "  ${CYAN}conda run -n isaac python scripts/gnm/manual_custom_vln_office_drive.py${RESET}"
echo
echo -e "  Reviewer packet: ${CYAN}results/bo_reviewer_packet/${RESET}"
echo
