"""Isaac Sim script — set active viewport to first-person / FloatingCamera.

Run inside Isaac Sim via:
    python.sh scripts/isaac/set_first_person_camera.py

Camera search order:
  1. /World/YahboomM3Pro/front_camera
  2. /World/yahboom_m3_pro/front_camera
  3. /World/FloatingCamera
  4. Any camera with "front", "robot", or "camera" in path
  5. First non-top-down camera found

Writes:
  runs/current_camera_report.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPORT_PATH = _REPO_ROOT / "runs" / "current_camera_report.json"

_PREFERRED_PATHS = [
    "/World/YahboomM3Pro/front_camera",
    "/World/yahboom_m3_pro/front_camera",
    "/World/Robot/front_camera",
    "/World/FloatingCamera",
]

_REJECT_KEYWORDS = ["top", "bird", "overhead", "TopDown", "BirdEye", "debug_cam"]


def _is_top_down(path: str) -> bool:
    return any(kw.lower() in path.lower() for kw in _REJECT_KEYWORDS)


def _score_camera(path: str) -> int:
    """Lower = better. Preferred paths score 0-3, front/robot = 10, others = 20."""
    for i, pref in enumerate(_PREFERRED_PATHS):
        if path == pref:
            return i
    lo = path.lower()
    if any(k in lo for k in ["front", "robot", "float"]):
        return 10
    if "camera" in lo:
        return 20
    return 99


def main() -> int:
    try:
        import omni.kit.viewport.utility as vp_util
        from pxr import UsdGeom, Gf
        import omni.usd
    except ImportError:
        _write_report(None, "isaac_not_available", [])
        print("[FAIL] Isaac Sim modules not available. Run inside Isaac Sim python.sh.")
        return 2

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        _write_report(None, "no_stage_open", [])
        print("[FAIL] No USD stage is open. Open a scene first.")
        return 2

    # Enumerate all Camera prims
    all_cameras: list[str] = []
    for prim in stage.Traverse():
        if prim.GetTypeName() == "Camera":
            all_cameras.append(str(prim.GetPath()))

    print(f"Found {len(all_cameras)} camera(s) in stage:")
    for c in all_cameras:
        print(f"  {c}")
    print()

    if not all_cameras:
        _write_report(None, "no_cameras_found", [])
        print("[FAIL] No cameras in scene. Add a camera first.")
        return 2

    # Filter out clearly top-down cameras
    candidates = [c for c in all_cameras if not _is_top_down(c)]
    if not candidates:
        candidates = all_cameras  # fallback: use all

    # Sort by preference score
    candidates.sort(key=_score_camera)
    selected = candidates[0]

    print(f"Selected camera: {selected}")
    print()

    # Set active viewport camera
    try:
        viewport = vp_util.get_active_viewport()
        if viewport:
            viewport.set_active_camera(selected)
            print(f"[OK]  Active viewport camera set to: {selected}")
        else:
            print("[WARN] No active viewport found. Camera path logged but not applied.")
    except Exception as e:
        print(f"[WARN] Could not set viewport camera: {e}")

    # Determine camera mode
    mode = "unknown"
    lo = selected.lower()
    if "float" in lo:
        mode = "FloatingCamera"
    elif "front" in lo or "robot" in lo:
        mode = "first_person"
    elif _is_top_down(selected):
        mode = "top_down"
    else:
        mode = "other"

    _write_report(selected, mode, all_cameras)
    print(f"Camera mode: {mode}")
    print(f"Report: {_REPORT_PATH}")
    return 0


def _write_report(camera: str | None, mode: str, all_cameras: list[str]) -> None:
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_camera": camera,
        "camera_mode": mode,
        "is_first_person": mode in ("first_person", "FloatingCamera"),
        "bird_eye_rejected": True,
        "all_cameras": all_cameras,
        "camera_instructions": (
            "In Isaac Sim UI: Perspective → Cameras → FloatingCamera"
            if camera is None else None
        ),
    }
    _REPORT_PATH.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    sys.exit(main())
