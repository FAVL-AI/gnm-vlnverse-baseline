#!/usr/bin/env python3
"""
check_sim_to_sim_agreement.py — MuJoCo ↔ Isaac physics agreement gate.

Runs identical open-loop action sequences through both the MuJoCo and Isaac
physics backends and compares trajectories, distances, and collision events.
Isaac physics results are NOT citable until this gate passes.

Three scenarios are run in sequence:

  kinematic_smoke      — constant forward drive, no obstacles.
                         Tests kinematic integration agreement.
  cluttered_navigation — sinusoidal path through 8-obstacle field.
                         Tests distance and near-violation agreement.
  forced_collision     — robot driven straight into a single obstacle.
                         Tests collision event agreement.

Pass thresholds (see THRESH dict below):
  final_xy_error_m        <= 0.25 m
  trajectory_rmse_m       <= 0.20 m
  path_length_delta_pct   <= 10 %
  collision_agreement     == True  (forced_collision scenario)
  near_violation_agreement >= 0.80

Exit codes:
  0   all non-skipped checks pass
  1   one or more checks FAIL
  2   Isaac not available (MuJoCo-only run, comparison incomplete)

Usage (CI — MuJoCo sanity only):
  python scripts/visualnav/check_sim_to_sim_agreement.py

Usage (full agreement gate, inside AppLauncher):
  conda activate isaac
  python -c "
  from isaaclab.app import AppLauncher
  app = AppLauncher({'headless': True}).app
  import sys, importlib.util
  from pathlib import Path
  spec = importlib.util.spec_from_file_location(
      'check_s2s',
      str(Path('scripts/visualnav/check_sim_to_sim_agreement.py').resolve()),
  )
  mod = importlib.util.module_from_spec(spec)
  sys.modules['check_s2s'] = mod
  spec.loader.exec_module(mod)
  ret = mod.main(['--with-isaac'])
  app.close()
  sys.exit(ret)
  "

Output:
  benchmarks/validation/sim_to_sim/<timestamp>/
      kinematic_smoke/mujoco_trajectory.csv
      kinematic_smoke/isaac_trajectory.csv     (if --with-isaac)
      kinematic_smoke/comparison.json
      cluttered_navigation/...
      forced_collision/...
      agreement_report.md
      summary.json
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

# ── Shared physical constant — must match both backends ───────────────────────
OBS_RADIUS_M = 0.10   # cylinder radius used by both YahboomObstacleEnv and IsaacNavBenchmarkEnv

# ── Consistent near-violation threshold (script-level, not backend-specific) ──
NEAR_MISS_M = 0.35

# ── Control frequency used for all rollouts ───────────────────────────────────
CONTROL_HZ = 4.0

# ── Pass thresholds ───────────────────────────────────────────────────────────
THRESH: dict[str, Any] = {
    "final_xy_error_m":       0.25,
    "trajectory_rmse_m":      0.20,
    "path_length_delta_pct":  10.0,
    "near_violation_agreement": 0.80,
    "collision_agreement":    True,
}

# ── Scenarios ─────────────────────────────────────────────────────────────────

_OBSTACLE_POSITIONS_CLUTTERED = [
    (0.5, 1.0), (-1.0, 2.0), (1.5, 0.0), (-0.5, -1.0),
    (2.0, 1.5), (-2.0, -0.5), (0.0, 2.5), (1.0, -1.5),
]

SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "kinematic_smoke",
        "description": (
            "Constant forward drive, no obstacles. "
            "Both backends use identical kinematics so trajectories must match exactly."
        ),
        "obstacle_positions": [],
        "start_xy": (0.0, 0.0),
        "start_yaw": 0.0,
        "n_steps": 20,
        "action_pattern": "constant",
        "action_params": {"vx": 0.20, "wz": 0.0},
        "applicable_thresholds": [
            "final_xy_error_m",
            "trajectory_rmse_m",
            "path_length_delta_pct",
        ],
    },
    {
        "name": "cluttered_navigation",
        "description": (
            "Sinusoidal path through the canonical cluttered_static obstacle field. "
            "Tests that both backends report matching obstacle distances and near-violation events."
        ),
        "obstacle_positions": _OBSTACLE_POSITIONS_CLUTTERED,
        "start_xy": (-2.0, -2.0),
        "start_yaw": 0.0,
        "n_steps": 30,
        "action_pattern": "sinusoidal",
        "action_params": {"vx": 0.20, "wz_amp": 0.30, "wz_period_steps": 5},
        "applicable_thresholds": [
            "trajectory_rmse_m",
            "path_length_delta_pct",
            "near_violation_agreement",
        ],
    },
    {
        "name": "forced_collision",
        "description": (
            "Robot driven straight into a single obstacle at (0.8, 0.0). "
            "Collision must occur at step 10 in both backends. "
            "Tests collision detection agreement."
        ),
        "obstacle_positions": [(0.8, 0.0)],
        "start_xy": (0.0, 0.0),
        "start_yaw": 0.0,
        "n_steps": 15,
        "action_pattern": "constant",
        "action_params": {"vx": 0.30, "wz": 0.0},
        "applicable_thresholds": [
            "collision_agreement",
            "near_violation_agreement",
        ],
    },
]


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class StepRecord:
    step: int
    x: float
    y: float
    yaw: float
    min_obstacle_dist_m: float
    collision: bool
    action_vx: float
    action_wz: float


@dataclass
class AgreementMetrics:
    scenario: str
    n_steps_mujoco: int
    n_steps_isaac: int
    n_steps_aligned: int
    final_xy_error_m: float
    trajectory_rmse_m: float
    path_length_mujoco_m: float
    path_length_isaac_m: float
    path_length_delta_pct: float
    min_obs_dist_mujoco_m: float
    min_obs_dist_isaac_m: float
    min_obstacle_distance_delta_m: float
    first_collision_step_mujoco: int | None
    first_collision_step_isaac: int | None
    collision_agreement: bool
    near_violation_agreement: float
    applicable_thresholds: list[str]
    passed: bool
    fail_reasons: list[str] = field(default_factory=list)


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _nearest_dist_m(
    robot_xy: tuple[float, float],
    obstacle_positions: list[tuple[float, float]],
) -> float:
    if not obstacle_positions:
        return 99.0
    dists = [
        math.hypot(robot_xy[0] - ox, robot_xy[1] - oy) - OBS_RADIUS_M
        for ox, oy in obstacle_positions
    ]
    return min(dists)


def _generate_actions(
    pattern: str,
    params: dict[str, Any],
    n_steps: int,
) -> np.ndarray:
    acts = np.zeros((n_steps, 2), dtype=np.float32)
    if pattern == "constant":
        acts[:, 0] = params["vx"]
        acts[:, 1] = params.get("wz", 0.0)
    elif pattern == "sinusoidal":
        vx = params["vx"]
        amp = params["wz_amp"]
        period = params["wz_period_steps"]
        for k in range(n_steps):
            acts[k, 0] = vx
            acts[k, 1] = amp * math.sin(k * math.pi / period)
    else:
        raise ValueError(f"Unknown action pattern: {pattern!r}")
    return acts


def _path_length(traj: list[StepRecord]) -> float:
    total = 0.0
    for k in range(1, len(traj)):
        total += math.hypot(traj[k].x - traj[k-1].x, traj[k].y - traj[k-1].y)
    return total


# ── Rollout ───────────────────────────────────────────────────────────────────

def _run_rollout(
    env: Any,
    start_xy: tuple[float, float],
    start_yaw: float,
    actions: np.ndarray,
    obstacle_positions: list[tuple[float, float]],
    seed: int = 0,
) -> list[StepRecord]:
    records: list[StepRecord] = []

    env.reset(seed=seed)
    env.teleport_to(start_xy[0], start_xy[1], start_yaw)

    x0, y0, yaw0 = env.get_robot_pose()
    min_d0 = _nearest_dist_m((x0, y0), obstacle_positions)
    records.append(StepRecord(
        step=0, x=x0, y=y0, yaw=yaw0,
        min_obstacle_dist_m=min_d0, collision=min_d0 < 0.0,
        action_vx=0.0, action_wz=0.0,
    ))

    for k, action in enumerate(actions):
        _obs, _rew, terminated, truncated, info = env.step(action)
        x, y, yaw = env.get_robot_pose()
        records.append(StepRecord(
            step=k + 1,
            x=float(info["robot_xy"][0]),
            y=float(info["robot_xy"][1]),
            yaw=yaw,
            min_obstacle_dist_m=float(info["min_obstacle_dist_m"]),
            collision=bool(info["collision"]),
            action_vx=float(action[0]),
            action_wz=float(action[1]),
        ))
        if terminated or truncated:
            break

    return records


# ── Metrics ───────────────────────────────────────────────────────────────────

def _compute_metrics(
    scenario_name: str,
    mj_traj: list[StepRecord],
    ik_traj: list[StepRecord],
    applicable_thresholds: list[str],
) -> AgreementMetrics:
    n_aligned = min(len(mj_traj), len(ik_traj))

    # Trajectory RMSE and final error
    errors_sq = [
        (mj_traj[k].x - ik_traj[k].x) ** 2 + (mj_traj[k].y - ik_traj[k].y) ** 2
        for k in range(n_aligned)
    ]
    rmse = math.sqrt(sum(errors_sq) / n_aligned) if n_aligned > 0 else 0.0
    final_xy_err = math.sqrt(errors_sq[-1]) if errors_sq else 0.0

    # Path lengths
    pl_mj = _path_length(mj_traj)
    pl_ik = _path_length(ik_traj)
    pl_ref = max(pl_mj, 1e-6)
    pl_delta_pct = abs(pl_mj - pl_ik) / pl_ref * 100.0

    # Min obstacle distance
    min_d_mj = min(r.min_obstacle_dist_m for r in mj_traj)
    min_d_ik = min(r.min_obstacle_dist_m for r in ik_traj)
    min_d_delta = abs(min_d_mj - min_d_ik)

    # Collision agreement
    first_col_mj = next((r.step for r in mj_traj if r.collision), None)
    first_col_ik = next((r.step for r in ik_traj if r.collision), None)
    col_agree = first_col_mj == first_col_ik

    # Near-violation agreement
    near_mj = [r.min_obstacle_dist_m < NEAR_MISS_M for r in mj_traj[:n_aligned]]
    near_ik = [r.min_obstacle_dist_m < NEAR_MISS_M for r in ik_traj[:n_aligned]]
    if n_aligned > 0:
        near_agree = sum(a == b for a, b in zip(near_mj, near_ik)) / n_aligned
    else:
        near_agree = 1.0

    # Pass/fail against applicable thresholds
    fail_reasons: list[str] = []
    for key in applicable_thresholds:
        threshold = THRESH[key]
        if key == "final_xy_error_m" and final_xy_err > threshold:
            fail_reasons.append(f"final_xy_error_m={final_xy_err:.4f} > {threshold}")
        elif key == "trajectory_rmse_m" and rmse > threshold:
            fail_reasons.append(f"trajectory_rmse_m={rmse:.4f} > {threshold}")
        elif key == "path_length_delta_pct" and pl_delta_pct > threshold:
            fail_reasons.append(f"path_length_delta_pct={pl_delta_pct:.2f}% > {threshold}%")
        elif key == "near_violation_agreement" and near_agree < threshold:
            fail_reasons.append(f"near_violation_agreement={near_agree:.3f} < {threshold}")
        elif key == "collision_agreement" and not col_agree:
            fail_reasons.append(
                f"collision_agreement: MuJoCo col@step={first_col_mj}, Isaac col@step={first_col_ik}"
            )

    return AgreementMetrics(
        scenario=scenario_name,
        n_steps_mujoco=len(mj_traj),
        n_steps_isaac=len(ik_traj),
        n_steps_aligned=n_aligned,
        final_xy_error_m=round(final_xy_err, 6),
        trajectory_rmse_m=round(rmse, 6),
        path_length_mujoco_m=round(pl_mj, 4),
        path_length_isaac_m=round(pl_ik, 4),
        path_length_delta_pct=round(pl_delta_pct, 3),
        min_obs_dist_mujoco_m=round(min_d_mj, 4),
        min_obs_dist_isaac_m=round(min_d_ik, 4),
        min_obstacle_distance_delta_m=round(min_d_delta, 6),
        first_collision_step_mujoco=first_col_mj,
        first_collision_step_isaac=first_col_ik,
        collision_agreement=col_agree,
        near_violation_agreement=round(near_agree, 4),
        applicable_thresholds=applicable_thresholds,
        passed=len(fail_reasons) == 0,
        fail_reasons=fail_reasons,
    )


# ── Output writers ────────────────────────────────────────────────────────────

def _write_trajectory_csv(path: Path, traj: list[StepRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["step", "x", "y", "yaw", "min_obstacle_dist_m",
                    "collision", "action_vx", "action_wz"])
        for r in traj:
            w.writerow([
                r.step,
                f"{r.x:.6f}", f"{r.y:.6f}", f"{r.yaw:.6f}",
                f"{r.min_obstacle_dist_m:.6f}",
                int(r.collision),
                f"{r.action_vx:.4f}", f"{r.action_wz:.4f}",
            ])


def _write_comparison_json(
    path: Path,
    scenario: dict[str, Any],
    metrics: AgreementMetrics,
    generated_at: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "generated_at": generated_at,
        "scenario": scenario["name"],
        "description": scenario["description"],
        "obstacle_positions": scenario["obstacle_positions"],
        "start_xy": list(scenario["start_xy"]),
        "start_yaw": scenario["start_yaw"],
        "n_steps_requested": scenario["n_steps"],
        "control_hz": CONTROL_HZ,
        "near_miss_m": NEAR_MISS_M,
        "obs_radius_m": OBS_RADIUS_M,
        "metrics": {
            "final_xy_error_m": metrics.final_xy_error_m,
            "trajectory_rmse_m": metrics.trajectory_rmse_m,
            "path_length_mujoco_m": metrics.path_length_mujoco_m,
            "path_length_isaac_m": metrics.path_length_isaac_m,
            "path_length_delta_pct": metrics.path_length_delta_pct,
            "min_obs_dist_mujoco_m": metrics.min_obs_dist_mujoco_m,
            "min_obs_dist_isaac_m": metrics.min_obs_dist_isaac_m,
            "min_obstacle_distance_delta_m": metrics.min_obstacle_distance_delta_m,
            "first_collision_step_mujoco": metrics.first_collision_step_mujoco,
            "first_collision_step_isaac": metrics.first_collision_step_isaac,
            "collision_agreement": metrics.collision_agreement,
            "near_violation_agreement": metrics.near_violation_agreement,
        },
        "thresholds": {k: THRESH[k] for k in metrics.applicable_thresholds},
        "n_steps_mujoco": metrics.n_steps_mujoco,
        "n_steps_isaac": metrics.n_steps_isaac,
        "passed": metrics.passed,
        "fail_reasons": metrics.fail_reasons,
    }
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")


def _write_agreement_report(
    out_dir: Path,
    all_metrics: list[AgreementMetrics],
    isaac_available: bool,
    generated_at: str,
) -> None:
    lines: list[str] = []

    lines.append("# MuJoCo ↔ Isaac Sim-to-Sim Agreement Report\n")
    lines.append(f"Generated: {generated_at}  ")
    lines.append(f"Isaac available: {'yes' if isaac_available else 'no (MuJoCo-only run)'}  ")
    lines.append(f"Control Hz: {CONTROL_HZ}  ")
    lines.append(f"OBS_RADIUS_M: {OBS_RADIUS_M}  ")
    lines.append(f"NEAR_MISS_M: {NEAR_MISS_M}\n")

    n_pass = sum(1 for m in all_metrics if m.passed)
    n_fail = sum(1 for m in all_metrics if not m.passed)
    lines.append(f"**PASS={n_pass}  FAIL={n_fail}**\n")

    if not isaac_available:
        lines.append(
            "> **INCOMPLETE** — Isaac backend was not available. "
            "MuJoCo trajectories written but cross-backend comparison not performed. "
            "Re-run inside AppLauncher with `--with-isaac` for the full gate.\n"
        )

    # Per-scenario table
    lines.append("## Scenario Summary\n")
    lines.append(
        "| Scenario | Steps | RMSE (m) | FinalXY (m) | PathΔ (%) "
        "| ColAgree | NearAgree | Passed |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|"
    )
    for m in all_metrics:
        status = "✓" if m.passed else "✗"
        lines.append(
            f"| {m.scenario} | {m.n_steps_aligned} "
            f"| {m.trajectory_rmse_m:.4f} "
            f"| {m.final_xy_error_m:.4f} "
            f"| {m.path_length_delta_pct:.2f} "
            f"| {'✓' if m.collision_agreement else '✗'} "
            f"| {m.near_violation_agreement:.3f} "
            f"| {status} |"
        )
    lines.append("")

    # Thresholds reference
    lines.append("## Thresholds\n")
    lines.append("| Metric | Threshold |")
    lines.append("|---|---|")
    for k, v in THRESH.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    # Fail details
    for m in all_metrics:
        if m.fail_reasons:
            lines.append(f"## Failures — {m.scenario}\n")
            for reason in m.fail_reasons:
                lines.append(f"- {reason}")
            lines.append("")

    # Citable status
    lines.append("## Citable Status\n")
    if not isaac_available:
        lines.append(
            "Isaac physics results are **NOT citable** — comparison gate not run."
        )
    elif n_fail == 0:
        lines.append(
            "All agreement checks PASSED. "
            "Isaac physics results may be used as supporting simulation evidence. "
            "Record this report in the paper submission artifact."
        )
    else:
        lines.append(
            f"**{n_fail} scenario(s) FAILED.** "
            "Isaac physics results are NOT citable until all scenarios pass."
        )

    report_path = out_dir / "agreement_report.md"
    report_path.write_text("\n".join(lines) + "\n")
    return report_path


def _write_summary_json(
    out_dir: Path,
    all_metrics: list[AgreementMetrics],
    isaac_available: bool,
    generated_at: str,
) -> None:
    n_pass = sum(1 for m in all_metrics if m.passed)
    n_fail = sum(1 for m in all_metrics if not m.passed)
    doc = {
        "generated_at": generated_at,
        "isaac_available": isaac_available,
        "control_hz": CONTROL_HZ,
        "near_miss_m": NEAR_MISS_M,
        "obs_radius_m": OBS_RADIUS_M,
        "thresholds": THRESH,
        "n_pass": n_pass,
        "n_fail": n_fail,
        "gate_passed": isaac_available and n_fail == 0,
        "scenarios": [asdict(m) for m in all_metrics],
    }
    with open(out_dir / "summary.json", "w") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")


# ── Printing helpers ──────────────────────────────────────────────────────────

def _info(msg: str = "") -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def _print_scenario_result(metrics: AgreementMetrics) -> None:
    marker = "✓" if metrics.passed else "✗"
    _info(f"  [{marker}] {metrics.scenario}")
    _info(f"       RMSE={metrics.trajectory_rmse_m:.4f}m  "
          f"finalXY={metrics.final_xy_error_m:.4f}m  "
          f"pathΔ={metrics.path_length_delta_pct:.2f}%  "
          f"nearAgree={metrics.near_violation_agreement:.3f}  "
          f"colAgree={metrics.collision_agreement}")
    for reason in metrics.fail_reasons:
        _info(f"       FAIL: {reason}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--with-isaac", action="store_true",
                   help="Run Isaac backend (requires AppLauncher already active)")
    p.add_argument("--output-dir", default=None,
                   help="Output directory (default: benchmarks/validation/sim_to_sim/<timestamp>)")
    p.add_argument("--seed", type=int, default=0,
                   help="RNG seed for both backends (default: 0)")
    args = p.parse_args(argv)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.output_dir is not None:
        out_root = Path(args.output_dir)
    else:
        out_root = _REPO_ROOT / "benchmarks" / "validation" / "sim_to_sim" / ts
    out_root.mkdir(parents=True, exist_ok=True)

    _info()
    _info("═" * 60)
    _info("  FleetSafe MuJoCo ↔ Isaac Sim-to-Sim Agreement Gate")
    _info("═" * 60)
    _info(f"  output   : {out_root}")
    _info(f"  seed     : {args.seed}")
    _info(f"  isaac    : {'enabled' if args.with_isaac else 'disabled (--with-isaac to enable)'}")
    _info()

    # ── Isaac availability check ──────────────────────────────────────────────
    isaac_available = False
    if args.with_isaac:
        try:
            from pxr import Usd as _Usd  # noqa: F401
            from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
                IsaacNavBenchmarkEnv,
                IsaacNotAvailableError,
            )
            isaac_available = True
        except ImportError as exc:
            _info(f"  Isaac not available: {exc}")
            _info("  Continuing in MuJoCo-only mode.")

    # ── MuJoCo import ─────────────────────────────────────────────────────────
    from fleet_safe_vla.envs.mujoco.yahboom.obstacle_env import YahboomObstacleEnv

    # ── Run scenarios ─────────────────────────────────────────────────────────
    all_metrics: list[AgreementMetrics] = []

    for scenario in SCENARIOS:
        name = scenario["name"]
        obs_positions: list[tuple[float, float]] = scenario["obstacle_positions"]
        start_xy: tuple[float, float] = scenario["start_xy"]
        start_yaw: float = scenario["start_yaw"]
        n_steps: int = scenario["n_steps"]
        applicable = scenario["applicable_thresholds"]

        _info(f"  ── {name} ({'no obstacles' if not obs_positions else f'{len(obs_positions)} obstacles'}) ──")

        actions = _generate_actions(
            scenario["action_pattern"], scenario["action_params"], n_steps
        )

        # MuJoCo rollout
        n_obs = len(obs_positions)
        env_mj = YahboomObstacleEnv(
            n_obstacles=n_obs,
            fixed_positions=obs_positions if obs_positions else None,
            max_episode_steps=n_steps + 1,
            control_hz=CONTROL_HZ,
        )
        mj_traj = _run_rollout(env_mj, start_xy, start_yaw, actions, obs_positions, seed=args.seed)
        env_mj.close()

        mj_csv = out_root / name / "mujoco_trajectory.csv"
        _write_trajectory_csv(mj_csv, mj_traj)
        try:
            _disp = mj_csv.relative_to(_REPO_ROOT)
        except ValueError:
            _disp = mj_csv
        _info(f"       MuJoCo: {len(mj_traj)} steps, written → {_disp}")

        # Isaac rollout (if available)
        ik_traj: list[StepRecord] | None = None
        if isaac_available:
            from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
                IsaacNavBenchmarkEnv, IsaacNotAvailableError,
            )
            try:
                env_ik = IsaacNavBenchmarkEnv(
                    fixed_positions=obs_positions if obs_positions else [],
                    n_obstacles=n_obs,
                    max_episode_steps=n_steps + 1,
                    control_hz=CONTROL_HZ,
                )
                ik_traj = _run_rollout(
                    env_ik, start_xy, start_yaw, actions, obs_positions, seed=args.seed
                )
                env_ik.close()
                ik_csv = out_root / name / "isaac_trajectory.csv"
                _write_trajectory_csv(ik_csv, ik_traj)
                try:
                    _ik_disp = ik_csv.relative_to(_REPO_ROOT)
                except ValueError:
                    _ik_disp = ik_csv
                _info(f"       Isaac : {len(ik_traj)} steps, written → {_ik_disp}")
            except Exception as exc:
                _info(f"       Isaac rollout failed: {exc}")
                ik_traj = None

        # Comparison metrics (only if both trajs available)
        if ik_traj is not None:
            metrics = _compute_metrics(name, mj_traj, ik_traj, applicable)
        else:
            # MuJoCo-only: create a self-comparison placeholder so we can still write files
            metrics = _compute_metrics(name, mj_traj, mj_traj, applicable)
            metrics = AgreementMetrics(
                **{
                    **asdict(metrics),
                    "n_steps_isaac": 0,
                    "passed": False,
                    "fail_reasons": ["Isaac backend not run — re-run with --with-isaac"],
                }
            )

        comp_json = out_root / name / "comparison.json"
        _write_comparison_json(comp_json, scenario, metrics, ts)
        _print_scenario_result(metrics)
        all_metrics.append(metrics)
        _info()

    # ── Write report ──────────────────────────────────────────────────────────
    _write_agreement_report(out_root, all_metrics, isaac_available, ts)
    _write_summary_json(out_root, all_metrics, isaac_available, ts)

    n_pass = sum(1 for m in all_metrics if m.passed)
    n_fail = sum(1 for m in all_metrics if not m.passed)

    _info("─" * 60)
    _info(f"  PASS={n_pass}  FAIL={n_fail}")
    try:
        _rep_disp = (out_root / "agreement_report.md").relative_to(_REPO_ROOT)
    except ValueError:
        _rep_disp = out_root / "agreement_report.md"
    _info(f"  Report: {_rep_disp}")

    if not isaac_available:
        _info("  Gate status: INCOMPLETE — Isaac not run")
        _info("═" * 60)
        _info()
        return 2

    if n_fail > 0:
        _info("  Gate status: FAIL — Isaac results NOT citable")
        _info("═" * 60)
        _info()
        return 1

    _info("  Gate status: PASS — Isaac physics evidence accepted")
    _info("═" * 60)
    _info()
    return 0


if __name__ == "__main__":
    sys.exit(main())
