"""Validate a shadow-mode GNM episode log.

Usage:
    python3 scripts/gnm/validate_shadow_gnm.py [episode_dir]

Defaults to the newest directory under assets/experiments/trajectories/.
Exit code 0 only if every check passes.

Checks:
    1. trajectory + metadata files exist (base validator's domain is
       re-run implicitly for motion/z-stability here where needed)
    2. required shadow fields exist on rows
    3. at least MIN_FRAMES image frames were received
    4. at least MIN_ATTEMPTS inference attempts occurred
    5. at least one candidate action is non-null
    6. latency is recorded (mean/max in metadata)
    7. actual /cmd_vel came from the scripted/manual controller on every
       row (actual_controller never 'gnm'; candidate values are logged in
       shadow fields only)
    8. robot remained stable (z drift within threshold)
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SHADOW_ROW_FIELDS = [
    "shadow_gnm_enabled", "shadow_gnm_status", "shadow_gnm_model_path",
    "shadow_gnm_latency_ms", "shadow_gnm_candidate_linear_velocity",
    "shadow_gnm_candidate_angular_velocity", "shadow_gnm_error",
    "actual_controller", "actual_linear_velocity_cmd",
    "actual_angular_velocity_cmd",
]
MIN_FRAMES = 100
MIN_ATTEMPTS = 50
Z_DRIFT_MAX_M = 0.02
ALLOWED_CONTROLLERS = {"scripted_cmd_vel", "manual_cmd_vel"}


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
    print(f"validating shadow episode: {ep_dir}")

    jsonl = ep_dir / "trajectory.jsonl"
    meta_path = ep_dir / "episode_metadata.json"
    if not jsonl.exists() or not meta_path.exists():
        return fail("trajectory.jsonl or episode_metadata.json missing")
    meta = json.loads(meta_path.read_text())
    rows = [json.loads(l) for l in jsonl.open()]
    if not rows:
        return fail("empty trajectory")

    shadow_rows = [r for r in rows if r.get("shadow_gnm_enabled")]
    if not shadow_rows:
        return fail("no rows with shadow_gnm_enabled=true")
    for i, r in enumerate(shadow_rows):
        missing = [f for f in SHADOW_ROW_FIELDS if f not in r]
        if missing:
            return fail(f"shadow row {i} missing fields: {missing}")
    print(f"shadow rows: {len(shadow_rows)}/{len(rows)}; all fields present")

    frames = meta.get("shadow_gnm_frames_received", 0)
    attempts = meta.get("shadow_gnm_inference_attempts", 0)
    successes = meta.get("shadow_gnm_inference_successes", 0)
    if frames < MIN_FRAMES:
        return fail(f"only {frames} image frames received (< {MIN_FRAMES})")
    if attempts < MIN_ATTEMPTS:
        return fail(f"only {attempts} inference attempts (< {MIN_ATTEMPTS})")
    print(f"frames={frames} attempts={attempts} successes={successes} "
          f"failures={meta.get('shadow_gnm_inference_failures')}")

    candidates = [r for r in shadow_rows
                  if r.get("shadow_gnm_candidate_linear_velocity") is not None]
    if not candidates:
        return fail("no non-null candidate actions logged")
    ex = candidates[len(candidates) // 2]
    print(f"non-null candidates: {len(candidates)}; example: "
          f"lin={ex['shadow_gnm_candidate_linear_velocity']} "
          f"ang={ex['shadow_gnm_candidate_angular_velocity']} "
          f"wp=({ex.get('shadow_gnm_candidate_waypoint_x')},"
          f"{ex.get('shadow_gnm_candidate_waypoint_y')}) "
          f"goal_dist={ex.get('shadow_gnm_goal_distance')}")

    if meta.get("shadow_gnm_mean_latency_ms") is None:
        return fail("no latency recorded")
    print(f"latency mean={meta['shadow_gnm_mean_latency_ms']}ms "
          f"max={meta['shadow_gnm_max_latency_ms']}ms")

    bad = [r for r in shadow_rows
           if r["actual_controller"] not in ALLOWED_CONTROLLERS]
    if bad:
        return fail(f"{len(bad)} rows with actual_controller outside "
                    f"{ALLOWED_CONTROLLERS} — GNM must not drive yet")
    print("actual_controller scripted/manual on every row; "
          "GNM never published /cmd_vel")

    z0 = rows[0]["robot_position_z"]
    z_drift = max(abs(r["robot_position_z"] - z0) for r in rows)
    if z_drift > Z_DRIFT_MAX_M:
        return fail(f"z drift {z_drift:.4f} m exceeds {Z_DRIFT_MAX_M}")
    print(f"robot stable: z drift {z_drift:.6f} m")

    print("PASS: all shadow-GNM checks passed")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
