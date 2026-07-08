"""Build the held-out stop-authority A/B comparison summary.

Pairs baseline_no_stop vs stop_authority_recalibrated episodes per goal
and computes the bounded-smoke comparison table. Measurement only; the
claim boundary lives in the status doc.

Output: assets/experiments/comparisons/stop_authority_ab_<date>/summary.{json,csv}
"""

import csv
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAIRS = {
    "D": ("authcmp_D_baseline", "authcmp_D_stopauth"),
    "E": ("authcmp_E_baseline", "authcmp_E_stopauth"),
}


def newest(prefix):
    root = REPO / "assets/experiments/trajectories"
    dirs = sorted(d for d in root.iterdir()
                  if d.is_dir() and d.name.startswith(prefix))
    return dirs[-1] if dirs else None


def load(prefix):
    d = newest(prefix)
    meta = json.loads((d / "episode_metadata.json").read_text())
    rows = [json.loads(l) for l in (d / "trajectory.jsonl").open()]
    d2g = [r["distance_to_goal_m"] for r in rows
           if r.get("distance_to_goal_m") is not None]
    return {
        "dir": d.name,
        "condition": meta["condition"],
        "goal_id": meta["goal_id"],
        "min_d2g": round(min(d2g), 4),
        "final_d2g": meta["final_distance_to_goal_m"],
        "overshoot_past_min": round(
            meta["final_distance_to_goal_m"] - min(d2g), 4),
        "stop_triggered": meta.get("stop_triggered", False),
        "stop_trigger_step": meta.get("stop_trigger_step"),
        "true_d2g_at_stop": meta.get("true_distance_to_goal_at_stop"),
        "pred_at_stop": meta.get("predicted_distance_at_stop"),
        "residual_after_stop_m": meta.get("residual_motion_after_stop_m"),
        "estop": meta.get("cl_emergency_stop", False),
    }


def main():
    out_rows = []
    for pair, (b_pre, a_pre) in PAIRS.items():
        b, a = load(b_pre), load(a_pre)
        assert b["goal_id"] == a["goal_id"], f"pair {pair}: goal mismatch"
        # early-stop distance: how far short of the nearest-achievable point
        early = (round(a["true_d2g_at_stop"] - b["min_d2g"], 4)
                 if a["stop_triggered"] else None)
        out_rows.append({
            "pair_id": pair,
            "goal_id": b["goal_id"],
            "baseline_min_d2g": b["min_d2g"],
            "baseline_final_d2g": b["final_d2g"],
            "baseline_overshoot_past_min": b["overshoot_past_min"],
            "auth_stop_triggered": a["stop_triggered"],
            "auth_true_d2g_at_stop": a["true_d2g_at_stop"],
            "auth_final_d2g": a["final_d2g"],
            "auth_residual_after_stop_m": a["residual_after_stop_m"],
            "final_d2g_delta_auth_minus_baseline": round(
                a["final_d2g"] - b["final_d2g"], 4),
            "early_stop_short_of_nearest_m": early,
            "episodes": [b["dir"], a["dir"]],
        })
    verdicts = []
    for r in out_rows:
        better = r["final_d2g_delta_auth_minus_baseline"] < 0
        verdicts.append(
            f"pair {r['pair_id']}: authority final d2g "
            f"{r['auth_final_d2g']} vs baseline {r['baseline_final_d2g']} "
            f"({'closer' if better else 'farther'}); "
            f"stopped {r['early_stop_short_of_nearest_m']} m short of the "
            f"baseline's nearest point (early stop)"
            if r["auth_stop_triggered"] else
            f"pair {r['pair_id']}: authority did not fire")
    summary = {
        "experiment": "stop_authority_ab_heldout_smoke",
        "label": ("bounded held-out authority A/B smoke comparison; "
                  "not campaign, not SR/SPL, not FleetSafe"),
        "rule": "recalibrated_dist_pred_gate dist_pred<=4.5 k=3",
        "pairs": out_rows,
        "verdicts": verdicts,
    }
    out = (REPO / "assets/experiments/comparisons"
           / f"stop_authority_ab_{date.today():%Y%m%d}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[k for k in out_rows[0]
                                          if k != "episodes"])
        w.writeheader()
        for r in out_rows:
            w.writerow({k: v for k, v in r.items() if k != "episodes"})
    for v in verdicts:
        print(v)
    print(f"summary written: {out}")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
