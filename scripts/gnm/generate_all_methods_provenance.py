#!/usr/bin/env python3
"""
Assemble per-episode metric provenance for all five Track A stop-policy methods.

Sources (all pre-existing in the repository):
  baseline_gnm            results/research_audit/tracka_per_episode_metric_provenance.csv
  hand_tuned_waypoint_gate results/bo_reviewer_packet/deployable_stop_policy/17_deployable_stop_policy_details.csv
  logistic_stop_head       results/bo_reviewer_packet/stop_head_train_val_protocol/19_learned_stop_head_details.csv
  temporal_neural_stop_head results/bo_reviewer_packet/temporal_stop_head/22_temporal_stop_head_details.csv
  geometry_aware_oracle    derived from baseline per-episode CSV

Output:
  results/research_audit/tracka_all_methods_per_episode_metric_provenance.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

BASELINE_CSV = ROOT / "results/research_audit/tracka_per_episode_metric_provenance.csv"
WAYPOINT_CSV = ROOT / "results/bo_reviewer_packet/deployable_stop_policy/17_deployable_stop_policy_details.csv"
LOGISTIC_CSV = ROOT / "results/bo_reviewer_packet/stop_head_train_val_protocol/19_learned_stop_head_details.csv"
TEMPORAL_CSV = ROOT / "results/bo_reviewer_packet/temporal_stop_head/22_temporal_stop_head_details.csv"

OUT_CSV = ROOT / "results/research_audit/tracka_all_methods_per_episode_metric_provenance.csv"

SUCCESS_RADIUS = 3.0
GENERATE_CMD = "python3 scripts/gnm/generate_all_methods_provenance.py"

OUTPUT_COLUMNS = [
    "episode_id",
    "scene_id",
    "method",
    "success_radius",
    "final_distance_to_goal",
    "minimum_distance_to_goal",
    "success_flag",
    "oracle_success_flag",
    "navigation_error",
    "source_file",
    "source_command",
]


def scene_from_episode(episode_id: str) -> str:
    parts = episode_id.split("_")
    return f"{parts[0]}_{parts[1]}"


def load_baseline() -> pd.DataFrame:
    df = pd.read_csv(BASELINE_CSV)
    rows = []
    for _, r in df.iterrows():
        success = float(r["final_distance_to_goal"]) <= SUCCESS_RADIUS
        oracle = float(r["minimum_distance_to_goal"]) <= SUCCESS_RADIUS
        rows.append({
            "episode_id": r["episode_id"],
            "scene_id": r["scene_id"],
            "method": "baseline_gnm",
            "success_radius": SUCCESS_RADIUS,
            "final_distance_to_goal": float(r["final_distance_to_goal"]),
            "minimum_distance_to_goal": float(r["minimum_distance_to_goal"]),
            "success_flag": success,
            "oracle_success_flag": oracle,
            "navigation_error": float(r["final_distance_to_goal"]),
            "source_file": str(BASELINE_CSV.relative_to(ROOT)),
            "source_command": GENERATE_CMD,
        })
    return pd.DataFrame(rows)


def load_hand_tuned_waypoint_gate() -> pd.DataFrame:
    df = pd.read_csv(WAYPOINT_CSV)
    df = df[df["policy"] == "waypoint_norm_k3"].copy()
    rows = []
    for _, r in df.iterrows():
        final_dist = float(r["final_dist_m"])
        success = bool(r["success"])
        oracle = bool(r["oracle_success"])
        # For an early-stopping policy, minimum distance is the stopping distance
        min_dist = final_dist
        rows.append({
            "episode_id": r["episode_id"],
            "scene_id": scene_from_episode(r["episode_id"]),
            "method": "hand_tuned_waypoint_gate",
            "success_radius": SUCCESS_RADIUS,
            "final_distance_to_goal": final_dist,
            "minimum_distance_to_goal": min_dist,
            "success_flag": success,
            "oracle_success_flag": oracle,
            "navigation_error": final_dist,
            "source_file": str(WAYPOINT_CSV.relative_to(ROOT)),
            "source_command": GENERATE_CMD,
        })
    return pd.DataFrame(rows)


def load_logistic_stop_head() -> pd.DataFrame:
    df_logistic = pd.read_csv(LOGISTIC_CSV)
    # Logistic head does not fire on the held-out validation set; trajectories run to
    # end like baseline. Minimum distance therefore matches the baseline trajectory.
    df_baseline = pd.read_csv(BASELINE_CSV).set_index("episode_id")
    rows = []
    for _, r in df_logistic.iterrows():
        final_dist = float(r["final_dist_m"])
        success = bool(r["success"])
        oracle = bool(r["oracle_success"])
        baseline_min = float(df_baseline.loc[r["episode_id"], "minimum_distance_to_goal"])
        rows.append({
            "episode_id": r["episode_id"],
            "scene_id": scene_from_episode(r["episode_id"]),
            "method": "logistic_stop_head",
            "success_radius": SUCCESS_RADIUS,
            "final_distance_to_goal": final_dist,
            "minimum_distance_to_goal": baseline_min,
            "success_flag": success,
            "oracle_success_flag": oracle,
            "navigation_error": final_dist,
            "source_file": str(LOGISTIC_CSV.relative_to(ROOT)),
            "source_command": GENERATE_CMD,
        })
    return pd.DataFrame(rows)


def load_temporal_neural_stop_head() -> pd.DataFrame:
    df = pd.read_csv(TEMPORAL_CSV)
    rows = []
    for _, r in df.iterrows():
        final_dist = float(r["final_dist_m"])
        success = bool(r["success"])
        oracle = bool(r["oracle_success"])
        # Temporal head fires once; oracle_success == success (OSR == SR = 33.3%).
        # Minimum distance is the stopping distance.
        min_dist = final_dist
        rows.append({
            "episode_id": r["episode_id"],
            "scene_id": scene_from_episode(r["episode_id"]),
            "method": "temporal_neural_stop_head",
            "success_radius": SUCCESS_RADIUS,
            "final_distance_to_goal": final_dist,
            "minimum_distance_to_goal": min_dist,
            "success_flag": success,
            "oracle_success_flag": oracle,
            "navigation_error": final_dist,
            "source_file": str(TEMPORAL_CSV.relative_to(ROOT)),
            "source_command": GENERATE_CMD,
        })
    return pd.DataFrame(rows)


def load_geometry_aware_oracle() -> pd.DataFrame:
    # The oracle stops at the closest point to the goal, so
    # final_distance_to_goal = minimum_distance_to_goal from the baseline trajectory.
    df_baseline = pd.read_csv(BASELINE_CSV)
    rows = []
    for _, r in df_baseline.iterrows():
        oracle_final = float(r["minimum_distance_to_goal"])
        success = oracle_final <= SUCCESS_RADIUS
        rows.append({
            "episode_id": r["episode_id"],
            "scene_id": r["scene_id"],
            "method": "geometry_aware_oracle",
            "success_radius": SUCCESS_RADIUS,
            "final_distance_to_goal": oracle_final,
            "minimum_distance_to_goal": oracle_final,
            "success_flag": success,
            "oracle_success_flag": success,
            "navigation_error": oracle_final,
            "source_file": str(BASELINE_CSV.relative_to(ROOT)),
            "source_command": GENERATE_CMD,
        })
    return pd.DataFrame(rows)


def main() -> int:
    missing = [p for p in [BASELINE_CSV, WAYPOINT_CSV, LOGISTIC_CSV, TEMPORAL_CSV] if not p.exists()]
    if missing:
        for p in missing:
            print(f"[FAIL] Missing source: {p.relative_to(ROOT)}")
        return 1

    frames = [
        load_baseline(),
        load_hand_tuned_waypoint_gate(),
        load_logistic_stop_head(),
        load_temporal_neural_stop_head(),
        load_geometry_aware_oracle(),
    ]

    combined = pd.concat(frames, ignore_index=True)[OUTPUT_COLUMNS]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUT_CSV, index=False)

    n_methods = combined["method"].nunique()
    n_rows = len(combined)
    print(f"[OK] Wrote {n_rows} rows ({n_methods} methods × {n_rows // n_methods} episodes)")
    print(f"     {OUT_CSV.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
