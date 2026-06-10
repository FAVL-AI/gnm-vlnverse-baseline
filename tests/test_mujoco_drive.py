"""
Regression tests for Yahboom MuJoCo differential-drive kinematics.

Asserts that the robot actually translates at commanded velocity —
the physics-actuator instability bug produced ~0 body speed despite
correct wheel commands.
"""
import math

import mujoco
import numpy as np
import pytest

from fleet_safe_vla.envs.mujoco.yahboom.base_env import YahboomMuJoCoBase


def _face_x(env: YahboomMuJoCoBase) -> None:
    """Force robot to face exactly +x (yaw=0)."""
    env._data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    mujoco.mj_forward(env._model, env._data)


def test_straight_line_drive():
    """1 second at 0.3 m/s → robot must travel > 0.20 m in x."""
    env = YahboomMuJoCoBase()
    env.reset(seed=0)
    _face_x(env)

    for _ in range(10):   # 10 steps × 0.1 s = 1.0 s
        env.step(np.array([0.3, 0.0], dtype=np.float32))

    x, y, yaw = env.get_robot_pose()
    assert x > 0.20, f"Expected x > 0.20 m, got {x:.4f}"
    assert abs(yaw) < 0.15, f"Expected |yaw| < 0.15 rad, got {yaw:.4f}"
    env.close()


def test_turning():
    """1 second spin at 1.0 rad/s → yaw must reach ≈ 1.0 rad."""
    env = YahboomMuJoCoBase()
    env.reset(seed=1)
    _face_x(env)

    for _ in range(10):
        env.step(np.array([0.0, 1.0], dtype=np.float32))

    _, _, yaw = env.get_robot_pose()
    assert abs(yaw - 1.0) < 0.05, f"Expected yaw ≈ 1.0 rad, got {yaw:.4f}"
    env.close()


def test_speed_accuracy():
    """Commanded speed matches integrated displacement within 2% over 2 s."""
    env = YahboomMuJoCoBase()
    env.reset(seed=2)
    _face_x(env)
    x0, _, _ = env.get_robot_pose()

    vx_cmd = 0.4
    n_steps = 20   # 2.0 s
    for _ in range(n_steps):
        env.step(np.array([vx_cmd, 0.0], dtype=np.float32))

    x, _, _ = env.get_robot_pose()
    displacement = x - x0
    expected = vx_cmd * (n_steps * 0.1)   # 0.8 m
    assert abs(displacement - expected) < 0.02, \
        f"Expected Δx ≈ {expected:.2f} m, got {displacement:.4f}"
    env.close()


def test_combined_motion():
    """Arced trajectory: vx=0.3, wz=0.5 for 1 s.  Robot must move AND rotate."""
    env = YahboomMuJoCoBase()
    env.reset(seed=3)
    _face_x(env)

    for _ in range(10):
        env.step(np.array([0.3, 0.5], dtype=np.float32))

    x, y, yaw = env.get_robot_pose()
    dist = math.sqrt(x**2 + y**2)
    assert dist > 0.20, f"Expected distance > 0.20 m, got {dist:.4f}"
    assert abs(yaw) > 0.3, f"Expected |yaw| > 0.3 rad, got {yaw:.4f}"
    env.close()


def test_yaw_drift_straight():
    """Straight-line command must not produce significant yaw drift."""
    env = YahboomMuJoCoBase()
    env.reset(seed=4)
    _face_x(env)

    for _ in range(30):   # 3 s
        env.step(np.array([0.5, 0.0], dtype=np.float32))

    _, _, yaw = env.get_robot_pose()
    assert abs(yaw) < 0.10, f"Yaw drift too large: {yaw:.4f} rad"
    env.close()
