"""
tests/gnm/test_live_dashboard.py
Tests for the live GNM input dashboard (--export-live-dashboard mode).
No Isaac Sim required.

Tests that require VLNVerse trajectory data (datasets/vlntube/train/) are
automatically skipped when the dataset is not present in this repo.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TRAIN_ROOT = REPO / "datasets/vlntube/train"
DATASET_PRESENT = TRAIN_ROOT.exists() and any(
    (d / "traj_data.pkl").exists() for d in TRAIN_ROOT.iterdir()
) if TRAIN_ROOT.exists() else False

needs_dataset = pytest.mark.skipif(
    not DATASET_PRESENT,
    reason="VLNVerse dataset not present in this repo (datasets/vlntube/train/)",
)


def _run(cmd: list[str], env_extra: dict | None = None) -> subprocess.CompletedProcess:
    import os
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable] + cmd,
        capture_output=True, text=True, cwd=str(REPO), env=env,
    )


@needs_dataset
def test_export_live_dashboard_runs():
    r = _run(["scripts/gnm/replay_gnm_demo.py", "--export-live-dashboard"])
    assert r.returncode == 0, f"--export-live-dashboard failed:\n{r.stderr}"


@needs_dataset
def test_export_live_dashboard_creates_frames():
    dash_dir = REPO / "results/bo_reviewer_packet/live_dashboard"
    frames = sorted(dash_dir.glob("dashboard_*.png"))
    assert frames, "No dashboard_*.png frames found"


def test_export_live_dashboard_first_frame_exists():
    first = REPO / "results/bo_reviewer_packet/live_dashboard/dashboard_000000.png"
    assert first.exists(), "dashboard_000000.png (frame 0) missing — run --export-live-dashboard on a machine with the dataset"


@needs_dataset
def test_export_live_dashboard_frame_size():
    from PIL import Image
    first = REPO / "results/bo_reviewer_packet/live_dashboard/dashboard_000000.png"
    assert first.exists()
    img = Image.open(first)
    w, h = img.size
    # Three 320px columns + 2×8 gap = 976; height = 46+44+240+96 = 426
    assert w == 976, f"Expected width 976, got {w}"
    assert h == 426, f"Expected height 426, got {h}"


@needs_dataset
def test_export_live_dashboard_stdout():
    r = _run(["scripts/gnm/replay_gnm_demo.py", "--export-live-dashboard"])
    assert "RUNNING" in r.stdout or "GOAL REACHED" in r.stdout
    assert "Saved" in r.stdout
    assert "Reviewer doc" in r.stdout


@needs_dataset
def test_export_live_dashboard_goal_reached_reported():
    r = _run(["scripts/gnm/replay_gnm_demo.py", "--export-live-dashboard"])
    assert "GOAL REACHED" in r.stdout, "Expected GOAL REACHED in at least one frame"


@needs_dataset
def test_export_live_dashboard_every_n():
    r = _run(
        ["scripts/gnm/replay_gnm_demo.py", "--export-live-dashboard"],
        env_extra={"DASHBOARD_EVERY_N": "5"},
    )
    assert r.returncode == 0, f"DASHBOARD_EVERY_N=5 failed:\n{r.stderr}"


def test_reviewer_doc_exists():
    p = REPO / "results/bo_reviewer_packet/13_live_gnm_input_dashboard.md"
    assert p.exists(), "13_live_gnm_input_dashboard.md missing"
    text = p.read_text()
    assert "START VIEW" in text
    assert "CURRENT LIVE VIEW" in text
    assert "GOAL VIEW" in text
    assert "GOAL REACHED" in text
    assert "traj_data.pkl" in text
    assert "not model prediction" in text.lower()


@needs_dataset
def test_dry_run_panels_still_works():
    r = _run(["scripts/gnm/replay_gnm_demo.py", "--dry-run-panels"])
    assert r.returncode == 0, f"--dry-run-panels failed:\n{r.stderr}"
    assert "export-live-dashboard" in r.stdout


def test_list_scenes_still_works():
    r = _run(["scripts/gnm/replay_gnm_demo.py", "--list-scenes"])
    assert r.returncode == 0, f"--list-scenes failed:\n{r.stderr}"
    assert "kujiale_0118" in r.stdout


@needs_dataset
def test_prove_dataset_still_works():
    r = _run(["scripts/gnm/replay_gnm_demo.py", "--prove-dataset"])
    assert r.returncode == 0, f"--prove-dataset failed:\n{r.stderr}"
    assert "SR" in r.stdout
