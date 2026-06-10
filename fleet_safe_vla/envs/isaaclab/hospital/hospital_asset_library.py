"""
hospital_asset_library.py — Catalog of hospital USD assets with procedural fallback.

Resolution order for every asset:
  1. Local filesystem path (repo assets/, user download, Isaac Sim extension data)
  2. Nucleus omniverse:// URL (requires connected Nucleus server)
  3. Procedural primitive (always succeeds inside Isaac Sim runtime)

Usage::

    lib = HospitalAssetLibrary()
    print(lib.has_photoreal_assets())          # True only if ≥1 local/Nucleus asset resolved

    # Spawn a hospital bed at world position (x, y, z)
    prim_path = lib.spawn_prop("hospital_bed", stage, "/World/Hospital/Props", (1.0, 0.5, 0.0))

    # Spawn a nurse character
    prim_path = lib.spawn_character("nurse", stage, "/World/Hospital/Agents/nurse_0", (0, 2, 0))

    # Bulk spawn from scene DynamicAgentSpec list
    paths = lib.spawn_agent_specs(specs, stage, base_prim="/World/Hospital/Agents")
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ── Asset catalog ─────────────────────────────────────────────────────────────

_REPO_ASSETS   = Path(__file__).parent / "assets"
_CONDA_PREFIX  = Path(os.environ.get("CONDA_PREFIX", "/nonexistent"))
_ISAACSIM_EXT  = _CONDA_PREFIX / "share" / "isaacsim"
_HOME          = Path.home()

# Omniverse content cache — written when an asset is loaded through the GUI.
# Isaac Sim 4.x caches under ~/.local/share/ov/data/; older builds use ~/.cache/ov/.
_OV_CACHE      = _HOME / ".local" / "share" / "ov" / "data"
_OV_CACHE_ALT  = _HOME / ".cache" / "ov" / "client"

# Isaac Sim versioned Nucleus path prefix.
# Isaac Sim 5.x uses a different path prefix than 4.x:
#   5.x: omniverse://localhost/NVIDIA/Assets/Isaac/5.0/Isaac/Environments/<name>/
#   4.x: omniverse://localhost/NVIDIA/Assets/Isaac/4.5.0/Isaac/Environments/<name>/
# The get_assets_root_path() API (needs AppLauncher) returns the canonical root
# for the running Isaac instance; we hardcode known versions as fallbacks.
_ISAAC_ENV_BASE = "omniverse://localhost/NVIDIA/Assets/Isaac"
_ISAAC_VERSIONS = ["5.1", "5.0", "4.5.0", "4.2.0", "2023.1.1"]


def _isaac_env_url(rel: str, ver: str | None = None) -> str:
    """Build a versioned Isaac Environments Nucleus URL."""
    v = ver or _ISAAC_VERSIONS[0]
    return f"{_ISAAC_ENV_BASE}/{v}/Isaac/Environments/{rel}"


def get_assets_root_path_safe() -> str | None:
    """
    Return the Isaac asset root path if AppLauncher is running, else None.

    Wraps isaacsim.storage.native.get_assets_root_path() which reads from
    carb settings populated at AppLauncher initialisation.
    """
    try:
        from isaacsim.storage.native import get_assets_root_path
        return get_assets_root_path()
    except Exception:
        return None


def _archvis_url(rel: str) -> str:
    return f"omniverse://localhost/NVIDIA/Assets/ArchVis/Medical/{rel}"


def _character_url(rel: str) -> str:
    return f"omniverse://localhost/NVIDIA/Assets/Characters/Biped/{rel}"


@dataclass
class _AssetEntry:
    """One catalogued USD asset with fallback chain."""
    category: str           # "environment" | "prop" | "character"
    name: str               # logical name key
    local_paths: list[Path] # ordered candidate local paths (first existing wins)
    nucleus_url: str        # omniverse:// URL (fallback when local absent)
    # Resolved at runtime
    _resolved_path: Optional[str] = field(default=None, init=False, repr=False)

    def resolve(self, nucleus_ok: bool = False) -> Optional[str]:
        """Return the first usable path, or None if only procedural is possible."""
        if self._resolved_path is not None:
            return self._resolved_path

        for lp in self.local_paths:
            if lp.exists():
                self._resolved_path = str(lp)
                return self._resolved_path

        if nucleus_ok and self.nucleus_url:
            # Optimistically accept Nucleus URL (caller must handle connection errors)
            self._resolved_path = self.nucleus_url
            return self._resolved_path

        return None

    @property
    def is_available(self) -> bool:
        return self.resolve(nucleus_ok=False) is not None


# Catalog — local_paths are checked in order; Nucleus URL is used only when
# nucleus_ok=True is passed to resolve().
def _ov_cached(*parts: str) -> list[Path]:
    """
    Return candidate local paths for a Nucleus asset that may have been cached
    by the Isaac Sim GUI after first load.  Both known OV cache roots are tried.
    """
    rel = Path(*parts)
    return [_OV_CACHE / rel, _OV_CACHE_ALT / rel]


_CATALOG: list[_AssetEntry] = [
    # ── Environments ──────────────────────────────────────────────────────────
    # isaac_hospital — try Isaac Sim 5.x paths first, then 4.x fallbacks.
    # get_assets_root_path() (needs AppLauncher) returns the canonical root;
    # the hardcoded paths below cover known version layouts.
    _AssetEntry(
        category="environment",
        name="isaac_hospital",
        local_paths=[
            _REPO_ASSETS / "hospital_world.usd",
            # OV cache written when user opens the asset in the Isaac Sim GUI
            *_ov_cached("Isaac", "Environments", "Hospital", "hospital.usd"),
            *_ov_cached("NVIDIA", "Assets", "Isaac", "5.1", "Isaac", "Environments", "Hospital", "hospital.usd"),
            *_ov_cached("NVIDIA", "Assets", "Isaac", "5.0", "Isaac", "Environments", "Hospital", "hospital.usd"),
            _ISAACSIM_EXT / "Isaac" / "Environments" / "Hospital" / "hospital.usd",
            _HOME / "isaac-sim" / "assets" / "Isaac" / "Environments" / "Hospital" / "hospital.usd",
        ],
        # Isaac Sim 5.x Nucleus path (primary)
        nucleus_url=_isaac_env_url("Hospital/hospital.usd", "5.1"),
    ),
    _AssetEntry(
        category="environment",
        name="isaac_hospital_50",
        local_paths=[
            *_ov_cached("NVIDIA", "Assets", "Isaac", "5.0", "Isaac", "Environments", "Hospital", "hospital.usd"),
        ],
        nucleus_url=_isaac_env_url("Hospital/hospital.usd", "5.0"),
    ),
    _AssetEntry(
        category="environment",
        name="isaac_hospital_45",
        local_paths=[
            *_ov_cached("NVIDIA", "Assets", "Isaac", "4.5.0", "Isaac", "Environments", "Hospital", "hospital.usd"),
        ],
        nucleus_url=_isaac_env_url("Hospital/hospital.usd", "4.5.0"),
    ),
    _AssetEntry(
        category="environment",
        name="isaac_office",
        local_paths=[
            *_ov_cached("Isaac", "Environments", "Office", "office.usd"),
            *_ov_cached("NVIDIA", "Assets", "Isaac", "5.1", "Isaac", "Environments", "Office", "office.usd"),
        ],
        nucleus_url=_isaac_env_url("Office/office.usd"),
    ),
    _AssetEntry(
        category="environment",
        name="isaac_warehouse",
        local_paths=[
            *_ov_cached("Isaac", "Environments", "Simple_Warehouse", "warehouse.usd"),
            *_ov_cached("NVIDIA", "Assets", "Isaac", "5.1", "Isaac", "Environments", "Simple_Warehouse", "warehouse.usd"),
        ],
        nucleus_url=_isaac_env_url("Simple_Warehouse/warehouse.usd"),
    ),
    # ArchVis Medical (requires separate Assets pack)
    _AssetEntry(
        category="environment",
        name="hospital_room",
        local_paths=[
            *_ov_cached("ArchVis", "Medical", "Rooms", "Hospital_Room.usd"),
            _ISAACSIM_EXT / "ArchVis" / "Medical" / "Rooms" / "Hospital_Room.usd",
        ],
        nucleus_url=_archvis_url("Rooms/Hospital_Room.usd"),
    ),
    _AssetEntry(
        category="environment",
        name="archvis_corridor",
        local_paths=[
            *_ov_cached("ArchVis", "Medical", "Rooms", "Corridor.usd"),
            _ISAACSIM_EXT / "ArchVis" / "Medical" / "Rooms" / "Corridor.usd",
        ],
        nucleus_url=_archvis_url("Rooms/Corridor.usd"),
    ),
    _AssetEntry(
        category="environment",
        name="waiting_room",
        local_paths=[
            *_ov_cached("ArchVis", "Medical", "Rooms", "Waiting_Room.usd"),
            _ISAACSIM_EXT / "ArchVis" / "Medical" / "Rooms" / "Waiting_Room.usd",
        ],
        nucleus_url=_archvis_url("Rooms/Waiting_Room.usd"),
    ),
    # ── Props ─────────────────────────────────────────────────────────────────
    _AssetEntry(
        category="prop",
        name="hospital_bed",
        local_paths=[
            *_ov_cached("ArchVis", "Medical", "Props", "Hospital_Bed.usd"),
            _ISAACSIM_EXT / "ArchVis" / "Medical" / "Props" / "Hospital_Bed.usd",
        ],
        nucleus_url=_archvis_url("Props/Hospital_Bed.usd"),
    ),
    _AssetEntry(
        category="prop",
        name="gurney",
        local_paths=[
            *_ov_cached("ArchVis", "Medical", "Props", "Gurney.usd"),
            _ISAACSIM_EXT / "ArchVis" / "Medical" / "Props" / "Gurney.usd",
        ],
        nucleus_url=_archvis_url("Props/Gurney.usd"),
    ),
    _AssetEntry(
        category="prop",
        name="wheelchair",
        local_paths=[
            *_ov_cached("ArchVis", "Medical", "Props", "Wheelchair.usd"),
            _ISAACSIM_EXT / "ArchVis" / "Medical" / "Props" / "Wheelchair.usd",
        ],
        nucleus_url=_archvis_url("Props/Wheelchair.usd"),
    ),
    _AssetEntry(
        category="prop",
        name="iv_stand",
        local_paths=[
            *_ov_cached("ArchVis", "Medical", "Props", "IV_Stand.usd"),
            _ISAACSIM_EXT / "ArchVis" / "Medical" / "Props" / "IV_Stand.usd",
        ],
        nucleus_url=_archvis_url("Props/IV_Stand.usd"),
    ),
    _AssetEntry(
        category="prop",
        name="pharmacy_shelf",
        local_paths=[
            *_ov_cached("ArchVis", "Medical", "Props", "Pharmacy_Shelf.usd"),
            _ISAACSIM_EXT / "ArchVis" / "Medical" / "Props" / "Pharmacy_Shelf.usd",
        ],
        nucleus_url=_archvis_url("Props/Pharmacy_Shelf.usd"),
    ),
    _AssetEntry(
        category="prop",
        name="medical_cart",
        local_paths=[
            *_ov_cached("ArchVis", "Medical", "Props", "Medical_Cart.usd"),
            _ISAACSIM_EXT / "ArchVis" / "Medical" / "Props" / "Medical_Cart.usd",
        ],
        nucleus_url=_archvis_url("Props/Medical_Cart.usd"),
    ),
    # ── Characters ────────────────────────────────────────────────────────────
    _AssetEntry(
        category="character",
        name="nurse",
        local_paths=[
            *_ov_cached("Characters", "Biped", "F_Medical", "nurse_f.usd"),
            _ISAACSIM_EXT / "Characters" / "Biped" / "F_Medical" / "nurse_f.usd",
        ],
        nucleus_url=_character_url("F_Medical/nurse_f.usd"),
    ),
    _AssetEntry(
        category="character",
        name="doctor",
        local_paths=[
            *_ov_cached("Characters", "Biped", "M_Medical", "doctor_m.usd"),
            _ISAACSIM_EXT / "Characters" / "Biped" / "M_Medical" / "doctor_m.usd",
        ],
        nucleus_url=_character_url("M_Medical/doctor_m.usd"),
    ),
    _AssetEntry(
        category="character",
        name="patient",
        local_paths=[
            *_ov_cached("Characters", "Biped", "M_Casual", "patient_m.usd"),
            _ISAACSIM_EXT / "Characters" / "Biped" / "M_Casual" / "patient_m.usd",
        ],
        nucleus_url=_character_url("M_Casual/patient_m.usd"),
    ),
    _AssetEntry(
        category="character",
        name="wheelchair_user",
        local_paths=[
            *_ov_cached("Characters", "Biped", "Wheelchair", "wheelchair_user.usd"),
            _ISAACSIM_EXT / "Characters" / "Biped" / "Wheelchair" / "wheelchair_user.usd",
        ],
        nucleus_url=_character_url("Wheelchair/wheelchair_user.usd"),
    ),
    _AssetEntry(
        category="character",
        name="visitor",
        local_paths=[
            *_ov_cached("Characters", "Biped", "F_Casual", "visitor_f.usd"),
            _ISAACSIM_EXT / "Characters" / "Biped" / "F_Casual" / "visitor_f.usd",
        ],
        nucleus_url=_character_url("F_Casual/visitor_f.usd"),
    ),
]

# Fast lookup by name
_BY_NAME: dict[str, _AssetEntry] = {e.name: e for e in _CATALOG}

# Map semantic_role → asset name (for character spawning)
_ROLE_TO_ASSET: dict[str, str] = {
    "nurse":           "nurse",
    "doctor":          "doctor",
    "patient":         "patient",
    "wheelchair_user": "wheelchair_user",
    "visitor":         "visitor",
    "gurney":          "gurney",
    "cleaning_cart":   "medical_cart",
    "delivery_robot":  "",        # no character asset — always procedural
    "unknown":         "visitor",
}

# Role-coloured capsule fallback colours (R, G, B) — mirrors hospital_scene_builder
_ROLE_COLORS_FALLBACK: dict[str, tuple[float, float, float]] = {
    "nurse":           (0.85, 0.85, 0.95),
    "doctor":          (0.20, 0.45, 0.85),
    "patient":         (0.75, 0.90, 0.75),
    "wheelchair_user": (0.65, 0.80, 0.95),
    "gurney":          (0.80, 0.80, 0.80),
    "cleaning_cart":   (0.90, 0.85, 0.55),
    "delivery_robot":  (0.55, 0.55, 0.90),
    "visitor":         (0.90, 0.70, 0.40),
    "unknown":         (0.70, 0.70, 0.70),
}


class HospitalAssetLibrary:
    """
    Catalog of hospital USD assets with three-tier resolution and procedural fallback.

    Parameters
    ----------
    nucleus_ok : bool
        If True, Nucleus omniverse:// URLs are accepted as valid (caller bears
        the responsibility of having a connected Nucleus server).
    verbose : bool
        Print resolution results to stdout.
    """

    def __init__(self, nucleus_ok: bool = False, verbose: bool = False) -> None:
        self._nucleus_ok = nucleus_ok
        self._verbose = verbose
        # Pre-resolve all entries at construction time for determinism
        self._resolved: dict[str, Optional[str]] = {
            e.name: e.resolve(nucleus_ok=nucleus_ok) for e in _CATALOG
        }
        n_resolved = sum(1 for v in self._resolved.values() if v is not None)
        if self._verbose:
            photoreal = self.has_photoreal_assets()
            print(
                f"[HospitalAssetLibrary] Resolved {n_resolved}/{len(_CATALOG)} assets.  "
                f"Photoreal: {photoreal}"
            )

    # ── Public API ────────────────────────────────────────────────────────────

    def has_photoreal_assets(self) -> bool:
        """Return True if at least one non-procedural asset is available."""
        return any(v is not None for v in self._resolved.values())

    def resolved_path(self, name: str) -> Optional[str]:
        """Return resolved USD path for asset *name*, or None if not available."""
        return self._resolved.get(name)

    def available_assets(self) -> list[str]:
        """Names of all assets that resolved to a usable path."""
        return [n for n, v in self._resolved.items() if v is not None]

    def spawn_environment(
        self,
        name: str,
        stage: Any,
        prim_path: str,
    ) -> Optional[str]:
        """
        Spawn environment USD reference at *prim_path*.

        Returns the prim path on success, None if only procedural is possible
        (caller should fall back to build_procedural_scene()).
        """
        usd_path = self._resolved.get(name)
        if usd_path is None:
            if self._verbose:
                print(f"[HospitalAssetLibrary] No asset for {name!r} — use procedural")
            return None
        return self._spawn_usd_reference(stage, prim_path, usd_path,
                                         position=(0.0, 0.0, 0.0))

    def spawn_prop(
        self,
        name: str,
        stage: Any,
        prim_path: str,
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> str:
        """
        Spawn a prop USD reference or capsule fallback.

        Always returns the prim_path (capsule fallback if USD unavailable).
        """
        usd_path = self._resolved.get(name)
        if usd_path:
            return self._spawn_usd_reference(stage, prim_path, usd_path, position) or \
                   self._spawn_capsule_fallback(stage, prim_path, position,
                                                color=(0.80, 0.80, 0.80))
        return self._spawn_capsule_fallback(stage, prim_path, position,
                                            color=(0.80, 0.80, 0.80))

    def spawn_character(
        self,
        semantic_role: str,
        stage: Any,
        prim_path: str,
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> str:
        """
        Spawn character USD reference or role-coloured capsule fallback.

        Always returns a prim_path.
        """
        asset_name = _ROLE_TO_ASSET.get(semantic_role, "visitor")
        usd_path = self._resolved.get(asset_name) if asset_name else None
        color = _ROLE_COLORS_FALLBACK.get(semantic_role, (0.70, 0.70, 0.70))

        if usd_path:
            result = self._spawn_usd_reference(stage, prim_path, usd_path, position)
            if result:
                return result

        return self._spawn_capsule_fallback(stage, prim_path, position, color=color)

    def spawn_agent_specs(
        self,
        specs: list[Any],
        stage: Any,
        base_prim: str = "/World/Hospital/Agents",
    ) -> list[str]:
        """
        Spawn a list of DynamicAgentSpec objects (or dicts) as characters.

        Accepts objects with .semantic_role and .position_at(), or dicts with
        "semantic_role" and "position_xy" keys.

        Returns list of prim paths created.
        """
        created: list[str] = []
        for i, spec in enumerate(specs):
            if hasattr(spec, "semantic_role"):
                role = spec.semantic_role
                xy = spec.position_at(0.0)
            else:
                role = spec.get("semantic_role", "unknown")
                xy = spec.get("position_xy", (0.0, 0.0))

            x, y = xy
            prim_path = f"{base_prim}/{role}_{i:03d}"
            created.append(
                self.spawn_character(role, stage, prim_path, position=(x, y, 0.85))
            )
        return created

    def summary(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary of resolution results."""
        return {
            "has_photoreal": self.has_photoreal_assets(),
            "available": self.available_assets(),
            "missing": [n for n, v in self._resolved.items() if v is None],
            "total_catalog": len(_CATALOG),
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _spawn_usd_reference(
        stage: Any,
        prim_path: str,
        usd_path: str,
        position: tuple[float, float, float],
    ) -> Optional[str]:
        """Spawn a USD reference prim. Returns prim_path on success, None on error."""
        try:
            from pxr import UsdGeom, Gf, Sdf
            xform = UsdGeom.Xform.Define(stage, prim_path)
            prim = xform.GetPrim()
            prim.GetReferences().AddReference(usd_path)
            xformable = UsdGeom.Xformable(prim)
            xformable.ClearXformOpOrder()
            t_op = xformable.AddTranslateOp()
            t_op.Set(Gf.Vec3d(*position))
            return prim_path
        except Exception:
            return None

    @staticmethod
    def _spawn_capsule_fallback(
        stage: Any,
        prim_path: str,
        position: tuple[float, float, float],
        color: tuple[float, float, float] = (0.70, 0.70, 0.70),
        height: float = 1.70,
        radius: float = 0.22,
    ) -> str:
        """Spawn a coloured capsule primitive as procedural fallback."""
        try:
            from pxr import UsdGeom, Gf
            capsule = UsdGeom.Capsule.Define(stage, prim_path)
            capsule.GetHeightAttr().Set(height)
            capsule.GetRadiusAttr().Set(radius)
            capsule.GetAxisAttr().Set("Z")
            capsule.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
            xformable = UsdGeom.Xformable(capsule.GetPrim())
            xformable.ClearXformOpOrder()
            t_op = xformable.AddTranslateOp()
            t_op.Set(Gf.Vec3d(*position))
        except Exception:
            pass
        return prim_path
