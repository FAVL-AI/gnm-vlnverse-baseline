"""
generate_hospital_usd.py
========================
Generate fleet_safe_vla/envs/isaaclab/hospital/assets/hospital_world.usd
by loading the procedural hospital scene inside Isaac Sim and exporting the
stage to USD.  This creates a local USD file so future runs can load it
without rebuilding geometry.

Usage:
  conda activate isaac
  python scripts/isaaclab/generate_hospital_usd.py [--output PATH]

The --output flag is optional; the default path is determined relative to
the repo root so the existing run_hospital.sh loader finds it automatically.

Once generated, run:
  ./scripts/isaaclab/run_hospital.sh --capture
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ── Repo root ─────────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT  = _SCRIPT_DIR.parent.parent

_DEFAULT_OUTPUT = (
    _REPO_ROOT
    / "fleet_safe_vla"
    / "envs"
    / "isaaclab"
    / "hospital"
    / "assets"
    / "hospital_world.usd"
)

# ── Argument parsing (before AppLauncher so --help works without Isaac) ───────

parser = argparse.ArgumentParser(
    description="Generate hospital_world.usd from the procedural scene."
)
parser.add_argument(
    "--output",
    type=Path,
    default=_DEFAULT_OUTPUT,
    help="Destination .usd file (default: %(default)s)",
)
args, remaining = parser.parse_known_args()

output_path: Path = args.output.resolve()
output_path.parent.mkdir(parents=True, exist_ok=True)

# ── AppLauncher (headless) ────────────────────────────────────────────────────
# Must happen before any omni.* imports.

from isaaclab.app import AppLauncher  # noqa: E402

launcher_args = argparse.Namespace(headless=True, enable_cameras=False)
app_launcher  = AppLauncher(launcher_args)
simulation_app = app_launcher.app

# ── Isaac / omni imports ──────────────────────────────────────────────────────

import omni.usd                          # noqa: E402
from isaaclab.sim import SimulationContext  # noqa: E402

sys.path.insert(0, str(_REPO_ROOT))

from fleet_safe_vla.envs.isaaclab.hospital.hospital_world_loader import (  # noqa: E402
    HospitalWorldLoader,
)

# ── Build scene ───────────────────────────────────────────────────────────────

print(f"\n[generate_hospital_usd] Repo root  : {_REPO_ROOT}")
print(f"[generate_hospital_usd] Output path: {output_path}")
print("[generate_hospital_usd] Building procedural scene ...")

sim = SimulationContext()

loader = HospitalWorldLoader(verbose=True, nucleus_ok=False)
loader.build_procedural_scene()

# Run 5 frames to let physics settle
sim.reset()
for _ in range(5):
    sim.step()

# ── Export stage to USD ───────────────────────────────────────────────────────

print("[generate_hospital_usd] Exporting stage to USD ...")

stage = omni.usd.get_context().get_stage()
stage.Export(str(output_path))

# ── Verify ────────────────────────────────────────────────────────────────────

if not output_path.exists():
    print(f"[generate_hospital_usd] ERROR: export did not produce file at {output_path}", file=sys.stderr)
    simulation_app.close()
    sys.exit(1)

file_size = output_path.stat().st_size
if file_size < 1000:
    print(
        f"[generate_hospital_usd] WARNING: file is suspiciously small ({file_size} bytes) — "
        "the export may have failed silently.",
        file=sys.stderr,
    )
else:
    print(f"[generate_hospital_usd] Saved: {output_path}  ({file_size:,} bytes)")

# ── Done ──────────────────────────────────────────────────────────────────────

print("\n[generate_hospital_usd] Next run:")
print("  ./scripts/isaaclab/run_hospital.sh --capture")
print()

simulation_app.close()
