"""Validate the Stage 4/5 expanded-data training experiment."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
R = REPO / "assets/experiments/training/expanded_topdown_20260708"

def fail(m): print(f"FAIL: {m}"); return False

def main():
    for f in ("expanded_test_results.json", "comparison_expanded_vs_incumbent.json",
              "checkpoint_manifest.sha256", "cuda_verification.json",
              "commands.sh", "driftguard_decision.json",
              "verdictplane_action_record.json", "sentinel_incidents.json",
              "professor_expanded_data_result_note.md", "run_card.json"):
        if not (R / f).exists(): return fail(f"missing {f}")
    res = json.loads((R / "expanded_test_results.json").read_text())
    comp = json.loads((R / "comparison_expanded_vs_incumbent.json").read_text())
    row = [r for r in comp["rows"] if r["model"] == "expanded_321"][0]
    for ck, tk in [("SR", "SR"), ("OSR", "OSR"), ("NE_m", "NE"), ("SPL", "SPL")]:
        if abs(row[ck] - res[tk]) > 1e-6:
            return fail(f"comparison {ck} mismatch vs result JSON")
    if "N/A" not in row["CR"]: return fail("CR not N/A offline")
    dg = json.loads((R / "driftguard_decision.json").read_text())
    vp = json.loads((R / "verdictplane_action_record.json").read_text())
    if dg["decision"] != "reject": return fail("DriftGuard decision mismatch")
    if vp["verdict"] != "deny": return fail("VerdictPlane verdict mismatch")
    note = " ".join((R / "professor_expanded_data_result_note.md").read_text().split())
    if "NOT promoted" not in note or "not a full VLNVerse benchmark" not in note:
        return fail("note missing claim guards")
    if "improved" in note.lower() and "does not automatically transfer" not in note:
        return fail("banned improvement claim")
    ckpt = (R / "checkpoint_manifest.sha256").read_text().split()[1]
    if not (REPO / ckpt).exists(): return fail("checkpoint missing")
    exp = REPO / "datasets/vlntube_expanded"
    if any("0271" in p.name for p in (exp / "train").iterdir()):
        return fail("kujiale_0271 leaked into expanded train root")
    print("expanded-data experiment valid: results/comparison consistent, "
          "CR N/A offline, DriftGuard reject + VerdictPlane deny recorded, "
          "no leakage, checkpoint hashed, claim guards present")
    print("PASS: expanded-data training experiment validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
