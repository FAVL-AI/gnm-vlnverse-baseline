"""import_yahboom_m3_urdf.py — Convert Yahboom M3 Pro URDF to USD via Isaac Sim.

Tries headless Isaac Sim first. If Isaac Python is unavailable writes a
manual_import_required status report and exits cleanly.

Output: assets/robots/yahboom_m3_pro/isaac_import_status.json
        assets/robots/yahboom_m3_pro/yahboom_m3pro.usd  (if successful)
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None

_REPO_ROOT   = Path(__file__).resolve().parents[2]
_URDF_PATH   = _REPO_ROOT / "assets" / "robots" / "yahboom_m3_pro" / "yahboom_m3pro.urdf"
_USD_PATH    = _REPO_ROOT / "assets" / "robots" / "yahboom_m3_pro" / "yahboom_m3pro.usd"
_STATUS_PATH = _REPO_ROOT / "assets" / "robots" / "yahboom_m3_pro" / "isaac_import_status.json"

_URDF_EXTENSIONS = [
    "isaacsim.asset.importer.urdf",
    "omni.importer.urdf",
    "omni.isaac.urdf",
    "omni.isaac.urdf_importer",
]


def _write_status(status: dict) -> None:
    _STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATUS_PATH.write_text(json.dumps(status, indent=2))
    print(f"[OK]  Status: {_STATUS_PATH}")


def _manual_required(reason: str) -> None:
    _write_status({
        "status": "manual_import_required",
        "urdf_exists": _URDF_PATH.exists(),
        "usd_exists": _USD_PATH.exists(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "message": (
            f"URDF importer API not available: {reason}. "
            "Import manually via Isaac UI — see docs/YAHBOOM_URDF_TO_USD_IMPORT.md"
        ),
    })
    print(f"[INFO] Manual import required: {reason}")


def _try_import_inside_isaac() -> bool:
    """Attempt URDF import using available Isaac extension APIs. Returns True on success."""
    import omni.kit.app  # type: ignore

    # Try each known extension name
    ext_manager = omni.kit.app.get_app().get_extension_manager()
    enabled_ext = None
    for ext_name in _URDF_EXTENSIONS:
        try:
            ext_manager.set_extension_enabled_immediate(ext_name, True)
            enabled_ext = ext_name
            print(f"  Enabled extension: {ext_name}")
            break
        except Exception as e:
            print(f"  [SKIP] {ext_name}: {e}")

    if enabled_ext is None:
        _manual_required("none of the URDF importer extensions could be enabled")
        return False

    # Try the modern isaacsim.asset.importer.urdf API first
    imported = False
    if enabled_ext == "isaacsim.asset.importer.urdf":
        # High-level one-shot API: URDFParseAndImportFile(urdf_path, config, dest_path)
        try:
            from isaacsim.asset.importer.urdf import _urdf, URDFParseAndImportFile  # type: ignore
            config = _urdf.ImportConfig()
            config.merge_fixed_joints = False
            config.convex_decomp = False
            config.import_inertia_tensor = True
            config.fix_base = False
            config.make_default_prim = True
            URDFParseAndImportFile(str(_URDF_PATH), config, str(_USD_PATH))
            imported = True
            print("  URDFParseAndImportFile completed.")
        except Exception as e:
            print(f"  [WARN] URDFParseAndImportFile failed: {e}")

        # Low-level fallback: acquire_urdf_interface + import_robot with dest stage
        if not imported or not _USD_PATH.exists():
            try:
                from isaacsim.asset.importer.urdf import _urdf as _urdf2  # type: ignore
                import omni.usd  # type: ignore
                iface = _urdf2.acquire_urdf_interface()
                config2 = _urdf2.ImportConfig()
                config2.merge_fixed_joints = False
                config2.import_inertia_tensor = True
                config2.fix_base = False
                config2.make_default_prim = True
                robot = iface.parse_urdf(str(_URDF_PATH), str(_URDF_PATH.parent) + "/", config2)
                usd_full = str(_USD_PATH)
                omni.usd.get_context().new_stage_with_callback(None)
                stage = omni.usd.get_context().get_stage()
                prim_path = iface.import_robot(
                    str(_USD_PATH.parent) + "/", _USD_PATH.stem, robot, config2
                )
                stage.Export(usd_full)
                imported = bool(prim_path)
                print(f"  Low-level import: prim_path={prim_path!r}")
            except Exception as e2:
                print(f"  [WARN] low-level _urdf import failed: {e2}")

    # Fall back to omni.importer.urdf API
    if not imported:
        try:
            import omni.importer.urdf as urdf_importer  # type: ignore
            config = urdf_importer.ImportConfig()
            config.merge_fixed_joints = False
            config.import_inertia_tensor = True
            config.fix_base = False
            urdf_importer.import_robot(str(_URDF_PATH), str(_USD_PATH), config)
            imported = True
        except Exception as e:
            print(f"  [WARN] omni.importer.urdf import failed: {e}")

    # Fall back to older omni.isaac.urdf API
    if not imported:
        try:
            import omni.isaac.urdf as isaac_urdf  # type: ignore
            config = isaac_urdf._urdf.ImportConfig()
            result, prim_path = isaac_urdf._urdf.import_robot(
                str(_URDF_PATH), str(_USD_PATH), config
            )
            if result:
                imported = True
        except Exception as e:
            print(f"  [WARN] omni.isaac.urdf import failed: {e}")

    if imported and _USD_PATH.exists():
        _write_status({
            "status": "imported",
            "urdf_exists": True,
            "usd_exists": True,
            "usd_path": str(_USD_PATH),
            "extension_used": enabled_ext,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"[OK]  USD written: {_USD_PATH}")
        return True

    _manual_required("import API returned but USD file was not written")
    return False


def main() -> None:
    print("=" * 50)
    print("  FleetSafe — Yahboom URDF → USD (headless Isaac)")
    print("=" * 50)
    print(f"  URDF: {_URDF_PATH}")
    print(f"  USD:  {_USD_PATH}")
    print(f"  URDF exists: {_URDF_PATH.exists()}")
    print(f"  USD exists:  {_USD_PATH.exists()}")
    print("")

    if not _URDF_PATH.exists():
        _write_status({
            "status": "urdf_missing",
            "urdf_exists": False,
            "usd_exists": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "message": f"URDF not found: {_URDF_PATH}",
        })
        print(f"[FAIL] URDF not found: {_URDF_PATH}")
        sys.exit(1)

    if _USD_PATH.exists():
        _write_status({
            "status": "already_exists",
            "urdf_exists": True,
            "usd_exists": True,
            "usd_path": str(_USD_PATH),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"[OK]  USD already exists: {_USD_PATH}")
        return

    # Check for display / GPU before launching SimulationApp
    import os
    import subprocess

    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    has_vulkan = (
        subprocess.run(["vulkaninfo"], capture_output=True, timeout=5).returncode == 0
        if _which("vulkaninfo") else False
    )

    if not has_display:
        _manual_required(
            "No display detected (DISPLAY/WAYLAND_DISPLAY not set). "
            "Headless Isaac Sim requires a GPU with Vulkan support and a valid display. "
            "Use Isaac Sim UI — see docs/YAHBOOM_URDF_TO_USD_IMPORT.md"
        )
        sys.exit(0)

    # Try to start Isaac Sim headless
    try:
        from isaacsim import SimulationApp  # type: ignore
        print("  Starting Isaac Sim headless (display detected)...")
        app = SimulationApp({"headless": True, "anti_aliasing": 0})
        print("  Isaac Sim started.")

        success = _try_import_inside_isaac()

        app.close()
        if not success:
            sys.exit(0)
    except ImportError:
        _manual_required("Isaac Sim Python (isaacsim) not importable from this environment")
        sys.exit(0)
    except Exception as e:
        _manual_required(f"Isaac Sim startup failed: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
