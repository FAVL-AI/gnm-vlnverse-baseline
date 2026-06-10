"""
Fleet Risk Monitor — Fleet-Safe-VLA-OS.

Monitors fleet-wide safety state across multiple robot instances.
Aggregates per-robot risk signals and provides fleet-level alerts.

Risk signals monitored:
  - per-robot: tilt angle, base height, joint limit proximity, CBF intervention rate
  - fleet-level: fraction of robots in non-nominal state, cascade risk

Integrates with:
  - robot-lab SafetyFilter (per-robot low-level)
  - CBFSafetyFilter (per-robot mid-level)
  - ROS2 /safety_status topic publisher

Usage:
    monitor = FleetRiskMonitor(n_robots=4)
    monitor.update_robot(0, obs, cbf_info)
    fleet_status = monitor.get_fleet_status()
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import numpy as np

# Import robot-lab SafetyFilter and SafetyState
from robot_lab.sim2real.safety_filter import SafetyFilter, SafetyConfig, SafetyState


class FleetRiskLevel(Enum):
    """Fleet-wide risk level."""
    NOMINAL    = auto()   # All robots nominal
    ELEVATED   = auto()   # ≥10% robots non-nominal
    HIGH       = auto()   # ≥25% robots non-nominal or cascade risk
    CRITICAL   = auto()   # ≥50% robots emergency / fleet-wide shutdown advised


@dataclass
class RobotRiskState:
    """Per-robot risk state."""
    robot_id: int
    safety_state: SafetyState = SafetyState.NOMINAL
    base_tilt_rad: float = 0.0
    base_height_m: float = 1.0
    cbf_intervention_rate: float = 0.0
    h_min: float = 1.0
    last_update: float = field(default_factory=time.time)
    fall_count: int = 0
    is_online: bool = True

    @property
    def is_safe(self) -> bool:
        return (
            self.safety_state == SafetyState.NOMINAL
            and self.base_tilt_rad < 0.6
            and self.base_height_m > 0.6
        )

    @property
    def risk_score(self) -> float:
        """
        Scalar risk score in [0, 1].
        0 = no risk, 1 = full emergency.
        """
        tilt_risk  = min(1.0, self.base_tilt_rad / 0.8)
        height_risk = max(0.0, 1.0 - (self.base_height_m - 0.5) / 0.5)
        cbf_risk   = min(1.0, self.cbf_intervention_rate * 2.0)
        h_min_risk = max(0.0, -self.h_min / (abs(self.h_min) + 0.1))
        state_risk = {
            SafetyState.NOMINAL:    0.0,
            SafetyState.RAMPING_UP: 0.1,
            SafetyState.HOLDING:    0.5,
            SafetyState.EMERGENCY:  1.0,
        }.get(self.safety_state, 0.5)
        return float(np.clip(
            0.3 * tilt_risk
            + 0.2 * height_risk
            + 0.2 * cbf_risk
            + 0.1 * h_min_risk
            + 0.2 * state_risk,
            0.0, 1.0,
        ))


@dataclass
class FleetStatus:
    """Snapshot of fleet-wide safety state."""
    timestamp: float
    fleet_risk_level: FleetRiskLevel
    n_robots: int
    n_nominal: int
    n_emergency: int
    fraction_safe: float
    mean_risk_score: float
    max_risk_score: float
    fleet_risk_score: float
    robots: list[RobotRiskState]
    alerts: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "fleet_risk_level": self.fleet_risk_level.name,
            "n_robots": self.n_robots,
            "n_nominal": self.n_nominal,
            "n_emergency": self.n_emergency,
            "fraction_safe": self.fraction_safe,
            "mean_risk_score": self.mean_risk_score,
            "max_risk_score": self.max_risk_score,
            "fleet_risk_score": self.fleet_risk_score,
            "alerts": self.alerts,
            "robots": [
                {
                    "id": r.robot_id,
                    "safety_state": r.safety_state.name,
                    "tilt_rad": r.base_tilt_rad,
                    "height_m": r.base_height_m,
                    "risk_score": r.risk_score,
                    "is_safe": r.is_safe,
                    "fall_count": r.fall_count,
                }
                for r in self.robots
            ],
        }


class FleetRiskMonitor:
    """
    Fleet-level risk aggregator and alert system.

    Manages per-robot SafetyFilter instances and CBF state.
    Computes fleet-wide risk level and generates alerts.

    Args:
        n_robots: number of robots in the fleet
        safety_cfg: SafetyConfig for per-robot low-level filter.
                    If None, uses conservative defaults.
        history_len: number of historical snapshots to keep for trend analysis
        stale_timeout_s: mark robot offline if no update in this many seconds
    """

    def __init__(
        self,
        n_robots: int = 1,
        safety_cfg: SafetyConfig | None = None,
        history_len: int = 100,
        stale_timeout_s: float = 2.0,
    ) -> None:
        self.n_robots = n_robots
        self._stale_timeout = stale_timeout_s

        # Per-robot risk states
        self._robot_states = {
            i: RobotRiskState(robot_id=i)
            for i in range(n_robots)
        }

        # Per-robot low-level safety filters (robot-lab)
        _cfg = safety_cfg or SafetyConfig(
            max_tilt_rad=0.8,
            min_base_height_m=0.5,
            torque_ramp_steps=50,
        )
        self._safety_filters = {
            i: SafetyFilter(_cfg)
            for i in range(n_robots)
        }

        # Fleet status history
        self._history: deque[FleetStatus] = deque(maxlen=history_len)

        # Alert callbacks
        self._alert_callbacks: list[callable] = []

        # Fleet-level cascade risk window
        self._cascade_window: deque[float] = deque(maxlen=20)

    # ── Update API ────────────────────────────────────────────────────────────

    def update_robot(
        self,
        robot_id: int,
        obs: np.ndarray,
        cbf_info: dict | None = None,
        raw_actions: np.ndarray | None = None,
        joint_pos: np.ndarray | None = None,
        joint_vel: np.ndarray | None = None,
    ) -> None:
        """
        Update risk state for a single robot.

        Args:
            robot_id:    robot index (0 to n_robots - 1)
            obs:         (45,) proprioceptive observation
            cbf_info:    dict from CBFSafetyFilter.filter_action()
            raw_actions: policy output (pre-filter)
            joint_pos:   current joint positions (for low-level filter state)
            joint_vel:   current joint velocities
        """
        if robot_id not in self._robot_states:
            return

        state = self._robot_states[robot_id]

        # Parse observation
        ang_vel   = obs[0:3]
        proj_grav = obs[3:6]

        # Compute tilt from projected gravity
        cos_tilt = float(np.clip(-proj_grav[2], -1.0, 1.0))
        tilt_rad = float(np.arccos(cos_tilt))

        # Estimate base height (not directly observable from proprio obs)
        # Use a proxy: if tilt is large, height is likely decreasing
        state.base_tilt_rad = tilt_rad

        # Update low-level safety filter state
        sf = self._safety_filters[robot_id]
        if joint_pos is not None and joint_vel is not None and raw_actions is not None:
            _ = sf.filter(
                raw_actions=raw_actions,
                joint_pos=joint_pos,
                joint_vel=joint_vel,
                base_tilt=tilt_rad,
                base_height=state.base_height_m,
            )
        state.safety_state = sf.state

        # Update CBF info
        if cbf_info is not None:
            state.h_min = float(cbf_info.get("h_min", 1.0))
            # Update intervention rate (exponential moving average)
            alpha = 0.1
            intervention = float(cbf_info.get("intervened", False))
            state.cbf_intervention_rate = (
                (1 - alpha) * state.cbf_intervention_rate + alpha * intervention
            )

        # Detect falls
        if tilt_rad > 0.8 or state.base_height_m < 0.5:
            prev_state = state.safety_state
            if prev_state != SafetyState.EMERGENCY:
                state.fall_count += 1

        state.last_update = time.time()
        state.is_online = True

    def update_base_height(self, robot_id: int, height_m: float) -> None:
        """Update base height for a specific robot (from external sensor/estimator)."""
        if robot_id in self._robot_states:
            self._robot_states[robot_id].base_height_m = float(height_m)

    # ── Fleet status ──────────────────────────────────────────────────────────

    def get_fleet_status(self) -> FleetStatus:
        """Compute current fleet-wide safety status."""
        now = time.time()

        # Mark stale robots offline
        for rid, state in self._robot_states.items():
            if now - state.last_update > self._stale_timeout:
                state.is_online = False

        robots = list(self._robot_states.values())
        online = [r for r in robots if r.is_online]

        n_nominal   = sum(1 for r in online if r.safety_state == SafetyState.NOMINAL)
        n_emergency = sum(1 for r in online if r.safety_state == SafetyState.EMERGENCY)
        fraction_safe = n_nominal / max(1, len(online))

        risk_scores = [r.risk_score for r in online]
        mean_risk = float(np.mean(risk_scores)) if risk_scores else 0.0
        max_risk  = float(np.max(risk_scores))  if risk_scores else 0.0

        # Cascade risk: trend in fraction unsafe
        self._cascade_window.append(1.0 - fraction_safe)
        cascade_risk = float(np.mean(self._cascade_window))

        fleet_risk = float(0.4 * max_risk + 0.4 * mean_risk + 0.2 * cascade_risk)

        # Fleet risk level
        if n_emergency >= max(1, len(online) // 2) or fleet_risk > 0.75:
            level = FleetRiskLevel.CRITICAL
        elif fleet_risk > 0.5 or fraction_safe < 0.75:
            level = FleetRiskLevel.HIGH
        elif fleet_risk > 0.25 or fraction_safe < 0.9:
            level = FleetRiskLevel.ELEVATED
        else:
            level = FleetRiskLevel.NOMINAL

        # Generate alerts
        alerts = self._generate_alerts(robots, level, fleet_risk, cascade_risk)

        status = FleetStatus(
            timestamp=now,
            fleet_risk_level=level,
            n_robots=self.n_robots,
            n_nominal=n_nominal,
            n_emergency=n_emergency,
            fraction_safe=fraction_safe,
            mean_risk_score=mean_risk,
            max_risk_score=max_risk,
            fleet_risk_score=fleet_risk,
            robots=robots,
            alerts=alerts,
        )
        self._history.append(status)

        # Fire callbacks
        for cb in self._alert_callbacks:
            try:
                cb(status)
            except Exception:
                pass

        return status

    def register_alert_callback(self, callback: callable) -> None:
        """Register a function to call when fleet status is computed."""
        self._alert_callbacks.append(callback)

    def get_robot_filter(self, robot_id: int) -> SafetyFilter | None:
        """Get the low-level SafetyFilter for a specific robot."""
        return self._safety_filters.get(robot_id)

    def reset_robot(self, robot_id: int) -> None:
        """Reset safety filter and risk state for a robot (e.g., after episode reset)."""
        if robot_id in self._robot_states:
            self._robot_states[robot_id] = RobotRiskState(robot_id=robot_id)
        if robot_id in self._safety_filters:
            self._safety_filters[robot_id].reset()

    def reset_all(self) -> None:
        """Reset all robots."""
        for rid in range(self.n_robots):
            self.reset_robot(rid)
        self._cascade_window.clear()
        self._history.clear()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _generate_alerts(
        self,
        robots: list[RobotRiskState],
        level: FleetRiskLevel,
        fleet_risk: float,
        cascade_risk: float,
    ) -> list[str]:
        alerts: list[str] = []

        if level == FleetRiskLevel.CRITICAL:
            alerts.append(f"CRITICAL: Fleet risk={fleet_risk:.2f}. Consider emergency stop.")

        for r in robots:
            if r.safety_state == SafetyState.EMERGENCY:
                alerts.append(f"Robot {r.robot_id}: EMERGENCY (tilt={r.base_tilt_rad:.2f} rad)")
            elif r.base_tilt_rad > 0.6:
                alerts.append(f"Robot {r.robot_id}: High tilt {r.base_tilt_rad:.2f} rad")
            if r.cbf_intervention_rate > 0.3:
                alerts.append(
                    f"Robot {r.robot_id}: High CBF intervention rate "
                    f"{r.cbf_intervention_rate:.1%}"
                )

        if cascade_risk > 0.3:
            alerts.append(f"Cascade risk elevated: {cascade_risk:.1%} of fleet non-nominal")

        return alerts

    # ── History / analytics ───────────────────────────────────────────────────

    def get_trend(self, key: str = "fleet_risk_score", window: int = 20) -> np.ndarray:
        """Return recent trend for a fleet status metric."""
        history = list(self._history)[-window:]
        return np.array([getattr(h, key) for h in history], dtype=np.float32)

    def summary(self) -> str:
        """Human-readable fleet summary."""
        if not self._history:
            return "No data yet."
        latest = self._history[-1]
        return (
            f"Fleet [{latest.fleet_risk_level.name}] "
            f"Risk={latest.fleet_risk_score:.2f} "
            f"Safe={latest.n_nominal}/{latest.n_robots} "
            f"Emergency={latest.n_emergency}"
        )
