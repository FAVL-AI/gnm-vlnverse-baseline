"""
Safe Policy wrapper — composes nominal policy with CBF filter.

Wraps any callable policy with the fleet-safe CBF layer so the combined
object satisfies the safety constraint at inference time.

Usage:
    from fleet_safe_vla.policies.safety.safe_policy import SafePolicy
    from fleet_safe_vla.fleet_safety.cbf_filter import make_cbf_filter

    cbf = make_cbf_filter()
    policy = SafePolicy(nominal_policy, cbf)
    safe_action = policy(obs)
"""
from __future__ import annotations

from typing import Callable

import numpy as np

from fleet_safe_vla.fleet_safety.cbf_filter import CBFSafetyFilter, make_cbf_filter


class SafePolicy:
    """
    Wraps a nominal policy with a CBF safety filter.

    The SafePolicy is callable: safe_action = safe_policy(obs)

    Args:
        nominal_policy: callable(obs) -> action
        cbf_filter:     CBFSafetyFilter instance. If None, creates a default one.
        log_interventions: if True, log intervention events
    """

    def __init__(
        self,
        nominal_policy: Callable[[np.ndarray], np.ndarray],
        cbf_filter: CBFSafetyFilter | None = None,
        log_interventions: bool = False,
    ) -> None:
        self._policy = nominal_policy
        self._cbf = cbf_filter or make_cbf_filter()
        self._log = log_interventions
        self._call_count = 0
        self._intervention_count = 0

    def __call__(self, obs: np.ndarray) -> np.ndarray:
        """
        Get safe action for observation.

        Args:
            obs: (45,) proprioceptive observation

        Returns:
            (18,) safe joint position targets
        """
        self._call_count += 1
        u_nom = self._policy(obs)
        safe_action, info = self._cbf.filter_action(obs, u_nom)

        if info.get("intervened"):
            self._intervention_count += 1
            if self._log:
                print(
                    f"[SafePolicy] Intervention #{self._intervention_count} "
                    f"at call {self._call_count}, h_min={info.get('h_min', 'nan'):.3f}"
                )

        return safe_action

    @property
    def intervention_rate(self) -> float:
        if self._call_count == 0:
            return 0.0
        return self._intervention_count / self._call_count

    def reset(self) -> None:
        """Reset CBF state (call at episode reset)."""
        self._cbf.reset()

    def get_stats(self) -> dict:
        return {
            "call_count": self._call_count,
            "intervention_count": self._intervention_count,
            "intervention_rate": self.intervention_rate,
            "cbf_stats": self._cbf.get_stats(),
        }
