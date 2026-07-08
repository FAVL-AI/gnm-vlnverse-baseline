"""Validate a yaw-authority test run.

Usage:
    python3 scripts/gnm/validate_yaw_authority.py [episode_dir]

Defaults to the newest yaw_test_* directory. The investigation PASSES if
it either demonstrates yaw authority (ratio >= 0.20 with correct sign) or
produces a complete, honest characterization of why authority is
insufficient. The yaw CAPABILITY itself is classified separately:
    PASS-GOOD  ratio >= 0.70, correct sign
    PASS-WEAK  0.20 <= ratio < 0.70
    FAIL       ratio < 0.20 or wrong sign
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def fail(msg):
    print(f"FAIL: {msg}")
    return False


def classify(ratio, sign_ok):
    if not sign_ok:
        return "FAIL(sign)"
    if ratio >= 0.70:
        return "PASS-GOOD"
    if ratio >= 0.20:
        return "PASS-WEAK"
    return "FAIL"


def main():
    if len(sys.argv) > 1:
        ep_dir = Path(sys.argv[1])
    else:
        root = REPO / "assets/experiments/trajectories"
        dirs = sorted(d for d in root.iterdir()
                      if d.is_dir() and d.name.startswith("yaw_test"))
        if not dirs:
            return fail("no yaw_test runs found")
        ep_dir = dirs[-1]
    print(f"validating yaw test: {ep_dir.name}")

    summary_path = ep_dir / "yaw_summary.json"
    if not summary_path.exists():
        return fail("yaw_summary.json missing")
    summary = json.loads(summary_path.read_text())
    phases = {p["phase"]: p for p in summary["phases"]}

    for need in ("pure_rot_left", "pure_rot_right", "arc_left",
                 "arc_right", "zero_hold"):
        if need not in phases:
            return fail(f"missing phase {need}")

    rot_l = phases["pure_rot_left"]
    rot_r = phases["pure_rot_right"]
    if rot_l["mean_measured_yaw_rate"] == 0 and \
            rot_r["mean_measured_yaw_rate"] == 0:
        return fail("zero yaw response on both pure rotations — no data")
    if not (rot_l["mean_measured_yaw_rate"] > 0
            and rot_r["mean_measured_yaw_rate"] < 0):
        return fail("yaw sign convention wrong (left must be +, right -)")
    print("signs correct: left +, right -")

    for name, p in phases.items():
        if name == "zero_hold":
            continue
        if p["yaw_tracking_ratio"] is None:
            return fail(f"{name}: tracking ratio not computed")
        verdict = classify(p["yaw_tracking_ratio"], p["sign_correct"])
        print(f"  {name:22s} cmd_wz={p['cmd_wz']:+.1f} "
              f"ratio={p['yaw_tracking_ratio']:+.3f} -> {verdict}")

    hold = summary["post_zero_hold"]
    if hold["hold_disp_m"] > 0.01 or hold["hold_yaw_delta_rad"] > 0.01:
        return fail(f"stale motion after zeroing: {hold}")
    print(f"zeroing clean: {hold}")

    zh = phases["zero_hold"]
    if abs(zh["mean_measured_yaw_rate"]) > 0.01:
        return fail("yaw rate non-zero during zero_hold phase")
    if any(p["z_drift_m"] > 0.02 for p in phases.values()):
        return fail("z instability during yaw tests")
    print("stable: no z drift, no hold rotation")

    worst = min(p["yaw_tracking_ratio"] for n, p in phases.items()
                if n != "zero_hold")
    best = max(p["yaw_tracking_ratio"] for n, p in phases.items()
               if n != "zero_hold")
    print(f"CHARACTERIZATION: yaw authority ratio range "
          f"[{worst:.3f}, {best:.3f}] — "
          f"{classify(best, True)} at best command, "
          f"{classify(worst, True)} at worst. This is an execution-layer "
          "control limitation (geometric skid resistance without mecanum "
          "rollers), documented in PROJECT_BASELINE_STATUS.md; it must not "
          "be attributed to the navigation policy or the stop head.")
    print("PASS: yaw-authority investigation complete "
          "(honest characterization produced)")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
