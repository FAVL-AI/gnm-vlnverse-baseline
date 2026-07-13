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
                                           check_map, check_curvature,
                                           check_xy_bound, RUNTIME_XY_LIMIT_M)

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
                    if check_xy_bound(wp):
                        continue
                    return [[round(x, 3), round(y, 3)] for x, y in wp], (cx, cy)
    return None, None


def _centroid(wp):
    return (sum(p[0] for p in wp) / len(wp), sum(p[1] for p in wp) / len(wp))


def _static_ok(wp, occ, meta, yaw):
    """All static route-authoring gates: map + XY-bound + curvature."""
    return (not check_map(wp, occ, meta)
            and not check_xy_bound(wp)
            and not check_curvature(wp, yaw)[1])


def main():
    occ, meta = load_measured_map()
    yaw = load_yaw_model()
    OUT.mkdir(parents=True, exist_ok=True)
    rejected_dir = OUT / "rejected"
    excluded = []

    # Pass 1 -- keep existing routes that still pass ALL static gates (incl.
    # the new XY-bound). Any that now fail are preserved as rejected evidence
    # and queued for targeted re-authoring; passing families stay byte-identical.
    keep, need_regen = {}, []
    for fam, rtype, split in FAMILIES:
        p = OUT / f"{fam}.json"
        if p.exists():
            wp = json.loads(p.read_text())["waypoints"]
            if _static_ok(wp, occ, meta, yaw):
                keep[fam] = (wp, _centroid(wp))
                continue
            oob = check_xy_bound(wp)
            rejected_dir.mkdir(parents=True, exist_ok=True)
            rej = json.loads(p.read_text())
            rej["rejected_reason"] = (
                f"exceeds +/-{RUNTIME_XY_LIMIT_M}m runtime XY control-authority "
                f"bound; out-of-bounds waypoints: {oob}") if oob else \
                "failed static re-gate (map/curvature)"
            (rejected_dir / f"{fam}__rejected.json").write_text(
                json.dumps(rej, indent=2))
            excluded.append({"route_family_id": fam, "route_type": rtype,
                             "reason": rej["rejected_reason"],
                             "out_of_bounds_waypoints": oob,
                             "preserved_as":
                             f"assets/experiments/hospital_h6_routes/rejected/{fam}__rejected.json"})
        need_regen.append((fam, rtype, split))

    kept_existing = list(keep.keys())
    placed = [c for (_, c) in keep.values()]

    # Pass 2 -- re-author only the families that need it, avoiding the kept
    # centroids; place() now also enforces the XY-bound.
    reauthored = []
    for fam, rtype, split in need_regen:
        wp, cent = place(TEMPLATES[rtype], occ, meta, yaw, placed)
        if wp is None:
            continue
        placed.append(cent)
        route = {"route_id": fam, "route_type": rtype, "waypoints": wp,
                 "start_pose": {"x": wp[0][0], "y": wp[0][1], "yaw_rad": 0.0},
                 "goal_pose": {"x": wp[-1][0], "y": wp[-1][1], "yaw_rad": 0.0},
                 "provenance":
                 f"H6 hard-route template, RE-AUTHORED within +/-{RUNTIME_XY_LIMIT_M}m "
                 f"runtime XY control-authority bound (prior placement left the box -> "
                 f"live precheck left_xy_bounds e-stop); decider-gated (check_map + "
                 f"check_xy_bound + check_curvature)"}
        (OUT / f"{fam}.json").write_text(json.dumps(route, indent=2))
        keep[fam] = (wp, cent)
        reauthored.append(fam)

    if excluded:
        (EVID / "h6_excluded_routes.json").write_text(json.dumps(excluded, indent=2))

    rows = []
    for fam, rtype, split in FAMILIES:
        if fam in keep:
            wp = keep[fam][0]
            length = sum(math.hypot(wp[i+1][0]-wp[i][0], wp[i+1][1]-wp[i][1])
                         for i in range(len(wp)-1))
            rows.append({"route_family_id": fam, "route_type": rtype,
                         "split_proposal": split, "n_waypoints": len(wp),
                         "route_length_m": round(length, 2),
                         "map_feasibility": "PASS", "xy_bound_feasibility": "PASS",
                         "yaw_feasibility": "PASS",
                         "decider_verdict": "PASS_DEMONSTRATION",
                         "route_file": f"assets/experiments/hospital_h6_routes/{fam}.json"})
        else:
            rows.append({"route_family_id": fam, "route_type": rtype,
                         "split_proposal": split, "n_waypoints": 0,
                         "map_feasibility": "FAIL", "xy_bound_feasibility": "FAIL",
                         "yaw_feasibility": "FAIL",
                         "decider_verdict": "REJECT_NO_PLACEMENT", "route_file": ""})

    cols = ["route_family_id", "route_type", "split_proposal", "n_waypoints",
            "route_length_m", "map_feasibility", "xy_bound_feasibility",
            "yaw_feasibility", "decider_verdict", "route_file"]
    with open(EVID / "h6_route_family_approval_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    npass = sum(r["decider_verdict"] == "PASS_DEMONSTRATION" for r in rows)
    print(f"{'family':20}{'type':22}{'split':16}{'nwp':>4}{'len':>7}  verdict")
    for r in rows:
        print(f"{r['route_family_id']:20}{r['route_type']:22}"
              f"{r['split_proposal']:16}{r.get('n_waypoints',0):>4}"
              f"{r.get('route_length_m',0):>7}  {r['decider_verdict']}")
    print(f"\nkept_existing={kept_existing}")
    print(f"re-authored={reauthored}")
    print(f"rejected_evidence={[e['route_family_id'] for e in excluded]}")
    print(f"PASS: {npass}/8")
    print("H6_PREFLIGHT_ROUTES_OK" if npass == 8 else "H6_PREFLIGHT_INCOMPLETE")


if __name__ == "__main__":
    main()
