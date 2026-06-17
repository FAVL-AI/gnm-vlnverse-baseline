#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

OUT_DIR="results/bo_reviewer_packet/reproducibility_pack"
LOG_FILE="$OUT_DIR/reproducibility_pack_latest.log"

mkdir -p "$OUT_DIR"

WITH_ISAAC="false"
if [[ "${1:-}" == "--with-isaac" ]]; then
  WITH_ISAAC="true"
fi

echo "============================================================"
echo " GNM-VLNVerse Reproducibility and Evidence Check"
echo "============================================================"
echo "Repo: $ROOT"
echo "Date UTC: $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
echo "Git commit: $(git rev-parse --short HEAD)"
echo "Git branch: $(git branch --show-current)"
echo "Python: $(python3 --version)"
echo "Log: $LOG_FILE"
echo "Isaac demo requested: $WITH_ISAAC"
echo "============================================================"

{
  echo "GNM-VLNVerse Reproducibility and Evidence Check"
  echo "Date UTC: $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo "Commit: $(git rev-parse --short HEAD)"
  echo "Branch: $(git branch --show-current)"
  echo "Python: $(python3 --version)"
  echo ""
} > "$LOG_FILE"

run_step() {
  local name="$1"
  shift

  echo ""
  echo "------------------------------------------------------------"
  echo "[STEP] $name"
  echo "------------------------------------------------------------"
  echo "[STEP] $name" >> "$LOG_FILE"

  "$@" 2>&1 | tee -a "$LOG_FILE"

  echo "[OK] $name" | tee -a "$LOG_FILE"
}

check_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "[FAIL] Missing required file: $path" | tee -a "$LOG_FILE"
    exit 1
  fi
  echo "[OK] Found $path" | tee -a "$LOG_FILE"
}

run_step "Compile dataset-scene manifest generator" \
  python3 -m py_compile scripts/gnm/generate_dataset_scene_manifest.py

run_step "Regenerate dataset-scene manifest" \
  python3 scripts/gnm/generate_dataset_scene_manifest.py

run_step "Run GNM test suite" \
  python3 -m pytest tests/gnm -q

echo ""
echo "------------------------------------------------------------"
echo "[STEP] Verify evidence files"
echo "------------------------------------------------------------"

check_file "README.md"
check_file "results/bo_reviewer_packet/27_supervisor_evidence_pack.md"
check_file "results/bo_reviewer_packet/28_dataset_scene_manifest.md"
check_file "results/bo_reviewer_packet/28_dataset_scene_manifest.csv"
check_file "results/bo_reviewer_packet/28_dataset_scene_manifest.json"
check_file "scripts/gnm/isaac_live_trajectory_demo.py"
check_file "scripts/gnm/generate_dataset_scene_manifest.py"

echo ""
echo "------------------------------------------------------------"
echo "[STEP] Verify v2.0 FleetSafe-GNM Isaac ROS 2 files"
echo "------------------------------------------------------------"

check_file "docs/FLEETSAFE_GNM_IMPLEMENTATION_MANUAL.md"
check_file "configs/gnm_fleetsafe_isaac.yaml"
check_file "scripts/gnm/check_ros2_topics.sh"
check_file "scripts/gnm/collect_isaac_rosbag_episode.sh"
check_file "scripts/gnm/convert_rosbag_to_gnm_dataset.py"
check_file "scripts/gnm/train_gnm_from_collected_data.sh"
check_file "scripts/gnm/eval_gnm_vs_fleetsafe.sh"
check_file "launch/gnm_fleetsafe_isaac.launch.py"

echo "[OK] All v2.0 files present" | tee -a "$LOG_FILE"

echo ""
echo "------------------------------------------------------------"
echo "[STEP] Verify v2.1 live Isaac ROS 2 bridge files"
echo "------------------------------------------------------------"

check_file "docs/v2.1_isaac_ros2_bridge_checklist.md"
check_file "docs/yahboom_control_scene_checklist.md"
check_file "scripts/gnm/check_isaac_bridge.sh"
check_file "scripts/gnm/verify_live_topics.py"

echo "[OK] All v2.1 files present" | tee -a "$LOG_FILE"

echo ""
echo "------------------------------------------------------------"
echo "[STEP] Verify v2.2 Yahboom sim-to-real prerequisite files"
echo "------------------------------------------------------------"

check_file "docs/v2.2_yahboom_m3pro_sim_to_real_plan.md"
check_file "scripts/gnm/discover_yahboom_assets.py"
check_file "scripts/gnm/check_yahboom_topic_contract.py"

echo "[OK] All v2.2 files present" | tee -a "$LOG_FILE"

echo ""
echo "------------------------------------------------------------"
echo "[STEP] Verify v2.3 Yahboom Isaac import and gate files"
echo "------------------------------------------------------------"

check_file "docs/v2.3_yahboom_isaac_import_topic_verification.md"
check_file "docs/track_a_track_b_completion_gates.md"
check_file "scripts/gnm/yahboom_isaac_import_plan.py"
check_file "scripts/gnm/verify_yahboom_live_topics.py"

echo "[OK] All v2.3 files present" | tee -a "$LOG_FILE"

echo ""
echo "------------------------------------------------------------"
echo "[STEP] v2.0 dry-run checks (no ROS 2 or Isaac Sim required)"
echo "------------------------------------------------------------"

run_step "v2.0 ROS 2 topic checker (dry-run mode)" \
  bash scripts/gnm/check_ros2_topics.sh

run_step "v2.0 rosbag episode collector (dry-run mode)" \
  bash scripts/gnm/collect_isaac_rosbag_episode.sh reproducibility_check --dry-run

run_step "v2.0 rosbag-to-GNM converter (dry-run mode)" \
  python3 scripts/gnm/convert_rosbag_to_gnm_dataset.py \
    --rosbag-root datasets/gnm_fleetsafe_rosbags \
    --output-root datasets/gnm_fleetsafe_converted \
    --episode-name reproducibility_check \
    --dry-run

run_step "v2.0 GNM training wrapper (dry-run mode)" \
  bash scripts/gnm/train_gnm_from_collected_data.sh --dry-run

run_step "v2.0 evaluation wrapper (dry-run mode)" \
  bash scripts/gnm/eval_gnm_vs_fleetsafe.sh --dry-run

echo ""
echo "------------------------------------------------------------"
echo "[STEP] v2.1 dry-run checks (no ROS 2 or Isaac Sim required)"
echo "------------------------------------------------------------"

run_step "v2.1 Isaac bridge checker (dry-run mode)" \
  bash scripts/gnm/check_isaac_bridge.sh

run_step "v2.1 live topic verifier (dry-run mode)" \
  python3 scripts/gnm/verify_live_topics.py

echo ""
echo "------------------------------------------------------------"
echo "[STEP] v2.2 dry-run checks (no Isaac Sim or robot required)"
echo "------------------------------------------------------------"

run_step "v2.2 Yahboom asset discovery" \
  python3 scripts/gnm/discover_yahboom_assets.py

run_step "v2.2 Yahboom topic contract (dry-run mode)" \
  python3 scripts/gnm/check_yahboom_topic_contract.py

echo ""
echo "------------------------------------------------------------"
echo "[STEP] v2.3 dry-run checks (no Isaac Sim or robot required)"
echo "------------------------------------------------------------"

run_step "v2.3 Yahboom Isaac import plan (dry-run mode)" \
  python3 scripts/gnm/yahboom_isaac_import_plan.py

run_step "v2.3 Yahboom live topic gate verifier (dry-run mode)" \
  python3 scripts/gnm/verify_yahboom_live_topics.py

echo ""
echo "------------------------------------------------------------"
echo "[STEP] Verify v2.4 Yahboom first rosbag2 episode files"
echo "------------------------------------------------------------"

check_file "docs/v2.4_yahboom_first_rosbag_episode.md"
check_file "scripts/gnm/collect_yahboom_episode.sh"
check_file "scripts/gnm/validate_yahboom_episode.py"

echo "[OK] All v2.4 files present" | tee -a "$LOG_FILE"

echo ""
echo "------------------------------------------------------------"
echo "[STEP] v2.4 dry-run checks (no Isaac Sim or robot required)"
echo "------------------------------------------------------------"

run_step "v2.4 Yahboom episode collector (dry-run mode)" \
  bash scripts/gnm/collect_yahboom_episode.sh --dry-run --episode-name reproducibility_check

run_step "v2.4 Yahboom episode validator (no episode path — CI mode)" \
  python3 scripts/gnm/validate_yahboom_episode.py

echo ""
echo "------------------------------------------------------------"
echo "[STEP] Verify README release matrix markers"
echo "------------------------------------------------------------"

grep -q "GNM_VLNVERSE_RELEASE_MATRIX_START" README.md
grep -q "Research release matrix" README.md
grep -q "Public README research release matrix" README.md
grep -q "Temporal neural stop head" README.md
grep -Eq "Stable Isaac live demo|Stable Isaac live trajectory demo" README.md
grep -q "v2.0" README.md
grep -q "FleetSafe-GNM" README.md
grep -q "v2.1" README.md
grep -q "v2.2" README.md
grep -q "v2.3" README.md
grep -q "v2.4" README.md

echo "[OK] README release matrix present" | tee -a "$LOG_FILE"

echo ""
echo "------------------------------------------------------------"
echo "[STEP] Verify manifest headline counts"
echo "------------------------------------------------------------"

grep -q "Train trajectory files: 238" results/bo_reviewer_packet/28_dataset_scene_manifest.md
grep -q "Validation trajectory files: 15" results/bo_reviewer_packet/28_dataset_scene_manifest.md
grep -q "Local environment scenes detected: 4" results/bo_reviewer_packet/28_dataset_scene_manifest.md
grep -q "kujiale_0092" results/bo_reviewer_packet/28_dataset_scene_manifest.md
grep -q "kujiale_0118" results/bo_reviewer_packet/28_dataset_scene_manifest.md
grep -q "kujiale_0203" results/bo_reviewer_packet/28_dataset_scene_manifest.md
grep -q "kujiale_0271" results/bo_reviewer_packet/28_dataset_scene_manifest.md

echo "[OK] Manifest counts and scene IDs verified" | tee -a "$LOG_FILE"

echo ""
echo "------------------------------------------------------------"
echo "[STEP] Optional Isaac live demo"
echo "------------------------------------------------------------"

if [[ "$WITH_ISAAC" == "true" ]]; then
  echo "[INFO] Running Isaac live trajectory demo. Close with Ctrl+C after replay completes." | tee -a "$LOG_FILE"
  python3 scripts/gnm/isaac_live_trajectory_demo.py 2>&1 | tee -a "$LOG_FILE"
else
  echo "[SKIP] Isaac demo not run by default." | tee -a "$LOG_FILE"
  echo "[INFO] To run it: bash scripts/gnm/run_reproducibility_pack.sh --with-isaac" | tee -a "$LOG_FILE"
fi

echo ""
echo "============================================================"
echo "[SUCCESS] Reproducibility pack completed"
echo "============================================================"
echo "Log written to: $LOG_FILE"
