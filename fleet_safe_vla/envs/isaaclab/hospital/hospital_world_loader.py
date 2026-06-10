"""
hospital_world_loader.py — Isaac Sim hospital world loader with procedural scene builder.

Three load strategies (tried in order):

  1. load_from_usd(usd_path)
       Loads a pre-authored hospital USD stage (photoreal assets).
       Raises FileNotFoundError when the USD file doesn't exist.
       The HOSPITAL_USD_PATH constant points to the expected location:
         fleet_safe_vla/envs/isaaclab/hospital/assets/hospital_world.usd

  2. load_zones_from_yaml(yaml_path)
       Reads a YAML/JSON sidecar file describing zone polygons and profiles.
       ZoneMap only — no 3-D geometry is spawned.

  3. build_procedural_scene(stage_prim)
       Builds the hospital floor plan from Isaac Lab primitives (cuboids):
       coloured floor panels, walls with doorways, ceiling, lighting.
       When HospitalAssetLibrary resolves photoreal USD references, those are
       used in place of capsule placeholders; otherwise capsules are spawned.
       Always succeeds inside an active AppLauncher.
       Returns (ZoneMap, list[prim_paths]).

Typical usage in IsaacNavBenchmarkEnv::

    loader = HospitalWorldLoader(verbose=True)
    zone_map, prim_paths = loader.build_procedural_scene()
    self._owned_prim_paths.extend(prim_paths)
    social_filter = SocialRiskFilter(profile=HOSPITAL_PROFILE, zone_map=zone_map)

Zone-map-only usage (mock / MuJoCo backends, no Isaac context)::

    zone_map = loader.fallback_synthetic_zones()
    social_filter = SocialRiskFilter(profile=HOSPITAL_PROFILE, zone_map=zone_map)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fleet_safe_vla.social_awareness.zone_map import ZoneMap, ZonePolygon
from fleet_safe_vla.benchmarks.hospital_scenes import _HOSPITAL_ZONES


HOSPITAL_USD_PATH = Path(__file__).parent / "assets" / "hospital_world.usd"

FALLBACK_ZONE_MAP = ZoneMap(
    zones=_HOSPITAL_ZONES,
    default_profile_name="hospital",
)


class HospitalWorldLoader:
    """
    Load hospital world geometry and return a ZoneMap for profile switching.

    Parameters
    ----------
    verbose : bool
        Print which strategy was used to stderr.
    """

    def __init__(self, verbose: bool = False, nucleus_ok: bool = False) -> None:
        self._verbose = verbose
        self._nucleus_ok = nucleus_ok
        # Asset library is resolved lazily to avoid import cost at module load
        self._asset_lib: "HospitalAssetLibrary | None" = None

    def _get_asset_lib(self) -> "HospitalAssetLibrary":
        if self._asset_lib is None:
            from fleet_safe_vla.envs.isaaclab.hospital.hospital_asset_library import (
                HospitalAssetLibrary,
            )
            self._asset_lib = HospitalAssetLibrary(
                nucleus_ok=self._nucleus_ok,
                verbose=self._verbose,
            )
        return self._asset_lib

    # ── Strategy 1: pre-authored USD ─────────────────────────────────────────

    def load_from_usd(self, usd_path: Path | str | None = None) -> ZoneMap:
        """
        Load zone polygons from a pre-authored USD stage.

        Reads /Hospital/Zones/* Xform prims.  Each prim must have:
          custom:zone_name    (string) — zone identifier
          custom:zone_profile (string) — profile key (e.g. "icu")
          and a child Mesh that defines the boundary polygon.

        Raises FileNotFoundError if the USD file does not exist.
        Raises RuntimeError if Isaac Sim runtime is not available.
        """
        path = Path(usd_path or HOSPITAL_USD_PATH)
        if not path.exists():
            raise FileNotFoundError(
                f"Hospital USD not found: {path}\n"
                "  → Author a hospital_world.usd in Isaac Sim and save it there, or\n"
                "  → Call build_procedural_scene() to use the procedural builder instead."
            )

        try:
            from pxr import Usd, UsdGeom
        except ImportError as e:
            raise RuntimeError(
                "pxr (OpenUSD) not importable — is this Python environment inside "
                "Isaac Sim / IsaacLab?\n"
                "  conda activate isaac"
            ) from e

        if self._verbose:
            print(f"[HospitalWorldLoader] Loading USD stage: {path}")

        stage = Usd.Stage.Open(str(path))
        zones = _extract_zones_from_stage(stage)

        if self._verbose:
            print(f"[HospitalWorldLoader] Loaded {len(zones)} zones from USD")

        return ZoneMap(zones=zones, default_profile_name="hospital")

    # ── Strategy 2: YAML / JSON sidecar ──────────────────────────────────────

    def load_zones_from_yaml(self, yaml_path: Path | str) -> ZoneMap:
        """
        Load zone polygons from a YAML sidecar file.

        Expected YAML structure::

            default_profile: hospital
            zones:
              - name: icu
                profile: icu
                vertices: [[-10,2],[-2,2],[-2,8],[-10,8]]
              - name: emergency_corridor
                profile: emergency_corridor
                vertices: [[-10,-1.5],[10,-1.5],[10,2],[-10,2]]

        Supports YAML (if PyYAML installed) and JSON.
        """
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Zone YAML not found: {path}")

        if path.suffix.lower() == ".json":
            with path.open() as fh:
                data: dict[str, Any] = json.load(fh)
        else:
            try:
                import yaml  # type: ignore[import]
                with path.open() as fh:
                    data = yaml.safe_load(fh)
            except ImportError:
                with path.open() as fh:
                    data = json.load(fh)

        default_profile = data.get("default_profile", "hospital")
        zones = [
            ZonePolygon(
                name=z["name"],
                profile_name=z["profile"],
                vertices=[tuple(v) for v in z["vertices"]],  # type: ignore[misc]
            )
            for z in data.get("zones", [])
        ]
        if self._verbose:
            print(f"[HospitalWorldLoader] Loaded {len(zones)} zones from {path}")
        return ZoneMap(zones=zones, default_profile_name=default_profile)

    # ── Strategy 3: procedural builder (always available inside Isaac) ────────

    def build_procedural_scene(
        self,
        base_prim: str = "/World/Hospital",
        spawn_lights: bool = True,
        agent_specs: list[dict] | None = None,
    ) -> tuple[ZoneMap, list[str]]:
        """
        Spawn a hospital scene into the current Isaac Sim stage.

        When photoreal USD assets are available (local or Nucleus), they are
        used for agent characters; otherwise role-coloured capsule prims are
        spawned.  Room geometry (floor panels, walls, ceiling) always uses the
        procedural builder regardless of asset availability.

        Must be called inside an active AppLauncher/SimulationContext.

        Parameters
        ----------
        base_prim : USD prim path prefix.
        spawn_lights : bool
            If True, spawn dome + disk lights for clinical ambience.
        agent_specs : optional list of agent dicts or DynamicAgentSpec objects.
            When provided, characters are spawned (photoreal if available).

        Returns
        -------
        (ZoneMap, list[str]) — zone map and list of created prim paths.
        """
        # If AppLauncher is running, try to extend the asset library with the
        # runtime-discovered asset root (get_assets_root_path needs carb settings).
        from fleet_safe_vla.envs.isaaclab.hospital.hospital_asset_library import (
            get_assets_root_path_safe,
        )
        runtime_root = get_assets_root_path_safe()
        if runtime_root and self._verbose:
            print(f"[HospitalWorldLoader] Runtime asset root: {runtime_root}")

        from fleet_safe_vla.envs.isaaclab.hospital.hospital_scene_builder import (
            spawn_hospital_scene,
            spawn_hospital_lights,
            spawn_semantic_agents,
        )

        asset_lib = self._get_asset_lib()
        has_photoreal = asset_lib.has_photoreal_assets()
        print(f"[HospitalWorldLoader] Using photoreal assets: {has_photoreal}")

        if self._verbose:
            print(f"[HospitalWorldLoader] Building procedural hospital at {base_prim!r}")

        created: list[str] = []

        # 1. Floor panels + walls (always procedural)
        created.extend(spawn_hospital_scene(base_prim=base_prim))

        # 2. Lighting
        if spawn_lights:
            created.extend(spawn_hospital_lights(base_prim=base_prim.rsplit("/", 1)[0]))

        # 3. Agent characters — photoreal USD reference or capsule fallback
        if agent_specs:
            agents_prim = f"{base_prim}/Agents"
            if has_photoreal:
                # Attempt USD-reference spawning via asset library
                try:
                    from pxr import Usd
                    stage = Usd.Stage.Open("/World")  # active stage
                    paths = asset_lib.spawn_agent_specs(agent_specs, stage, agents_prim)
                    created.extend(paths)
                except Exception:
                    # pxr stage access failed — fall back to capsules
                    created.extend(spawn_semantic_agents(agent_specs, base_prim=agents_prim))
            else:
                created.extend(spawn_semantic_agents(agent_specs, base_prim=agents_prim))

        if self._verbose:
            print(f"[HospitalWorldLoader] Spawned {len(created)} prims")

        return FALLBACK_ZONE_MAP, created

    # ── Zone-map-only fallback (always available, no Isaac needed) ────────────

    def fallback_synthetic_zones(self) -> ZoneMap:
        """Return the hardcoded ZoneMap (always available, no Isaac required)."""
        if self._verbose:
            print("[HospitalWorldLoader] Using fallback synthetic zone map.")
        return FALLBACK_ZONE_MAP


# ── USD zone extractor (used by load_from_usd) ────────────────────────────────

def _extract_zones_from_stage(stage: Any) -> list[ZonePolygon]:
    """
    Extract ZonePolygon list from a USD stage.

    Looks for Xform prims under /Hospital/Zones/ with attributes:
      custom:zone_name    (string)
      custom:zone_profile (string)
    and a child Mesh prim whose points define the zone boundary polygon.
    """
    from pxr import UsdGeom, Sdf
    zones: list[ZonePolygon] = []
    zones_prim = stage.GetPrimAtPath("/Hospital/Zones")
    if not zones_prim.IsValid():
        return zones

    for child in zones_prim.GetChildren():
        name_attr    = child.GetAttribute("custom:zone_name")
        profile_attr = child.GetAttribute("custom:zone_profile")
        if not (name_attr.IsValid() and profile_attr.IsValid()):
            continue
        zone_name    = name_attr.Get()
        zone_profile = profile_attr.Get()

        # Find first child Mesh to extract boundary vertices
        vertices: list[tuple[float, float]] = []
        for mesh_prim in child.GetChildren():
            geo = UsdGeom.Mesh(mesh_prim)
            if geo:
                pts = geo.GetPointsAttr().Get()
                if pts:
                    vertices = [(float(p[0]), float(p[1])) for p in pts]
                break

        if vertices:
            zones.append(ZonePolygon(name=zone_name, profile_name=zone_profile,
                                      vertices=vertices))
    return zones
