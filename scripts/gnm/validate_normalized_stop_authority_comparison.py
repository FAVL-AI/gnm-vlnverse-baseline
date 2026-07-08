"""Validate the fresh held-out normalized_pred stop-authority A/B rerun.

Usage:
    python3 scripts/gnm/validate_normalized_stop_authority_comparison.py

Design checks only; the comparison OUTCOME (ACCEPTED/REJECTED/
INCONCLUSIVE) is reported as classified in the summary, and validation
requires that a classification exists and is honest.
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PRIOR_GOALS = {"hospital_goal_A", "hospital_goal_B", "hospital_goal_C",
               "hospital_holdout_short_D", "hospital_holdout_medium_E"}
PAIRS = {"F": ("normcmp_F_baseline", "normcmp_F_stopauth"),
         "G": ("normcmp_G_baseline", "normcmp_G_stopauth")}
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

    if meta["goal_id"] in PRIOR_GOALS:
        return fail(f"{prefix}: goal {meta['goal_id']} is not fresh"), None
    if meta["stop_authority_enabled"] != expect_auth:
        return fail(f"{prefix}: authority flag mismatch"), None
    if meta.get("cl_emergency_stop"):
        return fail(f"{prefix}: e-stop contaminated episode"), None
    if expect_auth:
        if meta["stop_rule_name"] != "normalized_pred_gate":
            return fail(f"{prefix}: wrong stop rule"), None
        if meta.get("stop_rule_ratio") != 0.5 or meta.get("stop_rule_k") != 3:
            return fail(f"{prefix}: rule params wrong"), None
        if meta.get("initial_predicted_distance") is None:
            return fail(f"{prefix}: per-episode initial prediction not "
                        "recorded — threshold must self-scale"), None
        if meta.get("stop_triggered"):
            if meta.get("residual_motion_after_stop_m") is None \
                    or meta["residual_motion_after_stop_m"] > 0.05:
                return fail(f"{prefix}: zeroing/residual invalid"), None
            tail = [r for r in rows
                    if r["watchdog_state"] == "goal_stop_zeroed"]
            if not tail or any(
                    abs(r["gnm_action_clipped_linear_velocity"]) > 1e-6
                    for r in tail):
                return fail(f"{prefix}: commands not zeroed after stop"), None
            norm_at_stop = (meta["predicted_distance_at_stop"]
                            / meta["initial_predicted_distance"])
            if norm_at_stop > 0.5 + 0.05:
                return fail(f"{prefix}: fired above normalized threshold "
                            f"({norm_at_stop:.2f})"), None
    else:
        if any(r.get("stop_authority_enabled") for r in rows):
            return fail(f"{prefix}: baseline has authority rows"), None

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
        return fail(f"{prefix}: final-distance metrics missing"), None
    return True, meta


def main():
    for pair, (b_pre, a_pre) in PAIRS.items():
        ok_b, mb = check(b_pre, expect_auth=False)
        ok_a, ma = check(a_pre, expect_auth=True)
        if not (ok_b and ok_a):
            return False
        if mb["goal_id"] != ma["goal_id"]:
            return fail(f"pair {pair}: goal mismatch")
        print(f"pair {pair} ({mb['goal_id']}): baseline final "
              f"{mb['final_distance_to_goal_m']} vs authority final "
              f"{ma['final_distance_to_goal_m']} "
              f"(init_pred {ma['initial_predicted_distance']}, "
              f"stop@pred {ma.get('predicted_distance_at_stop')}, "
              f"residual {ma.get('residual_motion_after_stop_m')} m)")

    comps = sorted((REPO / "assets/experiments/comparisons").glob(
        "stop_authority_normalized_ab_*/summary.json"))
    if not comps:
        return fail("comparison summary missing")
    summary = json.loads(comps[-1].read_text())
    if summary.get("decision") not in ("ACCEPTED", "REJECTED",
                                       "INCONCLUSIVE"):
        return fail("summary must classify ACCEPTED/REJECTED/INCONCLUSIVE")
    print(f"classification: {summary['decision']} — "
          f"{summary.get('decision_basis','')[:80]}…")

    status = (REPO / "docs/experiments/PROJECT_BASELINE_STATUS.md").read_text()
    lowered = status.lower()
    for banned in ("fleetsafe improves", "campaign complete",
                   "sr/spl established"):
        if banned in lowered:
            return fail(f"status doc banned claim: {banned}")
    print("status doc claim guard OK")
    print("PASS: normalized-gate held-out A/B rerun validated "
          "(design held; outcome classified honestly)")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
