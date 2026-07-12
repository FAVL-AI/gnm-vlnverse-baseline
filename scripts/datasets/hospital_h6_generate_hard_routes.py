"""H6 hard-route family generator (PREFLIGHT, planning phase).

Generates 8 hard-route family templates spanning the 6 target hard route types,
auto-places each on measured free space, and gates every candidate with the
IDENTICAL decider checks (check_map robot-radius dilation + check_curvature yaw
feasibility). Emits route JSONs + the route-family approval table. NO Isaac,
NO recording, NO training — this only produces decider-approved route plans.

Target (Frank, 2026-07-11): 8 families x2 variants = 16 episodes.
Split: 5 train families / 1 val family / 2 fresh held-out families.
Types: uturn, chain, ftL_sharp, sharp_multi_turn, tight_corridor_turn, compound_turn.
"""
import csv, json, math, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts/gnm"))
from execution_feasibility_decider import (load_measured_map, load_yaw_model,
                                           check_map, check_curvature)

OUT = REPO / "assets/experiments/hospital_h6_routes"
EVID = REPO / "assets/experiments/hospital_h2_collection_20260709"


def rot(pts, deg, ax, ay):
    t = math.radians(deg)
    return [(ax + x * math.cos(t) - y * math.sin(t),
             ay + x * math.sin(t) + y * math.cos(t)) for x, y in pts]


# local-frame templates (metres) — each produces its hard maneuver
TEMPLATES = {
    "uturn":              [(0, 0), (1.4, 0), (1.4, 0.85), (0, 0.85)],
    "chain":              [(0, 0), (0.8, 0.55), (1.6, 0), (2.4, 0.55),
                           (3.2, 0), (4.0, 0.55)],
    "ftL_sharp":          [(0, 0), (1.5, 0), (1.5, 1.25)],
    "sharp_multi_turn":   [(0, 0), (0.95, 0), (0.95, 0.95), (0, 0.95), (0, 1.9)],
    "tight_corridor_turn":[(0, 0), (1.25, 0), (1.25, 0.65), (0.25, 0.65)],
    "compound_turn":      [(0, 0), (0.75, 0.35), (1.25, 0.95), (1.5, 1.7),
                           (1.5, 2.55)],
}

# 8 families: type -> list of family ids, with split assignment
FAMILIES = [
    ("h6_uturn_01", "uturn", "train"),
    ("h6_chain_01", "chain", "train"),
    ("h6_ftL_01", "ftL_sharp", "train"),
    ("h6_sharpmulti_01", "sharp_multi_turn", "train"),
    ("h6_tightcorr_01", "tight_corridor_turn", "train"),
    ("h6_compound_01", "compound_turn", "validation"),
    ("h6_uturn_02", "uturn", "fresh_heldout"),
    ("h6_chain_02", "chain", "fresh_heldout"),
]


def place(template, occ, meta, yaw, placed_centroids):
    """search anchor+orientation+scale for a decider-clean placement, spatially
    distinct from already-placed families."""
    for scale in (1.0, 0.9, 0.8):
        for ax in [x / 10 for x in range(-40, 41, 5)]:
            for ay in [y / 10 for y in range(-40, 41, 5)]:
                for deg in (0, 45, 90, 135, 180, 225, 270, 315):
                    local = [(x * scale, y * scale) for x, y in template]
                    wp = rot(local, deg, ax, ay)
                    cx = sum(p[0] for p in wp) / len(wp)
                    cy = sum(p[1] for p in wp) / len(wp)
                    if any(math.hypot(cx - px, cy - py) < 1.6
                           for px, py in placed_centroids):
                        continue
                    if check_map(wp, occ, meta):
                        continue
                    _, viol = check_curvature(wp, yaw)
                    if viol:
                        continue
                    return [[round(x, 3), round(y, 3)] for x, y in wp], (cx, cy)
    return None, None


def main():
    occ, meta = load_measured_map()
    yaw = load_yaw_model()
    OUT.mkdir(parents=True, exist_ok=True)

    placed, rows = [], []
    for fam, rtype, split in FAMILIES:
        wp, cent = place(TEMPLATES[rtype], occ, meta, yaw, placed)
        if wp is None:
            rows.append({"route_family_id": fam, "route_type": rtype,
                         "split_proposal": split, "n_waypoints": 0,
                         "map_feasibility": "FAIL", "yaw_feasibility": "FAIL",
                         "decider_verdict": "REJECT_NO_PLACEMENT",
                         "route_file": ""})
            continue
        placed.append(cent)
        length = sum(math.hypot(wp[i+1][0]-wp[i][0], wp[i+1][1]-wp[i][1])
                     for i in range(len(wp)-1))
        route = {"route_id": fam, "route_type": rtype, "waypoints": wp,
                 "start_pose": {"x": wp[0][0], "y": wp[0][1], "yaw_rad": 0.0},
                 "goal_pose": {"x": wp[-1][0], "y": wp[-1][1], "yaw_rad": 0.0},
                 "provenance": "H6 authored hard-route template, decider-gated "
                               "(check_map + check_curvature); measured occupancy "
                               "+ continuous yaw model"}
        (OUT / f"{fam}.json").write_text(json.dumps(route, indent=2))
        rows.append({"route_family_id": fam, "route_type": rtype,
                     "split_proposal": split, "n_waypoints": len(wp),
                     "route_length_m": round(length, 2),
                     "map_feasibility": "PASS", "yaw_feasibility": "PASS",
                     "decider_verdict": "PASS_DEMONSTRATION",
                     "route_file": f"assets/experiments/hospital_h6_routes/{fam}.json"})

    cols = ["route_family_id", "route_type", "split_proposal", "n_waypoints",
            "route_length_m", "map_feasibility", "yaw_feasibility",
            "decider_verdict", "route_file"]
    with open(EVID / "h6_route_family_approval_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    npass = sum(r["decider_verdict"] == "PASS_DEMONSTRATION" for r in rows)
    by_split = {}
    for r in rows:
        if r["decider_verdict"] == "PASS_DEMONSTRATION":
            by_split[r["split_proposal"]] = by_split.get(r["split_proposal"], 0) + 1
    print(f"{'family':20}{'type':22}{'split':16}{'nwp':>4}{'len':>7}  verdict")
    for r in rows:
        print(f"{r['route_family_id']:20}{r['route_type']:22}"
              f"{r['split_proposal']:16}{r.get('n_waypoints',0):>4}"
              f"{r.get('route_length_m',0):>7}  {r['decider_verdict']}")
    print(f"\nPASS: {npass}/8 | by split: {by_split}")
    print("H6_PREFLIGHT_ROUTES_OK" if npass == 8 else "H6_PREFLIGHT_INCOMPLETE")


if __name__ == "__main__":
    main()
