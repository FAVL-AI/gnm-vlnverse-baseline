"""
test_semantic_agents.py — Verify SemanticRole taxonomy and AgentBehaviorPrior lookup.
"""
from __future__ import annotations

import pytest

from fleet_safe_vla.social_awareness.semantic_agents import (
    AgentBehaviorPrior,
    BEHAVIOR_PRIORS,
    SemanticRole,
    get_behavior_prior,
)


def test_all_roles_have_priors():
    for role in SemanticRole:
        assert role in BEHAVIOR_PRIORS, f"Missing prior for {role}"


def test_nurse_is_faster_than_patient():
    assert (
        BEHAVIOR_PRIORS[SemanticRole.NURSE].typical_speed_ms
        > BEHAVIOR_PRIORS[SemanticRole.PATIENT].typical_speed_ms
    )


def test_gurney_is_widest():
    widths = {r: p.width_m for r, p in BEHAVIOR_PRIORS.items()}
    assert widths[SemanticRole.GURNEY] == max(widths.values())


def test_gurney_has_largest_turning_radius():
    radii = {r: p.turning_radius_m for r, p in BEHAVIOR_PRIORS.items()}
    assert radii[SemanticRole.GURNEY] == max(radii.values())


def test_delivery_robot_highest_predictability():
    scores = {r: p.path_predictability for r, p in BEHAVIOR_PRIORS.items()}
    assert scores[SemanticRole.DELIVERY_ROBOT] == max(scores.values())


def test_patient_and_wheelchair_highest_priority():
    """Patients and wheelchair users have highest priority (robot yields first)."""
    patient_p  = BEHAVIOR_PRIORS[SemanticRole.PATIENT].priority_level
    wc_p       = BEHAVIOR_PRIORS[SemanticRole.WHEELCHAIR_USER].priority_level
    gurney_p   = BEHAVIOR_PRIORS[SemanticRole.GURNEY].priority_level
    assert patient_p >= 6
    assert wc_p >= 6
    assert gurney_p >= 6


def test_wheelchair_is_silent_approach():
    assert BEHAVIOR_PRIORS[SemanticRole.WHEELCHAIR_USER].silent_approach is True


def test_delivery_robot_is_silent_approach():
    assert BEHAVIOR_PRIORS[SemanticRole.DELIVERY_ROBOT].silent_approach is True


def test_nurse_is_not_silent():
    assert BEHAVIOR_PRIORS[SemanticRole.NURSE].silent_approach is False


def test_get_behavior_prior_by_string():
    prior = get_behavior_prior("nurse")
    assert prior.role == SemanticRole.NURSE


def test_get_behavior_prior_by_enum():
    prior = get_behavior_prior(SemanticRole.DOCTOR)
    assert prior.role == SemanticRole.DOCTOR


def test_get_behavior_prior_unknown_string_returns_unknown():
    prior = get_behavior_prior("nonexistent_role")
    assert prior.role == SemanticRole.UNKNOWN


def test_semantic_role_values_are_strings():
    for role in SemanticRole:
        assert isinstance(role.value, str)


def test_dynamic_agent_carries_semantic_role():
    """DynamicAgent dataclass accepts semantic_role field."""
    from fleet_safe_vla.social_awareness.dynamic_agent_tracker import (
        DynamicAgent,
        AgentType,
    )
    agent = DynamicAgent(
        agent_id="a0",
        agent_type=AgentType.HUMAN,
        position_xy=(1.0, 2.0),
        velocity_xy=(0.0, 0.0),
        speed_ms=0.0,
        timestamp=0.0,
        confidence=1.0,
        semantic_role="nurse",
    )
    assert agent.semantic_role == "nurse"


def test_detection_carries_semantic_role():
    """Detection dataclass accepts semantic_role field."""
    from fleet_safe_vla.social_awareness.dynamic_agent_tracker import (
        Detection,
        AgentType,
    )
    det = Detection(
        position_xy=(0.0, 0.0),
        agent_type=AgentType.HUMAN,
        timestamp=0.0,
        confidence=1.0,
        semantic_role="patient",
    )
    assert det.semantic_role == "patient"


def test_tracker_propagates_semantic_role():
    """Semantic role set in Detection is carried through to tracked DynamicAgent."""
    from fleet_safe_vla.social_awareness.dynamic_agent_tracker import (
        Detection,
        DynamicAgentTracker,
        AgentType,
    )
    tracker = DynamicAgentTracker()
    det = Detection(
        position_xy=(1.0, 0.0),
        agent_type=AgentType.HUMAN,
        timestamp=0.0,
        confidence=1.0,
        semantic_role="nurse",
    )
    agents = tracker.update([det], timestamp=0.0)
    assert len(agents) == 1
    assert agents[0].semantic_role == "nurse"
