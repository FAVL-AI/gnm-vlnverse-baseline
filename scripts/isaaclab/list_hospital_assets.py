#!/usr/bin/env python3
"""
list_hospital_assets.py — Discover hospital / medical USD assets available to Isaac Sim.

Searches three tiers:

  1. Local filesystem — installed Isaac Sim extension data, user downloads,
     and the repo's own assets/ directory.
  2. Nucleus localhost — tries an omniverse:// connection to localhost and
     lists matching paths if the server answers.
  3. NVIDIA cloud catalog — prints the known Nucleus cloud URLs for hospital
     assets (these require a logged-in Nucleus client; no connection is made).

Usage
-----
  conda activate isaac
  python scripts/isaaclab/list_hospital_assets.py

  # Only local search:
  python scripts/isaaclab/list_hospital_assets.py --local-only

  # JSON output (for HospitalAssetLibrary auto-discovery):
  python scripts/isaaclab/list_hospital_assets.py --json > assets_found.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ── Keywords that identify medical / hospital assets ──────────────────────────

_KEYWORDS = [
    "hospital", "clinic", "medical", "corridor", "ward",
    "bed", "gurney", "stretcher", "wheelchair", "iv_stand", "iv-stand",
    "nurse", "doctor", "patient", "visitor",
    "pharmacy", "cabinet", "shelf", "cart", "trolley",
    "examination", "reception", "waiting_room",
]

# ── Known NVIDIA Nucleus cloud paths (require logged-in Nucleus) ───────────────
# Versioned paths per Isaac Sim 4.2 / 4.5 docs:
#   https://docs.isaacsim.omniverse.nvidia.com/4.2.0/features/environment_setup/assets/usd_assets_environments.html
# Pattern: omniverse://localhost/NVIDIA/Assets/Isaac/<ver>/Isaac/Environments/<name>/
_ISAAC_VERSIONS = ["5.1", "5.0", "4.5.0", "4.2.0", "2023.1.1"]

NUCLEUS_CLOUD_CATALOG: list[dict[str, str]] = [
    # ── Isaac Environments (versioned) ────────────────────────────────────────
    # Isaac Sim 5.x paths (installed via conda: isaacsim 5.1)
    {"category": "environment",
     "name": "isaac_hospital_51",
     "url": "omniverse://localhost/NVIDIA/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd"},
    {"category": "environment",
     "name": "isaac_hospital_50",
     "url": "omniverse://localhost/NVIDIA/Assets/Isaac/5.0/Isaac/Environments/Hospital/hospital.usd"},
    # Isaac Sim 4.x legacy paths
    {"category": "environment",
     "name": "isaac_hospital_45",
     "url": "omniverse://localhost/NVIDIA/Assets/Isaac/4.5.0/Isaac/Environments/Hospital/hospital.usd"},
    {"category": "environment",
     "name": "isaac_hospital_42",
     "url": "omniverse://localhost/NVIDIA/Assets/Isaac/4.2.0/Isaac/Environments/Hospital/hospital.usd"},
    {"category": "environment",
     "name": "isaac_office",
     "url": "omniverse://localhost/NVIDIA/Assets/Isaac/5.1/Isaac/Environments/Office/office.usd"},
    {"category": "environment",
     "name": "isaac_warehouse",
     "url": "omniverse://localhost/NVIDIA/Assets/Isaac/5.1/Isaac/Environments/Simple_Warehouse/warehouse.usd"},
    # ── ArchVis Medical interiors (Isaac Sim Assets pack) ─────────────────────
    {"category": "environment",
     "name": "hospital_room",
     "url": "omniverse://localhost/NVIDIA/Assets/ArchVis/Medical/Rooms/Hospital_Room.usd"},
    {"category": "environment",
     "name": "hospital_corridor",
     "url": "omniverse://localhost/NVIDIA/Assets/ArchVis/Medical/Rooms/Corridor.usd"},
    {"category": "environment",
     "name": "waiting_room",
     "url": "omniverse://localhost/NVIDIA/Assets/ArchVis/Medical/Rooms/Waiting_Room.usd"},
    # ── Props ─────────────────────────────────────────────────────────────────
    {"category": "prop",
     "name": "hospital_bed",
     "url": "omniverse://localhost/NVIDIA/Assets/ArchVis/Medical/Props/Hospital_Bed.usd"},
    {"category": "prop",
     "name": "gurney",
     "url": "omniverse://localhost/NVIDIA/Assets/ArchVis/Medical/Props/Gurney.usd"},
    {"category": "prop",
     "name": "wheelchair",
     "url": "omniverse://localhost/NVIDIA/Assets/ArchVis/Medical/Props/Wheelchair.usd"},
    {"category": "prop",
     "name": "iv_stand",
     "url": "omniverse://localhost/NVIDIA/Assets/ArchVis/Medical/Props/IV_Stand.usd"},
    {"category": "prop",
     "name": "pharmacy_shelf",
     "url": "omniverse://localhost/NVIDIA/Assets/ArchVis/Medical/Props/Pharmacy_Shelf.usd"},
    {"category": "prop",
     "name": "medical_cart",
     "url": "omniverse://localhost/NVIDIA/Assets/ArchVis/Medical/Props/Medical_Cart.usd"},
    # SimReady characters (biped)
    {"category": "character",
     "name": "nurse_f",
     "url": "omniverse://localhost/NVIDIA/Assets/Characters/Biped/F_Medical/nurse_f.usd"},
    {"category": "character",
     "name": "doctor_m",
     "url": "omniverse://localhost/NVIDIA/Assets/Characters/Biped/M_Medical/doctor_m.usd"},
    {"category": "character",
     "name": "patient_m",
     "url": "omniverse://localhost/NVIDIA/Assets/Characters/Biped/M_Casual/patient_m.usd"},
]

# ── Local search roots ─────────────────────────────────────────────────────────

def _local_search_roots() -> list[Path]:
    roots: list[Path] = []

    # Isaac Sim conda env (isaacsim Python package)
    try:
        import isaacsim  # type: ignore[import]
        roots.append(Path(isaacsim.__file__).parent)
    except ImportError:
        pass

    # IsaacLab source tree (if ISAACLAB_PATH env set)
    il_path = os.environ.get("ISAACLAB_PATH")
    if il_path:
        roots.append(Path(il_path))

    # Conda env data dirs
    conda_prefix = os.environ.get("CONDA_PREFIX", "")
    if conda_prefix:
        roots.extend([
            Path(conda_prefix) / "share" / "isaacsim",
            Path(conda_prefix) / "lib" / "python3.11" / "site-packages" / "isaacsim",
        ])

    # Common user download locations
    home = Path.home()
    roots.extend([
        home / "isaacsim",
        home / "isaac-sim",
        home / "nvidia" / "isaacsim",
        home / "Documents" / "Kit",
        Path("/opt/isaacsim"),
        Path("/opt/nvidia/isaacsim"),
    ])

    # Omniverse / Nucleus content cache — populated after dragging an asset into
    # the Isaac Sim viewport for the first time.
    roots.extend([
        home / ".local" / "share" / "ov" / "data",
        home / ".cache" / "ov" / "client",
        home / ".nvidia-omniverse" / "data",
        # Kit cache location used by newer Isaac Sim (6.x) builds
        home / ".local" / "share" / "ov" / "pkg",
    ])

    # Repo-local assets
    repo_root = Path(__file__).resolve().parents[2]
    roots.extend([
        repo_root / "fleet_safe_vla" / "envs" / "isaaclab" / "hospital" / "assets",
        repo_root / "third_party",
    ])

    return [r for r in roots if r.exists()]


@dataclass
class FoundAsset:
    category: str
    name: str
    path: str
    size_kb: float


def _search_local(roots: list[Path], verbose: bool) -> list[FoundAsset]:
    found: list[FoundAsset] = []
    seen: set[str] = set()

    for root in roots:
        if verbose:
            print(f"  Searching {root} …", file=sys.stderr)
        try:
            for usd in root.rglob("*.usd"):
                stem = usd.stem.lower()
                if any(kw in stem for kw in _KEYWORDS):
                    key = str(usd)
                    if key in seen:
                        continue
                    seen.add(key)
                    size_kb = round(usd.stat().st_size / 1024, 1)
                    category = _guess_category(stem)
                    found.append(FoundAsset(
                        category=category,
                        name=usd.stem,
                        path=key,
                        size_kb=size_kb,
                    ))
        except PermissionError:
            pass

    return found


def _guess_category(stem: str) -> str:
    if any(k in stem for k in ("nurse", "doctor", "patient", "visitor", "biped")):
        return "character"
    if any(k in stem for k in ("bed", "gurney", "wheelchair", "iv_stand", "shelf",
                                "cart", "trolley", "prop")):
        return "prop"
    if any(k in stem for k in ("hospital", "corridor", "ward", "clinic",
                                "waiting", "reception", "room")):
        return "environment"
    return "misc"


def _try_nucleus_local(verbose: bool) -> list[dict[str, str]]:
    """Try connecting to Nucleus localhost and listing medical asset paths."""
    try:
        import omni.client  # type: ignore[import]
    except ImportError:
        if verbose:
            print("  omni.client not importable (not inside Isaac Sim runtime)",
                  file=sys.stderr)
        return []

    results: list[dict[str, str]] = []
    base_paths = [
        "omniverse://localhost/NVIDIA/Assets/ArchVis/Medical/",
        "omniverse://localhost/Isaac/Environments/",
        "omniverse://localhost/NVIDIA/Assets/Characters/Biped/",
    ]
    for base in base_paths:
        try:
            result, entries = omni.client.list(base)
            if str(result) != "Result.OK":
                continue
            for e in entries:
                url = base + e.relative_path
                if any(kw in url.lower() for kw in _KEYWORDS):
                    results.append({"url": url, "type": str(e.flags)})
        except Exception as exc:
            if verbose:
                print(f"  Nucleus list({base!r}) failed: {exc}", file=sys.stderr)
    return results


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--local-only", action="store_true",
                   help="Skip Nucleus connection attempt")
    p.add_argument("--json", action="store_true",
                   help="Output JSON instead of human-readable text")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    # ── 1. Local search ───────────────────────────────────────────────────────
    roots = _local_search_roots()
    if args.verbose or not args.json:
        print(f"\n[asset-discovery] Searching {len(roots)} local root(s)…",
              file=sys.stderr)

    local_assets = _search_local(roots, verbose=args.verbose)

    # ── 2. Nucleus localhost ───────────────────────────────────────────────────
    nucleus_found: list[dict[str, str]] = []
    if not args.local_only:
        if args.verbose or not args.json:
            print("[asset-discovery] Trying Nucleus localhost…", file=sys.stderr)
        nucleus_found = _try_nucleus_local(verbose=args.verbose)

    # ── 3. Output ─────────────────────────────────────────────────────────────
    if args.json:
        report = {
            "local_assets": [asdict(a) for a in local_assets],
            "nucleus_localhost": nucleus_found,
            "nucleus_cloud_catalog": NUCLEUS_CLOUD_CATALOG,
        }
        print(json.dumps(report, indent=2))
        return 0

    # Human-readable
    print(f"\n{'='*68}")
    print(f"  LOCAL ASSETS FOUND: {len(local_assets)}")
    print(f"{'='*68}")
    if local_assets:
        for a in sorted(local_assets, key=lambda x: x.category):
            print(f"  [{a.category:12s}] {a.name}  ({a.size_kb} KB)")
            print(f"               {a.path}")
    else:
        print("  (none — no hospital/medical USD files found on local filesystem)")
        print()
        print("  To install NVIDIA hospital assets:")
        print("    1. Launch Omniverse Launcher → Library → Isaac Sim → Assets")
        print("    2. Install: 'Isaac Sim Assets' pack (includes ArchVis/Medical)")
        print("    3. Or connect a Nucleus server and use the paths in the catalog below")

    if nucleus_found:
        print(f"\n{'='*68}")
        print(f"  NUCLEUS LOCALHOST: {len(nucleus_found)}")
        print(f"{'='*68}")
        for item in nucleus_found:
            print(f"  {item['url']}")
    else:
        print(f"\n  NUCLEUS LOCALHOST: not available (omni.client required)")

    print(f"\n{'='*68}")
    print(f"  NUCLEUS CLOUD CATALOG ({len(NUCLEUS_CLOUD_CATALOG)} known paths)")
    print(f"{'='*68}")
    print("  These require a Nucleus server with NVIDIA Assets pack installed:")
    for item in NUCLEUS_CLOUD_CATALOG:
        print(f"  [{item['category']:12s}] {item['name']}")
        print(f"               {item['url']}")

    print(f"\n{'='*68}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
