"""
Yahboom-specific Control Barrier Function safety filter.

Barrier function h(x, obs_pos):
  h = ||robot_pos - obs_pos||² - d_safe²

  ḣ ≥ -α · h  (CBF condition)

QP: find [vx_safe, wz_safe] closest to nominal action such that
    all barrier conditions are satisfied.

Uses scipy for the QP (available without GPU). For real-time use,
consider osqp or qpsolvers.

Also implements:
  - Velocity hard clipping
  - Emergency stop on imminent collision
  - Velocity smoothing filter
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from scipy.optimize import minimize


@dataclass
class YahboomCBFConfig:
    max_linear_ms: float  = 0.5
    max_angular_rs: float = 1.0
    d_safe_m: float       = 0.30      # barrier radius
    alpha: float          = 1.0       # CBF decay rate
    estop_dist_m: float   = 0.15      # hard stop
    smoothing: float      = 0.7       # exponential smoothing α


class YahboomCBFFilter:
    """
    Filters [vx_nominal, wz_nominal] → [vx_safe, wz_safe] using CBF-QP.

    Usage:
        filt = YahboomCBFFilter(YahboomCBFConfig())
        safe = filt.filter(obs, nominal_action, obstacle_positions)
    """

    def __init__(self, cfg: YahboomCBFConfig | None = None):
        self.cfg = cfg or YahboomCBFConfig()
        self._prev_cmd = np.zeros(2)
        self._estop_active = False
        self._intervention_count = 0
        self._total_calls = 0

    def filter(
        self,
        obs: np.ndarray,
        nominal_action: np.ndarray,
        obstacle_positions: Sequence[np.ndarray] | None = None,
        robot_xy: np.ndarray | None = None,
        obstacle_radii: Sequence[float] | None = None,
    ) -> tuple[np.ndarray, dict]:
        """
        Args:
            obs:               Flat obs vector (any length; used only if robot_xy is None)
            nominal_action:    [vx, wz] from planner
            obstacle_positions: list of (2,) obstacle centre coordinates (world frame,
                                consistent with robot_xy frame)
            robot_xy:          Explicit (2,) robot world position.  When provided,
                                overrides obs-index extraction.  Pass this when the obs
                                vector layout differs from the 36-dim YahboomObsAdapter
                                default (e.g. 47-dim M3ProObsAdapter used by Isaac Sim).
            obstacle_radii:    Per-obstacle physical radii (m).  When provided the CBF
                                uses surface distance (center_dist − radius) for both the
                                early-exit check and the barrier function, giving a correct
                                safety margin relative to obstacle surfaces.  When None the
                                legacy centre-to-centre behaviour is used (MuJoCo path).

        Returns:
            safe_action: [vx, wz]
            info: dict with intervention details
        """
        self._total_calls += 1
        if robot_xy is not None:
            robot_xy = np.asarray(robot_xy, dtype=np.float64).flatten()[:2]
        else:
            # Default: 36-dim YahboomObsAdapter layout — odom at [16:26]
            robot_xy = np.array([float(obs[16]), float(obs[17])])

        # Hard clip to kinematics limits
        nominal = np.clip(
            nominal_action,
            [-self.cfg.max_linear_ms, -self.cfg.max_angular_rs],
            [ self.cfg.max_linear_ms,  self.cfg.max_angular_rs],
        ).astype(np.float64)

        obs_list  = list(obstacle_positions) if obstacle_positions else []
        radii_list = list(obstacle_radii) if obstacle_radii else [0.0] * len(obs_list)

        # Emergency stop check
        min_dist = self._min_dist(robot_xy, obs_list, radii_list)
        if min_dist < self.cfg.estop_dist_m:
            self._estop_active = True
            safe = np.zeros(2, dtype=np.float32)
            self._intervention_count += 1
            return safe, {
                "intervened": True, "estop": True, "min_dist_m": min_dist,
                "intervention_count": self._intervention_count,
            }
        self._estop_active = False

        # No obstacles — just clip and smooth
        if not obs_list or min_dist > self.cfg.d_safe_m * 2.0:
            safe = self._smooth(nominal)
            return safe.astype(np.float32), {
                "intervened": False, "estop": False,
                "min_dist_m": min_dist, "intervention_count": self._intervention_count,
            }

        # CBF-QP: minimise ||u - u_nom||² subject to CBF constraints
        safe_u, intervened = self._cbf_qp(nominal, robot_xy, obs_list, radii_list)
        safe = self._smooth(safe_u)

        if intervened:
            self._intervention_count += 1

        return safe.astype(np.float32), {
            "intervened": intervened, "estop": False,
            "min_dist_m": min_dist, "intervention_count": self._intervention_count,
        }

    def _cbf_qp(
        self,
        u_nom: np.ndarray,
        robot_xy: np.ndarray,
        obs_list: list[np.ndarray],
        radii_list: list[float] | None = None,
    ) -> tuple[np.ndarray, bool]:
        """Solve CBF-QP via scipy minimize (SLSQP)."""
        if radii_list is None:
            radii_list = [0.0] * len(obs_list)

        def objective(u):
            return np.sum((u - u_nom)**2)

        def objective_grad(u):
            return 2 * (u - u_nom)

        constraints = []
        for obs_pos, obs_r in zip(obs_list, radii_list):
            op = np.asarray(obs_pos[:2])
            center_dist = float(np.linalg.norm(robot_xy - op))
            surface_dist = center_dist - obs_r
            direction = robot_xy - op
            direction_norm = direction / (np.linalg.norm(direction) + 1e-8)

            if obs_r > 0.0:
                # Surface-distance barrier (Isaac path with finite-radius obstacles):
                # h = surface_dist² − d_safe²,  ḣ = 2·surface_dist·ṡ
                h = surface_dist**2 - self.cfg.d_safe_m**2

                def cbf_constraint(u, d=direction_norm, h_val=h, sd=surface_dist):
                    vx_component = u[0] * d[0]
                    return 2.0 * sd * vx_component + self.cfg.alpha * h_val
            else:
                # Legacy centre-to-centre barrier (MuJoCo path, obs_r=0):
                # h = center_dist² − d_safe²,  ḣ ≈ 2·vx_component  (original approximation)
                h = center_dist**2 - self.cfg.d_safe_m**2

                def cbf_constraint(u, d=direction_norm, h_val=h):
                    vx_component = u[0] * d[0]
                    return 2.0 * vx_component + self.cfg.alpha * h_val

            constraints.append({"type": "ineq", "fun": cbf_constraint})

        bounds = [
            (-self.cfg.max_linear_ms, self.cfg.max_linear_ms),
            (-self.cfg.max_angular_rs, self.cfg.max_angular_rs),
        ]

        try:
            result = minimize(
                objective, u_nom,
                jac=objective_grad,
                method="SLSQP",
                bounds=bounds,
                constraints=constraints,
                options={"maxiter": 50, "ftol": 1e-6},
            )
            u_safe = result.x
        except Exception:
            # Fallback: zero velocity
            u_safe = np.zeros(2)

        intervened = bool(np.linalg.norm(u_safe - u_nom) > 0.02)
        return u_safe, intervened

    def _smooth(self, u: np.ndarray) -> np.ndarray:
        α = self.cfg.smoothing
        smoothed = α * self._prev_cmd + (1 - α) * u
        self._prev_cmd = smoothed.copy()
        return smoothed

    @staticmethod
    def _min_dist(robot_xy: np.ndarray, obs_list: list, radii_list: list | None = None) -> float:
        if not obs_list:
            return 99.0
        _radii = radii_list if radii_list else [0.0] * len(obs_list)
        dists = [
            float(np.linalg.norm(robot_xy - np.asarray(o[:2]))) - r
            for o, r in zip(obs_list, _radii)
        ]
        return min(dists)

    def reset(self) -> None:
        self._prev_cmd = np.zeros(2)
        self._estop_active = False

    @property
    def intervention_rate(self) -> float:
        if self._total_calls == 0:
            return 0.0
        return self._intervention_count / self._total_calls

    @property
    def stats(self) -> dict:
        return {
            "total_calls": self._total_calls,
            "intervention_count": self._intervention_count,
            "intervention_rate": self.intervention_rate,
            "estop_active": self._estop_active,
        }
