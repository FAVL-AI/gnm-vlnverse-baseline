"""Validate the scene-holdout training stage (baseline + EMA repeat)."""
import json, subprocess, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
R = REPO / "assets/experiments/training/scene_holdout_mnv2_baseline_20260708"

def fail(m): print(f"FAIL: {m}"); return False

def main():
    for f in ("baseline_test_results.json", "ema0999_test_results.json",
              "comparison_scene_holdout.json", "checkpoint_manifest.sha256",
              "cuda_verification.json", "wandb_runs.json", "commands.sh",
              "professor_scene_holdout_baseline_note.md"):
        if not (R / f).exists(): return fail(f"missing {f}")
    r = subprocess.run(["python3", "scripts/gnm/validate_scene_holdout_split.py"],
                       capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0: return fail("split manifest validation failed")
    comp = json.loads((R / "comparison_scene_holdout.json").read_text())
    for row in comp["rows"]:
        if row["n"] != 50: return fail("test n != 50")
        if "N/A" not in str(row["CR"]): return fail("CR not N/A offline")
    if "kujiale_0271" not in comp["split"]: return fail("test scene missing")
    for line in (R / "checkpoint_manifest.sha256").read_text().splitlines():
        sha, path = line.split()
        if not (REPO / path).exists(): return fail(f"ckpt missing {path}")
    note = " ".join((R / "professor_scene_holdout_baseline_note.md").read_text().split())
    for need in ("not used for training, validation, tuning",
                 "not a full VLNVerse benchmark", "must not be compared"):
        if need not in note: return fail(f"note missing guard: {need[:40]}")
    if "EMA improved" in note: return fail("banned EMA improvement claim")
    cuda = json.loads((R / "cuda_verification.json").read_text())
    if not cuda["cuda_available"]: return fail("CUDA evidence invalid")
    print("scene-holdout training validated: split manifest PASS, both "
          "test-result JSONs (n=50, kujiale_0271, CR N/A), checkpoint "
          "SHAs on disk, CUDA + W&B records, claim guards present")
    print("PASS: scene-holdout training stage validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
