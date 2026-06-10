#!/usr/bin/env python3
"""
gen_proof_run.py — Create a hospital benchmark proof run without Isaac Sim.

Detects the hospital_world.usd asset, generates a procedural matplotlib
preview, writes all status files, and updates the latest/ symlink.
Run this whenever you want the dashboard to reflect the current asset state
without re-running Isaac Sim.

Usage:
    python scripts/isaaclab/gen_proof_run.py [--scene NAME] [--scenario NAME]
    python scripts/isaaclab/gen_proof_run.py --scenario crossing
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.isaaclab.hospital_capture_utils import (  # noqa: E402
    SCENARIO_AGENT_COUNTS,
    SCENARIO_WAYPOINTS,
    update_latest_symlink,
    write_capture_status,
    write_photoreal_status,
    write_procedural_preview,
    write_viewport_status,
)

USD_ASSET = (
    REPO_ROOT
    / "fleet_safe_vla"
    / "envs"
    / "isaaclab"
    / "hospital"
    / "assets"
    / "hospital_world.usd"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scene",    default="hospital_corridor")
    parser.add_argument("--scenario", default="crossing", choices=list(SCENARIO_WAYPOINTS))
    parser.add_argument("--log-dir",  default=str(REPO_ROOT / "logs" / "hospital_benchmark"))
    parser.add_argument("--isaac-version", default="0.54.3")
    args = parser.parse_args()

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_dir = Path(args.log_dir) / run_ts
    log_dir.mkdir(parents=True, exist_ok=True)

    usd_found = USD_ASSET.exists() and USD_ASSET.stat().st_size > 1000
    usd_size_kb = round(USD_ASSET.stat().st_size / 1024, 1) if usd_found else 0

    print(f"\n[gen_proof_run] Run dir  : {log_dir}")
    print(f"[gen_proof_run] Scene    : {args.scene}")
    print(f"[gen_proof_run] Scenario : {args.scenario}")
    print(f"[gen_proof_run] USD asset: {'FOUND (' + str(usd_size_kb) + ' KB)' if usd_found else 'MISSING'}")
    print(f"[gen_proof_run] USD path : {USD_ASSET}")

    # ── Session metadata ──────────────────────────────────────────────────────
    session_meta = {
        "timestamp":     run_ts,
        "scene":         args.scene,
        "scenario":      args.scenario,
        "agent_count":   SCENARIO_AGENT_COUNTS.get(args.scenario, 0),
        "degradation":   {},
        "steps_target":  0,
        "headless":      True,
        "capture":       True,
        "usd_available": usd_found,
        "usd_path":      str(USD_ASSET) if usd_found else None,
        "isaac_version": args.isaac_version,
        "method":        "gen_proof_run (no Isaac Sim)",
        "repo":          str(REPO_ROOT),
    }
    (log_dir / "session.json").write_text(json.dumps(session_meta, indent=2))

    # Empty per-run files so the API doesn't 500
    for fname in ("trajectory.csv", "safety_events.jsonl", "social_metrics.jsonl"):
        p = log_dir / fname
        if not p.exists():
            p.write_text("")
    (log_dir / "sensor_faults.json").write_text(json.dumps({}, indent=2))

    # ── Procedural preview (matplotlib, no GPU) ───────────────────────────────
    print("\n[gen_proof_run] Generating procedural preview...")
    preview_path = write_procedural_preview(
        log_dir,
        scene=args.scene,
        scenario=args.scenario,
        isaac_version=args.isaac_version,
        usd_available=usd_found,
        isaac_runtime="NOT_RUN",
    )
    procedural_status = "RECORDED" if (preview_path and preview_path.exists()) else "MISSING"
    if preview_path:
        print(f"[gen_proof_run] Preview  : {preview_path} ({preview_path.stat().st_size} bytes)")
    else:
        print("[gen_proof_run] WARNING: procedural preview failed (matplotlib missing?)")

    # ── Determine render status ───────────────────────────────────────────────
    # No Isaac Sim → no viewport screenshot, so status is PROCEDURAL at best.
    # If USD is found, we know the asset is present and ready for photoreal.
    render_status = "PROCEDURAL" if procedural_status == "RECORDED" else "MISSING"

    screenshot_path: Path | None = None  # no Isaac Sim, no viewport capture
    # Use the procedural preview as the display image
    display_path = str(preview_path) if preview_path else None

    # ── Write status files ────────────────────────────────────────────────────
    write_viewport_status(log_dir, render_status)

    write_capture_status(
        log_dir,
        scene=args.scene,
        scenario=args.scenario,
        isaac_runtime="NOT_RUN",          # Isaac Sim not launched
        usd_asset="FOUND" if usd_found else "MISSING",
        screenshot="MISSING",             # no viewport capture
        procedural_preview=procedural_status,
        method="gen_proof_run",
        timestamp=run_ts,
        isaac_version=args.isaac_version,
    )

    write_photoreal_status(
        log_dir,
        render_status=render_status,
        usd_loaded=usd_found,
        usd_path=str(USD_ASSET) if usd_found else None,
        screenshot_path=display_path,
        method="gen_proof_run_matplotlib",
        scene=args.scene,
        scenario=args.scenario,
        timestamp=run_ts,
        isaac_version=args.isaac_version,
    )

    # ── Update latest symlink ─────────────────────────────────────────────────
    update_latest_symlink(log_dir)
    latest = log_dir.parent / "latest"
    print(f"\n[gen_proof_run] Latest → {latest} → {log_dir.name}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "─" * 60)
    print("STATUS SUMMARY")
    print("─" * 60)
    print(f"  usd_asset        : {'FOUND (' + str(usd_size_kb) + ' KB)' if usd_found else 'MISSING'}")
    print(f"  usd_path         : {USD_ASSET}")
    print(f"  procedural_preview: {procedural_status}")
    print(f"  screenshot        : MISSING (Isaac Sim not launched)")
    print(f"  render_status     : {render_status}")
    print(f"  usd_loaded        : {usd_found}")
    print("─" * 60)
    if usd_found:
        print("\nNEXT STEP to reach PROVEN status:")
        print("  conda activate isaac")
        print("  ./scripts/isaaclab/run_hospital.sh --capture --steps 50")
        print("  → This will run Isaac Sim, load the USD, capture screenshot.png")
        print("  → render_status will become PROVEN")
    else:
        print("\nNEXT STEP to generate the USD:")
        print("  conda activate isaac")
        print("  ./scripts/isaaclab/generate_hospital_usd.sh")
    print("─" * 60 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
