"""
semantic_agents.py — Semantic role taxonomy and behaviour priors for hospital agents.

Each agent observed by the robot is assigned a SemanticRole.  The matching
AgentBehaviorPrior encodes expected motion characteristics: typical speed,
turning radius, how predictable the path is, and the social priority the robot
should yield to this agent type.

These priors are informational — they inform logging and zone-specific reasoning
but do not replace hard CBF safety constraints.  FleetSafe always enforces the
geometric safety margin regardless of semantic role.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SemanticRole(str, Enum):
    NURSE           = "nurse"
    DOCTOR          = "doctor"
    PATIENT         = "patient"
    WHEELCHAIR_USER = "wheelchair_user"
    GURNEY          = "gurney"
    CLEANING_CART   = "cleaning_cart"
    DELIVERY_ROBOT  = "delivery_robot"
    VISITOR         = "visitor"
    UNKNOWN         = "unknown"


@dataclass(frozen=True)
class AgentBehaviorPrior:
    """Expected motion characteristics for one semantic role."""
    role:                SemanticRole
    typical_speed_ms:    float   # expected cruising speed
    turning_radius_m:    float   # min turning radius (0 = point turn)
    path_predictability: float   # [0,1]; 1 = straight hallway, 0 = random walk
    priority_level:      int     # yield order: higher number → robot yields sooner
    width_m:             float   # body/cart width used for collision checking
    silent_approach:     bool    # True if the agent may approach without audible warning


BEHAVIOR_PRIORS: dict[SemanticRole, AgentBehaviorPrior] = {
    SemanticRole.NURSE: AgentBehaviorPrior(
        role=SemanticRole.NURSE,
        typical_speed_ms=1.2,
        turning_radius_m=0.4,
        path_predictability=0.7,
        priority_level=4,
        width_m=0.5,
        silent_approach=False,
    ),
    SemanticRole.DOCTOR: AgentBehaviorPrior(
        role=SemanticRole.DOCTOR,
        typical_speed_ms=1.4,
        turning_radius_m=0.4,
        path_predictability=0.6,
        priority_level=5,
        width_m=0.5,
        silent_approach=False,
    ),
    SemanticRole.PATIENT: AgentBehaviorPrior(
        role=SemanticRole.PATIENT,
        typical_speed_ms=0.4,
        turning_radius_m=0.2,
        path_predictability=0.5,
        priority_level=6,
        width_m=0.5,
        silent_approach=False,
    ),
    SemanticRole.WHEELCHAIR_USER: AgentBehaviorPrior(
        role=SemanticRole.WHEELCHAIR_USER,
        typical_speed_ms=0.8,
        turning_radius_m=0.6,
        path_predictability=0.6,
        priority_level=6,
        width_m=0.7,
        silent_approach=True,
    ),
    SemanticRole.GURNEY: AgentBehaviorPrior(
        role=SemanticRole.GURNEY,
        typical_speed_ms=0.6,
        turning_radius_m=1.2,
        path_predictability=0.8,
        priority_level=7,
        width_m=0.9,
        silent_approach=False,
    ),
    SemanticRole.CLEANING_CART: AgentBehaviorPrior(
        role=SemanticRole.CLEANING_CART,
        typical_speed_ms=0.3,
        turning_radius_m=0.5,
        path_predictability=0.4,
        priority_level=2,
        width_m=0.6,
        silent_approach=False,
    ),
    SemanticRole.DELIVERY_ROBOT: AgentBehaviorPrior(
        role=SemanticRole.DELIVERY_ROBOT,
        typical_speed_ms=0.5,
        turning_radius_m=0.3,
        path_predictability=0.9,
        priority_level=1,
        width_m=0.4,
        silent_approach=True,
    ),
    SemanticRole.VISITOR: AgentBehaviorPrior(
        role=SemanticRole.VISITOR,
        typical_speed_ms=0.9,
        turning_radius_m=0.3,
        path_predictability=0.4,
        priority_level=3,
        width_m=0.5,
        silent_approach=False,
    ),
    SemanticRole.UNKNOWN: AgentBehaviorPrior(
        role=SemanticRole.UNKNOWN,
        typical_speed_ms=0.8,
        turning_radius_m=0.4,
        path_predictability=0.3,
        priority_level=3,
        width_m=0.5,
        silent_approach=False,
    ),
}


def get_behavior_prior(role: str | SemanticRole) -> AgentBehaviorPrior:
    """Lookup behavior prior by role name or enum value."""
    if isinstance(role, str):
        try:
            role = SemanticRole(role.lower())
        except ValueError:
            role = SemanticRole.UNKNOWN
    return BEHAVIOR_PRIORS[role]
