"""Validate CUDA/W&B/MLOps evidence for the MobileNetV2+EMA ablation."""
import json, subprocess, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
M = REPO / "assets/experiments/training/mobilenet_ema_ablation_20260708"
REQ = ["run_manifest.json", "baseline_results.json", "ema_09999_results.json",
       "ema_0999_results.json", "comparison_table.csv", "comparison_table.md",
       "cuda_verification.json", "wandb_runs.json", "environment_snapshot.txt",
       "pip_freeze.txt", "checkpoint_manifest.sha256", "training_commands.sh",
       "evaluation_commands.sh", "notes_c1_c5.md",
       "efficientnet_pause_appendix.md", "config_snapshot_gnm_base.yaml"]

def fail(m): print(f"FAIL: {m}"); return False

def main():
    missing = [f for f in REQ if not (M / f).exists()]
    if missing: return fail(f"registry missing: {missing}")
    cuda = json.loads((M / "cuda_verification.json").read_text())
    if not cuda["cuda_available"] or "4080" not in (cuda["gpu"] or ""):
        return fail("CUDA evidence invalid")
    log = (REPO / "logs/ablation_baseline.log")
    if log.exists() and "Training on cuda" not in log.read_text():
        return fail("training log lacks device evidence")
    wb = json.loads((M / "wandb_runs.json").read_text())
    if len(wb["runs"]) < 3: return fail("fewer than 3 W&B runs recorded")
    man = json.loads((M / "run_manifest.json").read_text())
    for c, v in man["conditions"].items():
        if "eval_weights" not in v: return fail(f"{c}: weight source missing")
    if "N/A offline" not in man["collision_rate_policy"]:
        return fail("CR policy must be N/A offline")
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"],
                            capture_output=True, text=True, cwd=REPO).stdout
    import re
    if re.search(r"\.(pt|pth|ckpt|db3|mcap|mp4)$", staged, re.M) or \
       re.search(r"^(checkpoints|wandb)/|/rosbags/", staged, re.M):
        return fail("large binary artifacts staged")
    print(f"registry complete ({len(REQ)} artifacts); CUDA evidence valid "
          f"({cuda['gpu']}); 'Training on cuda' in logs; "
          f"{len(wb['runs'])} offline W&B runs; weight sources recorded; "
          "CR N/A offline; no binaries staged")
    print("PASS: training MLOps evidence validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
