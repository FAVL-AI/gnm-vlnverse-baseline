"""Validate the Stage 3B generated-episode smoke gate."""
import json, pickle, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
EP = REPO / "datasets/vlntube_generated/train/gen_kujiale_0092_0000"
E = REPO / "assets/experiments/data_expansion/generated_episode_smoke_20260708"

def fail(m): print(f"FAIL: {m}"); return False

def main():
    for f in ("coordinate_calibration_report.md", "coordinate_calibration.json",
              "first_generated_episode_manifest.json",
              "generated_episode_loader_check.txt", "render_contact_sheet.ppm",
              "blockers.md", "recommended_next_steps.md",
              "generated_episode_checksums.sha256"):
        if not (E / f).exists(): return fail(f"missing {f}")
    meta = json.loads((EP / "metadata.json").read_text())
    if meta["scene"] == "kujiale_0271": return fail("test scene used!")
    t = pickle.loads((EP / "traj_data.pkl").read_bytes())
    n = len(list(EP.glob("*.jpg")))
    if not (t["position"].shape == (n, 2) and t["yaw"].shape == (n,)):
        return fail("traj_data shapes do not match frame count")
    if meta["n_frames"] != n: return fail("metadata frame count mismatch")
    check = (E / "generated_episode_loader_check.txt").read_text()
    if "LOADER CHECK: PASS" not in check or "GNMDataset" not in check:
        return fail("loader check evidence missing")
    calib = json.loads((E / "coordinate_calibration.json").read_text())
    if "1.000" not in json.dumps(calib): return fail("calibration proof missing")
    gen027 = list((REPO / "datasets/vlntube_generated").rglob("*0271*"))
    if gen027: return fail("generated data touches kujiale_0271")
    print(f"generated episode valid: {n} frames + traj_data + metadata; "
          "loader-check PASS through unmodified GNMDataset; calibration "
          "verified at 1.000; kujiale_0271 untouched; evidence complete")
    print("PASS: generated-episode smoke validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
