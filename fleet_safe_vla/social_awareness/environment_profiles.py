"""
environment_profiles.py — per-environment safety parameters for the social-risk layer.

Each profile encodes the operational constraints appropriate for a deployment context.
Hospitals demand wider human margins and lower speeds than warehouses; schools demand
even more conservative crowding thresholds.  The profile drives zone thresholds,
speed limits, and margin expansion inside SocialRiskFilter.

Reviewer note
─────────────
These profiles encode **risk conservatism levels**, not social intelligence.
A hospital profile does not reason about intent — it requires larger margins and
lower speeds when any dynamic agent is nearby, regardless of predicted behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EnvironmentProfile:
    """Safety parameter set for one deployment environment."""

    name: str

    # ── Spatial margins ───────────────────────────────────────────────────────
    default_safety_margin_m: float   # base CBF safety radius
    human_margin_m: float            # extra margin around humans
    robot_margin_m: float            # extra margin around other robots

    # ── Speed limits by zone ──────────────────────────────────────────────────
    max_speed_nominal_ms: float      # GREEN zone max speed
    max_speed_amber_ms: float        # AMBER zone max speed (slow-down)
    stop_distance_red_m: float       # RED zone trigger: stop if agent < this dist

    # ── Occlusion caution ─────────────────────────────────────────────────────
    occlusion_caution_distance_m: float   # slow to amber if occlusion zone within this

    # ── Crowding thresholds ───────────────────────────────────────────────────
    crowding_radius_m: float         # count agents within this radius
    amber_crowding_agents: int       # ≥ this many agents in radius → AMBER
    red_crowding_agents: int         # ≥ this many agents in radius → RED

    # ── Zone transition thresholds ────────────────────────────────────────────
    human_amber_dist_m: float        # human closer than this → AMBER
    human_red_dist_m: float          # human closer than this → RED

    # ── Yield rules (informational, logged in intervention reason) ────────────
    yield_to: tuple[str, ...] = field(default=("human",))


# ── Predefined profiles ───────────────────────────────────────────────────────

HOSPITAL_PROFILE = EnvironmentProfile(
    name="hospital",
    default_safety_margin_m=0.50,
    human_margin_m=0.80,
    robot_margin_m=0.45,
    max_speed_nominal_ms=0.30,
    max_speed_amber_ms=0.10,
    stop_distance_red_m=0.60,
    occlusion_caution_distance_m=1.50,
    crowding_radius_m=2.50,
    amber_crowding_agents=2,
    red_crowding_agents=4,
    human_amber_dist_m=1.20,
    human_red_dist_m=0.60,
    yield_to=("human", "wheelchair", "bed"),
)

WAREHOUSE_PROFILE = EnvironmentProfile(
    name="warehouse",
    default_safety_margin_m=0.40,
    human_margin_m=0.60,
    robot_margin_m=0.35,
    max_speed_nominal_ms=0.50,
    max_speed_amber_ms=0.25,
    stop_distance_red_m=0.40,
    occlusion_caution_distance_m=1.00,
    crowding_radius_m=2.00,
    amber_crowding_agents=3,
    red_crowding_agents=6,
    human_amber_dist_m=0.90,
    human_red_dist_m=0.40,
    yield_to=("human", "forklift"),
)

SCHOOL_PROFILE = EnvironmentProfile(
    name="school",
    default_safety_margin_m=0.55,
    human_margin_m=1.00,
    robot_margin_m=0.45,
    max_speed_nominal_ms=0.25,
    max_speed_amber_ms=0.10,
    stop_distance_red_m=0.70,
    occlusion_caution_distance_m=1.80,
    crowding_radius_m=3.00,
    amber_crowding_agents=3,
    red_crowding_agents=5,
    human_amber_dist_m=1.50,
    human_red_dist_m=0.70,
    yield_to=("human", "child"),
)

OFFICE_PROFILE = EnvironmentProfile(
    name="office",
    default_safety_margin_m=0.40,
    human_margin_m=0.65,
    robot_margin_m=0.35,
    max_speed_nominal_ms=0.35,
    max_speed_amber_ms=0.20,
    stop_distance_red_m=0.45,
    occlusion_caution_distance_m=1.20,
    crowding_radius_m=2.00,
    amber_crowding_agents=3,
    red_crowding_agents=6,
    human_amber_dist_m=1.00,
    human_red_dist_m=0.45,
    yield_to=("human",),
)

SHOPPING_MALL_PROFILE = EnvironmentProfile(
    name="shopping_mall",
    default_safety_margin_m=0.45,
    human_margin_m=0.75,
    robot_margin_m=0.40,
    max_speed_nominal_ms=0.30,
    max_speed_amber_ms=0.15,
    stop_distance_red_m=0.50,
    occlusion_caution_distance_m=1.30,
    crowding_radius_m=3.00,
    amber_crowding_agents=4,
    red_crowding_agents=7,
    human_amber_dist_m=1.10,
    human_red_dist_m=0.50,
    yield_to=("human", "pram", "wheelchair"),
)

DEFAULT_PROFILE = EnvironmentProfile(
    name="default",
    default_safety_margin_m=0.35,
    human_margin_m=0.60,
    robot_margin_m=0.35,
    max_speed_nominal_ms=0.50,
    max_speed_amber_ms=0.25,
    stop_distance_red_m=0.35,
    occlusion_caution_distance_m=1.00,
    crowding_radius_m=2.00,
    amber_crowding_agents=3,
    red_crowding_agents=6,
    human_amber_dist_m=0.90,
    human_red_dist_m=0.40,
    yield_to=("human",),
)

ICU_PROFILE = EnvironmentProfile(
    name="icu",
    default_safety_margin_m=0.70,
    human_margin_m=1.20,
    robot_margin_m=0.60,
    max_speed_nominal_ms=0.15,
    max_speed_amber_ms=0.05,
    stop_distance_red_m=0.80,
    occlusion_caution_distance_m=2.00,
    crowding_radius_m=3.00,
    amber_crowding_agents=1,
    red_crowding_agents=2,
    human_amber_dist_m=1.50,
    human_red_dist_m=0.80,
    yield_to=("human", "wheelchair", "bed", "gurney", "nurse", "doctor"),
)

EMERGENCY_CORRIDOR_PROFILE = EnvironmentProfile(
    name="emergency_corridor",
    default_safety_margin_m=0.45,
    human_margin_m=0.70,
    robot_margin_m=0.40,
    max_speed_nominal_ms=0.40,
    max_speed_amber_ms=0.15,
    stop_distance_red_m=0.55,
    occlusion_caution_distance_m=1.40,
    crowding_radius_m=2.50,
    amber_crowding_agents=2,
    red_crowding_agents=4,
    human_amber_dist_m=1.10,
    human_red_dist_m=0.55,
    yield_to=("human", "gurney", "wheelchair"),
)

PHARMACY_PROFILE = EnvironmentProfile(
    name="pharmacy",
    default_safety_margin_m=0.50,
    human_margin_m=0.80,
    robot_margin_m=0.45,
    max_speed_nominal_ms=0.20,
    max_speed_amber_ms=0.08,
    stop_distance_red_m=0.60,
    occlusion_caution_distance_m=1.50,
    crowding_radius_m=2.00,
    amber_crowding_agents=2,
    red_crowding_agents=3,
    human_amber_dist_m=1.20,
    human_red_dist_m=0.60,
    yield_to=("human", "staff"),
)

WAITING_ROOM_PROFILE = EnvironmentProfile(
    name="waiting_room",
    default_safety_margin_m=0.55,
    human_margin_m=0.90,
    robot_margin_m=0.45,
    max_speed_nominal_ms=0.25,
    max_speed_amber_ms=0.10,
    stop_distance_red_m=0.65,
    occlusion_caution_distance_m=1.60,
    crowding_radius_m=3.00,
    amber_crowding_agents=3,
    red_crowding_agents=5,
    human_amber_dist_m=1.30,
    human_red_dist_m=0.65,
    yield_to=("human", "wheelchair", "child"),
)

ALL_PROFILES: dict[str, EnvironmentProfile] = {
    "hospital":             HOSPITAL_PROFILE,
    "warehouse":            WAREHOUSE_PROFILE,
    "school":               SCHOOL_PROFILE,
    "office":               OFFICE_PROFILE,
    "shopping_mall":        SHOPPING_MALL_PROFILE,
    "default":              DEFAULT_PROFILE,
    "icu":                  ICU_PROFILE,
    "emergency_corridor":   EMERGENCY_CORRIDOR_PROFILE,
    "pharmacy":             PHARMACY_PROFILE,
    "waiting_room":         WAITING_ROOM_PROFILE,
}


def get_profile(name: str) -> EnvironmentProfile:
    """Return a predefined profile by name (case-insensitive)."""
    key = name.lower().replace("-", "_").replace(" ", "_")
    if key not in ALL_PROFILES:
        raise ValueError(
            f"Unknown environment profile {name!r}. "
            f"Available: {sorted(ALL_PROFILES)}"
        )
    return ALL_PROFILES[key]
