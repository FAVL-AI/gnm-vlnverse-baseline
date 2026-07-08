"""Validate a scene-aligned goal capture.

Usage (run with the isaac env python so the GNM-loadability check works):
    python scripts/gnm/validate_scene_goal.py [goal_id]

Defaults to the newest goal under assets/experiments/goals/.
Exit code 0 only if every check passes.
"""

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REQUIRED_META = [
    "goal_id", "goal_image", "goal_image_sha256", "capture_source",
    "capture_command", "sim_time", "scene_stage_path", "camera_frame_id",
    "robot_pose_at_capture", "start_pose", "goal_pose", "git_commit",
    "git_branch", "image_resolution",
]


def fail(msg):
    print(f"FAIL: {msg}")
    return False


def main():
    root = REPO / "assets/experiments/goals"
    if len(sys.argv) > 1:
        gdir = root / sys.argv[1]
    else:
        dirs = sorted(d for d in root.iterdir() if d.is_dir())
        if not dirs:
            return fail(f"no goals under {root}")
        gdir = dirs[-1]
    print(f"validating goal: {gdir.name}")

    img = gdir / "goal_image.png"
    meta_path = gdir / "goal_metadata.json"
    if not img.exists():
        return fail("goal_image.png missing")
    if not meta_path.exists():
        return fail("goal_metadata.json missing")
    meta = json.loads(meta_path.read_text())

    missing = [k for k in REQUIRED_META if k not in meta]
    if missing:
        return fail(f"metadata missing fields: {missing}")
    print("metadata complete (scene path, frame_id, poses, git recorded)")

    sha = hashlib.sha256(img.read_bytes()).hexdigest()
    if sha != meta["goal_image_sha256"]:
        return fail("checksum mismatch — image and metadata disagree")
    print(f"checksum verified: {sha[:16]}…")

    if meta["capture_source"] != "isaac_live_annotator":
        return fail(f"capture_source is {meta['capture_source']}, not the "
                    "live Isaac annotator")
    w, h = meta["image_resolution"]
    if (w, h) != (640, 480):
        return fail(f"resolution {w}x{h} does not match the live camera "
                    "render product (640x480); dataset frames are 224x224")
    print("provenance: live Isaac annotator at live-camera resolution "
          "(not an external dataset frame)")

    sp, gp = meta["start_pose"], meta["goal_pose"]
    import math
    d = math.hypot(gp["x"] - sp["x"], gp["y"] - sp["y"])
    if not (0.5 <= d <= 10.0):
        return fail(f"start->goal distance {d:.2f} m not a sane smoke range")
    print(f"start/goal pose pair recorded: {d:.2f} m apart")

    try:
        import numpy as np
        from PIL import Image
        sys.path.insert(0, str(REPO))
        from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter \
            import GNMAdapter
        goal = np.array(Image.open(img).convert("RGB"))
        adapter = GNMAdapter(device="cpu")
        pre = adapter.preprocess_observation([goal] * 6, goal)
        shp = tuple(pre["goal_tensor"].shape)
        print(f"GNM pipeline loads the goal image: goal_tensor {shp}")
    except Exception as e:
        return fail(f"GNM pipeline could not load the goal image: {e}")

    print("PASS: scene-aligned goal capture valid "
          "(navigation quality still requires a closed-loop "
          "goal-conditioned run)")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
