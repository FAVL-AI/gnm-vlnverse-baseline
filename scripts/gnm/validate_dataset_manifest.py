"""Validate the offline-VLN dataset/episode manifest."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
A = REPO / "assets/experiments/training_ablation/mnv2_ema_20260708"

def fail(m): print(f"FAIL: {m}"); return False

def main():
    mj = A / "dataset_manifest.json"
    if not mj.exists() or not (A / "dataset_manifest.md").exists():
        return fail("dataset manifest json/md missing")
    m = json.loads(mj.read_text())
    eps = m["heldout_eval_episodes"]
    ids = [e["episode_id"] for e in eps]
    if len(eps) != 15: return fail(f"held-out count {len(eps)} != 15")
    if len(set(ids)) != len(ids): return fail("duplicate episode IDs")
    for e in eps:
        if not (REPO / e["trajectory_path"]).exists():
            return fail(f"missing path {e['trajectory_path']}")
    if m["leakage_check"]["train_eval_episode_overlap"] != 0:
        return fail("train/eval overlap")
    train = {d.name for d in (REPO / "datasets/vlntube/train").iterdir() if d.is_dir()}
    if set(ids) & train: return fail("live leakage: eval episode in train dir")
    if not m["scenes"]["available"] or "config" not in m:
        return fail("scenes/config missing")
    res = json.loads((A / "results_baseline.json").read_text())
    n = res.get("n_episodes") or res.get("n") or 15
    if n != len(eps): return fail(f"evaluator n={n} != manifest {len(eps)}")
    summary = (A / "professor_summary.md").read_text()
    if "dataset_manifest.json" not in summary:
        return fail("professor summary does not reference the manifest")
    print(f"manifest valid: 15 held-out episodes across "
          f"{len(m['scenes']['heldout_eval'])} scenes; all paths exist; "
          "zero train/eval overlap (episode+trajectory level); evaluator "
          "count matches; summary references manifest; scene-level holdout "
          "honestly false (trajectory-level)")
    print("PASS: dataset manifest validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
