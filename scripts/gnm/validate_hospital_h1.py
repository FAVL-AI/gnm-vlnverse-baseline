"""Validate the Hospital H1 experiment package."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
E = REPO / "assets/experiments/hospital_h1_front_rgb_finetune_20260708"
SPLIT_ROOT = REPO / "datasets/isaac_hospital_split"

def fail(m): print(f"FAIL: {m}"); return False

def main():
    for f in ("hospital_dataset_conversion_summary.csv",
              "hospital_split_manifest.json", "training_commands.sh",
              "evaluation_commands.sh", "baseline_hospital_eval.json",
              "finetuned_hospital_eval.json", "comparison_table.md",
              "checkpoint_manifest.sha256", "wandb_manifest.json",
              "professor_hospital_h1_note.md", "claim_boundaries.md",
              "hospital_topdown_incumbent_eval_card.json",
              "hospital_front_rgb_finetune_card.json",
              "driftguard_hospital_finetune_decision.json",
              "sentinel_hospital_domain_shift_summary.json",
              "verdictplane_hospital_model_action_record.json"):
        if not (E / f).exists(): return fail(f"missing {f}")
    sm = json.loads((E / "hospital_split_manifest.json").read_text())
    goals = {}
    for ep in sm["episodes"]:
        g = ep["goal_id"]
        if g in goals and goals[g] != ep["split"]:
            return fail(f"goal {g} leaks across splits")
        goals[g] = ep["split"]
    if sum(1 for e in sm["episodes"]) != 24:
        return fail("not all 24 episodes accounted for")
    if "frame-level splits banned" not in sm["policy"]:
        return fail("frame-split ban missing")
    ft = json.loads((E / "finetuned_hospital_eval.json").read_text())
    card = json.loads((E / "hospital_front_rgb_finetune_card.json").read_text())
    for ck, tk in [("sr", "SR"), ("ne_m", "NE"), ("spl", "SPL")]:
        if abs(card["metrics"][ck] - ft[tk]) > 1e-6:
            return fail(f"card {ck} not from result JSON")
    if card["metrics"]["collision_rate"] != "N/A offline":
        return fail("CR must be N/A offline")
    if "front-facing" not in card["dataset"]["camera"]:
        return fail("front-camera convention missing")
    dg = json.loads((E / "driftguard_hospital_finetune_decision.json").read_text())
    vp = json.loads((E / "verdictplane_hospital_model_action_record.json").read_text())
    if dg["decision"] not in ("promote", "reject", "human_review"):
        return fail("DriftGuard decision malformed")
    if vp["verdict"] not in ("allow", "deny", "require_human"):
        return fail("VerdictPlane verdict malformed")
    cb = (E / "claim_boundaries.md").read_text().lower()
    for need in ("not real-robot", "not a full vlnverse", "mixing"):
        if need not in cb: return fail(f"claim boundary missing {need}")
    for split, expect in (("train", 12), ("val", 4), ("test", 8)):
        n = len(list((SPLIT_ROOT / split).iterdir()))
        if n != expect: return fail(f"{split} count {n} != {expect}")
    print(f"H1 valid: 24/24 episodes converted+split (12/4/8, no goal "
          f"leakage, frame-splits banned); metrics from result JSONs; CR "
          f"N/A offline; DriftGuard {dg['decision']} + VerdictPlane "
          f"{vp['verdict']} recorded; front-camera convention + claim "
          "boundaries present")
    print("PASS: Hospital H1 validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
