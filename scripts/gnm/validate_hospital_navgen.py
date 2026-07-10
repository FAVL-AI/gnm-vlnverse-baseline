"""Validate Isaac-Hospital-NavGen-v0 scaffolding and pilot episodes."""
import json, pickle, subprocess, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
D = REPO / "assets/datasets/isaac_hospital_navgen_v0"
GEN = REPO / "datasets/isaac_hospital_navgen_v0/unassigned"

def fail(m): print(f"FAIL: {m}"); return False

def main():
    for f in ("scene_semantics.json", "safety_zones.json",
              "pilot_routes.json"):
        if not (D / f).exists(): return fail(f"missing {f}")
    routes = json.loads((D / "pilot_routes.json").read_text())["routes"]
    keys = {(tuple(r["start_world"]), tuple(r["goal_world"])) for r in routes}
    if len(keys) != len(routes): return fail("duplicate start/goal pairs")
    for r in routes:
        if r["zone_profile"]["red_fraction"] != 0.0:
            return fail(f"{r['route_id']}: red zone on planned route")
        if "front-facing" not in r["camera_convention"]:
            return fail("camera convention not front-facing")
    if not GEN.exists() or not any(GEN.iterdir()):
        return fail("no rendered pilot episodes yet")
    for ep in GEN.iterdir():
        m = json.loads((ep / "metadata.json").read_text())
        for f in ("goal.png", "traj_data.pkl", "instruction.json",
                  "metadata.json", "zone_trace.json", "checksums.sha256"):
            if not (ep / f).exists(): return fail(f"{ep.name}: missing {f}")
        n = len(list(ep.glob("[0-9]*.jpg")))
        t = pickle.loads((ep / "traj_data.pkl").read_bytes())
        if t["position"].shape != (n, 2): return fail(f"{ep.name}: schema")
        if "front-facing" not in m["camera"]["convention"]:
            return fail(f"{ep.name}: camera convention")
        if "not real-robot" not in m["claim"]:
            return fail(f"{ep.name}: claim boundary")
    r = subprocess.run(["python3",
                        "scripts/datasets/hospital_navgen_verify_episode.py",
                        str(GEN)], capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0: return fail("verifier failed:\n" + r.stdout[-400:])
    print(f"navgen valid: semantics+zones+routes (no red on routes, no "
          f"duplicates, front-camera); {len(list(GEN.iterdir()))} pilot "
          "episodes complete with instructions/zone traces; verifier PASS")
    print("PASS: Isaac-Hospital-NavGen-v0 validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
