"""
Regression tests for Yahboom physics-based differential-drive dynamics.

Tests are designed to be:
  - Deterministic (fixed seed, no randomisation)
  - Fast (<5s total, run at CI speed)
  - Physically meaningful (not just "no crash")

Acceptance thresholds come from yahboom_physics.yaml:
  vx_ss_error < 0.05 m/s
  mean_slip   < 0.15
  yaw_drift   < 0.05 rad/m
  t90         < 0.5 s
"""
from __future__ import annotations

import math

import mujoco
import numpy as np
import pytest

from fleet_safe_vla.envs.mujoco.yahboom.physics_env import YahboomPhysicsEnv
from fleet_safe_vla.validation.motion_validator import MotionValidator


# ── Fixtures ────────────────────────────────────────────────────────────────── #

@pytest.fixture(scope="module")
def env():
    """Nominal physics env, shared across tests in this module."""
    e = YahboomPhysicsEnv(friction=0.8, robot_mass=2.1, pid_kp=0.04, pid_ki=0.05, pid_kd=0.0)
    yield e
    e.close()


@pytest.fixture(scope="module")
def validator(env):
    return MotionValidator(env)


# ── Stability ────────────────────────────────────────────────────────────────── #

def test_physics_env_instantiates():
    env = YahboomPhysicsEnv()
    obs, info = env.reset(seed=0)
    assert obs.shape == (36,), f"Expected (36,), got {obs.shape}"
    assert np.all(np.isfinite(obs)), "Obs contains NaN/Inf"
    env.close()


def test_step_returns_valid_obs(env):
    env.reset(seed=0)
    for _ in range(5):
        obs, rew, term, trunc, info = env.step(np.array([0.2, 0.0], dtype=np.float32))
    assert np.all(np.isfinite(obs)), "Obs contains NaN/Inf after 5 steps"
    assert np.isfinite(rew), "Reward is NaN/Inf"


def test_no_numerical_instability(env):
    """100 steps at max speed must not produce NaN/Inf in any state."""
    env.reset(seed=1)
    for i in range(100):
        action = np.array([0.5, 0.0], dtype=np.float32)
        obs, rew, term, trunc, info = env.step(action)
        assert np.all(np.isfinite(obs)), f"NaN/Inf in obs at step {i}"
        assert math.isfinite(rew), f"NaN/Inf reward at step {i}"


# ── Velocity tracking ────────────────────────────────────────────────────────── #

def test_robot_translates_at_commanded_speed(validator):
    """
    3-second straight-line drive at 0.3 m/s.
    Steady-state velocity error must be < 0.05 m/s.
    """
    records = validator.run_straight_line(vx=0.3, duration_s=3.0, seed=0)
    m = validator.compute_metrics(records)

    assert m.stable, "Simulation unstable (NaN/Inf detected)"
    assert m.vx_ss_error < 0.05, (
        f"Steady-state vx error {m.vx_ss_error:.4f} m/s exceeds 0.05 m/s threshold"
    )


def test_minimum_achieved_speed(validator):
    """Body speed must reach at least 80 % of commanded speed in steady state."""
    records = validator.run_straight_line(vx=0.4, duration_s=3.0, seed=2)
    # Use last 50 % of episode
    ss = records[len(records) // 2:]
    mean_vx = float(np.mean([r.actual_vx for r in ss]))
    assert mean_vx >= 0.8 * 0.4, (
        f"Mean body speed {mean_vx:.4f} m/s is below 80 % of 0.4 m/s command"
    )


@pytest.mark.xfail(
    strict=False,
    reason="X3 structural baseline contact/slip tuning pending; not required for M3Pro VisualNav/Isaac gates",
)
def test_time_to_90_percent_speed(validator):
    """Robot should reach 90 % of commanded speed within 0.5 s."""
    records = validator.run_straight_line(vx=0.3, duration_s=3.0, seed=3)
    m = validator.compute_metrics(records)
    assert math.isfinite(m.time_to_90pct_s), "Never reached 90 % of commanded speed"
    assert m.time_to_90pct_s < 0.5, (
        f"Time to 90 % speed: {m.time_to_90pct_s:.3f}s exceeds 0.5s threshold"
    )


# ── Slip ratio ───────────────────────────────────────────────────────────────── #

@pytest.mark.xfail(
    strict=False,
    reason="X3 structural baseline contact/slip tuning pending; not required for M3Pro VisualNav/Isaac gates",
)
def test_steady_state_slip_below_threshold(validator):
    """Mean slip ratio in steady state must be < 0.15."""
    records = validator.run_straight_line(vx=0.3, duration_s=3.0, seed=4)
    
    # Use last 50% of episode for steady-state metrics
    ss_records = records[len(records) // 2:]
    m = validator.compute_metrics(ss_records)
    
    assert m.mean_slip < 0.15, (
        f"Mean slip ratio {m.mean_slip:.4f} exceeds 0.15 threshold"
    )


def test_slip_ratios_are_finite(env):
    """Slip ratios must be finite and in [0, 1]."""
    env.reset(seed=5)
    env._data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    mujoco.mj_forward(env._model, env._data)
    for _ in range(20):
        env.step(np.array([0.3, 0.0], dtype=np.float32))
        sl, sr = env.slip_ratios()
        assert 0.0 <= sl <= 1.0, f"Left slip ratio out of range: {sl}"
        assert 0.0 <= sr <= 1.0, f"Right slip ratio out of range: {sr}"


# ── Yaw drift ────────────────────────────────────────────────────────────────── #

def test_stable_contact_count(env):
    """Contact count must include both drive wheels."""
    env.reset(seed=0)
    for _ in range(50):
        env.step(np.array([0.3, 0.0], dtype=np.float32))
    
    contact_pairs = [(env._model.geom(g1).name, env._model.geom(g2).name) for g1, g2 in zip(env._data.contact.geom1, env._data.contact.geom2)]
    contact_geoms = set([geom for pair in contact_pairs for geom in pair])
    assert "left_wheel" in contact_geoms and "right_wheel" in contact_geoms, (
        f"Contacts do not include both drive wheels: {contact_geoms}"
    )

def test_straight_line_yaw_drift(validator):
    """Yaw drift must be near zero over a 3-second straight run."""
    records = validator.run_straight_line(vx=0.3, duration_s=3.0, seed=6)
    m = validator.compute_metrics(records)
    assert abs(m.yaw_drift_rad_per_m) < 0.01, (
        f"Yaw drift {m.yaw_drift_rad_per_m:.4f} rad/m exceeds 0.01 threshold"
    )


def test_turn_in_place_no_translation(validator):
    """Spin-in-place: lateral position drift must be < 0.05 m over 2 s."""
    records = validator.run_turn_in_place(wz=1.0, duration_s=2.0, seed=7)
    x0, y0 = records[0].x, records[0].y
    x1, y1 = records[-1].x, records[-1].y
    drift = math.sqrt((x1 - x0)**2 + (y1 - y0)**2)
    assert drift < 0.05, f"Position drift during spin: {drift:.4f} m > 0.05 m threshold"


# ── Determinism ──────────────────────────────────────────────────────────────── #

def test_deterministic_trajectory():
    """Same seed → same trajectory (to floating-point precision)."""
    def _run(seed):
        env = YahboomPhysicsEnv(friction=0.8)
        env.reset(seed=seed)
        env._data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
        mujoco.mj_forward(env._model, env._data)
        xs = []
        for _ in range(15):
            env.step(np.array([0.3, 0.0], dtype=np.float32))
            xs.append(env.get_robot_pose()[0])
        env.close()
        return xs

    xs_a = _run(seed=99)
    xs_b = _run(seed=99)
    assert xs_a == xs_b, "Physics trajectory not deterministic with same seed"


# ── Friction sensitivity ─────────────────────────────────────────────────────── #

@pytest.mark.parametrize("friction", [0.5, 0.8, 1.5])
def test_stable_across_friction_range(friction):
    """Physics env must be numerically stable for friction in [0.5, 1.5]."""
    env = YahboomPhysicsEnv(friction=friction)
    env.reset(seed=0)
    env._data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    mujoco.mj_forward(env._model, env._data)
    for _ in range(30):
        obs, _, _, _, _ = env.step(np.array([0.3, 0.0], dtype=np.float32))
        assert np.all(np.isfinite(obs)), f"NaN/Inf at friction={friction}"
    env.close()


# ── Body-velocity helper ─────────────────────────────────────────────────────── #

def test_body_velocity_helper(env):
    """body_velocity() must agree with obs-reported odom velocity."""
    env.reset(seed=0)
    env._data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    mujoco.mj_forward(env._model, env._data)
    for _ in range(15):
        env.step(np.array([0.3, 0.0], dtype=np.float32))
    vx_b, vy_b, wz = env.body_velocity()
    assert math.isfinite(vx_b) and math.isfinite(vy_b) and math.isfinite(wz)
    # For straight-line driving with yaw=0: vx_body ≈ qvel[0]
    assert abs(vx_b - env._data.qvel[0]) < 0.02, (
        f"body_velocity vx={vx_b:.4f} disagrees with qvel[0]={env._data.qvel[0]:.4f}"
    )
