"""Validate the scene-level held-out split manifest."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
M = REPO / ("assets/experiments/training_ablation/mnv2_ema_20260708/"
            "dataset_manifest_scene_holdout.json")

def fail(m): print(f"FAIL: {m}"); return False

def main():
    if not M.exists(): return fail("scene-holdout manifest missing")
    m = json.loads(M.read_text())
    eps = m["episodes"]
    ids = [e["episode_id"] for e in eps]
    if len(set(ids)) != len(ids): return fail("duplicate episode IDs")
    for e in eps:
        if not (REPO / e["trajectory_path"]).exists():
            return fail(f"missing path {e['trajectory_path']}")
        if not (REPO / e["goal_image_path"]).exists():
            return fail(f"missing goal image for {e['episode_id']}")
    tr = {e["scene_id"] for e in eps if e["split"] in ("train", "val")}
    te = {e["scene_id"] for e in eps if e["split"] == "test_scene_holdout"}
    if tr & te: return fail(f"scene overlap: {tr & te}")
    tr_traj = {e["trajectory_id"] for e in eps if e["split"] in ("train", "val")}
    te_traj = {e["trajectory_id"] for e in eps if e["split"] == "test_scene_holdout"}
    if tr_traj & te_traj: return fail("trajectory overlap")
    s = m["split_summary"]
    counts = {k: sum(1 for e in eps if e["split"] == v)
              for k, v in [("train", "train"), ("val", "val"),
                           ("test_scene_holdout", "test_scene_holdout")]}
    for k in counts:
        if counts[k] != s[k]: return fail(f"count mismatch {k}")
    if not m["leakage_check"]["scene_level_holdout"]:
        return fail("scene_level_holdout not asserted")
    banned = ("improved performance", "benchmark complete")
    txt = json.dumps(m).lower()
    for b in banned:
        if b in txt: return fail(f"claim violation: {b}")
    if "no performance claims" not in " ".join(m["usage_rules"]):
        return fail("no-claim usage rule missing")
    print(f"scene-holdout split valid: train {s['train']} / val {s['val']} "
          f"/ test {s['test_scene_holdout']} ({m['scenes']['test_scene_holdout']}); "
          "zero scene/trajectory/episode overlap; all paths + goal images "
          "exist; no performance claims")
    print("PASS: scene-level held-out split validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
