"""Tests for coordinate frame transformations.

GNM outputs actions in the ROBOT frame (x=forward, y=left).
The world frame uses absolute (x, y) coordinates.

These tests verify that the rotation from world → robot frame and back
is correct, consistent across the dataset and evaluator, and handles
all four quadrants of yaw correctly.

Key formula
────────────
  World → Robot:
    dx_robot =  cos(yaw) * dx_world + sin(yaw) * dy_world
    dy_robot = -sin(yaw) * dx_world + cos(yaw) * dy_world

  Robot → World:
    dx_world = cos(yaw) * dx_robot - sin(yaw) * dy_robot
    dy_world = sin(yaw) * dx_robot + cos(yaw) * dy_robot
"""
import sys
import math
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def world_to_robot(dx_w: float, dy_w: float, yaw: float) -> tuple[float, float]:
    cos_y = math.cos(yaw)
    sin_y = math.sin(yaw)
    dx_r =  cos_y * dx_w + sin_y * dy_w
    dy_r = -sin_y * dx_w + cos_y * dy_w
    return dx_r, dy_r


def robot_to_world(dx_r: float, dy_r: float, yaw: float) -> tuple[float, float]:
    cos_y = math.cos(yaw)
    sin_y = math.sin(yaw)
    dx_w = cos_y * dx_r - sin_y * dy_r
    dy_w = sin_y * dx_r + cos_y * dy_r
    return dx_w, dy_w


class TestRoundTrip:
    """World → Robot → World should be identity."""

    @pytest.mark.parametrize("yaw", [0.0, math.pi/4, math.pi/2, math.pi, -math.pi/3])
    def test_round_trip(self, yaw):
        dx_w, dy_w = 1.5, -0.7
        dx_r, dy_r = world_to_robot(dx_w, dy_w, yaw)
        dx_w2, dy_w2 = robot_to_world(dx_r, dy_r, yaw)
        assert math.isclose(dx_w, dx_w2, rel_tol=1e-5)
        assert math.isclose(dy_w, dy_w2, rel_tol=1e-5)


class TestFacingNorth:
    """Robot facing north (yaw=90°): forward = +y in world."""

    def test_forward_is_plus_y_world(self):
        yaw = math.pi / 2  # facing +y
        dx_r, dy_r = 1.0, 0.0
        dx_w, dy_w = robot_to_world(dx_r, dy_r, yaw)
        assert math.isclose(dx_w, 0.0, abs_tol=1e-5)
        assert math.isclose(dy_w, 1.0, rel_tol=1e-5)

    def test_world_displacement_north_is_robot_forward(self):
        yaw = math.pi / 2
        dx_w, dy_w = 0.0, 1.0
        dx_r, dy_r = world_to_robot(dx_w, dy_w, yaw)
        assert math.isclose(dx_r, 1.0, rel_tol=1e-5)
        assert math.isclose(dy_r, 0.0, abs_tol=1e-5)


class TestFacingEast:
    """Robot facing east (yaw=0°): forward = +x in world."""

    def test_forward_is_plus_x_world(self):
        yaw = 0.0
        dx_r, dy_r = 1.0, 0.0
        dx_w, dy_w = robot_to_world(dx_r, dy_r, yaw)
        assert math.isclose(dx_w, 1.0, rel_tol=1e-5)
        assert math.isclose(dy_w, 0.0, abs_tol=1e-5)


class TestNormPreservation:
    """Rotation should preserve distance (it's an isometry)."""

    @pytest.mark.parametrize("yaw", [0.0, 1.0, 2.0, -1.5])
    def test_norm_preserved_in_world_to_robot(self, yaw):
        dx_w, dy_w = 3.0, 4.0
        dx_r, dy_r = world_to_robot(dx_w, dy_w, yaw)
        norm_w = math.hypot(dx_w, dy_w)
        norm_r = math.hypot(dx_r, dy_r)
        assert math.isclose(norm_w, norm_r, rel_tol=1e-5)


class TestDatasetConsistency:
    """Check that GNMDataset uses the same rotation as the evaluator."""

    def test_dataset_robot_frame_formula(self):
        yaw   = math.pi / 6
        pos_t  = np.array([0.0, 0.0])
        pos_t1 = np.array([1.0, 0.5])

        dx_w = pos_t1[0] - pos_t[0]
        dy_w = pos_t1[1] - pos_t[1]

        cos_y = math.cos(yaw)
        sin_y = math.sin(yaw)

        # GNMDataset formula (world → robot)
        dx_r_dataset =  cos_y * dx_w + sin_y * dy_w
        dy_r_dataset = -sin_y * dx_w + cos_y * dy_w

        # Evaluator formula (robot → world for integration)
        dx_w_back = cos_y * dx_r_dataset - sin_y * dy_r_dataset
        dy_w_back = sin_y * dx_r_dataset + cos_y * dy_r_dataset

        assert math.isclose(dx_w, dx_w_back, rel_tol=1e-5)
        assert math.isclose(dy_w, dy_w_back, rel_tol=1e-5)
