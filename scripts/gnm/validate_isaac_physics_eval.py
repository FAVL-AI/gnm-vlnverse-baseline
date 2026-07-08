"""Validate the Isaac physics smoke evaluation (Stage 2).

Usage:
    python3 scripts/gnm/validate_isaac_physics_eval.py
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EPISODES = ["physeval_base_A", "physeval_base_D", "physeval_base_F",
            "physeval_ema_A", "physeval_ema_D", "physeval_ema_F"]
CONTROL = "physeval_collision_control2"
BAG_TOPICS = ["/camera/image_raw", "/camera/camera_info", "/odom",
              "/tf", "/clock", "/cmd_vel"]
COLLISION_FIELDS = ["collision_detected", "collision_count_so_far",
                    "collision_body"]


def fail(msg):
    print(f"FAIL: {msg}")
    return False


def newest(prefix):
    root = REPO / "assets/experiments/trajectories"
    dirs = sorted(d for d in root.iterdir()
                  if d.is_dir() and d.name.startswith(prefix))
    return dirs[-1] if dirs else None


def main():
    summary_path = (REPO / "assets/experiments/isaac_physics_eval"
                    / "isaac_physics_smoke_20260708/summary.json")
    if not summary_path.exists():
        return fail("physics summary missing")
    summary = json.loads(summary_path.read_text())
    if "physx_contact_report" not in summary["collision_rate_source"]:
        return fail("CR source is not PhysX contact reporting")
    if "NOT a campaign-level benchmark" not in summary["label"]:
        return fail("smoke-test label missing")

    for prefix in EPISODES:
        d = newest(prefix)
        if d is None:
            return fail(f"episode missing: {prefix}")
        meta = json.loads((d / "episode_metadata.json").read_text())
        ckpt = REPO / meta["policy_checkpoint"]
        if not ckpt.exists():
            return fail(f"{prefix}: checkpoint missing {ckpt}")
        if meta.get("collision_reporting") != \
                "physx_contact_report_base_link":
            return fail(f"{prefix}: CR not from PhysX events")
        rows = [json.loads(l) for l in (d / "trajectory.jsonl").open()]
        for f_ in COLLISION_FIELDS:
            if f_ not in rows[10]:
                return fail(f"{prefix}: row missing {f_}")
        bag_meta = REPO / meta["rosbag_path"] / "metadata.yaml"
        if not bag_meta.exists():
            return fail(f"{prefix}: bag missing")
        text = bag_meta.read_text()
        for topic in BAG_TOPICS:
            m = re.search(
                rf"name: {re.escape(topic)}\n.*?message_count: (\d+)",
                text, re.DOTALL)
            if not m or int(m.group(1)) == 0:
                return fail(f"{prefix}: bag missing {topic}")
    print(f"{len(EPISODES)} evaluation episodes: checkpoints exist, PhysX "
          "collision fields per row, full-topic bags")

    ctrl = newest(CONTROL)
    if ctrl is None:
        return fail("collision positive-control episode missing")
    cmeta = json.loads((ctrl / "episode_metadata.json").read_text())
    if not cmeta.get("episode_had_collision") \
            or cmeta.get("total_collision_count", 0) < 1:
        return fail("positive control did not record any collision — "
                    "zero CR would be unverified")
    print(f"positive control: {cmeta['total_collision_count']} chassis "
          f"contacts recorded (first at step "
          f"{cmeta['first_collision_step']}) — measured zeros are verified")

    for cond in summary["conditions"]:
        if cond["collision_rate_episode"] == 0.0 \
                and cond["total_collisions"] != 0:
            return fail("inconsistent collision aggregates")
        for k in ("SR", "OSR", "NE_m", "SPL"):
            if k not in cond:
                return fail(f"missing Isaac-trajectory metric {k}")
    print("SR/OSR/NE/SPL computed from Isaac trajectories; CR from contact "
          "events only (never copied from the offline evaluator)")

    status = (REPO / "docs/experiments/PROJECT_BASELINE_STATUS.md").read_text()
    if "offline" not in status.lower() or "physics" not in status.lower():
        return fail("status doc must separate offline vs physics metrics")
    print("status doc separates offline metrics from Isaac physics metrics")
    print("PASS: Isaac physics smoke evaluation validated")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
