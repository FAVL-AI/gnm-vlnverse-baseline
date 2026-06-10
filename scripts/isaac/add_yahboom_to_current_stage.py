"""add_yahboom_to_current_stage.py — Reference Yahboom M3 Pro USD in the open Isaac stage.

Only uses assets/robots/yahboom_m3_pro/yahboom_m3pro.usd.
Never substitutes TurtleBot, JetBot, Carter, or any generic robot.

Run inside Isaac Sim Script Editor / Console:
    exec(open('/home/favl/robotics/FleetSafe-VisualNav-Benchmark/scripts/isaac/add_yahboom_to_current_stage.py').read())

Output: runs/yahboom_stage_report.json
Fields: status, yahboom_usd_exists, yahboom_usd_path, yahboom_prim_path,
        stage_has_yahboom, timestamp, message, error
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_USD_PATH = _REPO_ROOT / "assets" / "robots" / "yahboom_m3_pro" / "yahboom_m3pro.usd"
_REPORT_PATH = _REPO_ROOT / "runs" / "yahboom_stage_report.json"
_STAGE_PRIM_PATH = "/World/YahboomM3Pro"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(report: dict) -> None:
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"[OK]  Stage report: {_REPORT_PATH}")


def _base(extra: dict) -> dict:
    return {
        "yahboom_usd_exists": _USD_PATH.exists(),
        "yahboom_usd_path": str(_USD_PATH),
        "yahboom_prim_path": _STAGE_PRIM_PATH,
        "stage_has_yahboom": False,
        "timestamp": _ts(),
        **extra,
    }


def _usd_missing() -> None:
    _write(_base({
        "status": "yahboom_usd_missing",
        "stage_has_yahboom": False,
        "message": (
            f"Yahboom USD not found at {_USD_PATH}. "
            "Convert first: bash scripts/import_yahboom_m3_urdf_to_isaac.sh"
        ),
    }))
    print(f"[BLOCKED] Yahboom USD missing: {_USD_PATH}")


def _outside_isaac() -> None:
    if not _USD_PATH.exists():
        _usd_missing()
        return
    _write(_base({
        "status": "isaac_python_unavailable",
        "stage_has_yahboom": False,
        "message": (
            "Isaac Python (omni.usd) not available. "
            "Run this script inside Isaac Sim Console/Script Editor: "
            f"exec(open('{__file__}').read())"
        ),
    }))
    print("[INFO] Isaac Python not available — run inside Isaac Sim to stage the robot.")
    print(f"  Isaac Console: exec(open('{__file__}').read())")
    print("  Or: File → Add Reference →")
    print(f"    {_USD_PATH}")


def _inside_isaac() -> None:
    if not _USD_PATH.exists():
        _usd_missing()
        return

    import omni.usd  # type: ignore
    from pxr import UsdGeom  # type: ignore

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        _write(_base({
            "status": "no_stage",
            "stage_has_yahboom": False,
            "message": "No Isaac stage loaded. Open a USD stage first.",
        }))
        print("[WARN] No stage loaded in Isaac.")
        return

    existing = stage.GetPrimAtPath(_STAGE_PRIM_PATH)
    if existing and existing.IsValid():
        print(f"[OK]  Yahboom already staged at {_STAGE_PRIM_PATH}")
        _write(_base({
            "status": "already_staged",
            "yahboom_stage_loaded": True,
            "stage_has_yahboom": True,
            "message": f"Yahboom M3 Pro already present at {_STAGE_PRIM_PATH}",
        }))
        return

    try:
        prim = stage.DefinePrim(_STAGE_PRIM_PATH)
        prim.GetReferences().AddReference(str(_USD_PATH))
        xform = UsdGeom.Xformable(prim)
        xform.AddTranslateOp().Set((0.0, 0.0, 0.05))
        print(f"[OK]  Yahboom M3 Pro staged at {_STAGE_PRIM_PATH}")
        print(f"  USD: {_USD_PATH}")
        _write(_base({
            "status": "staged",
            "yahboom_stage_loaded": True,
            "stage_has_yahboom": True,
            "message": f"Referenced {_USD_PATH} at {_STAGE_PRIM_PATH} (translate 0,0,0.05)",
        }))
    except Exception as e:
        _write(_base({
            "status": "stage_error",
            "stage_has_yahboom": False,
            "error": str(e),
            "message": f"Failed to stage Yahboom: {e}",
        }))
        print(f"[FAIL] Could not stage Yahboom: {e}")


def main() -> None:
    print("=" * 50)
    print("  FleetSafe — Add Yahboom to Isaac Stage")
    print("=" * 50)
    print(f"  USD:        {_USD_PATH}")
    print(f"  Stage path: {_STAGE_PRIM_PATH}")
    print(f"  USD exists: {_USD_PATH.exists()}")
    print()
    try:
        import omni.usd  # type: ignore  # noqa: F401
        print("  Isaac Sim Python detected.")
        _inside_isaac()
    except ImportError:
        print("  Isaac Python not detected — outside Isaac Sim.")
        _outside_isaac()


if __name__ == "__main__":
    main()
