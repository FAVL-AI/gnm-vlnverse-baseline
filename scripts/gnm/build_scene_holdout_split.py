"""Build the scene-level held-out split manifest over existing VLNTube data.

Assignment (manifest-based; no files are moved):
    train scenes : kujiale_0092, kujiale_0118, kujiale_0203
    val          : the existing val-directory episodes of the train scenes
                   (trajectory-level within train scenes)
    test scene   : kujiale_0271 — ALL of its episodes (from both train/ and
                   val/ directories) are held out for final testing and must
                   not be used for training or model selection.

Rationale: all four local scenes are upstream-trainval scenes, so a local
scene-level holdout must come from our own four; kujiale_0271 has the
fewest episodes (least training-data loss) while providing 50 test
episodes vs the previous 15-episode trajectory-level split.
"""

import json
import pickle
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "datasets/vlntube"
TEST_SCENE = "kujiale_0271"
TRAIN_SCENES = ["kujiale_0092", "kujiale_0118", "kujiale_0203"]
OUT = REPO / ("assets/experiments/training_ablation/mnv2_ema_20260708/"
              "dataset_manifest_scene_holdout.json")


def scene_of(ep):
    return "kujiale_" + ep.split("_kujiale_")[1].split("_")[0] \
        if "_kujiale_" in ep else ep


def episode_record(dirname, ep, split):
    p = DATA / dirname / ep
    frames = sorted(p.glob("*.jpg"))
    traj = pickle.loads((p / "traj_data.pkl").read_bytes())
    pos = traj["position"]
    path_len = float(sum(
        ((pos[i + 1] - pos[i]) ** 2).sum() ** 0.5 for i in range(len(pos) - 1)))
    return {
        "episode_id": ep, "scene_id": scene_of(ep), "trajectory_id": ep,
        "trajectory_path": f"datasets/vlntube/{dirname}/{ep}",
        "start_pose": [float(pos[0][0]), float(pos[0][1]),
                       float(traj["yaw"][0])],
        "goal_pose": [float(pos[-1][0]), float(pos[-1][1]),
                      float(traj["yaw"][-1])],
        "goal_image_path": f"datasets/vlntube/{dirname}/{ep}/{frames[-1].name}",
        "num_frames": len(frames),
        "path_length_m": round(path_len, 3),
        "split": split,
    }


def main():
    git = lambda *a: subprocess.run(["git"] + list(a), capture_output=True,
                                    text=True, cwd=REPO).stdout.strip()
    episodes = []
    for dirname in ("train", "val"):
        for ep in sorted(p.name for p in (DATA / dirname).iterdir()
                         if p.is_dir()):
            sc = scene_of(ep)
            if sc == TEST_SCENE:
                split = "test_scene_holdout"
            elif dirname == "val":
                split = "val"
            else:
                split = "train"
            episodes.append(episode_record(dirname, ep, split))

    by = lambda s: [e for e in episodes if e["split"] == s]
    train, val, test = by("train"), by("val"), by("test_scene_holdout")
    train_scenes = {e["scene_id"] for e in train} | {e["scene_id"] for e in val}
    test_scenes = {e["scene_id"] for e in test}
    assert not train_scenes & test_scenes, "scene leakage"
    ids = [e["episode_id"] for e in episodes]
    assert len(set(ids)) == len(ids), "duplicate episodes"

    manifest = {
        "dataset_name": "VLNVerse/VLNTube (local four-scene corpus)",
        "purpose": ("scene-level held-out split for final reporting; "
                    "supersedes the trajectory-level split of "
                    "dataset_manifest.json for future FINAL testing only"),
        "hypothesis": ("Increasing VLNVerse/VLNTube training and validation "
                       "coverage while preserving scene-level held-out "
                       "testing will produce a more reliable estimate of "
                       "MobileNetV2-GNM generalization than the current "
                       "four-scene, trajectory-level split."),
        "git_commit": git("rev-parse", "--short", "HEAD"),
        "git_branch": git("branch", "--show-current"),
        "scenes": {
            "available": sorted(train_scenes | test_scenes),
            "train": sorted({e["scene_id"] for e in train}),
            "val": sorted({e["scene_id"] for e in val}),
            "test_scene_holdout": sorted(test_scenes),
            "upstream_alignment": ("all four local scenes are upstream "
                                   "VLNTube trainval scenes "
                                   "(external/VLNTube/splits/"
                                   "scene_splits.json); no upstream test "
                                   "scene exists locally, so the local "
                                   "scene holdout is drawn from our own "
                                   "four scenes"),
        },
        "split_summary": {"train": len(train), "val": len(val),
                          "test_scene_holdout": len(test),
                          "total": len(episodes)},
        "usage_rules": [
            "test_scene_holdout episodes must not be used for training, "
            "hyperparameter tuning, or model selection",
            "val episodes are trajectory-level within train scenes and are "
            "for model selection only",
            "no performance claims from this split until models are "
            "retrained under it",
        ],
        "expansion_status": {
            "hf_download": "unavailable — dataset repo "
                           "frankleroyvan/fleetsafe-gnm-vlnverse not "
                           "published",
            "live_vistube_generation": "blocked — upstream pipeline is "
                                       "hardwired to the original authors' "
                                       "infrastructure and requires scene "
                                       "USDs; local envs have "
                                       "meshes/occupancy but zero composed "
                                       "scene USDs (vlntube_index.json)",
            "next_step": "rebuild scene USDs from local Meshes/Materials, "
                         "then run vistube A* trajectory generation for "
                         "TRAIN scenes only, keeping kujiale_0271 untouched",
        },
        "episodes": episodes,
        "leakage_check": {
            "train_test_scene_overlap": 0,
            "train_test_trajectory_overlap": 0,
            "train_test_episode_overlap": 0,
            "scene_level_holdout": True,
        },
    }
    OUT.write_text(json.dumps(manifest, indent=2))
    print(f"train {len(train)} / val {len(val)} / test(scene) {len(test)} "
          f"= {len(episodes)}; test scene: {TEST_SCENE}")
    print(f"wrote {OUT.relative_to(REPO)}")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
