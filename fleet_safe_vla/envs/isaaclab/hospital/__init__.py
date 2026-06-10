"""
fleet_safe_vla.envs.isaaclab.hospital
======================================
Hospital world loader, asset library, and procedural scene builder for Isaac Sim.

Public surface
--------------
    HospitalWorldLoader   — three load strategies: USD / YAML / procedural builder
    HospitalAssetLibrary  — photoreal asset catalog with deterministic fallback
    HOSPITAL_USD_PATH     — expected path to a pre-authored hospital USD (may not exist)
    HOSPITAL_ZONES_YAML   — bundled JSON sidecar with zone polygon definitions
    FALLBACK_ZONE_MAP     — ZoneMap always available without Isaac context
    spawn_hospital_scene  — low-level: spawn coloured floor+wall prims into stage
    spawn_semantic_agents — low-level: spawn role-coloured capsule agents
    spawn_hospital_lights — low-level: spawn clinical dome + disk lights
"""
from fleet_safe_vla.envs.isaaclab.hospital.hospital_world_loader import (
    HospitalWorldLoader,
    HOSPITAL_USD_PATH,
    FALLBACK_ZONE_MAP,
)
from fleet_safe_vla.envs.isaaclab.hospital.hospital_asset_library import (
    HospitalAssetLibrary,
)

from pathlib import Path
# JSON sidecar preferred (no PyYAML dependency); YAML copy also present for human editing
HOSPITAL_ZONES_YAML = Path(__file__).parent / "assets" / "hospital_zones.json"

# Low-level builders (require active Isaac Sim context when called)
from fleet_safe_vla.envs.isaaclab.hospital.hospital_scene_builder import (
    spawn_hospital_scene,
    spawn_semantic_agents,
    spawn_hospital_lights,
)

__all__ = [
    "HospitalWorldLoader",
    "HospitalAssetLibrary",
    "HOSPITAL_USD_PATH",
    "HOSPITAL_ZONES_YAML",
    "FALLBACK_ZONE_MAP",
    "spawn_hospital_scene",
    "spawn_semantic_agents",
    "spawn_hospital_lights",
]
