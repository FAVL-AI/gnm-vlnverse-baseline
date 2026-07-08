"""Validate the MLOps governance cards for the scene-holdout milestone."""
import json, re, subprocess, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
C = REPO / "assets/experiments/mlops_cards"
R = REPO / "assets/experiments/training/scene_holdout_mnv2_baseline_20260708"

def fail(m): print(f"FAIL: {m}"); return False

def main():
    cards = {}
    for name, res in [("mobilenet_baseline_scene_holdout_seed42",
                       "baseline_test_results.json"),
                      ("mobilenet_ema0999_scene_holdout_seed42",
                       "ema0999_test_results.json")]:
        p = C / f"{name}.json"
        if not p.exists(): return fail(f"missing card {name}")
        card = json.loads(p.read_text()); cards[name] = card
        if card["metrics"]["n_test_episodes"] != 50:
            return fail(f"{name}: n != 50")
        if card["dataset"]["heldout_scene"] != "kujiale_0271":
            return fail(f"{name}: wrong test scene")
        truth = json.loads((R / res).read_text())
        for ck, tk in [("sr", "SR"), ("osr", "OSR"), ("ne_m", "NE"),
                       ("spl", "SPL")]:
            if abs(card["metrics"][ck] - truth[tk]) > 1e-6:
                return fail(f"{name}: {ck} card={card['metrics'][ck]} "
                            f"result={truth[tk]}")
        if card["metrics"]["collision_rate"] != "N/A offline":
            return fail(f"{name}: CR must be 'N/A offline'")
    dg = json.loads((C / "driftguard_scene_holdout_promotion_decision.json").read_text())
    if dg["decision"] != "reject_candidate" or \
            dg["raw_gate_output"]["decision"] != "reject":
        return fail("DriftGuard must reject the EMA candidate")
    vp = json.loads((C / "verdictplane_scene_holdout_action_record.json").read_text())
    if vp["verdict"] != "deny" or vp["action"] != "promote_model":
        return fail("VerdictPlane must deny promote_model")
    sen = json.loads((C / "sentinel_scene_holdout_incident_summary.json").read_text())
    if "proxy_gap" not in sen["incident_type"]:
        return fail("Sentinel incident summary wrong type")
    pilot = (REPO / "docs/research/GNM_VLNVERSE_GOVERNANCE_PILOT.md")
    if not pilot.exists(): return fail("pilot doc missing from docs/research/")
    alltext = " ".join((pilot.read_text() + json.dumps(cards)).lower().split())
    if "ema improved" in alltext or "full vlnverse benchmark submission." not in alltext:
        return fail("claim boundary violated")
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"],
                            capture_output=True, text=True, cwd=REPO).stdout
    if re.search(r"\.(pt|pth|ckpt|db3|mcap|mp4)$", staged, re.M):
        return fail("heavy artifacts staged")
    print("governance cards valid: both run cards (n=50, kujiale_0271, "
          "metrics match result JSONs, CR N/A offline); DriftGuard "
          "reject_candidate; VerdictPlane deny; Sentinel proxy-gap "
          "incident; pilot doc in docs/research/; claim boundaries hold; "
          "no heavy artifacts staged")
    print("PASS: MLOps governance cards validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
