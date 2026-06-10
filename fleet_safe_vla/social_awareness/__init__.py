"""
fleet_safe_vla.social_awareness
================================
Social-risk, crowding, occlusion, and rare-event awareness layer.

Public surface
--------------
    SocialRiskFilter    — main integration point (use this first)
    SocialRiskOutput    — per-step decision object
    SocialRiskState     — per-step state snapshot
    SafetyZone          — GREEN / AMBER / RED enum
    ZoneClassification  — zone classifier result dataclass
    SafetyZoneClassifier — classify zone from agent/crowding/occlusion inputs
    EnvironmentProfile  — frozen parameter set for one deployment environment
    get_profile         — look up a profile by name
    ALL_PROFILES        — dict of all predefined profiles
    ZoneMap             — spatial zone partitioning for per-zone profile switching
    ZonePolygon         — one named polygon zone within a ZoneMap
    SemanticRole        — agent semantic role enum (nurse / patient / etc.)
    AgentBehaviorPrior  — motion priors per semantic role
    BEHAVIOR_PRIORS     — dict[SemanticRole, AgentBehaviorPrior]
    get_behavior_prior  — lookup by role name or enum
    DynamicAgentTracker — nearest-neighbor dynamic agent tracker
    DynamicAgent        — tracked agent state dataclass
    Detection           — per-sensor-observation dataclass
    AgentType           — HUMAN / ROBOT / UNKNOWN enum
    CrowdingEstimator   — density-based crowding score
    OcclusionRisk       — geometric shadow-zone occlusion estimator
    OcclusionZone       — per-obstacle shadow-zone dataclass
    RareEventMonitor    — detect and log rare navigation hazards
    RareEvent           — one rare-event occurrence dataclass
    RareEventType       — 7-value rare-event type enum
"""

from fleet_safe_vla.social_awareness.dynamic_agent_tracker import (
    AgentType,
    Detection,
    DynamicAgent,
    DynamicAgentTracker,
)
from fleet_safe_vla.social_awareness.crowding_estimator import CrowdingEstimator
from fleet_safe_vla.social_awareness.environment_profiles import (
    ALL_PROFILES,
    DEFAULT_PROFILE,
    HOSPITAL_PROFILE,
    ICU_PROFILE,
    EMERGENCY_CORRIDOR_PROFILE,
    PHARMACY_PROFILE,
    WAITING_ROOM_PROFILE,
    OFFICE_PROFILE,
    SCHOOL_PROFILE,
    SHOPPING_MALL_PROFILE,
    WAREHOUSE_PROFILE,
    EnvironmentProfile,
    get_profile,
)
from fleet_safe_vla.social_awareness.occlusion_risk import OcclusionRisk, OcclusionZone
from fleet_safe_vla.social_awareness.rare_event_monitor import (
    RareEvent,
    RareEventMonitor,
    RareEventType,
)
from fleet_safe_vla.social_awareness.safety_zones import (
    SafetyZone,
    SafetyZoneClassifier,
    ZoneClassification,
)
from fleet_safe_vla.social_awareness.semantic_agents import (
    AgentBehaviorPrior,
    BEHAVIOR_PRIORS,
    SemanticRole,
    get_behavior_prior,
)
from fleet_safe_vla.social_awareness.social_risk_filter import (
    SocialRiskFilter,
    SocialRiskOutput,
    SocialRiskState,
)
from fleet_safe_vla.social_awareness.zone_map import ZoneMap, ZonePolygon

__all__ = [
    # Filter
    "SocialRiskFilter",
    "SocialRiskOutput",
    "SocialRiskState",
    # Zones
    "SafetyZone",
    "SafetyZoneClassifier",
    "ZoneClassification",
    # Zone map
    "ZoneMap",
    "ZonePolygon",
    # Profiles
    "EnvironmentProfile",
    "get_profile",
    "ALL_PROFILES",
    "DEFAULT_PROFILE",
    "HOSPITAL_PROFILE",
    "ICU_PROFILE",
    "EMERGENCY_CORRIDOR_PROFILE",
    "PHARMACY_PROFILE",
    "WAITING_ROOM_PROFILE",
    "WAREHOUSE_PROFILE",
    "SCHOOL_PROFILE",
    "OFFICE_PROFILE",
    "SHOPPING_MALL_PROFILE",
    # Semantic agents
    "SemanticRole",
    "AgentBehaviorPrior",
    "BEHAVIOR_PRIORS",
    "get_behavior_prior",
    # Tracker
    "DynamicAgentTracker",
    "DynamicAgent",
    "Detection",
    "AgentType",
    # Estimators
    "CrowdingEstimator",
    "OcclusionRisk",
    "OcclusionZone",
    # Rare events
    "RareEventMonitor",
    "RareEvent",
    "RareEventType",
]
