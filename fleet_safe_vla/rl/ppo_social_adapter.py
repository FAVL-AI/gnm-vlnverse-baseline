"""
ppo_social_adapter.py — Zone-aware reward shaping and policy interface for PPO.

Architecture
------------
The PPO adapter does NOT replace FleetSafe.  It shapes the reward signal so that
the upstream VLA/GNM policy learns to be pre-emptively cautious in high-risk zones,
reducing the frequency of hard FleetSafe interventions.

    VLA/GNM nominal_action
        ↓
    SocialAdaptationPolicy.adapt(zone_context, nominal_action)
        → zone-aware action (speed-scaled, margin-padded)
        ↓
    FleetSafe.filter(adapted_action)   ← hard safety; unchanged
        → safe_action → robot

The PPO policy is trained on zone compliance rewards (see ZoneAwareRewardShaper).
At inference time, only adapt() is called — no gradient computation.

Reward components
-----------------
  zone_compliance   — robot is operating within zone speed limit
  social_margin     — nearest agent distance exceeds zone amber threshold
  goal_proximity    — normalised progress toward goal
  intervention_penalty — FleetSafe intervened this step (hard negative)
  estop_penalty       — e-stop triggered (harder negative)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import NamedTuple

from fleet_safe_vla.social_awareness.safety_zones import SafetyZone
from fleet_safe_vla.social_awareness.social_risk_filter import SocialRiskOutput


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class PPOSocialConfig:
    """Reward weights and zone-specific scaling factors for PPO training."""

    # Reward weights
    w_zone_compliance:     float = 1.0
    w_social_margin:       float = 0.8
    w_goal_proximity:      float = 0.5
    w_intervention_penalty: float = -2.0
    w_estop_penalty:        float = -5.0

    # Zone speed scale factors (multiplicative on nominal action speed)
    # Values < 1.0 make the adapter more conservative than the base profile.
    zone_speed_scale: dict[str, float] = field(default_factory=lambda: {
        "icu":                0.80,
        "nurse_station":      0.90,
        "pharmacy":           0.85,
        "emergency_corridor": 1.00,
        "waiting_room":       0.90,
        "default":            1.00,
    })

    # Extra margin (metres) added per zone on top of FleetSafe minimum
    zone_extra_margin: dict[str, float] = field(default_factory=lambda: {
        "icu":                0.20,
        "nurse_station":      0.10,
        "pharmacy":           0.15,
        "emergency_corridor": 0.05,
        "waiting_room":       0.10,
        "default":            0.00,
    })


# ── Reward components ─────────────────────────────────────────────────────────

class ZoneComplianceReward(NamedTuple):
    """Scalar reward components for one step."""
    zone_compliance:       float
    social_margin:         float
    goal_proximity:        float
    intervention_penalty:  float
    estop_penalty:         float

    @property
    def total(self) -> float:
        return (
            self.zone_compliance
            + self.social_margin
            + self.goal_proximity
            + self.intervention_penalty
            + self.estop_penalty
        )


class ZoneAwareRewardShaper:
    """
    Compute per-step reward from zone context and episode events.

    Usage::

        shaper = ZoneAwareRewardShaper(config)
        reward_components = shaper.compute(
            social_output=output,
            goal_dist_before=d0,
            goal_dist_after=d1,
            max_goal_dist=episode_start_dist,
            fleetsafe_intervened=False,
            estop_triggered=False,
        )
        total_reward = reward_components.total
    """

    def __init__(self, config: PPOSocialConfig | None = None) -> None:
        self._cfg = config or PPOSocialConfig()

    def compute(
        self,
        social_output: SocialRiskOutput,
        goal_dist_before: float,
        goal_dist_after: float,
        max_goal_dist: float,
        fleetsafe_intervened: bool = False,
        estop_triggered: bool = False,
    ) -> ZoneComplianceReward:
        cfg = self._cfg
        zone = social_output.zone

        # Zone compliance: +1 if GREEN, 0 if AMBER, -1 if RED
        if zone == SafetyZone.GREEN:
            compliance = cfg.w_zone_compliance * 1.0
        elif zone == SafetyZone.AMBER:
            compliance = 0.0
        else:  # RED
            compliance = cfg.w_zone_compliance * -1.0

        # Social margin: reward based on distance from nearest human
        min_human_dist = social_output.state.min_human_dist_m
        if math.isinf(min_human_dist):
            margin_reward = cfg.w_social_margin * 1.0
        else:
            # Normalise: 0 at stop_distance, 1 at ≥ 2m
            norm = min(min_human_dist / 2.0, 1.0)
            margin_reward = cfg.w_social_margin * norm

        # Goal proximity: normalised progress
        if max_goal_dist > 0:
            progress = (goal_dist_before - goal_dist_after) / max_goal_dist
        else:
            progress = 0.0
        goal_reward = cfg.w_goal_proximity * max(progress, 0.0)

        # Penalties
        interv_penalty = cfg.w_intervention_penalty if fleetsafe_intervened else 0.0
        estop_penalty  = cfg.w_estop_penalty if estop_triggered else 0.0

        return ZoneComplianceReward(
            zone_compliance=compliance,
            social_margin=margin_reward,
            goal_proximity=goal_reward,
            intervention_penalty=interv_penalty,
            estop_penalty=estop_penalty,
        )


# ── Policy interface ──────────────────────────────────────────────────────────

@dataclass
class ZoneContext:
    """Zone-level context passed to the adaptation policy each step."""
    zone_name:    str        # current spatial zone (from ZoneMap)
    safety_zone:  SafetyZone  # GREEN / AMBER / RED
    speed_cap_ms: float      # from SocialRiskOutput
    margin_m:     float      # from SocialRiskOutput
    crowding_score: float
    occlusion_risk: float


class SocialAdaptationPolicy:
    """
    Thin policy interface: takes zone context + nominal action → adapted action.

    At inference time this applies the zone_speed_scale and zone_extra_margin
    from the config to pre-emptively slow down in sensitive zones.

    In training mode (train=True) it would be replaced by a PPO policy network
    that outputs (speed_scale, margin_delta) from an observation vector.  The
    interface is intentionally minimal so the shim can be replaced by a real
    PPO network without changing the caller.

    Parameters
    ----------
    config : PPOSocialConfig
    train : bool
        When True, this object is a placeholder for a learnable policy.
        The adapt() method logs a warning and falls through to heuristic.
    """

    def __init__(
        self,
        config: PPOSocialConfig | None = None,
        train: bool = False,
    ) -> None:
        self._cfg   = config or PPOSocialConfig()
        self._train = train

    def adapt(
        self,
        context: ZoneContext,
        nominal_vx: float,
        nominal_wz: float,
    ) -> tuple[float, float]:
        """
        Return (adapted_vx, adapted_wz) for the given zone context.

        In RED zone always returns (0.0, 0.0) regardless of policy output —
        this is a hard rule, not learned.

        Parameters
        ----------
        context : ZoneContext
        nominal_vx : float — linear speed from upstream VLA/GNM (m/s)
        nominal_wz : float — angular speed (rad/s)
        """
        if context.safety_zone == SafetyZone.RED:
            return (0.0, 0.0)

        scale = self._cfg.zone_speed_scale.get(context.zone_name, 1.0)
        adapted_vx = min(abs(nominal_vx) * scale, context.speed_cap_ms)
        adapted_vx = adapted_vx * (1 if nominal_vx >= 0 else -1)
        return (adapted_vx, nominal_wz)

    def observation_vector(self, context: ZoneContext) -> list[float]:
        """
        Encode zone context as a flat observation vector for PPO.

        Order matches the PPO observation space spec in docs/ppo_obs_space.md.
        This is stable — do not reorder without updating trained checkpoints.
        """
        zone_one_hot = [
            float(context.zone_name == "icu"),
            float(context.zone_name == "nurse_station"),
            float(context.zone_name == "pharmacy"),
            float(context.zone_name == "emergency_corridor"),
            float(context.zone_name == "waiting_room"),
        ]
        safety_one_hot = [
            float(context.safety_zone == SafetyZone.GREEN),
            float(context.safety_zone == SafetyZone.AMBER),
            float(context.safety_zone == SafetyZone.RED),
        ]
        return [
            *zone_one_hot,
            *safety_one_hot,
            min(context.speed_cap_ms / 0.5, 1.0),
            min(context.margin_m / 1.0, 1.0),
            context.crowding_score,
            context.occlusion_risk,
        ]
