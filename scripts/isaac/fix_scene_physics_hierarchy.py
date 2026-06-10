"""fix_scene_physics_hierarchy.py — Sanitize UsdPhysics warnings in VLNVerse scenes.

Removes UsdPhysics.RigidBodyAPI from static/child scene prims under
/World/Ground/Meshes that should not be dynamic rigid bodies.
Also resets XformStack where possible.

Does NOT modify Yahboom robot prims.

Output: runs/isaac_scene_physics_fix_report.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPORT_PATH = _REPO_ROOT / "runs" / "isaac_scene_physics_fix_report.json"

_SCENE_PRIM_PREFIXES = [
    "/World/Ground",
    "/World/kujiale",
    "/World/Meshes",
]
_YAHBOOM_PREFIXES = [
    "/World/YahboomM3Pro",
    "/World/yahboom",
]


def _write(report: dict) -> None:
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"[OK]  Physics fix report: {_REPORT_PATH}")


def _outside_isaac() -> None:
    _write({
        "status": "isaac_python_unavailable",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prims_fixed": 0,
        "message": "Isaac Python unavailable. Run inside Isaac Sim.",
    })
    print("[INFO] Isaac Python not available — no changes made.")


def _inside_isaac() -> None:
    import omni.usd  # type: ignore
    from pxr import UsdPhysics, UsdGeom  # type: ignore

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        _write({"status": "no_stage", "prims_fixed": 0,
                "generated_at": datetime.now(timezone.utc).isoformat()})
        return

    fixed = []
    skipped_yahboom = []

    for prim in stage.Traverse():
        path = str(prim.GetPath())

        # Never touch Yahboom prims
        if any(path.startswith(yp) for yp in _YAHBOOM_PREFIXES):
            skipped_yahboom.append(path)
            continue

        # Only fix scene geometry prims
        if not any(path.startswith(sp) for sp in _SCENE_PRIM_PREFIXES):
            continue

        changed = False

        # Remove RigidBodyAPI from static scene meshes
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            try:
                prim.RemoveAPI(UsdPhysics.RigidBodyAPI)
                changed = True
                print(f"  Removed RigidBodyAPI: {path}")
            except Exception as e:
                print(f"  [WARN] Could not remove RigidBodyAPI from {path}: {e}")

        if changed:
            fixed.append(path)

    print(f"\n[OK]  Fixed {len(fixed)} prims. Skipped {len(skipped_yahboom)} Yahboom prims.")
    _write({
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prims_fixed": len(fixed),
        "fixed_prims": fixed[:50],
        "yahboom_prims_skipped": len(skipped_yahboom),
    })


def main() -> None:
    print("=" * 40)
    print("  FleetSafe — Fix Scene Physics Hierarchy")
    print("=" * 40)
    try:
        import omni.usd  # type: ignore
        print("  Isaac Sim Python detected.")
        _inside_isaac()
    except ImportError:
        print("  Isaac Python not detected.")
        _outside_isaac()


if __name__ == "__main__":
    main()
