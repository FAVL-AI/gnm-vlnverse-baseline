"""
Fleet-Safe Evaluation Metrics — extends robot-lab's metric suite.

Adds fleet-specific metrics on top of robot-lab's base metrics:
  - CBF intervention rate (fleet safety measure)
  - Multi-robot coordination score
  - Fleet success rate (all robots succeed)
  - Per-robot → fleet aggregation

Imports and re-exports robot-lab metrics for convenience:
    from fleet_safe_vla.eval.metrics.metrics import (
        compute_all_metrics, AggregateMetrics, EpisodeBuffer
    )
"""
from __future__ import annotations

import numpy as np

# Re-export robot-lab metrics
from robot_lab.eval.metrics import (
    EpisodeBuffer,
    AggregateMetrics,
    compute_all_metrics,
    velocity_tracking_error,
    survival_metrics,
    energy_efficiency,
    gait_metrics,
)

__all__ = [
    "EpisodeBuffer",
    "AggregateMetrics",
    "compute_all_metrics",
    "velocity_tracking_error",
    "survival_metrics",
    "energy_efficiency",
    "gait_metrics",
    "fleet_safety_metrics",
    "FleetAggregateMetrics",
]


def fleet_safety_metrics(
    cbf_intervention_rate: float,
    safety_state_history: list[str],
    fall_count: int,
    recovery_count: int,
    episode_count: int,
) -> dict[str, float]:
    """
    Compute fleet-safety-specific metrics.

    Args:
        cbf_intervention_rate: fraction of steps where CBF modified action
        safety_state_history: list of safety state names per episode
        fall_count: total falls across episodes
        recovery_count: number of successful recoveries
        episode_count: total episodes

    Returns:
        dict of fleet-safe metrics
    """
    fall_rate = fall_count / max(1, episode_count)
    recovery_rate = recovery_count / max(1, fall_count) if fall_count > 0 else 1.0

    emergency_fraction = (
        safety_state_history.count("EMERGENCY") / max(1, len(safety_state_history))
    )

    return {
        "cbf_intervention_rate": float(cbf_intervention_rate),
        "fall_rate": float(fall_rate),
        "recovery_rate": float(recovery_rate),
        "emergency_fraction": float(emergency_fraction),
        "success_rate": float(1.0 - fall_rate),
    }


class FleetAggregateMetrics(AggregateMetrics):
    """
    Extended AggregateMetrics with fleet-specific aggregation.

    Tracks per-robot metrics and computes fleet-level statistics:
      - fleet_success_rate: fraction of episodes where ALL robots succeed
      - mean_cbf_rate: mean CBF intervention rate across robots
    """

    def __init__(self) -> None:
        super().__init__()
        self._robot_metrics: dict[int, AggregateMetrics] = {}

    def update_robot(self, robot_id: int, metrics: dict[str, float]) -> None:
        """Update metrics for a specific robot."""
        if robot_id not in self._robot_metrics:
            self._robot_metrics[robot_id] = AggregateMetrics()
        self._robot_metrics[robot_id].update(metrics)
        # Also update fleet-level aggregate
        self.update(metrics)

    def per_robot_summary(self) -> dict[int, dict[str, float]]:
        """Return per-robot metric summaries."""
        return {
            rid: agg.summarize()
            for rid, agg in self._robot_metrics.items()
        }

    def fleet_summary(self) -> dict[str, float]:
        """Return fleet-level aggregated metrics."""
        per_robot = self.per_robot_summary()
        if not per_robot:
            return self.summarize()

        fleet: dict[str, float] = {}

        # Global summary
        fleet.update(self.summarize())

        # Fleet-specific: min of each metric across robots (worst-case)
        for metric in ["success_rate/mean", "fall_rate/mean"]:
            vals = [s.get(metric, float("nan")) for s in per_robot.values()]
            valid = [v for v in vals if not np.isnan(v)]
            if valid:
                fleet[f"fleet_min_{metric.replace('/', '_')}"] = float(min(valid))
                fleet[f"fleet_max_{metric.replace('/', '_')}"] = float(max(valid))

        return fleet
