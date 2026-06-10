"""
discover_isaac_assets.py — Discover usable Isaac Sim / Nucleus assets
======================================================================
Tries multiple Isaac Sim APIs (version-dependent) to locate built-in
office/prop assets. Saves a manifest to results/custom_vln_office/.

If discovery fails (offline, no Nucleus, wrong API version), prints a
clear warning and records a primitive-fallback plan.

Dry-run mode: probes paths without launching Isaac Sim.

Usage:
  python3 scripts/gnm/discover_isaac_assets.py --dry-run
  conda run -n isaac python scripts/gnm/discover_isaac_assets.py
"""
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "results/custom_vln_office"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MANIFEST_PATH = OUT_DIR / "isaac_asset_manifest.json"

# Keywords to search for
SEARCH_KEYWORDS = [
    "office", "room", "chair", "table", "desk", "cabinet",
    "door", "shelf", "plant", "hallway", "warehouse",
]

# Well-known Isaac Sim Nucleus asset paths (vary by version)
CANDIDATE_ROOTS = [
    "omniverse://localhost/NVIDIA/Assets/Isaac/",
    "omniverse://localhost/NVIDIA/Assets/DigitalTwin/",
    "omniverse://localhost/Library/",
    "${ISAAC_PATH}/Props/",
    "${ISAAC_PATH}/Environments/",
    "/home/favl/.local/share/ov/pkg/isaac-sim-4.5.0/Assets/",
    "/opt/isaac-sim/Assets/",
    "/isaac-sim/Assets/",
]

# Local paths that might contain USD assets without Nucleus
LOCAL_CANDIDATE_DIRS = [
    REPO / "assets",
    Path.home() / ".local/share/ov/pkg",
    Path("/opt/isaac-sim"),
    Path("/isaac-sim"),
]

# Fallback primitives plan (used when no Isaac assets found)
PRIMITIVE_FALLBACK = {
    "floor":          "UsdGeom.Mesh / Cube (grey, scaled)",
    "wall":           "UsdGeom.Cube (white, scaled)",
    "desk":           "UsdGeom.Cube (brown, 1.5×0.8×0.75 m)",
    "chair":          "UsdGeom.Cube (dark grey, 0.5×0.5×0.9 m)",
    "cabinet":        "UsdGeom.Cube (grey, 0.6×1.2×1.8 m)",
    "plant":          "UsdGeom.Sphere (green, r=0.3 m)",
    "shelf":          "UsdGeom.Cube (beige, 0.4×2.0×1.8 m)",
    "meeting_table":  "UsdGeom.Cube (wood-brown, 2.5×1.5×0.75 m)",
    "partition_wall": "UsdGeom.Cube (cream, 0.1×2.0×1.5 m)",
    "light":          "UsdLux.RectLight",
    "camera":         "UsdGeom.Camera",
}


def _probe_local_paths() -> list[dict]:
    """Check for local Isaac Sim installation paths with USD assets."""
    found = []
    for base in LOCAL_CANDIDATE_DIRS:
        if base.exists():
            for keyword in SEARCH_KEYWORDS:
                hits = list(base.rglob(f"*{keyword}*.usd"))[:3]
                for h in hits:
                    found.append({"keyword": keyword, "path": str(h), "source": "local"})
    return found


def _probe_nucleus_api() -> list[dict]:
    """Try Isaac Sim Nucleus connection (requires running Isaac Sim)."""
    found = []
    try:
        import omni.client
        for root in CANDIDATE_ROOTS:
            if "${" in root:
                continue
            try:
                result, entries = omni.client.list(root)
                if str(result) == "Result.OK":
                    for e in (entries or []):
                        name = e.relative_path.lower()
                        for kw in SEARCH_KEYWORDS:
                            if kw in name:
                                full = root + e.relative_path
                                found.append({"keyword": kw, "path": full, "source": "nucleus"})
            except Exception:
                pass
    except ImportError:
        pass
    return found


def _probe_isaac_asset_root() -> list[dict]:
    """Try carb / omni.isaac.core asset root APIs."""
    found = []
    for api_path in [
        "omni.isaac.core.utils.nucleus.get_assets_root_path",
        "omni.isaac.nucleus.get_assets_root_path",
    ]:
        try:
            module_path, func = api_path.rsplit(".", 1)
            import importlib
            mod = importlib.import_module(module_path)
            root = getattr(mod, func)()
            if root:
                for kw in SEARCH_KEYWORDS:
                    path = f"{root}/Props/{kw.capitalize()}"
                    found.append({"keyword": kw, "path": path,
                                  "source": "isaac_core_api", "status": "path_only"})
                break
        except Exception:
            pass
    return found


def run(dry_run: bool = False) -> dict:
    print("=" * 60)
    print("Isaac Sim Asset Discovery — CustomVLN-Office")
    print("=" * 60)
    print(f"Mode: {'dry-run (no Isaac Sim)' if dry_run else 'live (requires Isaac Sim)'}")
    print()

    found = []
    warnings = []

    # 1. Probe local filesystem
    local = _probe_local_paths()
    if local:
        print(f"  Local filesystem: {len(local)} asset(s) found")
        found.extend(local)
    else:
        print("  Local filesystem: no Isaac Sim assets found in standard paths")
        warnings.append("No local Isaac Sim USD assets found")

    # 2. Probe Nucleus (requires Isaac Sim running)
    if not dry_run:
        nucleus = _probe_nucleus_api()
        if nucleus:
            print(f"  Nucleus server: {len(nucleus)} asset(s) found")
            found.extend(nucleus)
        else:
            print("  Nucleus server: unavailable or no matching assets")
            warnings.append("Nucleus server not reachable")

        # 3. Try asset root API
        root_assets = _probe_isaac_asset_root()
        if root_assets:
            print(f"  Isaac Core API: root path resolved ({len(root_assets)} search paths)")
            found.extend(root_assets)
        else:
            print("  Isaac Core API: not available")
            warnings.append("omni.isaac.core not importable (run inside Isaac Sim)")
    else:
        warnings.append("Nucleus probe skipped (dry-run mode)")
        warnings.append("Isaac Core API skipped (dry-run mode)")

    print()

    # 4. Build manifest
    if found:
        print(f"Total assets found: {len(found)}")
        for item in found[:10]:
            print(f"  [{item['keyword']}] {item['path']}")
        if len(found) > 10:
            print(f"  … and {len(found) - 10} more")
        use_primitives = False
    else:
        print("WARNING: No Isaac Sim assets found.")
        print("Scene will be built using USD primitives as fallback.")
        print("This is fully functional — all GNM methodology still applies.")
        use_primitives = True

    print()
    print("Primitive fallback plan:")
    for obj, desc in PRIMITIVE_FALLBACK.items():
        print(f"  {obj:<18} → {desc}")

    manifest = {
        "discovery_mode": "dry_run" if dry_run else "live",
        "assets_found": found,
        "n_assets_found": len(found),
        "use_primitives_fallback": use_primitives,
        "primitive_fallback_plan": PRIMITIVE_FALLBACK,
        "search_keywords": SEARCH_KEYWORDS,
        "candidate_roots_checked": CANDIDATE_ROOTS,
        "warnings": warnings,
        "note": (
            "CustomVLN-Office uses Isaac Sim assets where available, "
            "falling back to USD primitives. No VLNVerse assets are used."
        ),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest saved: {MANIFEST_PATH}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Probe local paths only, no Isaac Sim")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
