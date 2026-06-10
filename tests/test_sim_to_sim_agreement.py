"""
test_sim_to_sim_agreement.py — CI tests for the MuJoCo ↔ Isaac agreement gate.

Tests that can run WITHOUT Isaac (pure logic and MuJoCo):
  test_generate_actions_constant
  test_generate_actions_sinusoidal
  test_nearest_dist_m
  test_path_length
  test_compute_metrics_identical_trajectories
  test_compute_metrics_collision_agreement
  test_write_trajectory_csv_schema
  test_write_comparison_json_schema
  test_write_agreement_report_markdown
  test_mujoco_rollout_kinematic_smoke
  test_mujoco_rollout_forced_collision
  test_scenario_definitions_consistent

Test requiring Isaac (inside AppLauncher):
  test_isaac_rollout_matches_mujoco   (auto-skipped if not inside AppLauncher)
"""
from __future__ import annotations

import csv
import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pytest

# ── Make repo root importable ─────────────────────────────────────────────────
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.visualnav.check_sim_to_sim_agreement import (
    CONTROL_HZ,
    NEAR_MISS_M,
    OBS_RADIUS_M,
    SCENARIOS,
    THRESH,
    AgreementMetrics,
    StepRecord,
    _compute_metrics,
    _generate_actions,
    _nearest_dist_m,
    _path_length,
    _write_agreement_report,
    _write_comparison_json,
    _write_trajectory_csv,
    _run_rollout,
)

# ── AppLauncher probe (pxr importable ↔ inside Isaac process) ─────────────────
try:
    from pxr import Usd as _Usd  # noqa: F401
    _INSIDE_APPLAUNCH = True
except ImportError:
    _INSIDE_APPLAUNCH = False

_SKIP_NO_ISAAC = pytest.mark.skipif(
    not _INSIDE_APPLAUNCH,
    reason="Isaac Sim not active — run inside AppLauncher",
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_traj(n: int = 10, dx: float = 0.05) -> list[StepRecord]:
    records = []
    for k in range(n):
        x = k * dx
        records.append(StepRecord(
            step=k, x=x, y=0.0, yaw=0.0,
            min_obstacle_dist_m=1.0 - k * 0.05,
            collision=False,
            action_vx=0.2, action_wz=0.0,
        ))
    return records


def _make_mujoco_obstacle_env(obstacle_positions, n_steps=20):
    from fleet_safe_vla.envs.mujoco.yahboom.obstacle_env import YahboomObstacleEnv
    return YahboomObstacleEnv(
        n_obstacles=len(obstacle_positions),
        fixed_positions=obstacle_positions if obstacle_positions else None,
        max_episode_steps=n_steps + 1,
        control_hz=CONTROL_HZ,
    )


# ── Action generation ─────────────────────────────────────────────────────────

def test_generate_actions_constant():
    acts = _generate_actions("constant", {"vx": 0.2, "wz": 0.1}, n_steps=10)
    assert acts.shape == (10, 2)
    assert np.allclose(acts[:, 0], 0.2)
    assert np.allclose(acts[:, 1], 0.1)


def test_generate_actions_sinusoidal():
    acts = _generate_actions(
        "sinusoidal", {"vx": 0.2, "wz_amp": 0.3, "wz_period_steps": 5}, n_steps=15
    )
    assert acts.shape == (15, 2)
    assert np.allclose(acts[:, 0], 0.2)
    # At step 0: wz = 0.3 * sin(0) = 0.0
    assert abs(acts[0, 1]) < 1e-9
    # At step 5: wz = 0.3 * sin(pi) ≈ 0.0
    assert abs(acts[5, 1]) < 1e-6


def test_generate_actions_unknown_pattern():
    with pytest.raises(ValueError, match="Unknown action pattern"):
        _generate_actions("bogus", {}, n_steps=5)


# ── Geometry helpers ──────────────────────────────────────────────────────────

def test_nearest_dist_m_no_obstacles():
    assert _nearest_dist_m((0.0, 0.0), []) == pytest.approx(99.0)


def test_nearest_dist_m_single_obstacle():
    # Robot at (0,0), obstacle at (1,0), radius=0.10 → dist=0.90
    d = _nearest_dist_m((0.0, 0.0), [(1.0, 0.0)])
    assert d == pytest.approx(1.0 - OBS_RADIUS_M, abs=1e-9)


def test_nearest_dist_m_collision():
    # Robot at (0.05, 0), obstacle at (0, 0), radius=0.10 → dist = 0.05 - 0.10 = -0.05
    d = _nearest_dist_m((0.05, 0.0), [(0.0, 0.0)])
    assert d < 0.0


def test_nearest_dist_m_multiple_obstacles():
    obs = [(0.5, 0.0), (5.0, 5.0)]
    d = _nearest_dist_m((0.0, 0.0), obs)
    assert d == pytest.approx(0.5 - OBS_RADIUS_M, abs=1e-9)


# ── Path length ───────────────────────────────────────────────────────────────

def test_path_length_straight():
    traj = _make_traj(n=11, dx=0.1)  # 0.0, 0.1, ..., 1.0
    pl = _path_length(traj)
    assert pl == pytest.approx(1.0, abs=1e-9)


def test_path_length_single_step():
    traj = [StepRecord(0, 0.0, 0.0, 0.0, 99.0, False, 0.0, 0.0)]
    assert _path_length(traj) == pytest.approx(0.0)


# ── Metrics computation ───────────────────────────────────────────────────────

def test_compute_metrics_identical_trajectories():
    traj = _make_traj(n=10, dx=0.05)
    applicable = ["final_xy_error_m", "trajectory_rmse_m", "path_length_delta_pct"]
    m = _compute_metrics("test", traj, traj, applicable)
    assert m.final_xy_error_m == pytest.approx(0.0, abs=1e-9)
    assert m.trajectory_rmse_m == pytest.approx(0.0, abs=1e-9)
    assert m.path_length_delta_pct == pytest.approx(0.0, abs=1e-6)
    assert m.collision_agreement is True
    assert m.near_violation_agreement == pytest.approx(1.0)
    assert m.passed is True


def test_compute_metrics_collision_agreement_match():
    def make_col_traj():
        t = _make_traj(n=8, dx=0.05)
        t[-1] = StepRecord(
            step=7, x=0.35, y=0.0, yaw=0.0,
            min_obstacle_dist_m=-0.05, collision=True,
            action_vx=0.2, action_wz=0.0,
        )
        return t
    mj = make_col_traj()
    ik = make_col_traj()
    m = _compute_metrics("col_match", mj, ik, ["collision_agreement"])
    assert m.collision_agreement is True
    assert m.first_collision_step_mujoco == 7
    assert m.first_collision_step_isaac == 7
    assert m.passed is True


def test_compute_metrics_collision_agreement_mismatch():
    traj_a = _make_traj(n=5)
    traj_a[-1] = StepRecord(4, 0.4, 0.0, 0.0, -0.05, True, 0.2, 0.0)

    traj_b = _make_traj(n=5)  # no collision in b

    m = _compute_metrics("col_mismatch", traj_a, traj_b, ["collision_agreement"])
    assert m.collision_agreement is False
    assert m.passed is False


def test_compute_metrics_near_violation_agreement():
    # All steps near-violation in both → agreement = 1.0
    def near_traj():
        return [
            StepRecord(k, 0.0, 0.0, 0.0, min_obstacle_dist_m=0.10, collision=False,
                       action_vx=0.0, action_wz=0.0)
            for k in range(10)
        ]
    m = _compute_metrics("near", near_traj(), near_traj(), ["near_violation_agreement"])
    assert m.near_violation_agreement == pytest.approx(1.0)
    assert m.passed is True


def test_compute_metrics_pass_thresholds():
    traj = _make_traj(n=10, dx=0.05)
    applicable = list(THRESH.keys())
    m = _compute_metrics("identical", traj, traj, applicable)
    # Identical trajectories pass all numeric thresholds
    assert m.trajectory_rmse_m <= THRESH["trajectory_rmse_m"]
    assert m.final_xy_error_m <= THRESH["final_xy_error_m"]
    assert m.path_length_delta_pct <= THRESH["path_length_delta_pct"]
    assert m.near_violation_agreement >= THRESH["near_violation_agreement"]
    assert m.collision_agreement == THRESH["collision_agreement"]


# ── File output ───────────────────────────────────────────────────────────────

def test_write_trajectory_csv_schema():
    traj = _make_traj(n=5)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "traj.csv"
        _write_trajectory_csv(path, traj)
        rows = list(csv.DictReader(open(path)))
    assert len(rows) == 5
    required_cols = {"step", "x", "y", "yaw", "min_obstacle_dist_m",
                     "collision", "action_vx", "action_wz"}
    assert required_cols.issubset(set(rows[0].keys()))
    assert rows[0]["collision"] in ("0", "1")


def test_write_comparison_json_schema():
    traj = _make_traj(n=10)
    scenario = SCENARIOS[0]
    applicable = scenario["applicable_thresholds"]
    m = _compute_metrics(scenario["name"], traj, traj, applicable)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "comparison.json"
        _write_comparison_json(path, scenario, m, "2026-05-16T00:00:00Z")
        doc = json.loads(path.read_text())
    required_keys = {
        "generated_at", "scenario", "metrics", "thresholds", "passed", "fail_reasons",
        "n_steps_mujoco", "n_steps_isaac", "control_hz", "near_miss_m", "obs_radius_m",
    }
    assert required_keys.issubset(doc.keys())
    metric_keys = {
        "trajectory_rmse_m", "final_xy_error_m", "path_length_delta_pct",
        "collision_agreement", "near_violation_agreement",
        "min_obstacle_distance_delta_m",
    }
    assert metric_keys.issubset(doc["metrics"].keys())


def test_write_agreement_report_markdown():
    trajs = [_make_traj(n=10), _make_traj(n=10)]
    all_metrics = [
        _compute_metrics("kinematic_smoke", trajs[0], trajs[0],
                         ["final_xy_error_m", "trajectory_rmse_m"]),
        _compute_metrics("forced_collision", trajs[1], trajs[1],
                         ["collision_agreement"]),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir)
        _write_agreement_report(out, all_metrics, isaac_available=True,
                                generated_at="2026-05-16T00:00:00Z")
        text = (out / "agreement_report.md").read_text()

    assert "# MuJoCo" in text
    assert "PASS=" in text
    assert "kinematic_smoke" in text
    assert "forced_collision" in text
    assert "Citable Status" in text


# ── Scenario definitions ──────────────────────────────────────────────────────

def test_scenario_definitions_consistent():
    required_keys = {
        "name", "description", "obstacle_positions", "start_xy", "start_yaw",
        "n_steps", "action_pattern", "action_params", "applicable_thresholds",
    }
    valid_thresholds = set(THRESH.keys())
    for s in SCENARIOS:
        assert required_keys.issubset(s.keys()), f"Missing keys in {s['name']}"
        for t in s["applicable_thresholds"]:
            assert t in valid_thresholds, f"Unknown threshold {t!r} in {s['name']}"
        # Validate action generation doesn't raise
        _generate_actions(s["action_pattern"], s["action_params"], s["n_steps"])


def test_scenario_forced_collision_math():
    """Verify forced_collision scenario produces collision at step 10 analytically."""
    s = next(s for s in SCENARIOS if s["name"] == "forced_collision")
    obs_pos = s["obstacle_positions"][0]  # (0.8, 0.0)
    vx = s["action_params"]["vx"]         # 0.3
    dt = 1.0 / CONTROL_HZ                  # 0.25 s
    # step 9: x=9*vx*dt=0.675, dist=0.8-0.675-0.10=0.025 (no collision)
    # step 10: x=10*vx*dt=0.75, dist=0.8-0.75-0.10=-0.05 (collision)
    x_step9 = 9 * vx * dt
    x_step10 = 10 * vx * dt
    dist9 = obs_pos[0] - x_step9 - OBS_RADIUS_M
    dist10 = obs_pos[0] - x_step10 - OBS_RADIUS_M
    assert dist9 > 0.0, f"Expected no collision at step 9, got dist={dist9}"
    assert dist10 < 0.0, f"Expected collision at step 10, got dist={dist10}"


# ── MuJoCo rollouts (no Isaac required) ──────────────────────────────────────

def test_mujoco_rollout_kinematic_smoke():
    """Forward drive with no obstacles — trajectory must match analytical formula."""
    actions = _generate_actions("constant", {"vx": 0.2, "wz": 0.0}, n_steps=20)
    env = _make_mujoco_obstacle_env([], n_steps=20)
    traj = _run_rollout(env, (0.0, 0.0), 0.0, actions, [], seed=0)
    env.close()

    assert len(traj) == 21  # step 0 + 20 steps

    # Analytical: x = k * 0.2 * (1/CONTROL_HZ) = k * 0.05
    dt = 1.0 / CONTROL_HZ
    for k, r in enumerate(traj):
        expected_x = k * 0.2 * dt
        assert abs(r.x - expected_x) < 1e-6, f"Step {k}: x={r.x:.6f} expected {expected_x:.6f}"
        assert abs(r.y) < 1e-6
        assert r.min_obstacle_dist_m == pytest.approx(99.0)
        assert r.collision is False

    pl = _path_length(traj)
    assert pl == pytest.approx(20 * 0.2 * dt, rel=1e-5)


def test_mujoco_rollout_forced_collision():
    """Robot driven into obstacle at (0.8, 0.0) — collision must occur at step 10."""
    obs_positions = [(0.8, 0.0)]
    actions = _generate_actions("constant", {"vx": 0.3, "wz": 0.0}, n_steps=15)
    env = _make_mujoco_obstacle_env(obs_positions, n_steps=15)
    traj = _run_rollout(env, (0.0, 0.0), 0.0, actions, obs_positions, seed=0)
    env.close()

    # Terminated at step 10 (collision ends episode)
    first_col = next((r.step for r in traj if r.collision), None)
    assert first_col == 10, f"Expected collision at step 10, got {first_col}"

    # Step 9 must not be a collision
    r9 = next(r for r in traj if r.step == 9)
    assert r9.min_obstacle_dist_m > 0.0


def test_mujoco_rollout_cluttered_navigation():
    """Sinusoidal path in cluttered scene — basic sanity checks."""
    obs_positions = [
        (0.5, 1.0), (-1.0, 2.0), (1.5, 0.0), (-0.5, -1.0),
        (2.0, 1.5), (-2.0, -0.5), (0.0, 2.5), (1.0, -1.5),
    ]
    actions = _generate_actions(
        "sinusoidal", {"vx": 0.2, "wz_amp": 0.3, "wz_period_steps": 5}, n_steps=30
    )
    env = _make_mujoco_obstacle_env(obs_positions, n_steps=30)
    traj = _run_rollout(env, (-2.0, -2.0), 0.0, actions, obs_positions, seed=0)
    env.close()

    assert len(traj) >= 2
    for r in traj:
        # Robot started at (-2,-2), obstacles are at least 1m away — no collision expected
        # (unless sinusoidal path drives into one, which it won't from this start)
        assert isinstance(r.x, float)
        assert isinstance(r.collision, bool)


# ── Live Isaac agreement test (requires AppLauncher) ─────────────────────────

@_SKIP_NO_ISAAC
def test_isaac_rollout_matches_mujoco():
    """
    Run kinematic_smoke through both backends and verify agreement.
    Both use identical kinematic integration so trajectories must match exactly.
    """
    from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import IsaacNavBenchmarkEnv
    from fleet_safe_vla.envs.mujoco.yahboom.obstacle_env import YahboomObstacleEnv

    actions = _generate_actions("constant", {"vx": 0.2, "wz": 0.0}, n_steps=15)
    obs_positions: list = []

    env_mj = YahboomObstacleEnv(
        n_obstacles=0, fixed_positions=None,
        max_episode_steps=16, control_hz=CONTROL_HZ,
    )
    mj_traj = _run_rollout(env_mj, (0.0, 0.0), 0.0, actions, obs_positions, seed=0)
    env_mj.close()

    env_ik = IsaacNavBenchmarkEnv(
        fixed_positions=[], n_obstacles=0,
        max_episode_steps=16, control_hz=CONTROL_HZ,
    )
    ik_traj = _run_rollout(env_ik, (0.0, 0.0), 0.0, actions, obs_positions, seed=0)
    env_ik.close()

    applicable = ["final_xy_error_m", "trajectory_rmse_m", "path_length_delta_pct"]
    m = _compute_metrics("kinematic_smoke_live", mj_traj, ik_traj, applicable)

    assert m.trajectory_rmse_m <= THRESH["trajectory_rmse_m"], (
        f"Trajectory RMSE {m.trajectory_rmse_m:.6f} exceeds threshold "
        f"{THRESH['trajectory_rmse_m']}"
    )
    assert m.final_xy_error_m <= THRESH["final_xy_error_m"], (
        f"Final XY error {m.final_xy_error_m:.6f} exceeds threshold "
        f"{THRESH['final_xy_error_m']}"
    )
    assert m.path_length_delta_pct <= THRESH["path_length_delta_pct"]
    assert m.passed is True


@_SKIP_NO_ISAAC
def test_isaac_forced_collision_agreement():
    """Both backends must report collision at step 10 for forced_collision scenario."""
    from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import IsaacNavBenchmarkEnv
    from fleet_safe_vla.envs.mujoco.yahboom.obstacle_env import YahboomObstacleEnv

    obs_positions = [(0.8, 0.0)]
    actions = _generate_actions("constant", {"vx": 0.3, "wz": 0.0}, n_steps=15)

    env_mj = YahboomObstacleEnv(
        n_obstacles=1, fixed_positions=obs_positions,
        max_episode_steps=16, control_hz=CONTROL_HZ,
    )
    mj_traj = _run_rollout(env_mj, (0.0, 0.0), 0.0, actions, obs_positions, seed=0)
    env_mj.close()

    env_ik = IsaacNavBenchmarkEnv(
        fixed_positions=obs_positions, n_obstacles=1,
        max_episode_steps=16, control_hz=CONTROL_HZ,
    )
    ik_traj = _run_rollout(env_ik, (0.0, 0.0), 0.0, actions, obs_positions, seed=0)
    env_ik.close()

    m = _compute_metrics("forced_collision_live", mj_traj, ik_traj, ["collision_agreement"])
    assert m.collision_agreement is True, (
        f"Collision step mismatch: MuJoCo={m.first_collision_step_mujoco}, "
        f"Isaac={m.first_collision_step_isaac}"
    )
    assert m.first_collision_step_mujoco == 10
    assert m.first_collision_step_isaac == 10
