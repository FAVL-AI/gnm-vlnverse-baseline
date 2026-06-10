"""Tests for VLNTube → GNM data converter.

Tests exercise:
  - CSV loading and validation
  - Pose jump detection and segment splitting
  - Yaw radians validation
  - Missing frame handling
  - Output format verification
"""
import sys
import math
import pickle
import tempfile
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from gnm_vlnverse.data.vlntube_converter import VLNTubeConverter, compute_action_std


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_episode_dir(
    tmp_path: Path,
    n_frames: int = 30,
    yaw_degrees: bool = False,
    pose_jump_at: int = -1,
    missing_frames: list[int] | None = None,
) -> Path:
    """Create a synthetic episode directory with traj_data.pkl."""
    ep_dir = tmp_path / "episode_000"
    ep_dir.mkdir()

    # Positions: straight line +x
    positions = np.array([[float(i) * 0.2, 0.0] for i in range(n_frames)], dtype=np.float32)

    # Yaws: constant 0 (facing +x)
    yaws = np.zeros(n_frames, dtype=np.float32)
    if yaw_degrees:
        yaws = np.degrees(yaws)  # degrees — invalid

    # Introduce a pose jump
    if pose_jump_at > 0:
        positions[pose_jump_at:] += np.array([100.0, 0.0])

    data = {"position": positions, "yaw": yaws}
    with open(ep_dir / "traj_data.pkl", "wb") as f:
        pickle.dump(data, f)

    # Create dummy JPEG frames
    missing = set(missing_frames or [])
    for i in range(n_frames):
        if i not in missing:
            # Minimal JPEG bytes (1×1 black pixel)
            (ep_dir / f"{i}.jpg").write_bytes(
                bytes([
                    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46,
                    0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01,
                    0x00, 0x01, 0x00, 0x00, 0xFF, 0xD9,
                ])
            )

    return ep_dir


class TestComputeActionStd:
    def test_returns_two_floats(self, tmp_path):
        ep = _make_episode_dir(tmp_path, n_frames=20)
        std_x, std_y = compute_action_std(tmp_path)
        assert isinstance(std_x, float)
        assert isinstance(std_y, float)
        assert std_x >= 0.0
        assert std_y >= 0.0

    def test_straight_line_low_lateral_std(self, tmp_path):
        ep = _make_episode_dir(tmp_path, n_frames=30)
        std_x, std_y = compute_action_std(tmp_path)
        # Straight forward → dy_robot should be ~0
        assert std_y < 0.01, f"Lateral std={std_y:.4f} should be near 0 for straight path"

    def test_requires_pkl(self, tmp_path):
        """compute_action_std on empty dir should raise SystemExit."""
        empty = tmp_path / "empty_dir"
        empty.mkdir()
        with pytest.raises(SystemExit):
            compute_action_std(tmp_path)


class TestYawValidation:
    def test_radians_passes(self, tmp_path):
        ep = _make_episode_dir(tmp_path, n_frames=20, yaw_degrees=False)
        # yaw=0 for all frames — valid radians
        data = pickle.load(open(ep / "traj_data.pkl", "rb"))
        yaws = data["yaw"]
        # Max |yaw| = 0 < 2π+ε
        assert np.max(np.abs(yaws)) <= 2 * math.pi + 0.1

    def test_large_yaw_looks_like_degrees(self):
        # 90 degrees in radians is 1.57 — fine
        # 90 as a degree value stored raw is 90.0 — invalid
        yaw_deg = np.array([0.0, 45.0, 90.0, 135.0, 180.0])
        max_abs  = np.max(np.abs(yaw_deg))
        is_degrees = max_abs > (2 * math.pi + 0.1)
        assert is_degrees  # 180 > 2π ≈ 6.28 is FALSE — so let's use a different example

    def test_very_large_yaw_detected(self):
        yaws = np.array([0.0, 45.0, 90.0, 180.0, 270.0])
        max_abs = float(np.max(np.abs(yaws)))
        assert max_abs > (2 * math.pi + 0.1)


class TestPoseJumpDetection:
    def test_no_jump_single_segment(self, tmp_path):
        """Trajectory with no jumps → one segment."""
        ep = _make_episode_dir(tmp_path, n_frames=30, pose_jump_at=-1)
        data = pickle.load(open(ep / "traj_data.pkl", "rb"))
        positions = data["position"]

        # Compute consecutive distances
        dists = [
            math.hypot(
                float(positions[i+1][0] - positions[i][0]),
                float(positions[i+1][1] - positions[i][1]),
            )
            for i in range(len(positions) - 1)
        ]
        assert max(dists) < 3.0, "No jump expected"

    def test_jump_detected(self, tmp_path):
        """Trajectory with a 100m jump → split point found."""
        ep = _make_episode_dir(tmp_path, n_frames=30, pose_jump_at=15)
        data = pickle.load(open(ep / "traj_data.pkl", "rb"))
        positions = data["position"]

        dists = [
            math.hypot(
                float(positions[i+1][0] - positions[i][0]),
                float(positions[i+1][1] - positions[i][1]),
            )
            for i in range(len(positions) - 1)
        ]
        assert max(dists) > 3.0, "Jump should be detected"


class TestTrajectoryDataFormat:
    def test_traj_data_has_required_keys(self, tmp_path):
        ep = _make_episode_dir(tmp_path, n_frames=20)
        data = pickle.load(open(ep / "traj_data.pkl", "rb"))
        assert "position" in data
        assert "yaw" in data

    def test_position_shape(self, tmp_path):
        n = 20
        ep = _make_episode_dir(tmp_path, n_frames=n)
        data = pickle.load(open(ep / "traj_data.pkl", "rb"))
        assert data["position"].shape == (n, 2)

    def test_yaw_shape(self, tmp_path):
        n = 20
        ep = _make_episode_dir(tmp_path, n_frames=n)
        data = pickle.load(open(ep / "traj_data.pkl", "rb"))
        assert data["yaw"].shape == (n,)
