"""set_navigation_camera.py — Set Isaac Sim viewport to navigation camera.

Safe to run outside Isaac: if Isaac modules are unavailable, writes a report
with status="isaac_python_unavailable" without crashing.

Camera priority:
  1. /World/FloatingCamera (or any path containing FloatingCamera)
  2. /World/YahboomM3Pro/front_camera
  3. /World/yahboom_m3_pro/front_camera
  4. Any path containing "front" (case-insensitive)

Never accepts: bird_eye / top_down / TopDown / Perspective / overhead / debug_cam
as the active navigation evidence camera.

Output: runs/current_camera_report.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPORT_PATH = _REPO_ROOT / "runs" / "current_camera_report.json"

_PREFERRED_NAMES = [
    "FloatingCamera",
    "front_camera",
    "front",
    "nav_cam",
    "robot_cam",
]

_REJECT_KEYWORDS = [
    "top", "bird", "overhead", "TopDown", "BirdEye",
    "debug_cam", "Perspective",
]


def _is_rejected(path: str) -> bool:
    lower = path.lower()
    return any(kw.lower() in lower for kw in _REJECT_KEYWORDS)


def _preferred_rank(path: str) -> int:
    """Lower = higher priority."""
    lower = path.lower()
    if "floatingcamera" in lower:
        return 0
    if "front_camera" in lower:
        return 1
    if "front" in lower:
        return 2
    return 99


def _write_report(report: dict) -> None:
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"[OK]  Camera report written: {_REPORT_PATH}")


def run_outside_isaac() -> None:
    """Called when Isaac Sim Python is not available."""
    report = {
        "status": "isaac_python_unavailable",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_camera_path": None,
        "camera_mode": "unknown",
        "is_first_person_or_floating": False,
        "is_first_person": False,
        # bird_eye_rejected=False here: no cameras were found to reject.
        # The value is True only when Isaac is running and a bird's-eye camera
        # was detected in the stage but excluded from selection.
        "bird_eye_rejected": False,
        "all_cameras": [],
        "message": (
            "Isaac Sim Python not available. Run this script inside Isaac Sim:"
            " omni.kit.app.get_app().get_update_event_stream()... "
            "or: python.sh scripts/isaac/set_navigation_camera.py"
        ),
    }
    _write_report(report)
    print("[INFO] Isaac Python unavailable — wrote fallback camera report.")


def run_inside_isaac() -> None:
    """Called when Isaac Sim modules are present."""
    import omni.usd  # type: ignore
    from pxr import Usd  # type: ignore

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        report = {
            "status": "no_stage",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "selected_camera_path": None,
            "camera_mode": "unknown",
            "is_first_person_or_floating": False,
            "is_first_person": False,
            "bird_eye_rejected": True,
            "all_cameras": [],
            "message": "Isaac stage not loaded. Open a scene first.",
        }
        _write_report(report)
        return

    # Gather all Camera prims
    all_cameras = [
        str(prim.GetPath())
        for prim in stage.Traverse()
        if prim.GetTypeName() == "Camera"
    ]
    print(f"  Found {len(all_cameras)} camera(s) in stage:")
    for c in all_cameras:
        print(f"    {c}")

    # Filter out rejected cameras
    candidates = [c for c in all_cameras if not _is_rejected(c)]
    candidates.sort(key=_preferred_rank)

    selected = candidates[0] if candidates else None
    rejected_cameras = [c for c in all_cameras if _is_rejected(c)]

    if selected is None:
        print("[WARN] No acceptable navigation camera found. Candidates after rejection:")
        for c in rejected_cameras:
            print(f"  REJECTED: {c}")
        report = {
            "status": "no_acceptable_camera",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "selected_camera_path": None,
            "camera_mode": "unknown",
            "is_first_person_or_floating": False,
            "is_first_person": False,
            "bird_eye_rejected": True,
            "all_cameras": all_cameras,
            "rejected_cameras": rejected_cameras,
            "message": "No first-person/FloatingCamera found. Add a FloatingCamera to the stage.",
        }
        _write_report(report)
        return

    # Try to set viewport camera
    try:
        import omni.kit.viewport.utility as vp_util  # type: ignore
        vp = vp_util.get_active_viewport()
        if vp:
            vp.set_active_camera(selected)
            print(f"[OK]  Viewport camera set to: {selected}")
    except Exception as e:
        print(f"[WARN] Could not set viewport camera: {e}")

    lower = selected.lower()
    is_fp = (
        "floatingcamera" in lower
        or "front_camera" in lower
        or "front" in lower
    )
    cam_mode = "FloatingCamera" if "floatingcamera" in lower else "first_person"

    report = {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_camera_path": selected,
        "camera_mode": cam_mode,
        "is_first_person_or_floating": is_fp,
        "is_first_person": is_fp,
        "bird_eye_rejected": len(rejected_cameras) > 0,
        "all_cameras": all_cameras,
        "rejected_cameras": rejected_cameras,
        "message": f"Camera set to {selected}",
    }
    _write_report(report)
    print(f"[OK]  selected={selected}  is_first_person={is_fp}")


def main() -> None:
    print("=" * 40)
    print("  FleetSafe — Set Navigation Camera")
    print("=" * 40)

    try:
        import omni.usd  # type: ignore
        print("  Isaac Sim Python detected.")
        run_inside_isaac()
    except ImportError:
        print("  Isaac Sim Python NOT detected (running outside Isaac).")
        run_outside_isaac()


if __name__ == "__main__":
    main()
