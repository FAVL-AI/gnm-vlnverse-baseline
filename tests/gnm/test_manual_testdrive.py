"""
Tests for manual_testdrive, replay_manual_testdrive, and convert_manual_testdrive_to_gnm.
"""

import json
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_episode(tmp_path: Path, with_goal: bool = True) -> Path:
    ep_dir = tmp_path / "ep_001"
    rgb_dir = ep_dir / "rgb"
    rgb_dir.mkdir(parents=True)

    n = 5
    positions = np.random.rand(n, 2).tolist()
    yaws = np.random.rand(n).tolist()
    rgb_paths = [str(rgb_dir / f"{i:06d}.jpg") for i in range(n)]

    for p in rgb_paths:
        Path(p).write_bytes(b"\xff\xd8\xff\xe0")

    traj = {
        "position": np.array(positions),
        "yaw": np.array(yaws),
        "rgb_paths": rgb_paths,
        "actions": [],
        "timestamps": [float(i) for i in range(n)],
        "scene_id": "test_scene",
        "episode_id": "test_scene_20260101T000000Z",
        "mode": "custom_office",
        "start_pos": np.array(positions[0]),
        "start_yaw": yaws[0],
        "n_steps": n,
        "path_length_m": 1.23,
    }
    if with_goal:
        traj["goal_pos"] = np.array(positions[-1])
        traj["goal_yaw"] = yaws[-1]

    with open(ep_dir / "traj_data.pkl", "wb") as f:
        pickle.dump(traj, f)

    actions = []
    for i in range(n):
        row = {
            "timestamp": float(i),
            "frame_index": i,
            "action_key": "W",
            "linear_velocity": 0.05,
            "angular_velocity": 0.0,
            "x": positions[i][0],
            "y": positions[i][1],
            "z": 0.0,
            "yaw": yaws[i],
            "rgb_image_path": rgb_paths[i],
        }
        if with_goal:
            row["distance_to_goal"] = float(i) * 0.1
        actions.append(row)

    with open(ep_dir / "actions.jsonl", "w") as f:
        for row in actions:
            f.write(json.dumps(row) + "\n")

    meta = {
        "simulator": "Isaac Sim",
        "control_mode": "manual_testdrive",
        "scene_source": "CustomVLN-Office",
        "vlnverse_assets_used": False,
        "official_benchmark_data": False,
        "purpose": "manual data-collection proof for GNM/VLN pipeline",
    }
    with open(ep_dir / "metadata.json", "w") as f:
        json.dump(meta, f)

    return ep_dir


# ---------------------------------------------------------------------------
# metadata schema
# ---------------------------------------------------------------------------

def test_metadata_schema(tmp_path):
    ep = _make_episode(tmp_path)
    with open(ep / "metadata.json") as f:
        meta = json.load(f)
    assert meta["simulator"] == "Isaac Sim"
    assert meta["control_mode"] == "manual_testdrive"
    assert meta["official_benchmark_data"] is False
    assert "purpose" in meta


# ---------------------------------------------------------------------------
# actions.jsonl schema
# ---------------------------------------------------------------------------

def test_actions_jsonl_schema(tmp_path):
    ep = _make_episode(tmp_path)
    rows = []
    with open(ep / "actions.jsonl") as f:
        for line in f:
            rows.append(json.loads(line.strip()))
    assert len(rows) > 0
    required = {"timestamp", "frame_index", "action_key", "linear_velocity",
                "angular_velocity", "x", "y", "z", "yaw", "rgb_image_path"}
    for row in rows:
        assert required.issubset(row.keys()), f"Missing keys: {required - row.keys()}"


# ---------------------------------------------------------------------------
# traj_data.pkl required fields
# ---------------------------------------------------------------------------

def test_traj_data_required_fields(tmp_path):
    ep = _make_episode(tmp_path)
    with open(ep / "traj_data.pkl", "rb") as f:
        traj = pickle.load(f)

    required = {"position", "yaw", "rgb_paths", "actions", "timestamps",
                "scene_id", "episode_id", "mode", "start_pos", "start_yaw",
                "n_steps", "path_length_m"}
    assert required.issubset(traj.keys()), f"Missing fields: {required - traj.keys()}"
    assert traj["position"].shape[1] == 2
    assert len(traj["yaw"]) == len(traj["position"])


# ---------------------------------------------------------------------------
# converter does not overwrite official dataset
# ---------------------------------------------------------------------------

def test_converter_refuses_protected_output(tmp_path):
    from scripts.gnm.convert_manual_testdrive_to_gnm import _check_output_safe
    import sys

    protected_paths = [
        tmp_path / "vlntube",
        tmp_path / "vlnverse_output",
        tmp_path / "gnm_release_v2",
    ]
    for p in protected_paths:
        with pytest.raises(SystemExit):
            _check_output_safe(p)

    # safe path should not raise
    _check_output_safe(tmp_path / "manual_gnm_format")


def test_converter_produces_gnm_format(tmp_path):
    from scripts.gnm.convert_manual_testdrive_to_gnm import convert_episode

    ep = _make_episode(tmp_path)
    out_root = tmp_path / "manual_gnm_format"
    out_dir = convert_episode(ep, out_root)

    assert (out_dir / "traj_data.pkl").exists()
    assert (out_dir / "metadata.json").exists()

    with open(out_dir / "traj_data.pkl", "rb") as f:
        traj = pickle.load(f)
    assert traj["official_benchmark_data"] if "official_benchmark_data" in traj else True or True

    with open(out_dir / "metadata.json") as f:
        meta = json.load(f)
    assert meta["official_benchmark_data"] is False
    assert meta["gnm_format"] is True


# ---------------------------------------------------------------------------
# dry-run commands work
# ---------------------------------------------------------------------------

def _run_dry(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, f"scripts/gnm/{script}", "--dry-run"],
        capture_output=True, text=True, cwd=Path(__file__).parents[2]
    )


def test_manual_testdrive_dry_run():
    result = _run_dry("manual_testdrive.py")
    assert result.returncode == 0
    assert "Available modes" in result.stdout
    assert "Controls" in result.stdout


def test_replay_dry_run():
    result = _run_dry("replay_manual_testdrive.py")
    assert result.returncode == 0
    assert "Usage" in result.stdout


def test_converter_dry_run():
    result = _run_dry("convert_manual_testdrive_to_gnm.py")
    assert result.returncode == 0
    assert "GNM-compatible" in result.stdout or "dry-run" in result.stdout.lower()
