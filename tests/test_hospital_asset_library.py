"""
test_hospital_asset_library.py — HospitalAssetLibrary deterministic fallback tests.

Verifies:
  - Asset library can be constructed without Isaac Sim runtime
  - has_photoreal_assets() is deterministic (same result across calls)
  - available_assets() returns a consistent list
  - resolved_path() returns None for catalog entries without local files
  - summary() contains expected keys
  - Role → asset name mapping covers all semantic roles
  - ROLE_TO_ASSET and ROLE_COLORS_FALLBACK cover same roles
  - CATALOG has expected asset categories
  - Discovery script is importable without Isaac
  - list_hospital_assets NUCLEUS_CLOUD_CATALOG has required fields
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Optional

import pytest

# ── Import (no Isaac Sim required) ────────────────────────────────────────────

from fleet_safe_vla.envs.isaaclab.hospital.hospital_asset_library import (
    HospitalAssetLibrary,
    _CATALOG,
    _BY_NAME,
    _ROLE_TO_ASSET,
    _ROLE_COLORS_FALLBACK,
)


# ── Construction ──────────────────────────────────────────────────────────────

def test_library_constructs_without_isaac():
    lib = HospitalAssetLibrary(nucleus_ok=False, verbose=False)
    assert lib is not None


def test_library_constructs_with_verbose():
    lib = HospitalAssetLibrary(nucleus_ok=False, verbose=True)
    assert lib is not None


def test_library_constructs_twice_independently():
    lib1 = HospitalAssetLibrary(nucleus_ok=False)
    lib2 = HospitalAssetLibrary(nucleus_ok=False)
    # Both must report the same result
    assert lib1.has_photoreal_assets() == lib2.has_photoreal_assets()


# ── Determinism ───────────────────────────────────────────────────────────────

def test_has_photoreal_deterministic():
    """has_photoreal_assets() must return the same bool on repeated calls."""
    lib = HospitalAssetLibrary(nucleus_ok=False)
    result_a = lib.has_photoreal_assets()
    result_b = lib.has_photoreal_assets()
    assert result_a == result_b


def test_available_assets_deterministic():
    """available_assets() must return identical lists on repeated calls."""
    lib = HospitalAssetLibrary(nucleus_ok=False)
    a = lib.available_assets()
    b = lib.available_assets()
    assert a == b


def test_resolved_path_deterministic():
    """resolved_path() for every catalog entry must be the same on repeated calls."""
    lib = HospitalAssetLibrary(nucleus_ok=False)
    for entry in _CATALOG:
        p1 = lib.resolved_path(entry.name)
        p2 = lib.resolved_path(entry.name)
        assert p1 == p2, f"Non-deterministic for {entry.name!r}: {p1!r} vs {p2!r}"


# ── Local-asset state consistency ────────────────────────────────────────────

def test_has_photoreal_consistent_with_available_count():
    """has_photoreal_assets() is True iff available_assets() is non-empty."""
    lib = HospitalAssetLibrary(nucleus_ok=False)
    available = lib.available_assets()
    if available:
        assert lib.has_photoreal_assets() is True, (
            f"Local assets found {available} but has_photoreal_assets() returned False"
        )
    else:
        assert lib.has_photoreal_assets() is False, (
            "No local assets found but has_photoreal_assets() returned True"
        )


def test_resolved_paths_none_for_missing_assets():
    """resolved_path() returns None for catalog entries with no local file."""
    lib = HospitalAssetLibrary(nucleus_ok=False)
    for name in _BY_NAME:
        path = lib.resolved_path(name)
        if path is not None:
            assert Path(path).exists(), (
                f"resolved_path({name!r}) = {path!r} but file does not exist"
            )


def test_available_assets_all_exist_on_disk():
    """Every asset reported available must have a file that exists on disk."""
    lib = HospitalAssetLibrary(nucleus_ok=False)
    for name in lib.available_assets():
        path = lib.resolved_path(name)
        assert path is not None, f"available asset {name!r} has no resolved_path"
        assert Path(path).exists(), f"available asset {name!r} path {path!r} missing"


# ── Summary ───────────────────────────────────────────────────────────────────

def test_summary_has_expected_keys():
    lib = HospitalAssetLibrary(nucleus_ok=False)
    s = lib.summary()
    assert "has_photoreal" in s
    assert "available" in s
    assert "missing" in s
    assert "total_catalog" in s


def test_summary_total_catalog_matches_catalog_length():
    lib = HospitalAssetLibrary(nucleus_ok=False)
    assert lib.summary()["total_catalog"] == len(_CATALOG)


def test_summary_missing_plus_available_equals_total():
    lib = HospitalAssetLibrary(nucleus_ok=False)
    s = lib.summary()
    assert len(s["available"]) + len(s["missing"]) == s["total_catalog"]


def test_summary_has_photoreal_consistent_with_available():
    lib = HospitalAssetLibrary(nucleus_ok=False)
    s = lib.summary()
    assert s["has_photoreal"] == (len(s["available"]) > 0)


# ── Catalog coverage ──────────────────────────────────────────────────────────

def test_catalog_has_environment_entries():
    cats = {e.category for e in _CATALOG}
    assert "environment" in cats


def test_catalog_has_prop_entries():
    cats = {e.category for e in _CATALOG}
    assert "prop" in cats


def test_catalog_has_character_entries():
    cats = {e.category for e in _CATALOG}
    assert "character" in cats


def test_catalog_has_hospital_bed():
    assert "hospital_bed" in _BY_NAME


def test_catalog_has_gurney():
    assert "gurney" in _BY_NAME


def test_catalog_has_wheelchair():
    assert "wheelchair" in _BY_NAME


def test_catalog_has_nurse():
    assert "nurse" in _BY_NAME


def test_catalog_has_patient():
    assert "patient" in _BY_NAME


def test_catalog_has_isaac_hospital_env():
    assert "isaac_hospital" in _BY_NAME


# ── Role → asset mapping ──────────────────────────────────────────────────────

_KNOWN_ROLES = [
    "nurse", "doctor", "patient", "wheelchair_user",
    "visitor", "gurney", "cleaning_cart", "delivery_robot", "unknown",
]


@pytest.mark.parametrize("role", _KNOWN_ROLES)
def test_role_to_asset_covers_role(role: str):
    assert role in _ROLE_TO_ASSET, f"Role {role!r} missing from _ROLE_TO_ASSET"


@pytest.mark.parametrize("role", _KNOWN_ROLES)
def test_role_colors_fallback_covers_role(role: str):
    assert role in _ROLE_COLORS_FALLBACK, (
        f"Role {role!r} missing from _ROLE_COLORS_FALLBACK"
    )


def test_role_colors_are_valid_rgb_tuples():
    for role, color in _ROLE_COLORS_FALLBACK.items():
        assert len(color) == 3, f"Color for {role!r} is not a 3-tuple"
        for c in color:
            assert 0.0 <= c <= 1.0, (
                f"Color component for {role!r} out of [0,1]: {c}"
            )


# ── Asset entries have valid structure ────────────────────────────────────────

def test_all_catalog_entries_have_nucleus_url():
    for e in _CATALOG:
        assert e.nucleus_url.startswith("omniverse://"), (
            f"{e.name!r}: nucleus_url must start with 'omniverse://', "
            f"got {e.nucleus_url!r}"
        )


def test_all_catalog_entries_have_at_least_one_local_path():
    for e in _CATALOG:
        assert len(e.local_paths) >= 1, f"{e.name!r}: local_paths is empty"


def test_catalog_names_unique():
    names = [e.name for e in _CATALOG]
    assert len(names) == len(set(names)), "Duplicate names in _CATALOG"


# ── Discovery script importable ───────────────────────────────────────────────

def test_list_hospital_assets_importable():
    spec = importlib.util.find_spec  # just use importlib.util below
    script = Path(__file__).resolve().parents[1] / "scripts" / "isaaclab" / "list_hospital_assets.py"
    assert script.exists(), "list_hospital_assets.py not found"


def test_nucleus_cloud_catalog_structure():
    from scripts.isaaclab.list_hospital_assets import NUCLEUS_CLOUD_CATALOG
    assert len(NUCLEUS_CLOUD_CATALOG) > 0
    for item in NUCLEUS_CLOUD_CATALOG:
        assert "category" in item
        assert "name" in item
        assert "url" in item
        assert item["url"].startswith("omniverse://")


def test_nucleus_cloud_catalog_has_environment_entries():
    from scripts.isaaclab.list_hospital_assets import NUCLEUS_CLOUD_CATALOG
    cats = {item["category"] for item in NUCLEUS_CLOUD_CATALOG}
    assert "environment" in cats


def test_nucleus_cloud_catalog_has_prop_entries():
    from scripts.isaaclab.list_hospital_assets import NUCLEUS_CLOUD_CATALOG
    cats = {item["category"] for item in NUCLEUS_CLOUD_CATALOG}
    assert "prop" in cats


def test_nucleus_cloud_catalog_has_character_entries():
    from scripts.isaaclab.list_hospital_assets import NUCLEUS_CLOUD_CATALOG
    cats = {item["category"] for item in NUCLEUS_CLOUD_CATALOG}
    assert "character" in cats


# ── HospitalWorldLoader integration ──────────────────────────────────────────

def test_loader_has_get_asset_lib_method():
    from fleet_safe_vla.envs.isaaclab.hospital import HospitalWorldLoader
    loader = HospitalWorldLoader(verbose=False)
    lib = loader._get_asset_lib()
    assert lib is not None
    assert isinstance(lib, HospitalAssetLibrary)


def test_loader_asset_lib_cached():
    """_get_asset_lib() must return the same object on repeated calls."""
    from fleet_safe_vla.envs.isaaclab.hospital import HospitalWorldLoader
    loader = HospitalWorldLoader(verbose=False)
    lib1 = loader._get_asset_lib()
    lib2 = loader._get_asset_lib()
    assert lib1 is lib2


def test_loader_photoreal_flag_consistent_with_lib():
    """Loader's asset lib must agree with standalone library on photoreal status."""
    from fleet_safe_vla.envs.isaaclab.hospital import HospitalWorldLoader
    loader = HospitalWorldLoader(verbose=False)
    lib_direct = HospitalAssetLibrary(nucleus_ok=False)
    lib_via_loader = loader._get_asset_lib()
    assert lib_via_loader.has_photoreal_assets() == lib_direct.has_photoreal_assets()
