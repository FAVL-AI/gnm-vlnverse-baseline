"""VLN Hub API router — VLNVerse, VLNTube, IAmGoodNavigator, and Yahboom integration.

Endpoints
---------
  GET /api/vln-hub/status              — combined status of all sources
  GET /api/vln-hub/vlnverse            — VLNVerse index
  GET /api/vln-hub/vlntube             — VLNTube index
  GET /api/vln-hub/previews            — available preview images
  GET /api/vln-hub/trajectories        — trajectory metadata
  GET /api/vln-hub/instructions        — sample instructions
  GET /api/vln-hub/live                — live Isaac/demo/camera/asset status
  GET /api/vln-hub/imported-episodes   — IAmGoodNavigator episodes imported
  GET /api/vln-hub/episode/{src}/{task}/{index} — specific episode metadata
  GET /api/vln-hub/camera/latest       — current camera report
  GET /api/vln-hub/asset-report        — Yahboom robot asset status
  GET /api/yahboom/assets              — Yahboom URDF/USD asset report
  POST /api/vln-hub/refresh            — re-run indexers and return fresh data
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/vln-hub", tags=["vln-hub"])

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VLNTUBE_INDEX      = _REPO_ROOT / "datasets" / "vlntube"  / "vlntube_index.json"
_VLNVERSE_INDEX     = _REPO_ROOT / "datasets" / "vlnverse" / "vlnverse_index.json"
_IANG_STATUS        = _REPO_ROOT / "datasets" / "vlnverse" / "iamgoodnavigator_status.json"
_IANG_IMPORT_DIR    = _REPO_ROOT / "datasets" / "vlnverse" / "imported" / "iamgoodnavigator"
_CAMERA_REPORT      = _REPO_ROOT / "runs" / "current_camera_report.json"
_ASSET_REPORT       = _REPO_ROOT / "assets" / "robots" / "yahboom_m3_pro" / "asset_report.json"
_VLNTUBE_DL_REPORT  = _REPO_ROOT / "datasets" / "vlntube" / "asset_download_report.json"
_SCENE_VALIDATION   = _REPO_ROOT / "runs" / "isaac_scene_validation.json"
_ASSET_PATH_STATUS  = _REPO_ROOT / "datasets" / "vlnverse" / "asset_path_fix_status.json"
_YAHBOOM_USD        = _REPO_ROOT / "assets" / "robots" / "yahboom_m3_pro" / "yahboom_m3pro.usd"
_EVIDENCE_SUMMARY   = _REPO_ROOT / "evidence" / "fleetsafe_vlnverse_plus" / "evidence_summary.json"
_YAHBOOM_STAGE_RPT  = _REPO_ROOT / "runs" / "yahboom_stage_report.json"
_LIVE_STATUS        = _REPO_ROOT / "evidence" / "fleetsafe_vlnverse_plus" / "live" / "live_status.json"
_E2E_SUMMARY        = _REPO_ROOT / "evidence" / "fleetsafe_vlnverse_plus" / "live" / "e2e_motion_summary.json"


def _read_index(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _run_indexer(module: str) -> bool:
    """Re-run a Python indexer module. Returns True on success."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", module],
            capture_output=True, text=True, timeout=30,
            cwd=str(_REPO_ROOT),
        )
        return result.returncode == 0
    except Exception:
        return False


@router.get("/status")
async def status() -> Dict[str, Any]:
    """Combined status of VLNVerse and VLNTube."""
    vt = _read_index(_VLNTUBE_INDEX)
    vv = _read_index(_VLNVERSE_INDEX)

    vt_sum = vt["summary"] if vt else {}
    vv_sum = vv["summary"] if vv else {}

    return {
        "ok": True,
        "vlntube": {
            "indexed": vt is not None,
            "repo_available": vt_sum.get("repo_available", False),
            "usd_scenes": vt_sum.get("usd_scenes", 0),
            "rgb_sequences": vt_sum.get("rgb_sequences", 0),
            "scene_graphs": vt_sum.get("scene_graphs", 0),
            "instruction_files": vt_sum.get("instruction_files", 0),
            "indexed_at": vt.get("indexed_at") if vt else None,
        },
        "vlnverse": {
            "indexed": vv is not None,
            "data_available": vv_sum.get("data_available", False),
            "scene_count": vv_sum.get("scene_count", 0),
            "preview_count": vv_sum.get("preview_count", 0),
            "instruction_count": vv_sum.get("instruction_count", 0),
            "trajectory_count": vv_sum.get("trajectory_count", 0),
            "indexed_at": vv.get("indexed_at") if vv else None,
        },
        "next_actions": {
            "vlntube": (vt or {}).get("next_actions", ["Run: python -m fleetsafe_vln.datagen.vlntube_indexer"]),
            "vlnverse": (vv or {}).get("next_actions", ["Run: python -m fleetsafe_vln.benchmark.vlnverse_indexer"]),
        },
    }


@router.get("/vlntube")
async def vlntube_index() -> Dict[str, Any]:
    """Full VLNTube index. 404 if not yet indexed."""
    data = _read_index(_VLNTUBE_INDEX)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "VLNTube not indexed yet",
                "fix": "Run: python -m fleetsafe_vln.datagen.vlntube_indexer",
            },
        )
    return data


@router.get("/vlnverse")
async def vlnverse_index() -> Dict[str, Any]:
    """Full VLNVerse index. 404 if not yet indexed."""
    data = _read_index(_VLNVERSE_INDEX)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "VLNVerse not indexed yet",
                "fix": "Run: python -m fleetsafe_vln.benchmark.vlnverse_indexer",
            },
        )
    return data


@router.get("/previews")
async def previews() -> Dict[str, Any]:
    """Return available preview image paths (relative to repo root)."""
    images: List[str] = []

    # VLNTube outputs
    vt = _read_index(_VLNTUBE_INDEX)
    if vt:
        for p in vt.get("datasets", {}).get("image_sample_paths", []):
            images.append(f"datasets/vlntube/{p}")

    # VLNVerse previews
    vv = _read_index(_VLNVERSE_INDEX)
    if vv:
        for p in vv.get("datasets", {}).get("preview_paths", []):
            images.append(f"datasets/vlnverse/{p}")

    return {
        "count": len(images),
        "images": images,
        "has_data": len(images) > 0,
        "missing_data_message": (
            "No preview images found. "
            "Run bash scripts/setup_vlntube.sh and bash scripts/setup_vlnverse.sh --sample "
            "then python -m fleetsafe_vln.datagen.vlntube_indexer"
            if not images else None
        ),
    }


@router.get("/trajectories")
async def trajectories() -> Dict[str, Any]:
    """Return trajectory metadata samples."""
    trajs: List[Dict[str, Any]] = []

    vt = _read_index(_VLNTUBE_INDEX)
    if vt:
        for t in vt.get("datasets", {}).get("image_sample_paths", [])[:3]:
            trajs.append({"source": "vlntube", "path": t})

    vv = _read_index(_VLNVERSE_INDEX)
    if vv:
        for t in vv.get("datasets", {}).get("sample_trajectories", []):
            trajs.append({"source": "vlnverse", **t})

    return {
        "count": len(trajs),
        "trajectories": trajs,
        "has_data": len(trajs) > 0,
    }


@router.get("/instructions")
async def instructions() -> Dict[str, Any]:
    """Return sample navigation instructions."""
    samples: List[Dict[str, str]] = []

    vt = _read_index(_VLNTUBE_INDEX)
    if vt:
        for p in vt.get("datasets", {}).get("image_sample_paths", [])[:2]:
            samples.append({"source": "vlntube", "text": f"[sample from {p}]"})

    vv = _read_index(_VLNVERSE_INDEX)
    if vv:
        for instr in vv.get("datasets", {}).get("sample_instructions", []):
            samples.append({"source": "vlnverse", "text": instr})

    return {
        "count": len(samples),
        "instructions": samples,
        "has_data": len(samples) > 0,
        "missing_data_message": (
            None if samples else
            "No instructions indexed yet. Run: bash scripts/setup_vlnverse.sh --sample"
        ),
    }


@router.post("/refresh")
async def refresh() -> Dict[str, Any]:
    """Re-run both indexers and return fresh status."""
    vt_ok = _run_indexer("fleetsafe_vln.datagen.vlntube_indexer")
    vv_ok = _run_indexer("fleetsafe_vln.benchmark.vlnverse_indexer")
    return {
        "ok": True,
        "vlntube_refreshed": vt_ok,
        "vlnverse_refreshed": vv_ok,
        "status": await status(),
    }


@router.get("/live")
async def live() -> Dict[str, Any]:
    """Aggregated live status: Isaac scene, camera, robot assets, imported episodes."""
    iang          = _read_index(_IANG_STATUS)
    cam           = _read_index(_CAMERA_REPORT)
    asset         = _read_index(_ASSET_REPORT)
    vt            = _read_index(_VLNTUBE_INDEX)
    vv            = _read_index(_VLNVERSE_INDEX)
    dl_rep        = _read_index(_VLNTUBE_DL_REPORT)
    scene_val     = _read_index(_SCENE_VALIDATION)
    asset_paths   = _read_index(_ASSET_PATH_STATUS)
    ev_summary    = _read_index(_EVIDENCE_SUMMARY)
    stage_rpt     = _read_index(_YAHBOOM_STAGE_RPT)
    live_status   = _read_index(_LIVE_STATUS)
    e2e_summary   = _read_index(_E2E_SUMMARY)

    # Count imported episodes; find latest episode_meta for scene evidence info
    ep_count = 0
    latest_ep_meta: Optional[Dict[str, Any]] = None
    if _IANG_IMPORT_DIR.exists():
        for d in sorted(_IANG_IMPORT_DIR.iterdir()):
            if d.is_dir() and (d / "episode_meta.json").exists():
                ep_count += 1
                latest_ep_meta = _read_index(d / "episode_meta.json")

    # Determine camera status
    cam_status  = (cam or {}).get("status", "unknown")
    cam_is_fp   = (cam or {}).get("is_first_person", False)
    cam_path    = (cam or {}).get("selected_camera")
    cam_outside = cam_status == "isaac_python_unavailable"
    cam_ok      = cam_is_fp and not cam_outside

    # Yahboom asset status
    yahboom_urdf_ok = (asset or {}).get("has_urdf", False)
    yahboom_usd_ok  = _YAHBOOM_USD.exists()

    # VLNTube real data
    vt_real    = (vt or {}).get("summary", {}).get("has_real_data", False)
    vt_hf_real = (dl_rep or {}).get("real_data_present", False)

    # Scene existence
    scene_exists          = (latest_ep_meta or {}).get("scene_exists", False)
    expected_scene_path   = (latest_ep_meta or {}).get("expected_scene_path")
    episode_evidence_valid = (latest_ep_meta or {}).get("evidence_valid", False)
    episode_status        = (latest_ep_meta or {}).get("status", "none")

    # Isaac scene validation (only populated when run inside Isaac)
    isaac_scene_valid     = (scene_val or {}).get("valid_for_evidence", False)
    isaac_invalid_reasons = (scene_val or {}).get("invalid_reasons", [])
    # Yahboom staged: prefer dedicated stage_report over scene_validation
    has_yahboom_staged    = (
        (stage_rpt or {}).get("stage_has_yahboom", False)
        or (scene_val or {}).get("has_yahboom", False)
    )
    yahboom_stage_status  = (stage_rpt or {}).get("status", "not_run")

    # Live capture state
    live_capture_active   = (live_status or {}).get("window_found", False)
    live_capture_ts       = (live_status or {}).get("last_frame_time")
    live_frame_exists     = (
        _REPO_ROOT / "command-center" / "frontend" / "public" / "live" / "isaac_live.png"
    ).exists()

    # Asset path fix status
    scenes_missing = (asset_paths or {}).get("scenes_missing", [])

    # Build exact missing steps list
    exact_missing_steps: List[str] = []
    if not scene_exists:
        exact_missing_steps.append(
            f"VLN scene USD missing: {expected_scene_path or 'unknown'}. "
            "Run: bash scripts/fix_iamgoodnavigator_asset_paths.sh"
        )
    if not yahboom_usd_ok:
        exact_missing_steps.append(
            "Yahboom M3 Pro USD missing. "
            "Run: bash scripts/import_yahboom_m3_urdf_to_isaac.sh assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf"
        )
    if cam_outside:
        exact_missing_steps.append(
            "Camera report was captured outside Isaac Sim — run set_navigation_camera.py inside Isaac Sim"
        )
    if not cam_is_fp and not cam_outside:
        exact_missing_steps.append(
            "Isaac camera is not first-person/FloatingCamera. "
            "In Isaac Sim: Perspective → Cameras → FloatingCamera"
        )
    if episode_evidence_valid is False and scene_exists:
        exact_missing_steps.append(
            "Episode produced no trajectory/image output — run demo interactively inside Isaac Sim"
        )

    evidence_ready = (
        scene_exists and yahboom_usd_ok and cam_ok and episode_evidence_valid
    )

    return {
        "ok": True,
        "isaac": {
            "camera_status": cam_status,
            "camera_path": cam_path,
            "camera_is_first_person": cam_is_fp,
            "camera_ok": cam_ok,
            "camera_outside_isaac": cam_outside,
            "camera_report_exists": cam is not None,
            "scene_valid_for_evidence": isaac_scene_valid,
            "scene_invalid_reasons": isaac_invalid_reasons,
            "has_yahboom_staged": has_yahboom_staged,
            "yahboom_stage_status": yahboom_stage_status,
            "camera_instructions": "In Isaac Sim: Perspective → Cameras → FloatingCamera",
        },
        "live_capture": {
            "running": live_capture_active,
            "last_frame_time": live_capture_ts,
            "frame_exists": live_frame_exists,
            "frame_url": "/live/isaac_live.png",
            "message": (live_status or {}).get("message"),
            "tool": (live_status or {}).get("capture_tool"),
            "start_cmd": "bash scripts/capture_isaac_live.sh",
        },
        "e2e_motion": {
            "demo_run": e2e_summary is not None,
            "autonomous_robot_control": (e2e_summary or {}).get("autonomous_robot_control", False),
            "mode": (e2e_summary or {}).get("mode", "not_run"),
            "e2e_evidence": (e2e_summary or {}).get("e2e_evidence", False),
            "timesteps": (e2e_summary or {}).get("timesteps", 0),
            "note": (e2e_summary or {}).get("note"),
        },
        "iamgoodnavigator": {
            "available": (iang or {}).get("root_exists", False),
            "demo_py": (iang or {}).get("demo_py_exists", False),
            "fine_episodes": (iang or {}).get("fine_episodes", 0),
            "coarse_episodes": (iang or {}).get("coarse_episodes", 0),
            "data_downloaded": (iang or {}).get("data_downloaded", False),
            "imported_episodes": ep_count,
            "ready": (iang or {}).get("ready", False),
            "missing": (iang or {}).get("missing", []),
            "scene_exists": scene_exists,
            "expected_scene_path": expected_scene_path,
            "episode_status": episode_status,
            "episode_evidence_valid": episode_evidence_valid,
            "scenes_missing_from_disk": scenes_missing,
            "next_step": (
                "Run: bash scripts/run_iamgoodnavigator_episode.sh fine 0"
                if (iang or {}).get("ready") else
                "Run: bash scripts/setup_iamgoodnavigator.sh"
            ),
        },
        "vlntube": {
            "repo_available": (vt or {}).get("summary", {}).get("repo_available", False),
            "has_real_data": vt_real,
            "hf_data_downloaded": vt_hf_real,
            "usd_scenes": (vt or {}).get("summary", {}).get("usd_scenes", 0),
            "rgb_images": (vt or {}).get("summary", {}).get("rgb_images", 0),
            "instruction_files": (vt or {}).get("summary", {}).get("instruction_files", 0),
        },
        "yahboom": {
            "urdf_found": yahboom_urdf_ok,
            "usd_exists": yahboom_usd_ok,
            "usd_path": str(_YAHBOOM_USD) if yahboom_usd_ok else None,
            "canonical_urdf": (asset or {}).get("canonical_urdf"),
            "status": (asset or {}).get("status", "unknown"),
            "staged": has_yahboom_staged,
            "stage_status": yahboom_stage_status,
            "stage_prim_path": (stage_rpt or {}).get("yahboom_prim_path"),
            "blocked": not yahboom_urdf_ok,
            "usd_blocked": not yahboom_usd_ok,
            "stage_instructions": (
                None if has_yahboom_staged else
                "Run: bash scripts/add_yahboom_to_isaac_stage.sh  "
                "or in Isaac: File → Add Reference → yahboom_m3pro.usd"
            ),
            "block_message": (
                None if yahboom_urdf_ok else
                "Yahboom M3 URDF not found. Run: bash scripts/setup_yahboom_m3_assets.sh"
            ),
            "usd_block_message": (
                None if yahboom_usd_ok else
                "Yahboom M3 USD not found. Convert: "
                "bash scripts/import_yahboom_m3_urdf_to_isaac.sh "
                "assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf"
            ),
        },
        "evidence": {
            "ready": evidence_ready,
            "summary_exists": ev_summary is not None,
            "all_images_present": (ev_summary or {}).get("all_images_present", False),
            "camera_is_first_person": (ev_summary or {}).get("camera_is_first_person", False),
            "episode_evidence_valid": (ev_summary or {}).get("episode_evidence_valid", False),
            "yahboom_urdf_exists": (ev_summary or {}).get("yahboom_urdf_exists", False),
            "yahboom_usd_exists": (ev_summary or {}).get("yahboom_usd_exists", False),
            "missing_steps": (ev_summary or {}).get("missing_steps", []),
        },
        "exact_missing_steps": exact_missing_steps,
        "blocking_issues": [
            x for x in [
                f"VLN scene USD missing ({expected_scene_path})" if not scene_exists else None,
                "Yahboom M3 Pro USD not generated" if not yahboom_usd_ok else None,
                "Camera report captured outside Isaac Sim" if cam_outside else None,
                "Camera not set to FloatingCamera (first-person)" if not cam_is_fp and not cam_outside else None,
                "Episode has no trajectory/image output" if episode_status == "completed_no_output" else None,
                "Yahboom M3 URDF missing" if not yahboom_urdf_ok else None,
            ]
            if x is not None
        ],
    }


@router.get("/imported-episodes")
async def imported_episodes() -> Dict[str, Any]:
    """List imported IAmGoodNavigator episodes."""
    episodes: List[Dict[str, Any]] = []
    if _IANG_IMPORT_DIR.exists():
        for ep_dir in sorted(_IANG_IMPORT_DIR.iterdir()):
            if not ep_dir.is_dir():
                continue
            meta_file = ep_dir / "episode_meta.json"
            if meta_file.exists():
                try:
                    episodes.append(json.loads(meta_file.read_text()))
                except Exception:
                    episodes.append({"name": ep_dir.name, "status": "parse_error"})
            else:
                episodes.append({"name": ep_dir.name, "status": "no_meta"})
    return {
        "count": len(episodes),
        "episodes": episodes,
        "has_data": len(episodes) > 0,
        "import_dir": str(_IANG_IMPORT_DIR),
        "missing_data_message": (
            None if episodes else
            "No episodes imported yet. Run: bash scripts/run_iamgoodnavigator_episode.sh fine 0"
        ),
    }


@router.get("/episode/{source}/{task}/{index}")
async def episode_detail(source: str, task: str, index: str) -> Dict[str, Any]:
    """Return metadata for a specific imported episode."""
    if source == "iamgoodnavigator":
        ep_dir = _IANG_IMPORT_DIR / f"{task}_{index}"
        meta_file = ep_dir / "episode_meta.json"
        if not meta_file.exists():
            raise HTTPException(
                status_code=404,
                detail={
                    "error": f"Episode {source}/{task}/{index} not imported",
                    "fix": f"Run: bash scripts/run_iamgoodnavigator_episode.sh {task} {index}",
                },
            )
        return json.loads(meta_file.read_text())
    raise HTTPException(status_code=404, detail={"error": f"Unknown source: {source}"})


@router.get("/camera/latest")
async def camera_latest() -> Dict[str, Any]:
    """Return the current Isaac camera report."""
    data = _read_index(_CAMERA_REPORT)
    if data is None:
        return {
            "ok": False,
            "camera_mode": "unknown",
            "selected_camera": None,
            "is_first_person": False,
            "message": (
                "No camera report. Run Isaac Sim and execute: "
                "python.sh scripts/isaac/set_first_person_camera.py"
            ),
            "camera_instructions": "In Isaac Sim: Perspective → Cameras → FloatingCamera",
        }
    data["ok"] = True
    return data


@router.get("/project-page")
async def project_page_status() -> Dict[str, Any]:
    """Status of all project-page components."""
    paper_draft = _REPO_ROOT / "docs" / "paper" / "FleetSafe_VLN_Paper_Draft.md"
    paper_pdf   = _REPO_ROOT / "docs" / "paper" / "FleetSafe_VLN.pdf"
    iang_status = _read_index(_IANG_STATUS)
    vt          = _read_index(_VLNTUBE_INDEX)
    ep_count    = sum(1 for d in _IANG_IMPORT_DIR.iterdir()
                      if d.is_dir() and (d / "episode_meta.json").exists()
                      ) if _IANG_IMPORT_DIR.exists() else 0

    return {
        "ok": True,
        "paper": {
            "draft_exists": paper_draft.exists(),
            "pdf_exists": paper_pdf.exists(),
            "draft_path": str(paper_draft),
        },
        "data": {
            "vlnverse_indexed": (_VLNVERSE_INDEX).exists(),
            "vlntube_indexed": (_VLNTUBE_INDEX).exists(),
            "real_data_present": (vt or {}).get("summary", {}).get("has_real_data", False),
            "iamgoodnavigator_ready": (iang_status or {}).get("ready", False),
        },
        "code": {
            "repo": "https://github.com/FAVL-AI/FleetSafe-VisualNav-Benchmark",
            "gnm_adapter": (_REPO_ROOT / "fleetsafe_vln" / "backbones" / "gnm_adapter.py").exists(),
            "cbf_qp": (_REPO_ROOT / "fleetsafe_vln" / "safety" / "cbf_qp_shield.py").exists(),
            "vlntube_indexer": (_REPO_ROOT / "fleetsafe_vln" / "datagen" / "vlntube_indexer.py").exists(),
        },
        "demo": {
            "iamgoodnavigator_cloned": (iang_status or {}).get("root_exists", False),
            "demo_py": (iang_status or {}).get("demo_py_exists", False),
            "imported_episodes": ep_count,
        },
        "evidence": {
            "evidence_dir_exists": (_REPO_ROOT / "evidence" / "live_imported_vln_demo").exists(),
        },
    }


@router.get("/vlntube-pipeline")
async def vlntube_pipeline() -> Dict[str, Any]:
    """VLNTube pipeline module status."""
    vt = _read_index(_VLNTUBE_INDEX)
    repo = _REPO_ROOT / "external" / "VLNTube"
    modules = {}
    for mod in ["scene_graph", "vistube", "instube", "datatube", "splits"]:
        mod_dir = repo / mod
        modules[mod] = {
            "present": mod_dir.exists(),
            "files": sum(1 for _ in mod_dir.rglob("*") if _.is_file()) if mod_dir.exists() else 0,
        }
    dl_report = _read_index(_VLNTUBE_DL_REPORT)
    return {
        "ok": True,
        "repo_available": repo.exists(),
        "modules": modules,
        "real_files": (vt or {}).get("summary", {}).get("has_real_data", False),
        "usd_scenes": (vt or {}).get("summary", {}).get("usd_scenes", 0),
        "rgb_images": (vt or {}).get("summary", {}).get("rgb_images", 0),
        "room_meta_files": (vt or {}).get("summary", {}).get("room_metadata_files", 0),
        "instruction_files": (vt or {}).get("summary", {}).get("instruction_files", 0),
        "datatube_exports": (vt or {}).get("summary", {}).get("datatube_exports", 0),
        "download_report": dl_report,
    }


@router.get("/paper")
async def paper_status() -> Dict[str, Any]:
    """Paper draft status."""
    draft = _REPO_ROOT / "docs" / "paper" / "FleetSafe_VLN_Paper_Draft.md"
    pdf   = _REPO_ROOT / "docs" / "paper" / "FleetSafe_VLN.pdf"
    return {
        "ok": True,
        "draft_exists": draft.exists(),
        "draft_path": str(draft) if draft.exists() else None,
        "pdf_exists": pdf.exists(),
        "pdf_path": str(pdf) if pdf.exists() else None,
        "export_command": "pandoc docs/paper/FleetSafe_VLN_Paper_Draft.md -o docs/paper/FleetSafe_VLN.pdf",
    }


@router.get("/asset-report")
@router.get("/yahboom-assets")
async def asset_report() -> Dict[str, Any]:
    """Yahboom robot URDF/USD asset status."""
    data = _read_index(_ASSET_REPORT)
    if data is None:
        return {
            "ok": False,
            "robot": "Yahboom ROSMASTER M3 Pro",
            "has_urdf": False,
            "has_usd": False,
            "status": "not_searched",
            "message": "Run: bash scripts/setup_yahboom_m3_assets.sh",
        }
    data["ok"] = True
    return data


# Alias under /api/yahboom namespace
yahboom_router = APIRouter(prefix="/api/yahboom", tags=["yahboom"])


@yahboom_router.get("/assets")
async def yahboom_assets() -> Dict[str, Any]:
    """Yahboom robot asset status (same as /api/vln-hub/asset-report)."""
    return await asset_report()
