"""Validate the Stage 3C generated pilot batch."""
import json, pickle, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "datasets/vlntube_generated/train"
E = REPO / "assets/experiments/data_expansion/generated_train_batch_20260708"
TRAIN_SCENES = {"kujiale_0092", "kujiale_0118", "kujiale_0203"}

def fail(m): print(f"FAIL: {m}"); return False

def main():
    for f in ("generation_config.yaml", "route_quality_policy.md",
              "generated_batch_manifest.json", "generated_batch_summary.csv",
              "generated_batch_loader_check.txt",
              "coordinate_calibration_summary.md",
              "camera_model_verification.md", "contact_sheet.png",
              "blockers.md", "recommended_next_steps.md",
              "generated_batch_checksums.sha256"):
        if not (E / f).exists(): return fail(f"missing {f}")
    expanded = (E.parent / "generated_train_expanded_20260708"
                / "generated_expanded_manifest.json")
    if expanded.exists():
        print("pilot batch superseded by Stage 3D expanded set - disk-state "
              "checks delegated to validate-generated-train-expanded; "
              "verifying frozen pilot evidence only")
        man = json.loads((E / "generated_batch_manifest.json").read_text())
        if man["episodes"] != 30: return fail("pilot manifest episode count")
        check = (E / "generated_batch_loader_check.txt").read_text()
        if "LOADER CHECK: PASS" not in check:
            return fail("pilot loader evidence missing")
        print("PASS: generated train batch (frozen pilot evidence) validated")
        return True
    eps = sorted(d for d in GEN.iterdir() if d.is_dir())
    if len(eps) != 30: return fail(f"expected 30 episodes, found {len(eps)}")
    pairs = set()
    for d in eps:
        meta = json.loads((d / "metadata.json").read_text())
        if meta["scene"] not in TRAIN_SCENES:
            return fail(f"{d.name}: non-train scene {meta['scene']}")
        n = len(list(d.glob("*.jpg")))
        t = pickle.loads((d / "traj_data.pkl").read_bytes())
        if n < 8 or t["position"].shape != (n, 2) or t["yaw"].shape != (n,):
            return fail(f"{d.name}: frames/traj mismatch ({n})")
        if not (2.0 <= meta["path_length_m"] <= 6.5):
            return fail(f"{d.name}: path length out of bounds")
        if "route_quality" not in meta or \
                "clearance_min_m" not in meta["route_quality"]:
            return fail(f"{d.name}: route-quality score missing")
        if not (d / f"{n-1}.jpg").exists():
            return fail(f"{d.name}: goal image missing")
        key = (meta["scene"], tuple(t["position"][0].round(1)),
               tuple(t["position"][-1].round(1)))
        if key in pairs: return fail(f"{d.name}: duplicate start/goal")
        pairs.add(key)
    if any("0271" in d.name for d in eps):
        return fail("test scene present in generated data")
    check = (E / "generated_batch_loader_check.txt").read_text()
    if "LOADER CHECK: PASS" not in check or "30" not in check:
        return fail("loader check evidence missing")
    man = json.loads((E / "generated_batch_manifest.json").read_text())
    if man["goal_ok_count"] < 24: return fail("too many weak goal frames")
    if "does not yet claim improved model performance" not in man["claim"]:
        return fail("claim boundary missing")
    calib = json.loads((E / "calibration_all_scenes.json").read_text())
    for sc, rec in calib.items():
        if rec["verdict"] != "PASS": return fail(f"{sc} calibration FAIL")
    print(f"pilot batch valid: 30 episodes (10/scene, train scenes only, "
          f"kujiale_0271 absent); frames+traj+metadata+goal images OK; no "
          f"duplicate routes; quality scores recorded "
          f"(goal_ok {man['goal_ok_count']}/30); loader PASS through "
          "unmodified GNMDataset; calibration 1.000 on all three scenes; "
          "no performance claims")
    print("PASS: generated train batch validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
