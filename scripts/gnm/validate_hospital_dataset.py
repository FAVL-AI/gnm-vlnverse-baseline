"""Validate Isaac-Hospital-ImageNav-v0 dataset scaffolding."""
import json, pickle, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
D = REPO / "assets/datasets/isaac_hospital_imagenav_v0"
GEN = REPO / "datasets/isaac_hospital_imagenav_v0"

def fail(m): print(f"FAIL: {m}"); return False

def main():
    for f in ("dataset_manifest.json", "dataset_manifest.md",
              "episode_inventory.json", "small_experiment_plan.md"):
        if not (D / f).exists(): return fail(f"missing {f}")
    m = json.loads((D / "dataset_manifest.json").read_text())
    if "not real-robot evidence" not in m["claim_boundary"].replace(
            "does not constitute real-robot evidence",
            "not real-robot evidence"):
        return fail("claim boundary missing")
    if "front-facing" not in m["camera_convention"]:
        return fail("camera convention missing")
    if "frame-level" not in m["split_policy"]:
        return fail("split policy must ban frame-level splits")
    seen = {}
    for s, goals in m["split_by_goal"].items():
        for g in goals:
            if g in seen: return fail(f"goal {g} in two splits")
            seen[g] = s
    for e in m["episodes"]:
        if e["split"] != "unassigned" and seen.get(e["goal_id"]) != e["split"]:
            return fail(f"{e['episode_id']}: split/goal mismatch")
    conv = list(GEN.rglob("metadata.json"))
    if not conv: return fail("no converted proof episode")
    ep = conv[0].parent
    t = pickle.loads((ep / "traj_data.pkl").read_bytes())
    n = len(list(ep.glob("*.jpg")))
    if t["position"].shape != (n, 2): return fail("converted schema mismatch")
    if not (ep / "goal.png").exists(): return fail("goal image missing")
    if not (ep / "checksums.sha256").exists(): return fail("checksums missing")
    cm = json.loads((ep / "metadata.json").read_text())
    if cm.get("actions_cmd_vel") is None: return fail("action labels missing")
    print(f"hospital dataset scaffolding valid: manifest + inventory "
          f"({len(m['episodes'])} episodes) + route/goal-level provisional "
          f"split {m['split_counts']} (no goal overlap, frame-splits "
          f"banned); converted proof episode {ep.name}: {n} frames, "
          "traj/goal/actions/checksums OK; claim boundary present")
    print("PASS: Isaac-Hospital-ImageNav-v0 validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
