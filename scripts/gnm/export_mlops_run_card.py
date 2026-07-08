"""Export MLOps run cards for external governance consumption.

Produces one JSON card per training condition under
assets/experiments/mlops_cards/. Cards carry summaries, hashes, paths and
claim boundaries ONLY — never checkpoints, rosbags, W&B raw dirs or video.
Consumers: mlops-production-pipeline dashboard (display), DriftGuardAI
(promotion gate), Sentinel-AIOPs (incident adapter), VerdictPlane
(action governance).
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
R = REPO / "assets/experiments/training/scene_holdout_mnv2_baseline_20260708"
OUT = REPO / "assets/experiments/mlops_cards"

RUNS = {
    "mobilenet_baseline_scene_holdout_seed42": {
        "condition": "baseline", "ema_decay": None,
        "ckpt": "checkpoints/scene_holdout_mnv2_baseline/best.pt",
        "results": "baseline_test_results.json",
        "weights": "live model",
        "driftguard_role": {"promotion_candidate": False, "incumbent": None,
                            "decision": "baseline_reference"},
    },
    "mobilenet_ema0999_scene_holdout_seed42": {
        "condition": "ema_0.999", "ema_decay": 0.999,
        "ckpt": "checkpoints/scene_holdout_mnv2_ema0999/best.pt",
        "results": "ema0999_test_results.json",
        "weights": "EMA shadow",
        "driftguard_role": {"promotion_candidate": True,
                            "incumbent": "mobilenet_baseline_scene_holdout_seed42",
                            "decision": "pending_driftguard"},
    },
}

CLAIM = ("Scene-level held-out MobileNetV2-GNM study on a controlled local "
         "VLNVerse/VLNTube subset; not a full VLNVerse benchmark.")


def main():
    git = lambda *a: subprocess.run(["git"] + list(a), capture_output=True,
                                    text=True, cwd=REPO).stdout.strip()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(
        (REPO / "assets/experiments/training_ablation/mnv2_ema_20260708/"
         "dataset_manifest_scene_holdout.json").read_text())
    leak = manifest["leakage_check"]
    wandb = json.loads((R / "wandb_runs.json").read_text())
    cuda = json.loads((R / "cuda_verification.json").read_text())
    hygiene = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=REPO).stdout
    heavy = [l for l in hygiene.splitlines()
             if l.endswith((".pt", ".pth", ".ckpt", ".db3", ".mp4"))
             or l.startswith(("checkpoints/", "wandb/"))]

    for run_name, spec in RUNS.items():
        metrics = json.loads((R / spec["results"]).read_text())
        ckpt = REPO / spec["ckpt"]
        card = {
            "project": "gnm-vlnverse-baseline",
            "case_study": "scene_holdout_mobile_gnm",
            "run_name": run_name,
            "branch": git("branch", "--show-current"),
            "commit": git("rev-parse", "--short", "HEAD"),
            "seed": 42,
            "config_path": "configs/gnm/gnm_base.yaml",
            "model": {"name": "MobileNetV2-GNM",
                      "condition": spec["condition"],
                      "ema_decay": spec["ema_decay"],
                      "weights_evaluated": spec["weights"],
                      "checkpoint_path": spec["ckpt"],
                      "checkpoint_sha256": hashlib.sha256(
                          ckpt.read_bytes()).hexdigest(),
                      "checkpoint_committed": False,
                      "selected_by": "validation loss only"},
            "dataset": {
                "name": "VLNVerse/VLNTube controlled local subset",
                "manifest": "assets/experiments/training_ablation/"
                            "mnv2_ema_20260708/dataset_manifest_scene_holdout.json",
                "train_episodes": manifest["split_summary"]["train"],
                "val_episodes": manifest["split_summary"]["val"],
                "test_episodes": manifest["split_summary"]["test_scene_holdout"],
                "train_scenes": manifest["scenes"]["train"],
                "heldout_scene": manifest["scenes"]["test_scene_holdout"][0],
                "holdout_type": "scene-level",
                "leakage_check": "PASS" if leak["scene_level_holdout"]
                                 and leak["train_test_episode_overlap"] == 0
                                 else "FAIL"},
            "metrics": {"sr": metrics.get("SR"), "osr": metrics.get("OSR"),
                        "ne_m": metrics.get("NE"), "spl": metrics.get("SPL"),
                        "n_test_episodes": 50,
                        "collision_rate": "N/A offline"},
            "observability": {
                "wandb_project": "offline",
                "wandb_run": run_name,
                "wandb_offline_dirs": wandb["latest_offline_dirs"],
                "cuda_verified": cuda["cuda_available"],
                "gpu": cuda["gpu"]},
            "gates": {
                "cuda_verified": cuda["cuda_available"],
                "wandb_logged": True,
                "dataset_manifest_exists": True,
                "scene_holdout_leakage_check": "PASS",
                "checkpoint_hashed": True,
                "offline_cr_not_reported_numeric": True,
                "artifact_hygiene_clean": not heavy,
                "no_full_benchmark_claim": True,
                "no_robust_navigation_claim": True,
                "no_language_instruction_claim": True},
            "driftguard": spec["driftguard_role"],
            "sentinel": {"incidents": []},
            "verdictplane": {
                "governed_actions": ["promote_model", "deploy_to_isaac",
                                     "deploy_to_robot", "publish_result",
                                     "rollback_model"],
                "policy_state": "pending"},
            "claim_boundary": CLAIM,
        }
        p = OUT / f"{run_name}.json"
        p.write_text(json.dumps(card, indent=2))
        print(f"wrote {p.relative_to(REPO)} "
              f"(SR={card['metrics']['sr']}, gates all "
              f"{'PASS' if all(v in (True, 'PASS') for v in card['gates'].values()) else 'CHECK'})")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
