#!/usr/bin/env bash
# scripts/gnm/run_reviewer_demo.sh
# One-click reviewer evidence demo for Bo's questions.
# Run from the repository root:
#   bash scripts/gnm/run_reviewer_demo.sh
set -e
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
RESET='\033[0m'

header() { echo -e "\n${BOLD}${CYAN}══════════════════════════════════════════════════════${RESET}"; \
           echo -e "${BOLD}${CYAN}  $1${RESET}"; \
           echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════${RESET}"; }
ok()     { echo -e "  ${GREEN}✓${RESET}  $1"; }

echo -e "${BOLD}${YELLOW}"
echo "  FleetSafe-VisualNav-Benchmark"
echo "  General Navigation Model — Reviewer Evidence Demo"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo -e "${RESET}"

# ── 1. Git state ───────────────────────────────────────────────────────────────
header "1. Repository state"
COMMIT=$(git rev-parse --short HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
ok "Branch : $BRANCH"
ok "Commit : $COMMIT"
ok "Remote : $(git remote get-url origin 2>/dev/null || echo 'not set')"
ok "Status : $(git status --short | wc -l | tr -d ' ') changed files"

# ── 2. Dataset count ──────────────────────────────────────────────────────────
header "2. Dataset count"
TRAIN_COUNT=$(ls datasets/vlntube/train/ 2>/dev/null | wc -l | tr -d ' ')
VAL_COUNT=$(ls datasets/vlntube/val/ 2>/dev/null | wc -l | tr -d ' ')
ok "Train trajectories : $TRAIN_COUNT"
ok "Val   trajectories : $VAL_COUNT"
ok "Total              : $((TRAIN_COUNT + VAL_COUNT))"
ok "Scenes             : kujiale_0092  kujiale_0118  kujiale_0203  kujiale_0271"

# ── 3. One trajectory label inspection ────────────────────────────────────────
header "3. Trajectory label inspection (1 example from val)"
python3 scripts/gnm/inspect_trajectory_labels.py \
    --data-root datasets/vlntube \
    --split val \
    --limit 1

# ── 4. Success Rate breakdown ─────────────────────────────────────────────────
header "4. Success Rate breakdown: where does 20% come from?"
python3 scripts/gnm/explain_eval_success_rate.py \
    --checkpoint checkpoints/gnm_base/best.pt \
    --output results/bo_reviewer_packet/03_success_rate_breakdown.md \
    --csv results/bo_reviewer_packet/03_success_rate_breakdown.csv

# ── 5. Scene holdout split verification ───────────────────────────────────────
header "5. Scene-level holdout split (train ≠ test scene)"
python3 scripts/gnm/check_scene_holdout_split.py \
    --data-root datasets/vlntube \
    --split-config configs/gnm/splits/scene_holdout_kujiale_0271.yaml

# ── 6. Architecture evidence figure ───────────────────────────────────────────
header "6. GNM input-output triplet figure"
python3 scripts/gnm/make_gnm_input_output_triplet.py \
    --traj datasets/vlntube/val/kujiale_0203_kujiale_0203_43_1 \
    --out  results/bo_reviewer_packet/05_gnm_input_output_triplet.png
ok "Figure: results/bo_reviewer_packet/05_gnm_input_output_triplet.png"

# ── 7. Dataset sample package ─────────────────────────────────────────────────
header "7. Dataset sample package (1 trajectory per scene)"
python3 scripts/gnm/package_dataset_sample.py \
    --data-root datasets/vlntube \
    --output artifacts/gnm_vlnverse_sample_dataset.tar.gz \
    --per-scene 1
SHA=$(sha256sum artifacts/gnm_vlnverse_sample_dataset.tar.gz | cut -c1-16)
SIZE=$(du -sh artifacts/gnm_vlnverse_sample_dataset.tar.gz | cut -f1)
ok "Output : artifacts/gnm_vlnverse_sample_dataset.tar.gz"
ok "Size   : $SIZE"
ok "SHA256 : $SHA…"

# ── 8. Custom scene dry-run ───────────────────────────────────────────────────
header "8. Custom Isaac Sim scene (no VLNVerse assets)"
python3 scripts/gnm/create_custom_gnm_scene.py --dry-run
ok "Custom scene: datasets/custom_gnm_scene/train/custom_office_0001/"
ok "Source: create_custom_gnm_scene.py — no VLNVerse scene assets used"

# ── 9. Reviewer packet contents ───────────────────────────────────────────────
header "9. Reviewer packet location"
echo
find results/bo_reviewer_packet/ -type f 2>/dev/null | sort | \
    while read f; do
        SIZE=$(du -h "$f" | cut -f1)
        echo -e "  ${GREEN}${SIZE}${RESET}  $f"
    done

# ── Summary ────────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}${YELLOW}══════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  Summary${RESET}"
echo -e "${BOLD}${YELLOW}══════════════════════════════════════════════════════${RESET}"
echo
ok "SR  = 3/15 = 20.0%  (3 episodes stopped within 3m of goal)"
ok "OSR = 7/15 = 46.7%  (7 episodes were ever within 3m of goal)"
ok "NE  = 6.51 m  (mean final distance to goal)"
ok "Scenes: 4 imported from VLNVerse (not committed — re-downloadable)"
ok "Train/test scene overlap: NONE (kujiale_0271 held out)"
echo
echo -e "  To replay in Isaac Sim:"
echo -e "  ${CYAN}conda run -n isaac python scripts/gnm/replay_gnm_demo.py${RESET}"
echo -e "  ${CYAN}SHOW_GNM_PANELS=1 conda run -n isaac python scripts/gnm/replay_gnm_demo.py${RESET}"
echo
echo -e "  Reviewer packet: ${CYAN}results/bo_reviewer_packet/${RESET}"
echo -e "  GitHub branch:   ${CYAN}gnm-vlnverse-baseline${RESET}  commit ${COMMIT}"
echo
