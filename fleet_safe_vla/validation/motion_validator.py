"""
MotionValidator — characterises Yahboom wheel-ground contact dynamics.

Records per-step kinematics from a YahboomPhysicsEnv and computes:
  - commanded vs achieved linear / angular velocity
  - wheel angular velocity
  - per-wheel slip ratio  (0 = perfect rolling, 1 = full spin)
  - lateral body velocity (should be ~0 for diff-drive)
  - cumulative yaw drift from straight-line target

Exports:
  - CSV:  one row per step, all signals
  - PNG:  velocity tracking, slip ratio, yaw drift (via matplotlib)
"""
from __future__ import annotations

import csv
import math
import time
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Callable, Sequence

import numpy as np


# ── Data types ──────────────────────────────────────────────────────────────── #

@dataclass
class StepRecord:
    t: float            # elapsed time (s)
    step: int

    cmd_vx: float       # commanded forward speed (m/s)
    cmd_wz: float       # commanded yaw rate (rad/s)

    actual_vx: float    # body-frame forward velocity (m/s)
    actual_vy: float    # body-frame lateral velocity (m/s, should ≈ 0)
    actual_wz: float    # body angular velocity (rad/s)

    wheel_l_vel: float  # left joint angular velocity (rad/s)
    wheel_r_vel: float  # right joint angular velocity (rad/s)

    slip_ratio_l: float # left wheel slip  ∈ [0, 1]
    slip_ratio_r: float # right wheel slip ∈ [0, 1]

    x: float            # world-frame position x (m)
    y: float            # world-frame position y (m)
    yaw: float          # heading (rad)


@dataclass
class MotionMetrics:
    vx_rmse: float              # RMS(cmd_vx - actual_vx) over full episode
    vx_ss_error: float          # mean |error| in last 50 % of steps (steady-state)
    wz_rmse: float              # RMS(cmd_wz - actual_wz)
    lateral_rms: float          # RMS of lateral velocity (should be near 0)
    mean_slip: float            # mean slip ratio (both wheels averaged)
    max_slip: float             # peak slip ratio
    yaw_drift_rad_per_m: float  # yaw drift divided by distance (straight-line metric)
    time_to_90pct_s: float      # time until |actual_vx| >= 0.9 * |cmd_vx| (first occurrence)
    stable: bool                # no NaN or Inf detected
    n_steps: int


# ── Validator ───────────────────────────────────────────────────────────────── #

class MotionValidator:
    """
    Run standardised motion tests on a YahboomPhysicsEnv and collect metrics.

    Usage::

        from fleet_safe_vla.envs.mujoco.yahboom.physics_env import YahboomPhysicsEnv
        from fleet_safe_vla.validation import MotionValidator

        env = YahboomPhysicsEnv(friction=0.8)
        validator = MotionValidator(env)
        records = validator.run_straight_line(vx=0.3, duration_s=3.0)
        metrics = validator.compute_metrics(records)
        validator.export_csv(records, "logs/straight_line.csv")
        validator.plot_velocity_tracking(records, "logs/velocity_tracking.png")
    """

    WHEEL_R = 0.048   # m

    def __init__(self, env):
        self._env = env

    # ── Episode runners ──────────────────────────────────────────────────────── #

    def _set_initial_pose(self) -> None:
        """Face +x, zero all velocities, update kinematics."""
        import mujoco
        env = self._env
        env._data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
        env._data.qvel[:] = 0.0
        mujoco.mj_forward(env._model, env._data)

    def run_straight_line(
        self,
        vx: float = 0.3,
        duration_s: float = 3.0,
        seed: int = 0,
    ) -> list[StepRecord]:
        """Drive straight ahead and record every control step."""
        env = self._env
        env.reset(seed=seed)
        self._set_initial_pose()

        action = np.array([vx, 0.0], dtype=np.float32)
        n_steps = max(1, round(duration_s * env.control_hz))
        return self._run(action_fn=lambda _: action, n_steps=n_steps)

    def run_turn_in_place(
        self,
        wz: float = 1.0,
        duration_s: float = 2.0,
        seed: int = 0,
    ) -> list[StepRecord]:
        """Spin in place and record every control step."""
        env = self._env
        env.reset(seed=seed)
        self._set_initial_pose()

        action = np.array([0.0, wz], dtype=np.float32)
        n_steps = max(1, round(duration_s * env.control_hz))
        return self._run(action_fn=lambda _: action, n_steps=n_steps)

    def run_velocity_ramp(
        self,
        vx_max: float = 0.5,
        duration_s: float = 4.0,
        seed: int = 0,
    ) -> list[StepRecord]:
        """Linearly ramp vx from 0 → vx_max and record response."""
        env = self._env
        env.reset(seed=seed)
        self._set_initial_pose()

        n_steps = max(1, round(duration_s * env.control_hz))

        def _ramp(step: int) -> np.ndarray:
            t = step / max(n_steps - 1, 1)
            return np.array([vx_max * t, 0.0], dtype=np.float32)

        return self._run(action_fn=_ramp, n_steps=n_steps)

    def _run(
        self,
        action_fn: Callable[[int], np.ndarray],
        n_steps: int,
    ) -> list[StepRecord]:
        env = self._env
        records: list[StepRecord] = []
        dt = 1.0 / env.control_hz
        t = 0.0

        for step in range(n_steps):
            action = action_fn(step)
            cmd_vx, cmd_wz = float(action[0]), float(action[1])

            _, _, _, _, info = env.step(action)

            vx_b      = info.get("body_vx", 0.0)
            vy_b      = info.get("body_vy", 0.0)
            wz_b      = info.get("body_wz", 0.0)
            sl        = info.get("slip_ratio_l", 0.0)
            sr        = info.get("slip_ratio_r", 0.0)
            ol        = info.get("wheel_omega_l", 0.0)
            orr       = info.get("wheel_omega_r", 0.0)
            x_pos, y_pos, yaw = env.get_robot_pose()

            records.append(StepRecord(
                t=t, step=step,
                cmd_vx=cmd_vx, cmd_wz=cmd_wz,
                actual_vx=vx_b, actual_vy=vy_b, actual_wz=wz_b,
                wheel_l_vel=ol, wheel_r_vel=orr,
                slip_ratio_l=sl, slip_ratio_r=sr,
                x=x_pos, y=y_pos, yaw=yaw,
            ))
            t += dt

        return records

    # ── Metrics ─────────────────────────────────────────────────────────────── #

    def compute_metrics(self, records: list[StepRecord]) -> MotionMetrics:
        if not records:
            return MotionMetrics(0, 0, 0, 0, 0, 0, 0, float("nan"), False, 0)

        vx_err = np.array([r.cmd_vx - r.actual_vx for r in records])
        wz_err = np.array([r.cmd_wz - r.actual_wz for r in records])
        lat    = np.array([r.actual_vy for r in records])
        slips  = np.array([(r.slip_ratio_l + r.slip_ratio_r) / 2 for r in records])

        # Steady-state = last 50 % of steps
        ss_start = len(records) // 2
        vx_ss_error = float(np.mean(np.abs(vx_err[ss_start:])))

        # Yaw drift per meter (straight-line test)
        total_dist = sum(
            math.sqrt((records[i].x - records[i-1].x)**2 +
                      (records[i].y - records[i-1].y)**2)
            for i in range(1, len(records))
        )
        yaw_drift = abs(records[-1].yaw - records[0].yaw)
        yaw_per_m = yaw_drift / max(total_dist, 0.01)

        # Time to 90 % of commanded vx
        target_vx = max(abs(records[0].cmd_vx), 1e-4)
        t90 = float("nan")
        for r in records:
            if abs(r.actual_vx) >= 0.9 * target_vx:
                t90 = r.t
                break

        stable = all(
            math.isfinite(r.actual_vx) and math.isfinite(r.actual_wz)
            for r in records
        )

        return MotionMetrics(
            vx_rmse=float(np.sqrt(np.mean(vx_err**2))),
            vx_ss_error=vx_ss_error,
            wz_rmse=float(np.sqrt(np.mean(wz_err**2))),
            lateral_rms=float(np.sqrt(np.mean(lat**2))),
            mean_slip=float(np.mean(slips)),
            max_slip=float(np.max(slips)),
            yaw_drift_rad_per_m=yaw_per_m,
            time_to_90pct_s=t90,
            stable=stable,
            n_steps=len(records),
        )

    # ── CSV export ──────────────────────────────────────────────────────────── #

    @staticmethod
    def export_csv(records: list[StepRecord], path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not records:
            return path
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[fi.name for fi in fields(StepRecord)])
            writer.writeheader()
            writer.writerows(asdict(r) for r in records)
        return path

    @staticmethod
    def export_metrics_csv(
        rows: list[dict],   # each dict: {"param_name", "param_value", ...metrics}
        path: str | Path,
    ) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            return path
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return path

    # ── Plots ───────────────────────────────────────────────────────────────── #

    @staticmethod
    def plot_velocity_tracking(
        records: list[StepRecord],
        path: str | Path,
        title: str = "Velocity Tracking",
    ) -> Path:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        t = [r.t for r in records]
        cmd_vx    = [r.cmd_vx for r in records]
        actual_vx = [r.actual_vx for r in records]
        wheel_l   = [r.wheel_l_vel * 0.048 for r in records]   # rad/s → m/s surface

        fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)

        ax = axes[0]
        ax.plot(t, cmd_vx,    label="commanded vx",   linestyle="--", color="tab:blue")
        ax.plot(t, actual_vx, label="actual vx",      color="tab:orange")
        ax.set_ylabel("m/s")
        ax.set_title(title)
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)

        ax = axes[1]
        ax.plot(t, wheel_l, label="wheel surface speed (L)", color="tab:green")
        ax.plot(t, actual_vx, label="body speed", color="tab:orange", linestyle="--")
        ax.set_ylabel("m/s")
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)

        ax = axes[2]
        err = [cmd - act for cmd, act in zip(cmd_vx, actual_vx)]
        ax.plot(t, err, color="tab:red", label="vx error")
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_ylabel("m/s error")
        ax.set_xlabel("time (s)")
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        fig.savefig(path, dpi=120)
        plt.close(fig)
        return path

    @staticmethod
    def plot_slip_ratio(
        records: list[StepRecord],
        path: str | Path,
        title: str = "Wheel Slip Ratio",
    ) -> Path:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        t   = [r.t for r in records]
        sl  = [r.slip_ratio_l for r in records]
        sr  = [r.slip_ratio_r for r in records]
        avg = [(l + r) / 2 for l, r in zip(sl, sr)]

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(t, sl,  alpha=0.6, label="left wheel")
        ax.plot(t, sr,  alpha=0.6, label="right wheel")
        ax.plot(t, avg, linewidth=2, color="black", label="average")
        ax.axhline(0.1, linestyle="--", color="green",  label="10% threshold")
        ax.axhline(0.3, linestyle="--", color="orange", label="30% threshold")
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("slip ratio")
        ax.set_xlabel("time (s)")
        ax.set_title(title)
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        fig.savefig(path, dpi=120)
        plt.close(fig)
        return path

    @staticmethod
    def plot_yaw_drift(
        records: list[StepRecord],
        path: str | Path,
        title: str = "Yaw Drift (Straight-Line)",
    ) -> Path:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        t    = [r.t for r in records]
        yaw0 = records[0].yaw if records else 0.0
        yaw_drift = [math.degrees(r.yaw - yaw0) for r in records]

        fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)

        axes[0].plot(t, yaw_drift, color="tab:purple")
        axes[0].axhline(0, color="black", linewidth=0.5)
        axes[0].set_ylabel("yaw drift (°)")
        axes[0].set_title(title)
        axes[0].grid(True, alpha=0.3)

        # X-Y trajectory
        axes[1].plot([r.x for r in records], [r.y for r in records], color="tab:blue")
        axes[1].set_aspect("equal")
        axes[1].set_xlabel("x (m)")
        axes[1].set_ylabel("y (m)")
        axes[1].set_title("XY trajectory")
        axes[1].grid(True, alpha=0.3)

        plt.tight_layout()
        fig.savefig(path, dpi=120)
        plt.close(fig)
        return path

    @staticmethod
    def plot_sweep_summary(
        rows: list[dict],
        param_key: str,
        metrics: Sequence[str],
        path: str | Path,
        title: str = "Parameter Sweep",
    ) -> Path:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        param_vals = [r[param_key] for r in rows]
        n = len(metrics)
        fig, axes = plt.subplots(1, n, figsize=(5 * n, 4))
        if n == 1:
            axes = [axes]

        for ax, metric in zip(axes, metrics):
            vals = [r.get(metric, float("nan")) for r in rows]
            ax.bar(range(len(param_vals)), vals, tick_label=[f"{v:.3g}" for v in param_vals])
            ax.set_xlabel(param_key)
            ax.set_ylabel(metric)
            ax.set_title(metric)
            ax.grid(True, alpha=0.3, axis="y")

        fig.suptitle(title)
        plt.tight_layout()
        fig.savefig(path, dpi=120)
        plt.close(fig)
        return path
