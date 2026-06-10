"""
Domain-randomisation parameter sweeps for Yahboom physics validation.

Each sweep varies one parameter across a range while holding all others fixed,
running N straight-line episodes per point and averaging the motion metrics.

Usage::

    from fleet_safe_vla.envs.mujoco.yahboom.physics_env import YahboomPhysicsEnv
    from fleet_safe_vla.validation import FrictionSweep, MotionValidator

    sweep = FrictionSweep(n_episodes=5, vx_cmd=0.3, duration_s=3.0)
    rows  = sweep.run()
    MotionValidator.export_metrics_csv(rows, "logs/friction_sweep.csv")
    MotionValidator.plot_sweep_summary(
        rows, "friction", ["vx_rmse", "mean_slip", "yaw_drift_rad_per_m"],
        "logs/friction_sweep.png"
    )
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import numpy as np

from fleet_safe_vla.validation.motion_validator import MotionValidator, MotionMetrics


@dataclass
class SweepPoint:
    param_name: str
    param_value: float
    metrics: MotionMetrics

    def to_row(self) -> dict[str, Any]:
        row = {"param_name": self.param_name, "param_value": self.param_value}
        row.update(asdict(self.metrics))
        return row


class ParameterSweep:
    """Base class for single-parameter sweeps."""

    def __init__(
        self,
        param_name: str,
        values: list[float],
        n_episodes: int = 3,
        vx_cmd: float = 0.3,
        duration_s: float = 3.0,
        seed: int = 42,
    ):
        self.param_name = param_name
        self.values = values
        self.n_episodes = n_episodes
        self.vx_cmd = vx_cmd
        self.duration_s = duration_s
        self.seed = seed

    def _make_env(self, value: float):
        """Subclasses override to construct env with the swept parameter."""
        raise NotImplementedError

    def run(self, verbose: bool = True) -> list[dict]:
        """
        Run all sweep points and return a list of flat metric dicts.
        Each dict has 'param_name', 'param_value', and all MotionMetrics fields.
        """
        rows: list[dict] = []

        for v in self.values:
            if verbose:
                print(f"  [{self.param_name}={v:.4g}] ", end="", flush=True)

            env = self._make_env(v)
            validator = MotionValidator(env)
            all_metrics: list[MotionMetrics] = []

            for ep in range(self.n_episodes):
                records = validator.run_straight_line(
                    vx=self.vx_cmd,
                    duration_s=self.duration_s,
                    seed=self.seed + ep,
                )
                m = validator.compute_metrics(records)
                all_metrics.append(m)

            # Average numeric metrics across episodes
            avg = self._average_metrics(all_metrics)
            sp = SweepPoint(param_name=self.param_name, param_value=v, metrics=avg)
            row = sp.to_row()
            rows.append(row)

            if verbose:
                print(
                    f"vx_rmse={avg.vx_rmse:.4f}  "
                    f"slip={avg.mean_slip:.3f}  "
                    f"t90={avg.time_to_90pct_s:.3f}s  "
                    f"stable={avg.stable}"
                )

            env.close()

        return rows

    @staticmethod
    def _average_metrics(ms: list[MotionMetrics]) -> MotionMetrics:
        numeric = ["vx_rmse", "vx_ss_error", "wz_rmse", "lateral_rms",
                   "mean_slip", "max_slip", "yaw_drift_rad_per_m", "time_to_90pct_s"]

        def _mean(attr: str) -> float:
            vals = [getattr(m, attr) for m in ms]
            valid = [v for v in vals if np.isfinite(v)]
            return float(np.mean(valid)) if valid else float("nan")

        return MotionMetrics(
            vx_rmse=_mean("vx_rmse"),
            vx_ss_error=_mean("vx_ss_error"),
            wz_rmse=_mean("wz_rmse"),
            lateral_rms=_mean("lateral_rms"),
            mean_slip=_mean("mean_slip"),
            max_slip=_mean("max_slip"),
            yaw_drift_rad_per_m=_mean("yaw_drift_rad_per_m"),
            time_to_90pct_s=_mean("time_to_90pct_s"),
            stable=all(m.stable for m in ms),
            n_steps=ms[0].n_steps if ms else 0,
        )


# ── Concrete sweeps ──────────────────────────────────────────────────────────── #

class FrictionSweep(ParameterSweep):
    """Sweep wheel-floor sliding friction coefficient."""

    DEFAULT_VALUES = [0.3, 0.5, 0.8, 1.0, 1.5, 2.0]

    def __init__(self, values: list[float] | None = None, **kwargs):
        super().__init__(
            param_name="friction",
            values=values or self.DEFAULT_VALUES,
            **kwargs,
        )

    def _make_env(self, value: float):
        from fleet_safe_vla.envs.mujoco.yahboom.physics_env import YahboomPhysicsEnv
        return YahboomPhysicsEnv(friction=value)


class TimestepSweep(ParameterSweep):
    """Sweep physics timestep (affects numerical stability)."""

    DEFAULT_VALUES = [0.001, 0.002, 0.004, 0.006, 0.008]

    def __init__(self, values: list[float] | None = None, **kwargs):
        super().__init__(
            param_name="timestep",
            values=values or self.DEFAULT_VALUES,
            **kwargs,
        )

    def _make_env(self, value: float):
        from fleet_safe_vla.envs.mujoco.yahboom.physics_env import (
            YahboomPhysicsEnv,
            WHEEL_R_M,
        )
        env = YahboomPhysicsEnv()
        # Patch sim_dt and rebuild PID dt
        env._sim_dt = value
        env._decimation = max(1, round(1.0 / (env.control_hz * value)))
        env._pid_l._WheelPID__init_dt = value   # re-init PIDs with new dt
        env._pid_r._WheelPID__init_dt = value
        return env

    def _make_env(self, value: float):  # noqa: F811  (simplified override)
        from fleet_safe_vla.envs.mujoco.yahboom.physics_env import YahboomPhysicsEnv
        import mujoco

        # Build env, then patch model timestep
        env = YahboomPhysicsEnv()
        env._model.opt.timestep = value
        env._sim_dt = value
        env._decimation = max(1, round(1.0 / (env.control_hz * value)))
        env._pid_l = env._pid_l.__class__(
            env.pid_kp, env.pid_ki, env.pid_kd, value
        )
        env._pid_r = env._pid_r.__class__(
            env.pid_kp, env.pid_ki, env.pid_kd, value
        )
        return env


class ActuatorGainSweep(ParameterSweep):
    """Sweep PID proportional gain KP."""

    DEFAULT_VALUES = [0.01, 0.05, 0.10, 0.25, 0.50, 1.00]

    def __init__(self, values: list[float] | None = None, **kwargs):
        super().__init__(
            param_name="pid_kp",
            values=values or self.DEFAULT_VALUES,
            **kwargs,
        )

    def _make_env(self, value: float):
        from fleet_safe_vla.envs.mujoco.yahboom.physics_env import YahboomPhysicsEnv
        return YahboomPhysicsEnv(pid_kp=value)


class MassSweep(ParameterSweep):
    """Sweep robot base mass (models payload variance)."""

    DEFAULT_VALUES = [1.5, 2.1, 2.5, 3.0, 4.0]

    def __init__(self, values: list[float] | None = None, **kwargs):
        super().__init__(
            param_name="robot_mass",
            values=values or self.DEFAULT_VALUES,
            **kwargs,
        )

    def _make_env(self, value: float):
        from fleet_safe_vla.envs.mujoco.yahboom.physics_env import YahboomPhysicsEnv
        return YahboomPhysicsEnv(robot_mass=value)
