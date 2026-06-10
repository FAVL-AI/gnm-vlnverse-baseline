"""
fleet_safe_vla.rl
==================
Reinforcement-learning adaptation layer for zone-aware social navigation.

The PPO social adapter sits between the VLA/GNM policy and FleetSafe:

    VLA/GNM  →  SocialAdaptationPolicy (PPO)  →  FleetSafe  →  Robot

PPO tunes zone-aware speed and margin modifiers.  FleetSafe hard constraints
are never weakened — the adapter can only be *more* conservative, never less.

Public surface
--------------
    PPOSocialConfig         — reward weights and zone scaling factors
    ZoneComplianceReward    — per-step reward component for zone compliance
    ZoneAwareRewardShaper   — combines all reward components into a scalar
    SocialAdaptationPolicy  — thin interface wrapping zone context + nominal action
"""
from fleet_safe_vla.rl.ppo_social_adapter import (
    PPOSocialConfig,
    ZoneComplianceReward,
    ZoneAwareRewardShaper,
    SocialAdaptationPolicy,
)

__all__ = [
    "PPOSocialConfig",
    "ZoneComplianceReward",
    "ZoneAwareRewardShaper",
    "SocialAdaptationPolicy",
]
