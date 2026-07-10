"""H2.2 full-route precheck verdict table (nine-condition pass rule)."""
import glob, json, sys
from pathlib import Path

ROUTES = ["route_H_v2", "route_I_v2", "route_J_v2", "route_K_v2",
          "route_M_v2"]
MAX_TOTAL = 20
MAX_STREAK = 10   # consecutive collision-detected rows = sustained contact


def main():
    out = []
    print(f"{'route':11s} {'path':>6s} {'done':>5s} {'total':>6s} "
          f"{'streak':>6s} {'dens/m':>6s} {'first':>6s} verdict")
    for r in ROUTES:
        dirs = sorted(glob.glob(
            f"assets/experiments/trajectories/h22pre_{r}_2*"))
        if not dirs:
            print(f"{r:11s} MISSING"); continue
        d = Path(dirs[-1])
        m = json.loads((d / "episode_metadata.json").read_text())
        rows = [json.loads(l) for l in (d / "trajectory.jsonl").open()]
        streak = best = 0
        for row in rows:
            if row.get("collision_detected"):
                streak += 1
                best = max(best, streak)
            else:
                streak = 0
        tot = m.get("total_collision_count", 0)
        path = m.get("total_distance_m", 0) or 0.001
        dens = tot / path
        comp = bool(m.get("route_completed"))
        near = (m.get("final_distance_to_goal_m") or 9) < 0.5
        fc = m.get("first_collision_step")
        ok = ((comp or near) and tot <= MAX_TOTAL and best <= MAX_STREAK
              and (fc is None or fc >= 20))
        stage = ("" if ok else
                 "sustained_contact" if best > MAX_STREAK else
                 "mid_route_grind" if tot > MAX_TOTAL else
                 "spawn_contact" if fc is not None and fc < 20 else
                 "route_incomplete")
        out.append({"route_id": r, "path_length_m": round(path, 2),
                    "completion_status": "complete" if comp else
                    ("near_goal" if near else "incomplete"),
                    "total_contacts": tot, "max_contact_streak": best,
                    "contact_density_per_m": round(dens, 2),
                    "first_contact_step": fc, "failure_stage": stage,
                    "route_design_integrity": "pass" if ok else "fail",
                    "precheck_verdict": "PASS" if ok else "REJECT",
                    "redesign_required": not ok})
        print(f"{r:11s} {path:6.2f} {str(comp):>5s} {tot:6d} {best:6d} "
              f"{dens:6.2f} {str(fc):>6s} "
              f"{'PASS' if ok else 'REJECT ('+stage+')'}")
    Path("assets/experiments/hospital_h2_collection_20260709/"
         "h22_precheck_table.json").write_text(json.dumps(out, indent=2))
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
