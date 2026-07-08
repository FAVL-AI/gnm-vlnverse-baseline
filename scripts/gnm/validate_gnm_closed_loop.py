"""Validate a GNM closed-loop smoke episode.

Usage:
    python3 scripts/gnm/validate_gnm_closed_loop.py [episode_dir]

Defaults to the newest gnm_closed_loop_* directory under
assets/experiments/trajectories/. Exit code 0 only if every check passes.

This validates CONTROL AUTHORITY only — bounded, clamped, watchdog-
protected command flow — not navigation quality.
"""

import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CL_FIELDS = [
    "gnm_control_enabled", "gnm_action_raw_linear_velocity",
    "gnm_action_raw_angular_velocity", "gnm_action_clipped_linear_velocity",
    "gnm_action_clipped_angular_velocity", "action_clipped",
    "watchdog_state", "emergency_stop_triggered", "stop_reason",
    "actual_controller",
]
LIN_MAX, ANG_MAX, EPS = 0.20, 0.40, 1e-6
XY_BOUND = 6.0
Z_DRIFT_MAX = 0.02
MIN_MOTION_M = 0.05
HOLD_ROWS_MIN = 60
BAG_TOPICS = ["/camera/image_raw", "/camera/camera_info", "/odom",
              "/tf", "/clock", "/cmd_vel"]
BAG_DURATION_TOL = (0.3, 3.0)


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
    print(f"validating closed-loop episode: {ep_dir}")

    jsonl = ep_dir / "trajectory.jsonl"
    meta_path = ep_dir / "episode_metadata.json"
    if not jsonl.exists() or not meta_path.exists():
        return fail("trajectory.jsonl or episode_metadata.json missing")
    meta = json.loads(meta_path.read_text())
    rows = [json.loads(l) for l in jsonl.open()]
    if not rows:
        return fail("empty trajectory")

    for i, r in enumerate(rows):
        missing = [f for f in CL_FIELDS if f not in r]
        if missing:
            return fail(f"row {i} missing fields: {missing}")
    print(f"rows: {len(rows)}; all closed-loop fields present")

    if meta.get("shadow_gnm_inference_attempts", 0) <= 0:
        return fail("no GNM inference attempts")
    if meta.get("shadow_gnm_mean_latency_ms") is None:
        return fail("no latency recorded")
    print(f"inference attempts={meta['shadow_gnm_inference_attempts']} "
          f"successes={meta['shadow_gnm_inference_successes']} "
          f"mean_lat={meta['shadow_gnm_mean_latency_ms']}ms")

    bad_ctrl = [r for r in rows if r["actual_controller"] != "gnm_closed_loop"]
    if bad_ctrl:
        return fail(f"{len(bad_ctrl)} rows without gnm_closed_loop controller")
    print("actual_controller=gnm_closed_loop on every row")

    applied = [r for r in rows
               if abs(r["gnm_action_clipped_linear_velocity"]) > EPS
               or abs(r["gnm_action_clipped_angular_velocity"]) > EPS]
    if not applied and not meta.get("cl_emergency_stop"):
        return fail("GNM never applied a non-zero command and no e-stop")
    over = [r for r in rows
            if abs(r["gnm_action_clipped_linear_velocity"]) > LIN_MAX + EPS
            or abs(r["gnm_action_clipped_angular_velocity"]) > ANG_MAX + EPS]
    if over:
        return fail(f"{len(over)} applied commands exceed velocity limits")
    print(f"applied non-zero commands: {len(applied)}; all within "
          f"|v|<={LIN_MAX}, |w|<={ANG_MAX}")

    if any("watchdog_state" not in r or r["watchdog_state"] in (None, "")
           for r in rows):
        return fail("watchdog_state missing on some rows")
    print(f"watchdog recorded (final state: {rows[-1]['watchdog_state']})")

    tail = rows[-HOLD_ROWS_MIN:]
    if any(abs(r["gnm_action_clipped_linear_velocity"]) > EPS
           or abs(r["gnm_action_clipped_angular_velocity"]) > EPS
           for r in tail):
        return fail("no explicit zero command hold at episode end")
    hold_disp = meta.get("cl_zero_hold_displacement_m")
    if hold_disp is None or hold_disp > 0.05:
        return fail(f"zero-hold displacement {hold_disp} not verified <5cm")
    print(f"explicit zeroing verified: last {HOLD_ROWS_MIN}+ rows zero, "
          f"hold displacement {hold_disp} m")

    z0 = rows[0]["robot_position_z"]
    z_drift = max(abs(r["robot_position_z"] - z0) for r in rows)
    if z_drift > Z_DRIFT_MAX:
        return fail(f"z drift {z_drift:.4f} exceeds {Z_DRIFT_MAX}")
    out_xy = [r for r in rows if abs(r["robot_position_x"]) > XY_BOUND
              or abs(r["robot_position_y"]) > XY_BOUND]
    if out_xy:
        return fail(f"{len(out_xy)} rows outside XY bounds ±{XY_BOUND} m")
    print(f"stable: z drift {z_drift:.6f} m, inside XY bounds")

    dist = sum(math.hypot(b["robot_position_x"] - a["robot_position_x"],
                          b["robot_position_y"] - a["robot_position_y"])
               for a, b in zip(rows, rows[1:]))
    if dist < MIN_MOTION_M and not meta.get("cl_emergency_stop"):
        return fail(f"motion {dist:.3f} m too small without e-stop")
    print(f"motion under GNM control: {dist:.3f} m "
          f"(e-stop={meta.get('cl_emergency_stop')}, "
          f"reason={meta.get('cl_stop_reason')})")

    bag_rel = meta.get("rosbag_path")
    if not bag_rel:
        return fail("no rosbag recorded")
    bag_meta = REPO / bag_rel / "metadata.yaml"
    if not bag_meta.exists():
        return fail(f"rosbag metadata missing: {bag_meta}")
    text = bag_meta.read_text()
    for topic in BAG_TOPICS:
        m = re.search(
            rf"name: {re.escape(topic)}\n.*?message_count: (\d+)",
            text, re.DOTALL)
        if not m or int(m.group(1)) == 0:
            return fail(f"bag missing/empty topic {topic}")
    print(f"bag contains all {len(BAG_TOPICS)} topics with non-zero counts")

    m = re.search(r"nanoseconds:\s*(\d+)", text)
    bag_dur = int(m.group(1)) / 1e9 if m else 0
    traj_wall = rows[-1]["wall_time"] - rows[0]["wall_time"]
    ratio = traj_wall / bag_dur if bag_dur > 0 else 0
    if not (BAG_DURATION_TOL[0] <= ratio <= BAG_DURATION_TOL[1]):
        return fail(f"trajectory wall {traj_wall:.1f}s vs bag {bag_dur:.1f}s "
                    f"(ratio {ratio:.2f}) out of tolerance")
    print(f"bag {bag_dur:.1f}s vs trajectory wall {traj_wall:.1f}s "
          f"(ratio {ratio:.2f}) OK")

    print("PASS: all closed-loop checks passed "
          "(control authority only, not navigation quality)")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
