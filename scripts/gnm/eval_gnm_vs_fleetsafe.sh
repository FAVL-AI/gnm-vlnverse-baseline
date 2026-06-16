#!/usr/bin/env bash
# Evaluate GNM-only vs GNM-plus-FleetSafe.
# Usage: bash eval_gnm_vs_fleetsafe.sh [--dry-run]
#
# Writes results to results/gnm_fleetsafe_v2/ as CSV and Markdown.
# In dry-run mode, writes placeholder results with clear annotations.

set -euo pipefail

DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
RESULTS_DIR="$ROOT/results/gnm_fleetsafe_v2"
CSV_OUT="$RESULTS_DIR/eval_results.csv"
MD_OUT="$RESULTS_DIR/eval_summary.md"

echo "============================================================"
echo " FleetSafe-GNM Evaluation: GNM-only vs GNM+FleetSafe"
echo "============================================================"
echo "Results dir : $RESULTS_DIR"
echo "CSV output  : $CSV_OUT"
echo "MD output   : $MD_OUT"
echo "Dry-run     : $DRY_RUN"
echo "============================================================"

mkdir -p "$RESULTS_DIR"

TIMESTAMP="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

METRICS=(
  "success_rate"
  "path_efficiency"
  "navigation_error"
  "collision_rate"
  "min_clearance"
  "intervention_count"
  "intervention_magnitude"
  "certificate_validity_rate"
)

UNITS=(
  "fraction"
  "fraction"
  "metres"
  "fraction"
  "metres"
  "count"
  "m/s"
  "fraction"
)

if $DRY_RUN; then
  GNM_ONLY_VALS=("0.00" "0.00" "0.00" "0.00" "0.00" "0" "0.00" "N/A")
  GNM_FLEETSAFE_VALS=("0.00" "0.00" "0.00" "0.00" "0.00" "0" "0.00" "N/A")
  DRY_NOTE="[DRY-RUN: placeholder values — no live evaluation has been run]"
else
  GNM_ONLY_VALS=("0.00" "0.00" "0.00" "0.00" "0.00" "0" "0.00" "N/A")
  GNM_FLEETSAFE_VALS=("0.00" "0.00" "0.00" "0.00" "0.00" "0" "0.00" "N/A")
  DRY_NOTE="[Values pending live evaluation — run Isaac Sim episodes first]"
fi

# Write CSV.
{
  echo "metric,unit,gnm_only,gnm_plus_fleetsafe,evaluated_at,note"
  for i in "${!METRICS[@]}"; do
    echo "${METRICS[$i]},${UNITS[$i]},${GNM_ONLY_VALS[$i]},${GNM_FLEETSAFE_VALS[$i]},$TIMESTAMP,\"$DRY_NOTE\""
  done
} > "$CSV_OUT"

echo "[OK] CSV written: $CSV_OUT"

# Write Markdown summary.
{
  echo "# FleetSafe-GNM Evaluation Summary"
  echo ""
  echo "Evaluated at: $TIMESTAMP"
  echo ""
  if $DRY_RUN; then
    echo "> **Dry-run mode.** Numbers below are placeholders."
    echo "> Run live Isaac Sim episodes and re-run without --dry-run for real results."
  else
    echo "> Values pending live evaluation. Run Isaac Sim episodes first."
  fi
  echo ""
  echo "| Metric | Unit | GNM-only | GNM + FleetSafe |"
  echo "|---|---|---:|---:|"
  for i in "${!METRICS[@]}"; do
    echo "| ${METRICS[$i]} | ${UNITS[$i]} | ${GNM_ONLY_VALS[$i]} | ${GNM_FLEETSAFE_VALS[$i]} |"
  done
  echo ""
  echo "## Metric definitions"
  echo ""
  echo "- **success_rate**: fraction of episodes where the robot reached the goal"
  echo "  within the distance threshold."
  echo "- **path_efficiency**: ratio of shortest-path distance to actual distance"
  echo "  travelled. 1.0 is optimal."
  echo "- **navigation_error**: mean final distance to goal across all episodes."
  echo "- **collision_rate**: fraction of episodes with at least one collision."
  echo "- **min_clearance**: minimum obstacle clearance in metres across all steps."
  echo "- **intervention_count**: number of steps where FleetSafe overrode GNM."
  echo "  Zero for GNM-only (no FleetSafe active)."
  echo "- **intervention_magnitude**: mean speed change applied by FleetSafe when"
  echo "  overriding. Zero for GNM-only."
  echo "- **certificate_validity_rate**: fraction of steps where the CBF safety"
  echo "  certificate held. N/A for GNM-only."
  echo ""
  echo "## Next steps"
  echo ""
  echo "1. Collect Isaac Sim episodes: \`bash scripts/gnm/collect_isaac_rosbag_episode.sh\`"
  echo "2. Convert episodes: \`python3 scripts/gnm/convert_rosbag_to_gnm_dataset.py ...\`"
  echo "3. Fine-tune GNM: \`bash scripts/gnm/train_gnm_from_collected_data.sh\`"
  echo "4. Re-run evaluation without --dry-run."
} > "$MD_OUT"

echo "[OK] Markdown summary written: $MD_OUT"
echo ""

if $DRY_RUN; then
  echo "[DRY-RUN] No live evaluation was performed."
  echo "[DRY-RUN] All metric values are placeholders."
fi

echo ""
echo "============================================================"
echo "[OK] Evaluation wrapper complete."
echo "============================================================"
