"""Validate the Stage 3D expanded generated training set (130 episodes)."""
import json, pickle, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "datasets/vlntube_generated/train"
E = REPO / "assets/experiments/data_expansion/generated_train_expanded_20260708"
TRAIN_SCENES = {"kujiale_0092", "kujiale_0118", "kujiale_0203"}
CAM = {"z_m": 2.4, "focal_mm": 16.0, "rotation": "rotateXYZ(0,0,deg(yaw))"}

def fail(m): print(f"FAIL: {m}"); return False

def main():
    for f in ("generation_config.yaml", "generated_expanded_manifest.json",
              "generated_expanded_summary.csv",
              "weak_goal_resampling_report.md", "route_quality_summary.md",
              "camera_model_lock.md", "generated_loader_validation.txt",
              "contact_sheet_before_after.png", "blockers.md",
              "recommended_next_steps.md"):
        if not (E / f).exists(): return fail(f"missing {f}")
    eps = sorted(d for d in GEN.iterdir() if d.is_dir())
    if len(eps) != 130: return fail(f"expected 130 episodes, got {len(eps)}")
    pairs, weak = set(), 0
    for d in eps:
        m = json.loads((d / "metadata.json").read_text())
        if m["scene"] not in TRAIN_SCENES:
            return fail(f"{d.name}: scene {m['scene']}")
        cam = m["camera"]
        if (cam["z_m"], cam["focal_mm"], cam["rotation"]) != \
                (CAM["z_m"], CAM["focal_mm"], CAM["rotation"]):
            return fail(f"{d.name}: camera model not the locked top-down "
                        f"convention: {cam}")
        n = len(list(d.glob("*.jpg")))
        t = pickle.loads((d / "traj_data.pkl").read_bytes())
        if n < 8 or t["position"].shape != (n, 2) or t["yaw"].shape != (n,):
            return fail(f"{d.name}: schema mismatch")
        if not (2.0 <= m["path_length_m"] <= 6.5):
            return fail(f"{d.name}: path length {m['path_length_m']}")
        if not (d / f"{n-1}.jpg").exists():
            return fail(f"{d.name}: goal image missing")
        if "clearance_min_m" not in m["route_quality"]:
            return fail(f"{d.name}: quality score missing")
        if not m["route_quality"]["goal_frame_ok"]:
            weak += 1
        key = (m["scene"], tuple(t["position"][0].round(1)),
               tuple(t["position"][-1].round(1)))
        if key in pairs: return fail(f"{d.name}: duplicate route")
        pairs.add(key)
    if weak: return fail(f"{weak} weak goal frames remain")
    if any("0271" in d.name for d in eps): return fail("test scene present")
    check = (E / "generated_loader_validation.txt").read_text()
    if "LOADER CHECK: PASS" not in check or "130" not in check:
        return fail("loader evidence missing")
    man = json.loads((E / "generated_expanded_manifest.json").read_text())
    if "does not claim improved model performance" not in man["claim"]:
        return fail("claim boundary missing")
    if "TOP-DOWN" not in man["camera_regime"]:
        return fail("camera regime statement missing")
    print(f"expanded set valid: 130 episodes ({man['per_scene']}), "
          "train scenes only, kujiale_0271 absent; locked top-down camera "
          "on every episode; schemas/goal images/dedup OK; goal content "
          "130/130; loader PASS; no performance claims")
    print("PASS: expanded generated training set validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
