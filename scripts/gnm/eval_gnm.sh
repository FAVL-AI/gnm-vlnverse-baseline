#!/usr/bin/env bash
# scripts/gnm/eval_gnm.sh
# ─────────────────────────────────────────────────────────────────────────────
# Run a FleetSafe-VLN evaluation comparing pretrained vs fine-tuned GNM.
#
# Produces a comparison table:
#   Baseline pretrained GNM    (no safety filter)
#   Pretrained GNM + FleetSafe (cbf_qp)
#   Fine-tuned GNM + FleetSafe (cbf_qp)
#
# Usage:
#   bash scripts/gnm/eval_gnm.sh
#   bash scripts/gnm/eval_gnm.sh --platform isaac
#   bash scripts/gnm/eval_gnm.sh --tasks "tasks/hospital_corridor.yaml tasks/nurse_station.yaml"
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PLATFORM="mock"
TASKS=(
  tasks/hospital_corridor.yaml
  tasks/nurse_station.yaml
  tasks/dynamic_human_crossing.yaml
  tasks/blind_corner.yaml
  tasks/warehouse_aisle.yaml
)
LOGDIR="${REPO_ROOT}/runs/gnm_eval_$(date +%Y%m%d_%H%M%S)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform) PLATFORM="$2"; shift 2 ;;
    --log-dir)  LOGDIR="$2";   shift 2 ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

mkdir -p "${LOGDIR}"
source "${REPO_ROOT}/scripts/visualnav/activate_visualnav_env.sh" 2>/dev/null || \
  export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

echo "=== FleetSafe GNM Evaluation ==="
echo "  Platform: ${PLATFORM}"
echo "  Log dir:  ${LOGDIR}"
echo ""

# ── Evaluation matrix ─────────────────────────────────────────────────────────
declare -A CONFIGS=(
  ["gnm_none"]="gnm none"
  ["gnm_log_only"]="gnm log_only"
  ["gnm_cbf_qp"]="gnm cbf_qp"
  ["vint_cbf_qp"]="vint cbf_qp"
  ["nomad_cbf_qp"]="nomad cbf_qp"
)

for CONFIG_NAME in "${!CONFIGS[@]}"; do
  read -r MODEL SAFETY <<< "${CONFIGS[$CONFIG_NAME]}"
  echo "--- ${CONFIG_NAME} ---"

  for TASK in "${TASKS[@]}"; do
    TASK_ID="$(basename "${TASK}" .yaml)"
    EPISODE_DIR="${LOGDIR}/${CONFIG_NAME}/${TASK_ID}"

    python3 -m fleetsafe_vln.benchmark.episode_runner \
      --task "${TASK}" \
      --platform "${PLATFORM}" \
      --model "${MODEL}" \
      --safety "${SAFETY}" \
      --log-dir "${EPISODE_DIR}" \
      2>&1 | tail -3 || true
  done
  echo ""
done

# ── Print summary table ────────────────────────────────────────────────────────
echo "=== Summary ==="
python3 - <<PYEOF
import json, pathlib, math

logdir = pathlib.Path("${LOGDIR}")
rows = []
for metrics_path in sorted(logdir.rglob("metrics.json")):
    try:
        d = json.loads(metrics_path.read_text())
        rows.append({
            "config": metrics_path.parent.parent.name,
            "task":   d.get("task_id", ""),
            "model":  d.get("model", ""),
            "safety": d.get("safety", ""),
            "SR":     "✓" if d.get("success") else "✗",
            "SPL":    f'{d.get("spl", 0):.3f}',
            "CBF":    str(d.get("cbf_intervention_count", 0)),
            "Cert":   f'{d.get("certificate_validity_rate", 0):.3f}',
        })
    except Exception:
        pass

if not rows:
    print("No results.")
else:
    cols = ["config", "task", "SR", "SPL", "CBF", "Cert"]
    widths = {c: max(len(c), max(len(str(r[c])) for r in rows)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    print(header)
    print("  ".join("-"*widths[c] for c in cols))
    for r in rows:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))

print(f"\nFull results: ${LOGDIR}")
PYEOF
