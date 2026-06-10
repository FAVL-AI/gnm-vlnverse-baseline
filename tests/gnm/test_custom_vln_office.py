"""
tests/gnm/test_custom_vln_office.py
Fast, no-Isaac-Sim tests for the CustomVLN-Office pipeline.
"""
import json
import math
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable] + cmd,
        capture_output=True, text=True, cwd=str(REPO)
    )


# ── Config ────────────────────────────────────────────────────────────────────

def test_tasks_yaml_loads():
    p = REPO / "configs/custom_vln_office/tasks.yaml"
    assert p.exists(), "tasks.yaml missing"
    with open(p) as f:
        t = yaml.safe_load(f)
    assert "episodes" in t
    eps = t["episodes"]
    assert len(eps) >= 8, f"Expected ≥8 episodes, got {len(eps)}"


def test_tasks_yaml_fields():
    p = REPO / "configs/custom_vln_office/tasks.yaml"
    with open(p) as f:
        t = yaml.safe_load(f)
    required = {"episode_id", "split", "instruction", "start_pose", "goal_pose", "waypoints"}
    for ep in t["episodes"]:
        missing = required - set(ep.keys())
        assert not missing, f"{ep.get('episode_id','?')} missing: {missing}"


def test_tasks_splits():
    p = REPO / "configs/custom_vln_office/tasks.yaml"
    with open(p) as f:
        t = yaml.safe_load(f)
    train_ids = t.get("split_train", [])
    val_ids   = t.get("split_val",   [])
    assert len(train_ids) >= 4
    assert len(val_ids)   >= 2
    # No overlap
    assert not set(train_ids) & set(val_ids), "Train/val episode overlap"


# ── Dry-run script execution ──────────────────────────────────────────────────

def test_discover_assets_dry_run():
    r = _run(["scripts/gnm/discover_isaac_assets.py", "--dry-run"])
    assert r.returncode == 0, f"discover failed:\n{r.stderr}"
    assert "Primitive fallback" in r.stdout


def test_create_scene_dry_run():
    r = _run(["scripts/gnm/create_custom_vln_office_scene.py", "--dry-run"])
    assert r.returncode == 0, f"create_scene failed:\n{r.stderr}"
    stub = REPO / "assets/custom_vln_office/scene_layout.usda"
    assert stub.exists(), "USDA stub not created"
    manifest = REPO / "results/custom_vln_office/scene_manifest.md"
    assert manifest.exists(), "scene_manifest.md not created"


def test_collect_dry_run():
    r = _run(["scripts/gnm/collect_custom_vln_office_data.py", "--dry-run"])
    assert r.returncode == 0, f"collect failed:\n{r.stderr}"
    # Check episodes created
    train_dir = REPO / "datasets/custom_vln_office/train"
    val_dir   = REPO / "datasets/custom_vln_office/val"
    assert train_dir.exists()
    assert val_dir.exists()


def test_episode_data_structure():
    data_root = REPO / "datasets/custom_vln_office"
    ep_dirs = list(data_root.glob("*/cvlo_*"))
    assert ep_dirs, "No episodes found — run collect --dry-run first"
    for ep_dir in ep_dirs[:3]:
        assert (ep_dir / "traj_data.pkl").exists(), f"traj_data.pkl missing in {ep_dir}"
        assert (ep_dir / "actions.jsonl").exists(),  f"actions.jsonl missing in {ep_dir}"
        assert (ep_dir / "metadata.json").exists(),  f"metadata.json missing in {ep_dir}"
        assert (ep_dir / "rgb").exists(),             f"rgb/ missing in {ep_dir}"


def test_traj_data_content():
    ep_dirs = list((REPO / "datasets/custom_vln_office").glob("*/cvlo_*"))
    assert ep_dirs
    for ep_dir in ep_dirs[:3]:
        with open(ep_dir / "traj_data.pkl", "rb") as f:
            data = pickle.load(f)
        assert "position" in data
        assert "yaw"      in data
        pos = np.array(data["position"])
        yaw = np.array(data["yaw"])
        assert pos.ndim == 2 and pos.shape[1] == 2, f"position shape wrong: {pos.shape}"
        assert yaw.ndim == 1, f"yaw shape wrong: {yaw.shape}"
        assert len(pos) == len(yaw)
        assert data.get("scene_id") == "custom_vln_office"
        assert "episode_id" in data
        assert "vlnverse_assets_used" not in data or data.get("vlnverse_assets_used") is False


def test_metadata_no_vlnverse():
    ep_dirs = list((REPO / "datasets/custom_vln_office").glob("*/cvlo_*"))
    assert ep_dirs
    for ep_dir in ep_dirs:
        with open(ep_dir / "metadata.json") as f:
            meta = json.load(f)
        assert meta.get("vlnverse_assets_used") is False, \
            f"vlnverse_assets_used should be False in {ep_dir.name}"
        assert meta.get("scene_id") == "custom_vln_office"


def test_actions_jsonl_fields():
    ep_dirs = list((REPO / "datasets/custom_vln_office").glob("*/cvlo_*"))
    assert ep_dirs
    for ep_dir in ep_dirs[:2]:
        lines = (ep_dir / "actions.jsonl").read_text().strip().split("\n")
        assert lines
        first = json.loads(lines[0])
        required = {"frame_index", "x", "y", "yaw", "action_dx", "action_dy",
                    "local_waypoint_x", "local_waypoint_y", "rgb_image_path", "distance_to_goal"}
        missing = required - set(first.keys())
        assert not missing, f"actions.jsonl missing fields in {ep_dir.name}: {missing}"


def test_replay_dry_run():
    r = _run(["scripts/gnm/replay_custom_vln_office.py", "--dry-run", "--episode", "cvlo_ep001"])
    assert r.returncode == 0, f"replay dry-run failed:\n{r.stderr}"
    assert "cvlo_ep001" in r.stdout


def test_evaluate_dry_run():
    r = _run(["scripts/gnm/evaluate_custom_vln_office.py", "--dry-run"])
    assert r.returncode == 0, f"evaluate failed:\n{r.stderr}"
    assert (REPO / "results/custom_vln_office/eval_summary.md").exists()
    assert (REPO / "results/custom_vln_office/eval_summary.csv").exists()


def test_manual_drive_dry_run():
    r = _run(["scripts/gnm/manual_custom_vln_office_drive.py", "--dry-run"])
    assert r.returncode == 0, f"manual_drive dry-run failed:\n{r.stderr}"
    assert "W" in r.stdout  # controls listed


def test_reviewer_doc_exists():
    p = REPO / "results/bo_reviewer_packet/12_custom_vln_office_independent_isaac_scene.md"
    assert p.exists(), "reviewer doc missing"
    text = p.read_text()
    assert "VLNVerse" in text
    assert "CustomVLN-Office" in text
    assert "vlnverse_assets_used" in text.lower() or "no vlnverse" in text.lower()


def test_asset_manifest_created():
    r = _run(["scripts/gnm/discover_isaac_assets.py", "--dry-run"])
    assert r.returncode == 0
    manifest = REPO / "results/custom_vln_office/isaac_asset_manifest.json"
    assert manifest.exists()
    with open(manifest) as f:
        m = json.load(f)
    assert "use_primitives_fallback" in m
    assert "primitive_fallback_plan" in m
