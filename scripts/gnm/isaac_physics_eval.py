"""Build the Isaac physics smoke-evaluation summary (Stage 2, Table 2).

Computes SR/OSR/NE/SPL from the Isaac trajectory logs and Collision Rate
ONLY from the logged PhysX chassis-contact events. Preliminary physics
smoke test for Collision Rate and trajectory consistency — not a
campaign-level benchmark.

Definitions:
    SR   final true d2g <= 3 m at episode end (no stop policy runs here)
    OSR  min true d2g <= 3 m at any step
    NE   final true d2g
    SPL  success x (straight-line start-goal / max(path, straight-line))
    Episode CR = episodes with >=1 chassis collision / total episodes
    collisions_per_meter = total contacts / total path length
"""

import csv
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONDITIONS = {
    "mnv2_baseline": ["physeval_base_A", "physeval_base_D", "physeval_base_F"],
    "mnv2_ema0999": ["physeval_ema_A", "physeval_ema_D", "physeval_ema_F"],
}
SUCCESS_R = 3.0


def newest(prefix):
    root = REPO / "assets/experiments/trajectories"
    dirs = sorted(d for d in root.iterdir()
                  if d.is_dir() and d.name.startswith(prefix))
    return dirs[-1] if dirs else None


def episode_stats(prefix):
    d = newest(prefix)
    meta = json.loads((d / "episode_metadata.json").read_text())
    rows = [json.loads(l) for l in (d / "trajectory.jsonl").open()]
    ep = [r for r in rows if r.get("distance_to_goal_m") is not None]
    d2g = [r["distance_to_goal_m"] for r in ep]
    path = sum(math.hypot(b["robot_position_x"] - a["robot_position_x"],
                          b["robot_position_y"] - a["robot_position_y"])
               for a, b in zip(ep, ep[1:]))
    start_goal = d2g[0]
    final = meta["final_distance_to_goal_m"]
    success = final <= SUCCESS_R
    if meta.get("collision_reporting") != "physx_contact_report_base_link":
        raise RuntimeError(f"{d.name}: collision reporting not from PhysX "
                           "contact events — CR would be fake")
    return {
        "episode": d.name, "goal_id": meta["goal_id"],
        "checkpoint": meta.get("policy_checkpoint"),
        "weight_source": meta.get("policy_weight_source"),
        "success": success, "oracle": min(d2g) <= SUCCESS_R,
        "ne": round(final, 3), "min_d2g": round(min(d2g), 3),
        "path_m": round(path, 3),
        "spl": round((start_goal / max(path, start_goal)) if success else 0.0, 4),
        "had_collision": meta["episode_had_collision"],
        "collisions": meta["total_collision_count"],
        "first_collision_step": meta.get("first_collision_step"),
        "estop": meta.get("cl_emergency_stop", False),
    }


def main():
    out_rows, table2 = [], []
    for cond, prefixes in CONDITIONS.items():
        eps = [episode_stats(p) for p in prefixes]
        n = len(eps)
        total_coll = sum(e["collisions"] for e in eps)
        total_path = sum(e["path_m"] for e in eps)
        agg = {
            "condition": cond,
            "checkpoint": eps[0]["checkpoint"],
            "weight_source": eps[0]["weight_source"],
            "episodes": n,
            "SR": round(sum(e["success"] for e in eps) / n, 3),
            "OSR": round(sum(e["oracle"] for e in eps) / n, 3),
            "NE_m": round(sum(e["ne"] for e in eps) / n, 3),
            "SPL": round(sum(e["spl"] for e in eps) / n, 3),
            "collision_rate_episode": round(
                sum(e["had_collision"] for e in eps) / n, 3),
            "total_collisions": total_coll,
            "collisions_per_meter": round(total_coll / total_path, 3)
            if total_path > 0 else None,
            "total_path_m": round(total_path, 2),
            "per_episode": eps,
        }
        table2.append(agg)
        out_rows.extend(eps)

    out = (REPO / "assets/experiments/isaac_physics_eval"
           / "isaac_physics_smoke_20260708")
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "experiment": "isaac_physics_smoke_20260708",
        "label": ("preliminary Isaac physics smoke test for Collision Rate "
                  "and trajectory consistency — NOT a campaign-level "
                  "benchmark"),
        "collision_rate_source": "physx_contact_report_base_link "
                                 "(chassis contacts; wheel-floor excluded "
                                 "by construction)",
        "success_radius_m": SUCCESS_R,
        "conditions": table2,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[k for k in table2[0]
                                          if k != "per_episode"])
        w.writeheader()
        for t in table2:
            w.writerow({k: v for k, v in t.items() if k != "per_episode"})

    print(f"{'condition':16s} {'eps':>3s} {'SR':>5s} {'OSR':>5s} {'NE':>6s} "
          f"{'SPL':>6s} {'CR(ep)':>6s} {'coll':>5s} {'coll/m':>6s}")
    for t in table2:
        print(f"{t['condition']:16s} {t['episodes']:>3d} {t['SR']:>5.2f} "
              f"{t['OSR']:>5.2f} {t['NE_m']:>6.2f} {t['SPL']:>6.3f} "
              f"{t['collision_rate_episode']:>6.2f} "
              f"{t['total_collisions']:>5d} "
              f"{str(t['collisions_per_meter']):>6s}")
    print(f"summary: {out}")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
