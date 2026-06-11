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
echo "[STEP] Verify README release matrix markers"
echo "------------------------------------------------------------"

grep -q "GNM_VLNVERSE_RELEASE_MATRIX_START" README.md
grep -q "Research release matrix" README.md
grep -q "v1.6" README.md
grep -q "Temporal neural stop head" README.md
grep -Eq "Stable Isaac live demo|Stable Isaac live trajectory demo" README.md

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
