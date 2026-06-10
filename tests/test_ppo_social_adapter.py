"""
test_ppo_social_adapter.py — Verify PPO social adapter reward shaping and policy interface.
"""
from __future__ import annotations

import pytest

from fleet_safe_vla.rl.ppo_social_adapter import (
    PPOSocialConfig,
    SocialAdaptationPolicy,
    ZoneAwareRewardShaper,
    ZoneComplianceReward,
    ZoneContext,
)
from fleet_safe_vla.social_awareness.safety_zones import SafetyZone


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_output(zone: SafetyZone, speed_cap: float = 0.3, margin: float = 0.5,
                 crowding: float = 0.0, occlusion: float = 0.0, min_human: float = float("inf")):
    """Build a minimal SocialRiskOutput-like object."""
    from fleet_safe_vla.social_awareness.social_risk_filter import SocialRiskOutput, SocialRiskState
    from fleet_safe_vla.social_awareness.safety_zones import ZoneClassification

    zone_result = ZoneClassification(
        zone=zone,
        reasons=["test"],
        crowding_score=crowding,
        occlusion_risk=occlusion,
        min_human_dist_m=min_human,
        min_agent_dist_m=min_human,
        agents_in_radius=0,
        recommended_speed_ms=speed_cap,
        recommended_margin_m=margin,
    )
    state = SocialRiskState(
        timestamp=0.0,
        robot_xy=(0.0, 0.0),
        robot_speed_ms=0.2,
        crowding_score=crowding,
        occlusion_risk=occlusion,
        min_human_dist_m=min_human,
        agents=[],
        zone_result=zone_result,
        rare_events=[],
    )
    return SocialRiskOutput(
        veto=(zone == SafetyZone.RED),
        speed_cap_ms=speed_cap,
        margin_m=margin,
        zone=zone,
        reasons=["test"],
        rare_events=[],
        state=state,
    )


def _make_context(zone_name: str = "corridor", safety_zone: SafetyZone = SafetyZone.GREEN):
    return ZoneContext(
        zone_name=zone_name,
        safety_zone=safety_zone,
        speed_cap_ms=0.4,
        margin_m=0.5,
        crowding_score=0.0,
        occlusion_risk=0.0,
    )


# ── PPOSocialConfig ───────────────────────────────────────────────────────────

def test_config_defaults_are_sane():
    cfg = PPOSocialConfig()
    assert cfg.w_zone_compliance > 0
    assert cfg.w_social_margin > 0
    assert cfg.w_intervention_penalty < 0
    assert cfg.w_estop_penalty < 0


def test_config_zone_speed_scale_keys():
    cfg = PPOSocialConfig()
    for key in ("icu", "emergency_corridor", "waiting_room", "default"):
        assert key in cfg.zone_speed_scale


def test_icu_speed_scale_below_one():
    cfg = PPOSocialConfig()
    assert cfg.zone_speed_scale["icu"] < 1.0


# ── ZoneAwareRewardShaper ─────────────────────────────────────────────────────

def test_green_zone_gives_positive_compliance():
    shaper = ZoneAwareRewardShaper()
    output = _make_output(SafetyZone.GREEN)
    r = shaper.compute(output, goal_dist_before=5.0, goal_dist_after=4.5, max_goal_dist=5.0)
    assert r.zone_compliance > 0


def test_amber_zone_gives_zero_compliance():
    shaper = ZoneAwareRewardShaper()
    output = _make_output(SafetyZone.AMBER)
    r = shaper.compute(output, goal_dist_before=5.0, goal_dist_after=4.5, max_goal_dist=5.0)
    assert r.zone_compliance == 0.0


def test_red_zone_gives_negative_compliance():
    shaper = ZoneAwareRewardShaper()
    output = _make_output(SafetyZone.RED)
    r = shaper.compute(output, goal_dist_before=5.0, goal_dist_after=4.5, max_goal_dist=5.0)
    assert r.zone_compliance < 0


def test_goal_progress_positive_reward():
    shaper = ZoneAwareRewardShaper()
    output = _make_output(SafetyZone.GREEN)
    r = shaper.compute(output, goal_dist_before=5.0, goal_dist_after=4.0, max_goal_dist=5.0)
    assert r.goal_proximity > 0


def test_no_goal_progress_zero_goal_reward():
    shaper = ZoneAwareRewardShaper()
    output = _make_output(SafetyZone.GREEN)
    r = shaper.compute(output, goal_dist_before=5.0, goal_dist_after=5.0, max_goal_dist=5.0)
    assert r.goal_proximity == 0.0


def test_intervention_penalty_applied():
    shaper = ZoneAwareRewardShaper()
    output = _make_output(SafetyZone.AMBER)
    r = shaper.compute(output, goal_dist_before=5.0, goal_dist_after=4.5, max_goal_dist=5.0,
                       fleetsafe_intervened=True)
    assert r.intervention_penalty < 0


def test_estop_penalty_more_severe_than_intervention():
    shaper = ZoneAwareRewardShaper()
    output = _make_output(SafetyZone.RED)
    r_interv = shaper.compute(output, goal_dist_before=5.0, goal_dist_after=4.5,
                               max_goal_dist=5.0, fleetsafe_intervened=True)
    r_estop  = shaper.compute(output, goal_dist_before=5.0, goal_dist_after=4.5,
                               max_goal_dist=5.0, estop_triggered=True)
    assert r_estop.estop_penalty < r_interv.intervention_penalty


def test_no_penalty_when_no_event():
    shaper = ZoneAwareRewardShaper()
    output = _make_output(SafetyZone.GREEN)
    r = shaper.compute(output, goal_dist_before=5.0, goal_dist_after=4.5, max_goal_dist=5.0)
    assert r.intervention_penalty == 0.0
    assert r.estop_penalty == 0.0


def test_total_is_sum_of_components():
    shaper = ZoneAwareRewardShaper()
    output = _make_output(SafetyZone.GREEN)
    r = shaper.compute(output, goal_dist_before=5.0, goal_dist_after=4.5, max_goal_dist=5.0,
                       fleetsafe_intervened=True)
    assert abs(r.total - (r.zone_compliance + r.social_margin + r.goal_proximity
                           + r.intervention_penalty + r.estop_penalty)) < 1e-9


# ── SocialAdaptationPolicy ────────────────────────────────────────────────────

def test_adapt_red_zone_returns_zero_action():
    policy = SocialAdaptationPolicy()
    ctx = _make_context("icu", SafetyZone.RED)
    vx, wz = policy.adapt(ctx, nominal_vx=0.3, nominal_wz=0.1)
    assert vx == 0.0
    assert wz == 0.0


def test_adapt_green_scales_by_zone():
    cfg = PPOSocialConfig()
    policy = SocialAdaptationPolicy(config=cfg)
    ctx = _make_context("icu", SafetyZone.GREEN)
    vx, _ = policy.adapt(ctx, nominal_vx=0.5, nominal_wz=0.0)
    expected = 0.5 * cfg.zone_speed_scale["icu"]
    assert abs(vx - min(expected, ctx.speed_cap_ms)) < 1e-6


def test_adapt_does_not_exceed_speed_cap():
    policy = SocialAdaptationPolicy()
    ctx = ZoneContext("default", SafetyZone.GREEN, speed_cap_ms=0.1, margin_m=0.5,
                      crowding_score=0.0, occlusion_risk=0.0)
    vx, _ = policy.adapt(ctx, nominal_vx=2.0, nominal_wz=0.0)
    assert vx <= 0.1 + 1e-9


def test_adapt_preserves_angular_speed():
    policy = SocialAdaptationPolicy()
    ctx = _make_context("corridor", SafetyZone.GREEN)
    _, wz = policy.adapt(ctx, nominal_vx=0.3, nominal_wz=0.5)
    assert wz == 0.5


def test_adapt_preserves_backward_motion_sign():
    policy = SocialAdaptationPolicy()
    ctx = _make_context("corridor", SafetyZone.GREEN)
    vx, _ = policy.adapt(ctx, nominal_vx=-0.2, nominal_wz=0.0)
    assert vx <= 0.0


def test_observation_vector_length():
    # zone: icu, nurse_station, pharmacy, emergency_corridor, waiting_room = 5
    # safety: GREEN, AMBER, RED = 3
    # scalars: speed_cap, margin, crowding, occlusion = 4
    # total = 12
    policy = SocialAdaptationPolicy()
    ctx = _make_context("icu", SafetyZone.AMBER)
    obs = policy.observation_vector(ctx)
    assert len(obs) == 12


def test_observation_vector_zone_one_hot_icu():
    policy = SocialAdaptationPolicy()
    ctx = _make_context("icu", SafetyZone.GREEN)
    obs = policy.observation_vector(ctx)
    # First element is ICU one-hot
    assert obs[0] == 1.0
    assert obs[1] == 0.0
    assert obs[2] == 0.0


def test_observation_vector_safety_one_hot_amber():
    policy = SocialAdaptationPolicy()
    ctx = _make_context("default", SafetyZone.AMBER)
    obs = policy.observation_vector(ctx)
    # safety one-hot starts at index 5: [GREEN, AMBER, RED]
    assert obs[5] == 0.0   # GREEN
    assert obs[6] == 1.0   # AMBER
    assert obs[7] == 0.0   # RED
