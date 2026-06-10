"""validate_loaded_scene.py — Validate what is loaded in the Isaac Sim stage.

Safe to run outside Isaac (returns a report with status=isaac_python_unavailable).
When run inside Isaac, inspects the stage and writes a detailed validation report.

valid_for_evidence is False when:
- only /World/defaultGroundPlane (no VLN scene geometry)
- VLN scene geometry missing
- Yahboom robot not staged
- Camera is Perspective/top-down, not first-person/FloatingCamera

Output: runs/isaac_scene_validation.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPORT_PATH = _REPO_ROOT / "runs" / "isaac_scene_validation.json"

_GROUND_PLANE_PATHS = {"/World/defaultGroundPlane", "/World/GroundPlane", "/World/Ground"}
_REJECT_CAM_KEYWORDS = ["perspective", "top", "bird", "overhead", "debug"]
_FP_CAM_KEYWORDS = ["floatingcamera", "front_camera", "front", "nav_cam"]


def _write(report: dict) -> None:
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"[OK]  Scene validation report: {_REPORT_PATH}")


def _outside_isaac() -> None:
    report = {
        "status": "isaac_python_unavailable",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prim_count": 0,
        "has_default_ground_plane": False,
        "has_default_ground_plane_only": False,
        "has_imported_vln_scene": False,
        "has_yahboom": False,
        "has_floating_camera": False,
        "selected_camera": None,
        "valid_for_evidence": False,
        "message": "Isaac Sim Python unavailable. Run inside Isaac Sim.",
    }
    _write(report)
    print("[INFO] Isaac Python unavailable — wrote fallback scene validation.")


def _inside_isaac() -> None:
    import omni.usd  # type: ignore

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        _write({
            "status": "no_stage",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "valid_for_evidence": False,
            "message": "No stage loaded. Open a VLN scene first.",
        })
        return

    all_prims = [str(p.GetPath()) for p in stage.Traverse()]
    prim_count = len(all_prims)

    ground_prims = [p for p in all_prims if any(p.startswith(g) for g in _GROUND_PLANE_PATHS)]
    non_ground = [p for p in all_prims if not any(p.startswith(g) for g in _GROUND_PLANE_PATHS)
                  and p not in ("/", "/World")]
    cameras = [p for p in all_prims if "Camera" in p or "camera" in p]

    has_ground = len(ground_prims) > 0
    has_ground_only = has_ground and len(non_ground) == 0
    has_vln = any("kujiale" in p.lower() or "vlnverse" in p.lower() or "Room" in p or "Mesh" in p
                  for p in non_ground)
    has_yahboom = any("yahboom" in p.lower() or "m3pro" in p.lower() or "m3_pro" in p.lower()
                      for p in all_prims)

    fp_cams = [c for c in cameras if any(k in c.lower() for k in _FP_CAM_KEYWORDS)]
    has_fp_cam = len(fp_cams) > 0
    selected_cam = fp_cams[0] if fp_cams else (cameras[0] if cameras else None)

    cam_is_fp = (
        selected_cam is not None and
        any(k in selected_cam.lower() for k in _FP_CAM_KEYWORDS)
    )

    invalid_reasons = []
    if has_ground_only:
        invalid_reasons.append("only defaultGroundPlane visible — no VLN scene loaded")
    if not has_vln:
        invalid_reasons.append("VLN scene geometry not found in stage")
    if not has_yahboom:
        invalid_reasons.append("Yahboom M3 Pro not staged")
    if not cam_is_fp:
        invalid_reasons.append("camera is not first-person/FloatingCamera")

    valid = len(invalid_reasons) == 0

    report = {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prim_count": prim_count,
        "all_prims_sample": all_prims[:20],
        "has_default_ground_plane": has_ground,
        "has_default_ground_plane_only": has_ground_only,
        "has_imported_vln_scene": has_vln,
        "has_yahboom": has_yahboom,
        "has_floating_camera": has_fp_cam,
        "all_cameras": cameras,
        "selected_camera": selected_cam,
        "camera_is_first_person": cam_is_fp,
        "valid_for_evidence": valid,
        "invalid_reasons": invalid_reasons,
    }
    _write(report)
    print(f"  prim_count={prim_count}  has_vln={has_vln}  has_yahboom={has_yahboom}")
    print(f"  valid_for_evidence={valid}")
    if invalid_reasons:
        for r in invalid_reasons:
            print(f"  [!] {r}")


def main() -> None:
    print("=" * 40)
    print("  FleetSafe — Validate Isaac Scene")
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
