"""Validate the hospital-scene stop-head shadow episode set.

Usage:
    python3 scripts/gnm/validate_hospital_shadow_episodes.py [dir ...]

Defaults to the newest hospital_* episode directories (one per route
prefix). Exit 0 only if every episode passes every check. Non-firing of
the stop head is reported honestly and does not fail validation.
"""

import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BAG_TOPICS = ["/camera/image_raw", "/camera/camera_info", "/odom",
              "/tf", "/clock", "/cmd_vel"]
LIN_MAX, ANG_MAX, EPS = 0.20, 0.40, 1e-6
MAX_NET_YAW_RAD = 0.6      # straight/low-curvature guard
Z_DRIFT_MAX = 0.02
ROUTES = ["hospital_straight_short_A", "hospital_straight_medium_B",
          "hospital_low_curvature_C"]


def fail(msg):
    print(f"FAIL: {msg}")
    return False


def newest(prefix):
    root = REPO / "assets/experiments/trajectories"
    dirs = sorted(d for d in root.iterdir()
                  if d.is_dir() and d.name.startswith(prefix))
    return dirs[-1] if dirs else None


def check_episode(ep_dir):
    meta = json.loads((ep_dir / "episode_metadata.json").read_text())
    rows = [json.loads(l) for l in (ep_dir / "trajectory.jsonl").open()]
    ep = [r for r in rows if r["watchdog_state"] != "zeroed_hold"]

    if meta.get("scene_stage_path", "").find("hospital") < 0:
        return fail(f"{ep_dir.name}: not a hospital-scene episode")
    if any(r["actual_controller"] != "gnm_closed_loop" for r in rows):
        return fail(f"{ep_dir.name}: GNM not in control on every row")
    if any(not r.get("stop_head_enabled") or r["stop_head_mode"] != "shadow"
           or r["stop_authority_enabled"] for r in rows):
        return fail(f"{ep_dir.name}: stop head not shadow-only")
    if any(abs(r["gnm_action_clipped_linear_velocity"]) > LIN_MAX + EPS
           or abs(r["gnm_action_clipped_angular_velocity"]) > ANG_MAX + EPS
           for r in rows):
        return fail(f"{ep_dir.name}: clamp violation")

    yaws = [r["robot_yaw"] for r in ep]
    net_yaw = abs(math.atan2(math.sin(yaws[-1] - yaws[0]),
                             math.cos(yaws[-1] - yaws[0])))
    if net_yaw > MAX_NET_YAW_RAD:
        return fail(f"{ep_dir.name}: net yaw {net_yaw:.2f} rad exceeds "
                    "straight/low-curvature guard")
    z0 = rows[0]["robot_position_z"]
    if max(abs(r["robot_position_z"] - z0) for r in rows) > Z_DRIFT_MAX:
        return fail(f"{ep_dir.name}: z instability")

    probs = [r["stop_probability"] for r in ep
             if r.get("stop_probability") is not None]
    if not probs:
        return fail(f"{ep_dir.name}: no stop probabilities logged")
    d2g = [r["distance_to_goal_m"] for r in ep
           if r["distance_to_goal_m"] is not None]
    if not d2g or meta.get("final_distance_to_goal_m") is None:
        return fail(f"{ep_dir.name}: distance-to-goal metrics missing")

    bag_rel = meta.get("rosbag_path")
    bag_meta = REPO / bag_rel / "metadata.yaml"
    if not bag_meta.exists():
        return fail(f"{ep_dir.name}: rosbag metadata missing")
    text = bag_meta.read_text()
    for topic in BAG_TOPICS:
        m = re.search(rf"name: {re.escape(topic)}\n.*?message_count: (\d+)",
                      text, re.DOTALL)
        if not m or int(m.group(1)) == 0:
            return fail(f"{ep_dir.name}: bag missing/empty {topic}")

    fired = meta.get("stop_head_would_have_stopped_step") is not None
    fire_txt = (f"fired@step {meta['stop_head_would_have_stopped_step']} "
                f"d2g_at_signal={meta['stop_head_distance_at_stop_signal']} "
                f"overshoot_after={meta['stop_head_overshoot_after_predicted_stop_m']}"
                if fired else
                f"did not fire (max prob {max(probs):.3f}) — reported honestly")
    print(f"  {ep_dir.name}")
    print(f"    goal={meta['goal_id']} d2g start={d2g[0]:.3f} "
          f"min={min(d2g):.3f} final={meta['final_distance_to_goal_m']:.3f}")
    print(f"    net_yaw={net_yaw:.3f} rad, clamps OK, shadow-only OK, "
          f"bag topics OK")
    print(f"    stop head: {fire_txt}")
    return True


def main():
    if len(sys.argv) > 1:
        dirs = [Path(a) for a in sys.argv[1:]]
    else:
        dirs = [newest(r) for r in ROUTES]
        if any(d is None for d in dirs):
            return fail("missing one or more hospital route episodes")
    print(f"validating {len(dirs)} hospital shadow episodes:")
    if not all(check_episode(d) for d in dirs):
        return False

    status = (REPO / "docs/experiments/PROJECT_BASELINE_STATUS.md").read_text()
    lowered = status.lower()
    for banned in ("stop head improves", "fleetsafe improves",
                   "robust hospital navigation: valid",
                   "campaign complete"):
        if banned in lowered:
            return fail(f"status doc contains banned claim: {banned}")
    print("status doc claim guard OK")
    print("PASS: hospital shadow episode set validated "
          "(measurement only; no improvement claims)")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
