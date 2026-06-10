#!/usr/bin/env bash
# scripts/capture_vlnverse_evidence.sh
# ─────────────────────────────────────────────────────────────────────────────
# Capture VLNVerse-style evidence from a completed demo run.
#
# Reads metrics.json and safety_certificates.jsonl from each config sub-dir,
# writes a combined evidence bundle to runs/vlnverse_evidence/.
#
# Usage:
#   bash scripts/capture_vlnverse_evidence.sh --run-dir runs/vlnverse_demo_<ts>
#   bash scripts/capture_vlnverse_evidence.sh              # latest vlnverse run
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir) RUN_DIR="$2"; shift 2 ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

# Auto-detect latest vlnverse_demo run
if [[ -z "${RUN_DIR}" ]]; then
  RUN_DIR=$(ls -dt "${REPO_ROOT}/runs/vlnverse_demo_"* 2>/dev/null | head -1 || true)
  if [[ -z "${RUN_DIR}" ]]; then
    echo "[ERROR] No vlnverse_demo_* run found in runs/. Pass --run-dir."
    exit 1
  fi
  echo "  Auto-detected run dir: ${RUN_DIR}"
fi

EVIDENCE_DIR="${REPO_ROOT}/runs/vlnverse_evidence/$(basename "${RUN_DIR}")"
mkdir -p "${EVIDENCE_DIR}"

source "${REPO_ROOT}/scripts/visualnav/activate_visualnav_env.sh" 2>/dev/null || \
  export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

echo "========================================"
echo "  FleetSafe VLNVerse Evidence Capture"
echo "========================================"
echo "  Source:   ${RUN_DIR}"
echo "  Output:   ${EVIDENCE_DIR}"
echo ""

python3 - <<PYEOF
import sys, json, shutil
from pathlib import Path
from datetime import datetime, timezone

src = Path("${RUN_DIR}")
out = Path("${EVIDENCE_DIR}")
out.mkdir(parents=True, exist_ok=True)

configs = ["none", "log_only", "cbf_qp"]
labels  = {"none": "baseline", "log_only": "log_only", "cbf_qp": "fleetsafe_cbf"}
bundle  = {
    "captured_at": datetime.now(timezone.utc).isoformat(),
    "source_run_dir": str(src),
    "configs": {},
}

print("  Collecting artifacts...")
for cfg in configs:
    ep_dir = src / cfg
    label  = labels[cfg]
    entry  = {"config": cfg, "label": label, "artifacts": {}}

    # metrics.json
    mf = ep_dir / "metrics.json"
    if mf.exists():
        data = json.loads(mf.read_text())
        entry["metrics"] = data
        dest = out / f"metrics_{label}.json"
        shutil.copy2(mf, dest)
        entry["artifacts"]["metrics"] = str(dest)
        print(f"    ✓ metrics      {label}")

    # safety_certificates.jsonl
    cf = ep_dir / "safety_certificates.jsonl"
    if cf.exists():
        certs = [json.loads(ln) for ln in cf.read_text().splitlines() if ln.strip()]
        entry["certificate_count"] = len(certs)
        dest = out / f"certs_{label}.jsonl"
        shutil.copy2(cf, dest)
        entry["artifacts"]["certificates"] = str(dest)
        print(f"    ✓ certificates {label} ({len(certs)} entries)")

    # trajectory if present
    tf = ep_dir / "trajectory.json"
    if tf.exists():
        dest = out / f"trajectory_{label}.json"
        shutil.copy2(tf, dest)
        entry["artifacts"]["trajectory"] = str(dest)
        print(f"    ✓ trajectory   {label}")

    bundle["configs"][label] = entry

# Write evidence bundle
bundle_path = out / "evidence_bundle.json"
bundle_path.write_text(json.dumps(bundle, indent=2))
print(f"\n  Evidence bundle: {bundle_path}")

# Print comparison table
print("\n  ┌─────────────────┬─────────┬───────┬────────┬─────────┐")
print(  "  │ config          │ success │   spl │   cert │ cbf_int │")
print(  "  ├─────────────────┼─────────┼───────┼────────┼─────────┤")
for cfg in configs:
    label = labels[cfg]
    entry = bundle["configs"].get(label, {})
    m = entry.get("metrics", {})
    success = "✓" if m.get("success") else "✗"
    spl     = f"{m.get('spl', 0):.3f}"
    cert    = f"{m.get('certificate_validity_rate', 0):.3f}"
    cbf     = str(m.get("cbf_intervention_count", "—"))
    print(f"  │ {label:15s} │ {success:^7s} │ {spl:>5s} │ {cert:>6s} │ {cbf:>7s} │")
print(  "  └─────────────────┴─────────┴───────┴────────┴─────────┘")
PYEOF

echo ""
echo "Evidence written to: ${EVIDENCE_DIR}"
echo ""
echo "To view in dashboard:"
echo "  cd command-center && docker compose up -d"
echo "  open http://localhost:3000/replay"
