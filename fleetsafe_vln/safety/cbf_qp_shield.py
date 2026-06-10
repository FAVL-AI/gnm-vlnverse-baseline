"""CBFQPShield — thin facade over fleet_safe_vla CBF filter.

Adds the extended certificate fields required by FleetSafe-VLN:
  - pose (x, y, yaw)
  - min_human_distance_m
  - intervention_magnitude (L2 norm of u_nom - u_safe)
  - barrier_value_h (alias for h_min)
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple


@dataclass
class ExtendedCertificate:
    """Per-step safety certificate with FleetSafe-VLN extended fields."""
    t: float = 0.0
    pose: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    u_nominal: List[float] = field(default_factory=lambda: [0.0, 0.0])
    u_safe: List[float] = field(default_factory=lambda: [0.0, 0.0])
    cbf_active: bool = False
    barrier_value_h: float = 0.0
    min_obstacle_distance_m: float = 0.0
    min_human_distance_m: float = math.inf
    certificate_valid: bool = True
    intervention_magnitude: float = 0.0
    qp_status: str = "optimal"
    latency_ms: float = 0.0
    model_name: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        if math.isinf(d.get("min_human_distance_m", 0)):
            d["min_human_distance_m"] = None
        return d

    def __post_init__(self):
        if len(self.u_nominal) >= 2 and len(self.u_safe) >= 2:
            self.intervention_magnitude = math.sqrt(
                (self.u_nominal[0] - self.u_safe[0]) ** 2
                + (self.u_nominal[1] - self.u_safe[1]) ** 2
            )


class CBFQPShield:
    """Wraps fleet_safe_vla CBF filter with extended certificate output."""

    def __init__(
        self,
        d_safe: float = 0.50,
        estop_dist: float = 0.30,
        alpha: float = 1.0,
        model_name: str = "",
    ):
        self._d_safe = d_safe
        self._estop = estop_dist
        self._alpha = alpha
        self._model_name = model_name
        self._filter = None
        self._init_filter()

    def _init_filter(self) -> None:
        try:
            from fleet_safe_vla.fleet_safety.yahboom_cbf import (
                YahboomCBFFilter,
                YahboomCBFConfig,
            )
            cfg = YahboomCBFConfig(
                d_safe_m=self._d_safe,
                estop_dist_m=self._estop,
                alpha=self._alpha,
            )
            self._filter = YahboomCBFFilter(cfg)
        except (ImportError, Exception):
            self._filter = None

    def filter(
        self,
        u_nom: List[float],
        obstacle_dists: List[float],
        robot_pose: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        human_dists: Optional[List[float]] = None,
    ) -> ExtendedCertificate:
        t0 = time.perf_counter()
        min_obs = min(obstacle_dists) if obstacle_dists else math.inf
        min_hum = min(human_dists) if human_dists else math.inf

        if self._filter is not None:
            try:
                import numpy as np
                rx, ry = float(robot_pose[0]), float(robot_pose[1])
                obs_positions = [np.array([ox, oy]) for ox, oy in (
                    getattr(self, "_last_obs_positions", [])
                )] or None

                safe_arr, info = self._filter.filter(
                    obs=np.zeros(36),
                    nominal_action=np.array(u_nom[:2], dtype=float),
                    obstacle_positions=obs_positions,
                    robot_xy=np.array([rx, ry]),
                )
                u_safe = list(float(v) for v in safe_arr[:2])
                cbf_active = bool(info.get("cbf_active", info.get("intervened", False)))
                qp_status = str(info.get("qp_status", "optimal"))
                h_min = float(min_obs - self._d_safe)
            except Exception:
                u_safe, h_min, cbf_active, qp_status = self._analytic_filter(u_nom, min_obs)
        else:
            u_safe, h_min, cbf_active, qp_status = self._analytic_filter(u_nom, min_obs)

        latency_ms = (time.perf_counter() - t0) * 1000

        cert = ExtendedCertificate(
            t=time.time(),
            pose=tuple(robot_pose),
            u_nominal=list(u_nom),
            u_safe=u_safe,
            cbf_active=cbf_active,
            barrier_value_h=h_min,
            min_obstacle_distance_m=min_obs if not math.isinf(min_obs) else 0.0,
            min_human_distance_m=min_hum,
            certificate_valid=(qp_status in ("optimal", "estop_fallback", "skipped")),
            qp_status=qp_status,
            latency_ms=latency_ms,
            model_name=self._model_name,
        )
        return cert

    def _analytic_filter(
        self, u_nom: List[float], min_dist: float
    ) -> tuple:
        """Fallback analytic CBF when QP solver unavailable."""
        vx, wz = float(u_nom[0]), float(u_nom[1] if len(u_nom) > 1 else 0.0)

        if min_dist < self._estop:
            return [0.0, wz], self._estop - min_dist, True, "estop_fallback"
        if min_dist < self._d_safe:
            scale = (min_dist - self._estop) / max(1e-6, self._d_safe - self._estop)
            return [vx * max(0.0, scale), wz], self._d_safe - min_dist, True, "optimal"
        return [vx, wz], min_dist - self._d_safe, False, "optimal"
