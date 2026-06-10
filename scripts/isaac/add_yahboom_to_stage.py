"""add_yahboom_to_stage.py — Reference Yahboom M3 Pro USD asset in the Isaac stage.

Only uses assets/robots/yahboom_m3_pro/yahboom_m3pro.usd.
Never substitutes TurtleBot, JetBot, Carter, or any generic robot.

Output: runs/yahboom_stage_report.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_USD_PATH = _REPO_ROOT / "assets" / "robots" / "yahboom_m3_pro" / "yahboom_m3pro.usd"
_REPORT_PATH = _REPO_ROOT / "runs" / "yahboom_stage_report.json"
_STAGE_PRIM_PATH = "/World/YahboomM3Pro"


def _write(report: dict) -> None:
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"[OK]  Yahboom stage report: {_REPORT_PATH}")


def _usd_missing() -> None:
    report = {
        "status": "yahboom_usd_missing",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "expected_usd": str(_USD_PATH),
        "staged": False,
        "stage_prim_path": None,
        "message": (
            f"Yahboom USD not found at {_USD_PATH}. "
            "Convert from URDF first: "
            "bash scripts/import_yahboom_m3_urdf_to_isaac.sh assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf"
        ),
        "note": "Will NOT substitute TurtleBot/JetBot/Carter.",
    }
    _write(report)
    print(f"[BLOCKED] Yahboom USD missing: {_USD_PATH}")
    print("  Convert: bash scripts/import_yahboom_m3_urdf_to_isaac.sh assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf")


def _outside_isaac() -> None:
    if not _USD_PATH.exists():
        _usd_missing()
        return
    report = {
        "status": "isaac_python_unavailable",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "expected_usd": str(_USD_PATH),
        "usd_file_exists": True,
        "staged": False,
        "stage_prim_path": None,
        "message": (
            "Isaac Python unavailable. Run inside Isaac Sim to stage the robot. "
            "USD file is present and ready."
        ),
    }
    _write(report)
    print("[INFO] Isaac Python unavailable. USD exists — run inside Isaac to stage.")


def _inside_isaac() -> None:
    if not _USD_PATH.exists():
        _usd_missing()
        return

    import omni.usd  # type: ignore
    from pxr import UsdGeom, Sdf  # type: ignore

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        _write({
            "status": "no_stage",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "staged": False,
            "message": "No Isaac stage loaded.",
        })
        return

    existing = stage.GetPrimAtPath(_STAGE_PRIM_PATH)
    if existing and existing.IsValid():
        print(f"[OK]  Yahboom already staged at {_STAGE_PRIM_PATH}")
        _write({
            "status": "already_staged",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "expected_usd": str(_USD_PATH),
            "staged": True,
            "stage_prim_path": _STAGE_PRIM_PATH,
        })
        return

    try:
        prim = stage.DefinePrim(_STAGE_PRIM_PATH)
        prim.GetReferences().AddReference(str(_USD_PATH))
        UsdGeom.Xformable(prim).AddTranslateOp().Set((0, 0, 0))
        print(f"[OK]  Yahboom M3 Pro staged at {_STAGE_PRIM_PATH}")
        _write({
            "status": "staged",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "expected_usd": str(_USD_PATH),
            "staged": True,
            "stage_prim_path": _STAGE_PRIM_PATH,
            "message": f"Referenced {_USD_PATH} at {_STAGE_PRIM_PATH}",
        })
    except Exception as e:
        _write({
            "status": "stage_error",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "staged": False,
            "error": str(e),
        })
        print(f"[FAIL] Could not stage Yahboom: {e}")


def main() -> None:
    print("=" * 40)
    print("  FleetSafe — Add Yahboom to Stage")
    print("=" * 40)
    print(f"  USD: {_USD_PATH}")
    print(f"  Stage path: {_STAGE_PRIM_PATH}")
    print(f"  USD exists: {_USD_PATH.exists()}")
    try:
        import omni.usd  # type: ignore
        print("  Isaac Sim Python detected.")
        _inside_isaac()
    except ImportError:
        print("  Isaac Python not detected.")
        _outside_isaac()


if __name__ == "__main__":
    main()
