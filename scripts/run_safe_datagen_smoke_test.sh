#!/usr/bin/env bash
# FleetSafe-DataForge smoke test.
# Generates safe trajectories + instructions + exports for hospital_corridor.
# No Isaac, rendering, or VLNTube required.
# Exit 0 = passed. Exit 1 = failure.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

OUTDIR="$ROOT/data/datagen_smoke_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTDIR"

echo "=== FleetSafe-DataForge Smoke Test ==="
echo "Root:   $ROOT"
echo "Output: $OUTDIR"
echo ""

python - <<PYEOF
import sys
import json
from pathlib import Path

out = Path("$OUTDIR")

# ── 1. Scene graph ────────────────────────────────────────────────────────────
print("[1/5] Building scene graph...")
from fleetsafe_vln.datagen.scene_graph_plus import build_from_task
graph = build_from_task("hospital_corridor", "hospital_corridor")
graph.save(out / "scene_graph.json")
print(f"      nodes={len(graph.nodes)}  edges={len(graph.edges)}")

# ── 2. Safe trajectory generation ─────────────────────────────────────────────
print("[2/5] Generating safe trajectories...")
from fleetsafe_vln.datagen.safe_trajectory_generator import SafeTrajectoryGenerator
gen = SafeTrajectoryGenerator(seed=42)
obstacles = [(2.0, 0.8, 0.3), (4.5, -0.5, 0.3)]
trajs = []
for i, (start, goal) in enumerate([
    ((0.0, 0.0), (8.5, -1.2)),
    ((-3.0, 2.0), (4.0, -0.5)),
]):
    t = gen.generate(
        scene="hospital_corridor",
        start_xy=start,
        goal_xy=goal,
        obstacles=obstacles,
    )
    trajs.append(t)
    print(f"      traj {i}: success={t.success}  steps={len(t.steps)}  path={t.path_length_m:.2f}m")

# ── 3. Instruction generation ──────────────────────────────────────────────────
print("[3/5] Generating instructions...")
from fleetsafe_vln.datagen.instruction_generator import InstructionGenerator
ig = InstructionGenerator(seed=42)
instructions = ig.generate("nurse_station", n_fine=3, n_coarse=2, n_constrained=2)
for instr in instructions:
    print(f"      > {instr}")

# ── 4. Build episode records ───────────────────────────────────────────────────
print("[4/5] Building episode records...")
episodes = []
for i, t in enumerate(trajs):
    ep = {
        "trajectory_id": t.trajectory_id,
        "scene": t.scene,
        "success": t.success,
        "instructions": instructions,
        "trajectory": t.to_dict(),
        "safety_certificates": t.safety_certificates,
    }
    episodes.append(ep)

# ── 5. Export ──────────────────────────────────────────────────────────────────
print("[5/5] Exporting dataset...")
from fleetsafe_vln.datagen.dataset_exporters import DatasetExporter
exporter = DatasetExporter(out / "exports")
jsonl_path = exporter.export_fleetsafe_jsonl(episodes, "hospital_episodes.jsonl")
r2r_path = exporter.export_vln_r2r(episodes, split="smoke_test")

# Verify outputs
assert jsonl_path.exists(), f"Missing: {jsonl_path}"
assert r2r_path.exists(), f"Missing: {r2r_path}"

print()
print(f"Outputs in {out}:")
for p in sorted(out.rglob("*")):
    if p.is_file():
        print(f"  {p.relative_to(out)}")

print()
print("✅ DataForge smoke test passed.")
PYEOF

STATUS=$?
if [ "$STATUS" -ne 0 ]; then
    echo "❌ DataForge smoke test failed."
    exit 1
fi
