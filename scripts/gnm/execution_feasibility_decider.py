"""Execution-Aware Demonstration Gating for Vision-Based Robot Navigation
(FleetSafe-NavGen Decider).

A forensic execution-feasibility gate for navigation dataset generation:
routes, collectors, maps, and measured robot dynamics are checked BEFORE
training data is accepted. Its job is not to make the robot smarter; it
is to stop bad data from entering the research pipeline.

Five checks -> seven verdicts:
  1 map feasibility (measured occupancy, robot-radius dilation)
  2 yaw/curvature feasibility (measured yaw calibration curve)
  3 controller feasibility (full-route precheck telemetry)
  4 collector validity (scripted expert vs learned-policy rollout)
  5 evidence integrity (process + artifact completeness)

Verdicts: PASS_DEMONSTRATION | PASS_EVALUATION_ONLY | REJECT_MAP_DEFECT |
REJECT_YAW_INFEASIBLE | REJECT_CONTROLLER_INFEASIBLE |
REJECT_ARTIFACT_INCOMPLETE | REJECT_POLICY_NOT_EXPERT

Literature anchors (components exist; the combined gate is ours):
mecanum/omnidirectional tracking with dynamics-aware control (MPC),
kinodynamic local planning (TEB/DWA), occupancy-grid mapping (Elfes),
CBF-style safety filtering of nominal commands.
"""

import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
NAVGEN = REPO / "assets/datasets/isaac_hospital_navgen_v0"
ROBOT_RADIUS_M = 0.20
CURVATURE_MARGIN = 0.8          # use only 80% of measured capability


def load_measured_map():
    occ = np.load(NAVGEN / "measured_occupancy.npy")
    meta = json.loads((NAVGEN / "measured_occupancy.json").read_text())
    return occ, meta


def load_yaw_model():
    p = NAVGEN / "yaw_calibration.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def route_cells(waypoints, meta, step=0.02):
    res = meta["resolution_m"]
    x0, y0 = meta["origin_xy"]
    pts = []
    for (ax, ay), (bx, by) in zip(waypoints, waypoints[1:]):
        n = max(int(math.hypot(bx - ax, by - ay) / step), 1)
        for i in range(n + 1):
            t = i / n
            pts.append((ax + t * (bx - ax), ay + t * (by - ay)))
    return [(int((y - y0) / res), int((x - x0) / res)) for x, y in pts]


def check_map(waypoints, occ, meta):
    r_cells = int(math.ceil(ROBOT_RADIUS_M / meta["resolution_m"]))
    H, W = occ.shape
    hits = []
    for (r, c) in route_cells(waypoints, meta):
        r0, r1 = max(0, r - r_cells), min(H, r + r_cells + 1)
        c0, c1 = max(0, c - r_cells), min(W, c + r_cells + 1)
        if occ[r0:r1, c0:c1].any():
            x = meta["origin_xy"][0] + c * meta["resolution_m"]
            y = meta["origin_xy"][1] + r * meta["resolution_m"]
            hits.append((round(x, 2), round(y, 2)))
    return hits


def check_curvature(waypoints, yaw_model, v_nominal=0.15,
                    advance_radius=0.30):
    if yaw_model is None:
        return None, ["yaw model missing - run calibration first"]
    w_max = yaw_model["max_reliable_yaw_rate_rad_s"] * CURVATURE_MARGIN
    kappa_max = w_max / v_nominal
    if yaw_model.get("mode") == "stop_and_turn_only":
        # vertices are point turns (feasible, cost time); segments must be
        # long enough for the follower to re-align and advance
        violations = []
        import math as _m
        total_turn = 0.0
        for i in range(1, len(waypoints) - 1):
            ax, ay = waypoints[i - 1]; bx, by = waypoints[i]
            cx, cy = waypoints[i + 1]
            h1 = _m.atan2(by - ay, bx - ax)
            h2 = _m.atan2(cy - by, cx - bx)
            total_turn += abs(_m.atan2(_m.sin(h2 - h1), _m.cos(h2 - h1)))
            seg = _m.hypot(cx - bx, cy - by)
            if seg < 2 * advance_radius:
                violations.append({"waypoint_index": i + 1,
                                   "segment_m": round(seg, 2),
                                   "min_segment_m": 2 * advance_radius,
                                   "reason": "segment shorter than "
                                             "re-alignment distance"})
        turn_time_s = total_turn / max(
            yaw_model["max_reliable_yaw_rate_rad_s"], 1e-3)
        return {"mode": "stop_and_turn", "total_turn_rad":
                round(total_turn, 2), "turn_time_s": round(turn_time_s, 1),
                "kappa_max_continuous": round(kappa_max, 2)}, violations
    violations = []
    for i in range(1, len(waypoints) - 1):
        ax, ay = waypoints[i - 1]
        bx, by = waypoints[i]
        cx, cy = waypoints[i + 1]
        h1 = math.atan2(by - ay, bx - ax)
        h2 = math.atan2(cy - by, cx - bx)
        dh = abs(math.atan2(math.sin(h2 - h1), math.cos(h2 - h1)))
        seg = (math.hypot(bx - ax, by - ay) +
               math.hypot(cx - bx, cy - by)) / 2
        kappa = dh / max(seg, 1e-6)
        if kappa > kappa_max:
            violations.append({"waypoint_index": i,
                               "required_curvature": round(kappa, 3),
                               "max_feasible": round(kappa_max, 3),
                               "min_turn_radius_m":
                               round(1 / kappa_max, 2)})
    return kappa_max, violations


def decide(route_file, collector_type, route_family_seen_by_policy=False,
           precheck=None, artifacts_complete=None):
    """precheck: dict with completed/total_contacts/max_streak (optional).
    artifacts_complete: bool or None (unknown/not yet recorded)."""
    route = json.loads(Path(route_file).read_text())
    wp = route["waypoints"]
    occ, meta = load_measured_map()
    yaw_model = load_yaw_model()
    reasons = []

    hits = check_map(wp, occ, meta)
    if hits:
        return {"verdict": "REJECT_MAP_DEFECT",
                "route_id": route.get("route_id"),
                "occupied_intersections": hits[:8],
                "n_intersections": len(hits)}

    kmax, viol = check_curvature(wp, yaw_model)
    if viol and isinstance(viol, list) and isinstance(viol[0], dict):
        return {"verdict": "REJECT_YAW_INFEASIBLE",
                "route_id": route.get("route_id"),
                "violations": viol, "kappa_max": kmax}
    if kmax is None:
        reasons.append(viol[0])

    if precheck is not None:
        ok = (precheck.get("completed") or
              precheck.get("final_d2g_m", 9) < 0.5) and \
             precheck.get("total_contacts", 0) <= 20 and \
             precheck.get("max_streak", 0) <= 10
        if not ok:
            return {"verdict": "REJECT_CONTROLLER_INFEASIBLE",
                    "route_id": route.get("route_id"),
                    "precheck": precheck}

    if artifacts_complete is False:
        return {"verdict": "REJECT_ARTIFACT_INCOMPLETE",
                "route_id": route.get("route_id")}

    if collector_type == "learned_policy":
        if not route_family_seen_by_policy:
            return {"verdict": "PASS_EVALUATION_ONLY",
                    "route_id": route.get("route_id"),
                    "note": "policy rollouts are evaluation evidence, not "
                            "expert demonstrations, on unseen route "
                            "families"}
        return {"verdict": "REJECT_POLICY_NOT_EXPERT",
                "route_id": route.get("route_id"),
                "note": "imitation demonstrations must come from the "
                        "scripted expert executor"}

    return {"verdict": "PASS_DEMONSTRATION",
            "route_id": route.get("route_id"),
            "notes": reasons or None}


if __name__ == "__main__":
    rf = sys.argv[1]
    coll = sys.argv[2] if len(sys.argv) > 2 else "scripted_reference_path"
    print(json.dumps(decide(rf, coll), indent=2))
