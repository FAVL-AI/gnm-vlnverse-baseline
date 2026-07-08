"""Validate a goal-conditioned GNM closed-loop smoke episode.

Runs the full closed-loop validator first, then the goal-conditioning
checks. Usage:
    python3 scripts/gnm/validate_goal_conditioned_gnm.py [episode_dir]

Exit code 0 only if everything passes. Claim stays narrow: goal-
conditioned closed-loop smoke run, not navigation performance.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXPECTED_GOAL = "bringup_stage_goal_A"


def fail(msg):
    print(f"FAIL: {msg}")
    return False


def main():
    if len(sys.argv) > 1:
        ep_dir = Path(sys.argv[1])
    else:
        root = REPO / "assets/experiments/trajectories"
        dirs = sorted(d for d in root.iterdir()
                      if d.is_dir() and d.name.startswith("gnm_closed_loop"))
        if not dirs:
            return fail("no gnm_closed_loop episodes found")
        ep_dir = dirs[-1]

    base = subprocess.run(
        [sys.executable,
         str(REPO / "scripts/gnm/validate_gnm_closed_loop.py"), str(ep_dir)],
        capture_output=True, text=True)
    sys.stdout.write(base.stdout)
    if base.returncode != 0:
        return fail("closed-loop base validation failed")

    meta = json.loads((ep_dir / "episode_metadata.json").read_text())
    if meta.get("goal_id") != EXPECTED_GOAL:
        return fail(f"goal_id {meta.get('goal_id')} != {EXPECTED_GOAL}")
    if not meta.get("goal_scene_aligned"):
        return fail("episode goal is not scene-aligned")
    goal_img = REPO / meta["goal_image"]
    if not goal_img.exists():
        return fail(f"goal image missing: {goal_img}")
    print(f"goal-conditioned: goal_id={meta['goal_id']} "
          f"(scene-aligned, image present)")

    gval = subprocess.run(
        [sys.executable, str(REPO / "scripts/gnm/validate_scene_goal.py"),
         EXPECTED_GOAL], capture_output=True, text=True)
    if gval.returncode != 0:
        sys.stdout.write(gval.stdout)
        return fail("scene-goal validation failed for the episode's goal")
    print("scene-goal validation passed (checksum, provenance, loadability)")

    rows = [json.loads(l) for l in (ep_dir / "trajectory.jsonl").open()]
    d2g = [r["distance_to_goal_m"] for r in rows
           if r.get("distance_to_goal_m") is not None]
    if not d2g:
        return fail("no distance_to_goal_m telemetry on rows")
    final = meta.get("final_distance_to_goal_m")
    if final is None:
        return fail("final_distance_to_goal_m not computed")
    print(f"distance-to-goal telemetry: start={d2g[0]:.3f} m, "
          f"min={min(d2g):.3f} m, final={final:.3f} m over {len(d2g)} rows")

    status = (REPO / "docs/experiments/PROJECT_BASELINE_STATUS.md").read_text()
    for banned in ("SPL/SR: valid", "robust navigation: valid",
                   "six-run campaign: valid"):
        if banned.lower() in status.lower():
            return fail(f"status doc contains banned claim: {banned}")
    if "Still not valid" not in status and "not valid" not in status:
        return fail("status doc lost its not-valid guard section")
    print("status doc keeps SPL/SR, robust navigation and campaign "
          "claims not-valid")

    print("PASS: goal-conditioned closed-loop smoke validated "
          "(narrow claim only)")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
