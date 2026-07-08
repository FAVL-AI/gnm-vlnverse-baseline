"""Validate a stop-head shadow episode.

Usage:
    python3 scripts/gnm/validate_stop_head_shadow.py [episode_dir]

Chains the goal-conditioned validator, then verifies the stop head ran in
shadow only. A stop decision near the closest-goal region is reported if
present; its absence is reported honestly and does not fail validation
(measurement milestone, not improvement milestone).
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STOP_ROW_FIELDS = [
    "stop_head_enabled", "stop_head_mode", "stop_head_model_path",
    "stop_probability", "stop_decision_shadow", "stop_threshold",
    "stop_authority_enabled", "overshoot_detected",
    "nearest_goal_distance_so_far",
]


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
         str(REPO / "scripts/gnm/validate_goal_conditioned_gnm.py"),
         str(ep_dir)], capture_output=True, text=True)
    sys.stdout.write(base.stdout)
    if base.returncode != 0:
        return fail("goal-conditioned base validation failed")

    meta = json.loads((ep_dir / "episode_metadata.json").read_text())
    rows = [json.loads(l) for l in (ep_dir / "trajectory.jsonl").open()]
    srows = [r for r in rows if r.get("stop_head_enabled")]
    if not srows:
        return fail("no stop-head rows in trajectory")
    for i, r in enumerate(srows):
        missing = [f for f in STOP_ROW_FIELDS if f not in r]
        if missing:
            return fail(f"stop row {i} missing fields: {missing}")
    if any(r["stop_head_mode"] != "shadow" or r["stop_authority_enabled"]
           for r in srows):
        return fail("stop head left shadow mode or gained authority")
    if any(r["actual_controller"] != "gnm_closed_loop" for r in srows):
        return fail("GNM lost /cmd_vel control during stop-head shadow")
    print(f"stop-head rows: {len(srows)}; shadow-only, no authority, "
          "GNM kept control")

    probs = [r["stop_probability"] for r in srows
             if r["stop_probability"] is not None]
    if not probs:
        return fail("no stop probabilities logged")
    if meta.get("stop_head_mean_latency_ms") is None:
        return fail("no stop-head latency recorded")
    print(f"probabilities logged: {len(probs)} evaluations, "
          f"range [{min(probs):.3f}, {max(probs):.3f}], "
          f"mean latency {meta['stop_head_mean_latency_ms']} ms")

    if meta.get("stop_head_model_sha256") is None:
        return fail("stop-head model provenance (sha256) missing")
    print(f"model provenance: {meta['stop_head_model_path']} "
          f"sha256={meta['stop_head_model_sha256'][:16]}…")

    nearest = meta.get("stop_head_nearest_d2g")
    would = meta.get("stop_head_would_have_stopped_step")
    if would is not None:
        print(f"shadow stop decision at step {would} "
              f"(sim {meta['stop_head_would_have_stopped_sim_time']} s), "
              f"d2g at signal {meta['stop_head_distance_at_stop_signal']} m, "
              f"overshoot after predicted stop "
              f"{meta['stop_head_overshoot_after_predicted_stop_m']} m")
    else:
        print(f"HONEST REPORT: the learned stop head never fired in this "
              f"episode (max prob {max(probs):.3f} < threshold "
              f"{meta['stop_head_threshold']}); nearest d2g reached "
              f"{nearest} m, final {meta.get('final_distance_to_goal_m')} m. "
              "Measurement milestone stands; no improvement claim was made.")

    if "overshoot_detected" not in srows[-1]:
        return fail("overshoot computation missing")
    status = (REPO / "docs/experiments/PROJECT_BASELINE_STATUS.md").read_text()
    if "stop head improves" in status.lower():
        return fail("status doc claims stop-head improvement")
    print("status doc makes no stop-head improvement claim")

    print("PASS: stop-head shadow validated (stop-signal measurement only)")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
