#!/usr/bin/env python3
"""
Generate expanded Track A provenance for baseline_gnm and geometry_aware_oracle
across all 253 episodes (238 train + 15 val).

WHY ONLY 2 METHODS:
  - baseline_gnm / geometry_aware_oracle: metrics come from true_dist_m in Isaac Sim
    traces — these are exact, not simulated, and have no training contamination.
  - hand_tuned_waypoint_gate: cannot reliably simulate from baseline trajectories.
    The calibration sweep (sim) gives SR=20%, live Isaac Sim runs give SR=26.7%.
    The two diverge because stopping early changes the robot's subsequent path.
  - logistic_stop_head / temporal_neural_stop_head: were trained on these exact
    train-split trace features (19_learned_stop_head_traces.csv). Evaluating on
    training data gives in-distribution (biased) results.

SOURCES:
  Train episodes (238):
    results/bo_reviewer_packet/stop_head_train_val_protocol/19_learned_stop_head_traces.csv
    (step-level GNM traces from live Isaac Sim baseline runs)
  Val episodes (15):
    results/research_audit/tracka_per_episode_metric_provenance.csv
    (locked val provenance)

OUTPUT:
  results/research_audit/tracka_expanded_253ep_baseline_oracle_provenance.csv
  results/research_audit/tracka_expanded_split_lock.json
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "results/research_audit"

TRACES_CSV = ROOT / "results/bo_reviewer_packet/stop_head_train_val_protocol/19_learned_stop_head_traces.csv"
VAL_PROV_CSV = AUDIT / "tracka_per_episode_metric_provenance.csv"
OUT_CSV = AUDIT / "tracka_expanded_253ep_baseline_oracle_provenance.csv"
OUT_LOCK = AUDIT / "tracka_expanded_split_lock.json"

SUCCESS_RADIUS = 3.0

SCENE_MAP = {
    "kujiale_0092": "kujiale_0092",
    "kujiale_0118": "kujiale_0118",
    "kujiale_0203": "kujiale_0203",
    "kujiale_0271": "kujiale_0271",
}


def scene_id_from_episode(ep_id: str) -> str:
    for scene in SCENE_MAP:
        if ep_id.startswith(scene):
            return scene
    raise ValueError(f"Cannot determine scene from episode ID: {ep_id}")


def main() -> int:
    AUDIT.mkdir(parents=True, exist_ok=True)

    # ── 1. Load train-split traces ────────────────────────────────────────────
    print(f"[1/4] Loading train traces from {TRACES_CSV.name} ...")
    if not TRACES_CSV.exists():
        print(f"[ERROR] {TRACES_CSV} not found")
        return 1

    train_episodes: dict[str, list[dict]] = {}
    for row in csv.DictReader(TRACES_CSV.open()):
        train_episodes.setdefault(row["episode_id"], []).append(row)

    print(f"       Found {len(train_episodes)} train episodes")

    # ── 2. Load val provenance ────────────────────────────────────────────────
    print(f"[2/4] Loading val provenance from {VAL_PROV_CSV.name} ...")
    if not VAL_PROV_CSV.exists():
        print(f"[ERROR] {VAL_PROV_CSV} not found")
        return 1

    val_rows = list(csv.DictReader(VAL_PROV_CSV.open()))
    val_episodes = {r["episode_id"]: r for r in val_rows}
    print(f"       Found {len(val_episodes)} val episodes")

    overlap = set(train_episodes) & set(val_episodes)
    if overlap:
        print(f"[WARN] {len(overlap)} episodes appear in both train traces and val provenance: {overlap}")

    # ── 3. Build provenance rows ──────────────────────────────────────────────
    print("[3/4] Computing per-episode provenance ...")
    out_rows: list[dict] = []

    # Train episodes — compute from traces
    for ep_id, steps in sorted(train_episodes.items()):
        true_dists = [float(s["true_dist_m"]) for s in steps]
        final_d = true_dists[-1]
        min_d = min(true_dists)
        scene = scene_id_from_episode(ep_id)
        success = final_d <= SUCCESS_RADIUS
        oracle_success = min_d <= SUCCESS_RADIUS

        for method, fd, md in [
            ("baseline_gnm", final_d, min_d),
            ("geometry_aware_oracle", min_d, min_d),   # oracle stops at closest point
        ]:
            m_success = fd <= SUCCESS_RADIUS
            m_oracle  = md <= SUCCESS_RADIUS
            out_rows.append({
                "episode_id": ep_id,
                "scene_id": scene,
                "split": "train",
                "method": method,
                "success_radius": SUCCESS_RADIUS,
                "final_distance_to_goal": round(fd, 4),
                "minimum_distance_to_goal": round(md, 4),
                "success_flag": str(m_success),
                "oracle_success_flag": str(m_oracle),
                "navigation_error": round(fd, 4),
                "source_file": str(TRACES_CSV.relative_to(ROOT)),
                "source_command": "python3 scripts/gnm/generate_expanded_tracka_provenance.py",
            })

    # Val episodes — copy from existing provenance
    for ep_id, val_row in sorted(val_episodes.items()):
        scene = val_row["scene_id"]
        for method in ("baseline_gnm", "geometry_aware_oracle"):
            # Find this method in the all-methods CSV for final/min dist
            pass  # handled below via all-methods CSV for oracle

        # baseline_gnm from val provenance
        fd = float(val_row["final_distance_to_goal"])
        md = float(val_row["minimum_distance_to_goal"])
        out_rows.append({
            "episode_id": ep_id,
            "scene_id": scene,
            "split": "val",
            "method": "baseline_gnm",
            "success_radius": SUCCESS_RADIUS,
            "final_distance_to_goal": round(fd, 4),
            "minimum_distance_to_goal": round(md, 4),
            "success_flag": str(fd <= SUCCESS_RADIUS),
            "oracle_success_flag": str(md <= SUCCESS_RADIUS),
            "navigation_error": round(fd, 4),
            "source_file": str(VAL_PROV_CSV.relative_to(ROOT)),
            "source_command": "python3 scripts/gnm/generate_expanded_tracka_provenance.py",
        })

        # geometry_aware_oracle: final_dist = min_dist (oracle stops at closest point)
        out_rows.append({
            "episode_id": ep_id,
            "scene_id": scene,
            "split": "val",
            "method": "geometry_aware_oracle",
            "success_radius": SUCCESS_RADIUS,
            "final_distance_to_goal": round(md, 4),
            "minimum_distance_to_goal": round(md, 4),
            "success_flag": str(md <= SUCCESS_RADIUS),
            "oracle_success_flag": str(md <= SUCCESS_RADIUS),
            "navigation_error": round(md, 4),
            "source_file": str(VAL_PROV_CSV.relative_to(ROOT)),
            "source_command": "python3 scripts/gnm/generate_expanded_tracka_provenance.py",
        })

    # ── 4. Write outputs ──────────────────────────────────────────────────────
    print("[4/4] Writing outputs ...")
    fieldnames = [
        "episode_id", "scene_id", "split", "method",
        "success_radius", "final_distance_to_goal", "minimum_distance_to_goal",
        "success_flag", "oracle_success_flag", "navigation_error",
        "source_file", "source_command",
    ]
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    n_episodes = len(train_episodes) + len(val_episodes)
    n_rows = len(out_rows)
    print(f"[OK] {OUT_CSV.name}: {n_rows} rows ({n_episodes} episodes × 2 methods)")

    # Split lock
    scene_split_all: dict[str, dict[str, int]] = {}
    all_ep_ids = sorted(set(train_episodes) | set(val_episodes))
    for ep_id in all_ep_ids:
        scene = scene_id_from_episode(ep_id)
        split = "val" if ep_id in val_episodes else "train"
        scene_split_all.setdefault(scene, {"train": 0, "val": 0})[split] += 1

    lock = {
        "description": (
            "Expanded Track A evaluation split: 253 episodes (238 train + 15 val). "
            "Only baseline_gnm and geometry_aware_oracle are evaluated on all 253 episodes. "
            "hand_tuned_waypoint_gate, logistic_stop_head, temporal_neural_stop_head are "
            "evaluated on the 15-episode val split only. "
            "See tracka_expanded_methodology_note.md for rationale."
        ),
        "n_episodes_total": n_episodes,
        "n_train": len(train_episodes),
        "n_val": len(val_episodes),
        "methods_expanded": ["baseline_gnm", "geometry_aware_oracle"],
        "methods_val_only": [
            "hand_tuned_waypoint_gate",
            "logistic_stop_head",
            "temporal_neural_stop_head",
        ],
        "success_radius_m": SUCCESS_RADIUS,
        "scene_split": scene_split_all,
        "train_source": str(TRACES_CSV.relative_to(ROOT)),
        "val_source": str(VAL_PROV_CSV.relative_to(ROOT)),
        "episode_ids": all_ep_ids,
    }
    OUT_LOCK.write_text(json.dumps(lock, indent=2))
    print(f"[OK] {OUT_LOCK.name}")

    # Scene summary
    from collections import defaultdict
    scene_stats: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for row in out_rows:
        scene_stats[row["scene_id"]][row["method"]].append(row)
    print("\nPer-scene episode counts (train+val):")
    for scene in sorted(scene_stats):
        ep_count = len(set(r["episode_id"] for r in scene_stats[scene]["baseline_gnm"]))
        print(f"  {scene}: {ep_count} episodes")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
