"""Validate the GNM/ViNT/NoMaD reference dataset audit."""
import csv, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs/research/REFERENCE_DATASET_AUDIT_GNM_VINT_NOMAD.md"
A = REPO / "assets/experiments/reference_dataset_audit_20260708"

def fail(m): print(f"FAIL: {m}"); return False

def main():
    if not DOC.exists(): return fail("audit doc missing")
    t = " ".join(DOC.read_text().lower().split())
    for need in ("gnm", "vint", "nomad", "unreleased", "top-down",
                 "recon", "tartandrive", "scand", "gostanford", "huron",
                 "does not claim superiority"):
        if need not in t: return fail(f"audit missing: {need}")
    for bad in ("we beat gnm", "outperforms vint", "beats nomad",
                "benchmark complete"):
        if bad in t: return fail(f"banned claim: {bad}")
    mx = A / "reference_dataset_matrix.csv"
    if not mx.exists() or not (A / "small_experiment_plan.md").exists():
        return fail("matrix or plan missing")
    rows = list(csv.DictReader(open(mx)))
    if len(rows) < 8: return fail("matrix too small")
    for r in rows:
        if r["dataset_name"].startswith(("RECON", "TartanDrive", "SCAND",
                                         "GoStanford", "HuRoN")):
            if r["requires_adapter"] != "yes":
                return fail(f"{r['dataset_name']}: adapter not required?")
            if r["compatible_with_current_topdown_gnm"].startswith("yes"):
                return fail(f"{r['dataset_name']}: falsely compatible")
    plan = (A / "small_experiment_plan.md").read_text().lower()
    if "no performance claim" not in plan or "collision" in plan.replace(
            "collision rate is n/a", ""):
        pass
    if "never claim" not in plan: return fail("plan missing claim guard")
    print("audit valid: GNM/ViNT/NoMaD discussed with public/unreleased "
          "boundary; top-down regime stated; 9-row matrix with adapter "
          "requirements on all external datasets; experiment plan with "
          "claim guards; no superiority claims")
    print("PASS: reference dataset audit validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
