"""Validate the held-out stop-authority A/B comparison.

Usage:
    python3 scripts/gnm/validate_stop_authority_comparison.py

Exit 0 only if the experimental design held: held-out goals, matched
pairs, authority only where declared, goal-stops caused by the
recalibrated gate (not watchdog/e-stop), zeroing verified, evidence
complete. The comparison OUTCOME (better or worse) does not affect
validation — it is reported as measured.
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CALIB_GOALS = {"hospital_goal_A", "hospital_goal_B", "hospital_goal_C"}
PAIRS = {"D": ("authcmp_D_baseline", "authcmp_D_stopauth"),
         "E": ("authcmp_E_baseline", "authcmp_E_stopauth")}
BAG_TOPICS = ["/camera/image_raw", "/camera/camera_info", "/odom",
              "/tf", "/clock", "/cmd_vel"]


def fail(msg):
    print(f"FAIL: {msg}")
    return False


def newest(prefix):
    root = REPO / "assets/experiments/trajectories"
    dirs = sorted(d for d in root.iterdir()
                  if d.is_dir() and d.name.startswith(prefix))
    return dirs[-1] if dirs else None


def check(prefix, expect_auth):
    d = newest(prefix)
    if d is None:
        return fail(f"missing episode {prefix}"), None
    meta = json.loads((d / "episode_metadata.json").read_text())
    rows = [json.loads(l) for l in (d / "trajectory.jsonl").open()]

    if meta["goal_id"] in CALIB_GOALS:
        return fail(f"{prefix}: goal {meta['goal_id']} is a calibration "
                    "goal, not held-out"), None
    if meta["stop_authority_enabled"] != expect_auth:
        return fail(f"{prefix}: authority flag mismatch"), None
    auth_rows = [r for r in rows if r.get("stop_authority_enabled")]
    if expect_auth and not auth_rows:
        return fail(f"{prefix}: no authority rows"), None
    if not expect_auth and auth_rows:
        return fail(f"{prefix}: baseline has authority rows"), None
    if meta.get("cl_emergency_stop"):
        return fail(f"{prefix}: emergency stop contaminated episode"), None
    if expect_auth and meta.get("stop_triggered"):
        if meta["stop_rule_name"] != "recalibrated_dist_pred_gate":
            return fail(f"{prefix}: stop not caused by the gate"), None
        if meta.get("residual_motion_after_stop_m") is None:
            return fail(f"{prefix}: residual motion not measured"), None
        if meta["residual_motion_after_stop_m"] > 0.05:
            return fail(f"{prefix}: residual motion too large"), None
        tail = [r for r in rows if r["watchdog_state"] == "goal_stop_zeroed"]
        if not tail or any(
                abs(r["gnm_action_clipped_linear_velocity"]) > 1e-6
                for r in tail):
            return fail(f"{prefix}: commands not zeroed after stop"), None

    bag_meta = REPO / meta["rosbag_path"] / "metadata.yaml"
    if not bag_meta.exists():
        return fail(f"{prefix}: rosbag missing"), None
    text = bag_meta.read_text()
    for topic in BAG_TOPICS:
        m = re.search(rf"name: {re.escape(topic)}\n.*?message_count: (\d+)",
                      text, re.DOTALL)
        if not m or int(m.group(1)) == 0:
            return fail(f"{prefix}: bag missing {topic}"), None
    if meta.get("final_distance_to_goal_m") is None:
        return fail(f"{prefix}: overshoot metrics missing"), None
    return True, meta


def main():
    for pair, (b_pre, a_pre) in PAIRS.items():
        ok_b, mb = check(b_pre, expect_auth=False)
        ok_a, ma = check(a_pre, expect_auth=True)
        if not (ok_b and ok_a):
            return False
        if mb["goal_id"] != ma["goal_id"]:
            return fail(f"pair {pair}: goal mismatch between conditions")
        fired = ("fired" if ma.get("stop_triggered")
                 else "did not fire (honest)")
        print(f"pair {pair} ({mb['goal_id']}): baseline final "
              f"{mb['final_distance_to_goal_m']} m vs authority final "
              f"{ma['final_distance_to_goal_m']} m; gate {fired}, "
              f"residual {ma.get('residual_motion_after_stop_m')} m")

    comp = sorted((REPO / "assets/experiments/comparisons").glob(
        "stop_authority_ab_*/summary.json"))
    if not comp:
        return fail("comparison summary missing")
    print(f"comparison summary present: {comp[-1].parent.name}")

    status = (REPO / "docs/experiments/PROJECT_BASELINE_STATUS.md").read_text()
    lowered = status.lower()
    for banned in ("fleetsafe improves", "campaign complete",
                   "robust hospital navigation: valid",
                   "sr/spl established"):
        if banned in lowered:
            return fail(f"status doc contains banned claim: {banned}")
    print("status doc claim guard OK")
    print("PASS: held-out stop-authority A/B comparison validated "
          "(design held; outcome reported as measured)")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
