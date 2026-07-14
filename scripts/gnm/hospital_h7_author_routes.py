"""Author 8 H7-Hospital driving routes (4 families x 2 variants) in the bring-up
route schema. Waypoints are anchored on render-CONFIRMED free floor: the v1 of each
family reuses the exact robot-height camera positions from the gated pilot capture
(each rendered clear open floor at 0.35 m); v2 is a small parallel offset in the
same open zone. The driving smoke's collision report is the ground truth — any
route that collides gets re-authored. Coordinates stay in the central lobby
(x in [-2.6, 1.5], y in [-0.8, 1.1]) away from reception desk, wheelchair/vending,
glass doors, and walls.
"""
import json
import math
from pathlib import Path

OUT = Path("/home/favl/robotics/gnm-vlnverse-baseline/assets/experiments/"
           "hospital_h7_collection/routes")
OUT.mkdir(parents=True, exist_ok=True)

FAMILIES = {
    "reception_to_corridor": [
        ("h7_reception_01", [(-2.6, -0.8), (-0.8, -0.2), (1.2, 0.0)]),   # pilot v1 (confirmed)
        ("h7_reception_02", [(-2.6, -0.3), (-0.8, 0.2), (1.0, 0.4)]),
    ],
    "corridor_straight": [
        # goals trimmed to x=1.0 to stay inside the drive-validated envelope
        # (3 clean drives reached x~1.0; x>1.0 nears the vending/wheelchair band).
        ("h7_corridor_01", [(-1.5, 0.0), (0.0, 0.0), (1.0, 0.0)]),
        ("h7_corridor_02", [(-1.5, 0.6), (0.0, 0.6), (1.0, 0.6)]),
    ],
    "turn_t_junction": [
        ("h7_turn_01", [(-1.0, 0.8), (0.2, 0.8), (0.2, -0.2)]),          # L: +x then -y
        ("h7_turn_02", [(-1.0, -0.2), (0.2, -0.2), (0.2, 0.8)]),         # L: +x then +y
    ],
    "waiting_to_doorway": [
        ("h7_waiting_01", [(-2.2, 1.0), (-0.5, 0.4), (1.0, -0.2)]),      # diagonal
        ("h7_waiting_02", [(-2.0, 0.6), (-0.4, 0.1), (0.9, -0.4)]),
    ],
}


def yaw(a, b):
    return round(math.atan2(b[1] - a[1], b[0] - a[0]), 4)


manifest = {"dataset": "H7-Hospital Front-RGB ImageNav", "scene": "hospital",
            "asset": "Isaac 5.1 hospital.usd", "routes": []}
for rtype, variants in FAMILIES.items():
    for rid, wps in variants:
        length = sum(math.dist(wps[i], wps[i + 1]) for i in range(len(wps) - 1))
        route = {
            "route_id": rid, "route_type": rtype,
            "waypoints": [[round(x, 3), round(y, 3)] for x, y in wps],
            "start_pose": {"x": wps[0][0], "y": wps[0][1], "yaw_rad": yaw(wps[0], wps[1])},
            "goal_pose": {"x": wps[-1][0], "y": wps[-1][1], "yaw_rad": yaw(wps[-2], wps[-1])},
            "provenance": ("H7-Hospital route authored on render-confirmed free lobby floor "
                           "(v1 = gated-pilot robot-height camera positions); scene-identity "
                           "gated at record time; collision-report is ground truth."),
        }
        (OUT / f"{rid}.json").write_text(json.dumps(route, indent=2))
        manifest["routes"].append({"route_id": rid, "route_type": rtype,
                                   "n_waypoints": len(wps), "length_m": round(length, 2)})
        print(f"wrote {rid}: {len(wps)} wp, {length:.2f} m")

(OUT / "h7_routes_manifest.json").write_text(json.dumps(manifest, indent=2))
print(f"\n{len(manifest['routes'])} routes -> {OUT}")
