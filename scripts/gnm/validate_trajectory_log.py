"""Validate a per-step trajectory log against the Phase 2 evidence rules.

Usage:
    python3 scripts/gnm/validate_trajectory_log.py [episode_dir]

Defaults to the newest directory under assets/experiments/trajectories/.
Exit code 0 only if every check passes.

Checks (per PHASE2_REQUIREMENTS.md and the trajectory-logging milestone):
    1. trajectory.jsonl and episode_metadata.json exist
    2. every row has all required fields
    3. sim_time is monotonically increasing
    4. non-zero motion when /cmd_vel was non-zero
    5. z stability within threshold
    6. trajectory duration consistent with the rosbag duration (tolerance)
    7. final distance plausible for the command profile
"""

import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REQUIRED_FIELDS = [
    "episode_id", "step_idx", "sim_time", "wall_time",
    "robot_position_x", "robot_position_y", "robot_position_z",
    "robot_yaw", "linear_velocity_cmd", "angular_velocity_cmd",
    "odom_linear_velocity", "odom_angular_velocity",
    "camera_frame_id", "image_timestamp",
    "policy_mode", "stop_signal", "safety_state", "notes",
]
Z_DRIFT_MAX_M = 0.02
MIN_CMD_MOTION_M = 0.10
BAG_DURATION_TOL = (0.3, 3.0)  # traj wall duration / bag duration ratio


def fail(msg):
    print(f"FAIL: {msg}")
    return False


def main():
    if len(sys.argv) > 1:
        ep_dir = Path(sys.argv[1])
    else:
        root = REPO / "assets/experiments/trajectories"
        dirs = sorted(d for d in root.iterdir() if d.is_dir())
        if not dirs:
            return fail(f"no episodes under {root}")
        ep_dir = dirs[-1]
    print(f"validating: {ep_dir}")

    jsonl = ep_dir / "trajectory.jsonl"
    meta_path = ep_dir / "episode_metadata.json"
    if not jsonl.exists():
        return fail(f"missing {jsonl}")
    if not meta_path.exists():
        return fail(f"missing {meta_path}")
    meta = json.loads(meta_path.read_text())

    rows = [json.loads(line) for line in jsonl.open()]
    if not rows:
        return fail("trajectory.jsonl is empty")
    print(f"rows: {len(rows)}")

    for i, row in enumerate(rows):
        missing = [f for f in REQUIRED_FIELDS if f not in row]
        if missing:
            return fail(f"row {i} missing fields: {missing}")

    times = [r["sim_time"] for r in rows]
    if any(b < a for a, b in zip(times, times[1:])):
        return fail("sim_time is not monotonically increasing")
    print(f"sim_time monotonic: {times[0]:.2f} -> {times[-1]:.2f}")

    dist = sum(
        math.hypot(b["robot_position_x"] - a["robot_position_x"],
                   b["robot_position_y"] - a["robot_position_y"])
        for a, b in zip(rows, rows[1:]))
    cmd_active = any(abs(r["linear_velocity_cmd"]) > 1e-3
                     or abs(r["angular_velocity_cmd"]) > 1e-3 for r in rows)
    if cmd_active and dist < MIN_CMD_MOTION_M:
        return fail(f"cmd_vel active but motion only {dist:.3f} m")
    print(f"motion: {dist:.3f} m (cmd_active={cmd_active})")

    z0 = rows[0]["robot_position_z"]
    z_drift = max(abs(r["robot_position_z"] - z0) for r in rows)
    if z_drift > Z_DRIFT_MAX_M:
        return fail(f"z drift {z_drift:.4f} m exceeds {Z_DRIFT_MAX_M} m")
    print(f"z drift: {z_drift:.6f} m")

    bag_rel = meta.get("rosbag_path")
    if bag_rel:
        bag_meta = REPO / bag_rel / "metadata.yaml"
        if not bag_meta.exists():
            return fail(f"rosbag metadata missing: {bag_meta}")
        m = re.search(r"nanoseconds:\s*(\d+)", bag_meta.read_text())
        if not m:
            return fail("cannot parse rosbag duration")
        bag_dur = int(m.group(1)) / 1e9
        traj_wall = rows[-1]["wall_time"] - rows[0]["wall_time"]
        ratio = traj_wall / bag_dur if bag_dur > 0 else 0
        if not (BAG_DURATION_TOL[0] <= ratio <= BAG_DURATION_TOL[1]):
            return fail(f"trajectory wall duration {traj_wall:.1f}s vs bag "
                        f"{bag_dur:.1f}s (ratio {ratio:.2f}) out of tolerance")
        print(f"bag duration {bag_dur:.1f}s vs trajectory wall "
              f"{traj_wall:.1f}s (ratio {ratio:.2f}) OK")
    else:
        print("no rosbag recorded for this episode (allowed)")

    sim_dur = times[-1] - times[0]
    max_cmd = max(abs(r["linear_velocity_cmd"]) for r in rows)
    if cmd_active and dist > max_cmd * sim_dur * 1.5 + 0.5:
        return fail(f"final distance {dist:.2f} m implausible for "
                    f"{max_cmd:.2f} m/s over {sim_dur:.1f} s")
    print(f"final distance plausible for {max_cmd:.2f} m/s over {sim_dur:.1f} s")

    print("PASS: all trajectory-log checks passed")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
