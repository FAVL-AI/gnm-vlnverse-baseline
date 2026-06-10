"""
Isaac Sim control panel — start/stop/scene/benchmark/snapshot.

All destructive actions (start Isaac, run benchmark) go through
ProcessManager so they appear in the Job history and log stream.
"""
from __future__ import annotations

import csv
import io
import json
import threading
import time
from pathlib import Path
from typing import Any

import aiohttp
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import settings
from ..services.process_manager import process_manager
from ..services.stream_manager import STREAMS

# ── Audit helper (mirrors robot_ops._audit) ───────────────────────────────────

_AUDIT_PATH = settings.repo_root / "command-center" / "recordings" / "audit.jsonl"
_audit_lock = threading.Lock()


def _audit(op: str, args: dict, result: str, dry_run: bool) -> dict:
    entry = {
        "ts": time.time(),
        "op": op,
        "args": args,
        "result": result,
        "dry_run": dry_run,
    }
    _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _audit_lock:
        with _AUDIT_PATH.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    return entry

router = APIRouter(prefix="/api/isaac", tags=["isaac"])

_ISAAC_HTTP = "http://localhost:8211"
_ISAAC_NUCLEUS = "http://localhost:8080"

HOSPITAL_SCENES = [
    "hospital_corridor",
    "hospital_waiting_room",
    "hospital_narrow_passage",
    "hospital_crowded_junction",
    "hospital_elevator_lobby",
    "hospital_reception",
]


# ── Status ─────────────────────────────────────────────────────────────────────

@router.get("/status")
async def isaac_status() -> dict:
    """Probe Isaac Sim HTTP endpoint and Nucleus."""
    isaac_live = False
    webrtc_live = False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{_ISAAC_HTTP}/", timeout=aiohttp.ClientTimeout(total=1.5)) as r:
                isaac_live = r.status < 500
    except Exception:
        pass
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{_ISAAC_HTTP}/offer", timeout=aiohttp.ClientTimeout(total=1.0)) as r:
                webrtc_live = r.status in (200, 405)  # 405 = exists but wrong method
    except Exception:
        pass

    stream = STREAMS.get("isaac")
    return {
        "isaac_live":   isaac_live,
        "webrtc_live":  webrtc_live,
        "http_url":     _ISAAC_HTTP,
        "stream_status": stream.status if stream else "unknown",
    }


# ── Launch / stop ──────────────────────────────────────────────────────────────

class SceneRequest(BaseModel):
    scene: str = "hospital_corridor"
    extra_args: list[str] = []


@router.post("/start")
async def start_isaac(req: SceneRequest) -> dict:
    """Launch Isaac Sim with the hospital environment."""
    script = settings.repo_root / "scripts" / "isaaclab" / "run_hospital.sh"
    if not script.exists():
        # Fallback: look for any Isaac launch script
        candidates = list((settings.repo_root / "scripts").rglob("*isaac*.sh"))
        if not candidates:
            raise HTTPException(404, "No Isaac Sim launch script found in scripts/")
        script = candidates[0]

    cmd = ["bash", str(script), "--scene", req.scene] + req.extra_args
    job = await process_manager.launch(
        script_key="isaac_start",
        label=f"Isaac Sim — {req.scene}",
        cmd=cmd,
        cwd=settings.repo_root,
    )
    return {"job_id": job.job_id, "status": job.status}


@router.post("/stop")
async def stop_isaac() -> dict:
    """Kill all running Isaac jobs."""
    killed = []
    for job_d in process_manager.list_jobs():
        if "isaac" in job_d["script_key"].lower() and job_d["status"] == "running":
            await process_manager.kill(job_d["job_id"])
            killed.append(job_d["job_id"])
    return {"killed": killed}


@router.post("/benchmark")
async def run_isaac_benchmark(req: SceneRequest) -> dict:
    """Run the benchmark matrix against Isaac Sim."""
    script = settings.repo_root / "scripts" / "visualnav" / "run_baseline_isaac.sh"
    if not script.exists():
        raise HTTPException(404, "run_baseline_isaac.sh not found")
    cmd = ["bash", str(script)] + req.extra_args
    job = await process_manager.launch(
        script_key="isaac_benchmark",
        label="Isaac Sim benchmark",
        cmd=cmd,
        cwd=settings.repo_root,
    )
    return {"job_id": job.job_id, "status": job.status}


@router.post("/load-scene/{scene}")
async def load_scene(scene: str) -> dict:
    """Send load-scene command to a running Isaac instance via HTTP."""
    if scene not in HOSPITAL_SCENES:
        raise HTTPException(400, f"Unknown scene. Valid: {HOSPITAL_SCENES}")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{_ISAAC_HTTP}/load_scene",
                json={"scene": scene},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                body = await r.json()
                return {"scene": scene, "response": body}
    except Exception as e:
        raise HTTPException(503, f"Isaac not reachable: {e}")


@router.post("/snapshot")
async def snapshot_viewport() -> dict:
    """Request a viewport snapshot from Isaac."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{_ISAAC_HTTP}/snapshot",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                body = await r.json()
                return {"snapshot": body}
    except Exception as e:
        raise HTTPException(503, f"Isaac not reachable: {e}")


@router.get("/scenes")
async def list_scenes() -> list[str]:
    return HOSPITAL_SCENES


# ── Photoreal status + screenshot ─────────────────────────────────────────────

_HOSPITAL_LOG_ROOT = settings.repo_root / "logs" / "hospital_benchmark"
_LATEST = _HOSPITAL_LOG_ROOT / "latest"


def _latest_file(name: str) -> Path | None:
    """Return path to `name` in the latest run dir, or None if not present."""
    candidate = _LATEST / name
    if candidate.exists():
        return candidate
    # Fallback: scan all run dirs newest-first
    try:
        runs = sorted(
            [d for d in _HOSPITAL_LOG_ROOT.iterdir() if d.is_dir() and d.name != "latest"],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        for run in runs:
            p = run / name
            if p.exists():
                return p
    except Exception:
        pass
    return None


@router.get("/photoreal-status")
async def photoreal_status() -> dict:
    """
    Return the photoreal capture status of the most recent hospital run.
    Reads logs/hospital_benchmark/latest/photoreal_status.json.
    """
    p = _latest_file("photoreal_status.json")
    if p is None:
        return {
            "status": "NOT_RUN",
            "usd_loaded": False,
            "usd_path": None,
            "screenshot": None,
            "capture_method": None,
            "scene": None,
            "scenario": None,
            "timestamp": None,
            "isaac_version": None,
        }
    try:
        return json.loads(p.read_text())
    except Exception as e:
        raise HTTPException(500, f"Could not parse photoreal_status.json: {e}")


@router.get("/asset-status")
async def asset_status() -> dict:
    """Check whether the hospital_world.usd asset file exists on disk."""
    usd_path = settings.repo_root / "fleet_safe_vla" / "envs" / "isaaclab" / "hospital" / "assets" / "hospital_world.usd"
    exists = usd_path.exists()
    size_kb = round(usd_path.stat().st_size / 1024, 1) if exists else 0
    return {
        "usd_found": exists,
        "usd_path": str(usd_path),
        "size_kb": size_kb,
        "generate_cmd": "conda activate isaac && ./scripts/isaaclab/generate_hospital_usd.sh",
        "capture_cmd": "conda activate isaac && ./scripts/isaaclab/run_hospital.sh --capture --steps 50",
    }


@router.get("/screenshot")
async def get_screenshot():
    """
    Serve the latest viewport screenshot.png.
    Falls back to procedural_preview.png when no Isaac Sim render exists.
    """
    # Prefer real Isaac Sim screenshot
    p = _latest_file("screenshot.png")
    if p is not None and p.exists() and p.stat().st_size > 1000:
        return FileResponse(
            str(p),
            media_type="image/png",
            headers={"Cache-Control": "no-store", "X-Capture-Method": "isaac_viewport"},
        )

    # Fall back: read screenshot path from photoreal_status.json
    status_file = _latest_file("photoreal_status.json")
    if status_file is not None:
        try:
            st = json.loads(status_file.read_text())
            fallback = st.get("screenshot")
            if fallback:
                fb_path = Path(fallback) if Path(fallback).is_absolute() else settings.repo_root / fallback
                if fb_path.exists() and fb_path.stat().st_size > 1000:
                    return FileResponse(
                        str(fb_path),
                        media_type="image/png",
                        headers={"Cache-Control": "no-store", "X-Capture-Method": "procedural_preview"},
                    )
        except Exception:
            pass

    # Final fallback: look for procedural_preview.png directly
    p = _latest_file("procedural_preview.png")
    if p is not None and p.exists():
        return FileResponse(
            str(p),
            media_type="image/png",
            headers={"Cache-Control": "no-store", "X-Capture-Method": "procedural_preview"},
        )

    raise HTTPException(
        404,
        "No screenshot or preview found. Run: python scripts/isaaclab/gen_proof_run.py",
    )


# ── Sensor Degradation ─────────────────────────────────────────────────────────

class SensorDegradationConfig(BaseModel):
    motion_blur: float = 0.0          # 0–100 %
    low_light: float = 0.0            # 0–100 %
    lidar_dropout_rate: float = 0.0   # 0–50 %
    camera_packet_loss: float = 0.0   # 0–30 %
    latency_jitter_ms: float = 0.0    # 0–200 ms
    depth_corruption: bool = False


@router.post("/sensor-degradation")
async def sensor_degradation(config: SensorDegradationConfig) -> dict:
    """Apply sensor degradation parameters to Isaac Sim (stub — logs to audit)."""
    dry_run = settings.robot_dry_run
    _audit(
        "sensor_degradation",
        config.model_dump(),
        "DRY_RUN" if dry_run else "applied",
        dry_run=dry_run,
    )
    return {"applied": True, "dry_run": dry_run}


# ── Pedestrian Scenario ────────────────────────────────────────────────────────

PEDESTRIAN_SCENARIOS = [
    "crossing",
    "occlusion",
    "congestion",
    "yield",
    "corridor_rush",
]


class PedestrianScenarioRequest(BaseModel):
    scene: str
    scenario: str


@router.post("/pedestrian-scenario")
async def pedestrian_scenario(req: PedestrianScenarioRequest) -> dict:
    """Load a named pedestrian scenario in Isaac Sim (stub — logs to audit)."""
    if req.scenario not in PEDESTRIAN_SCENARIOS:
        raise HTTPException(400, f"Unknown scenario. Valid: {PEDESTRIAN_SCENARIOS}")
    dry_run = settings.robot_dry_run
    _audit(
        "pedestrian_scenario",
        {"scene": req.scene, "scenario": req.scenario},
        "DRY_RUN" if dry_run else "applied",
        dry_run=dry_run,
    )
    return {"applied": True, "dry_run": dry_run}


# ── Recovery Test ──────────────────────────────────────────────────────────────

RECOVERY_TESTS = [
    "blocked_path_recovery",
    "reroute_around_human",
    "resume_after_estop",
]


class RecoveryTestRequest(BaseModel):
    test_type: str


@router.post("/recovery-test")
async def recovery_test(req: RecoveryTestRequest) -> dict:
    """Run a named recovery behaviour test in Isaac Sim (stub — logs to audit)."""
    if req.test_type not in RECOVERY_TESTS:
        raise HTTPException(400, f"Unknown test_type. Valid: {RECOVERY_TESTS}")
    dry_run = settings.robot_dry_run
    _audit(
        "recovery_test",
        {"test_type": req.test_type},
        "DRY_RUN" if dry_run else "applied",
        dry_run=dry_run,
    )
    return {"applied": True, "dry_run": dry_run}


# ── Hospital Run History ───────────────────────────────────────────────────────

def _run_dir(timestamp: str) -> Path:
    """Resolve and validate a run directory by timestamp. Raises 404 if missing."""
    d = _HOSPITAL_LOG_ROOT / timestamp
    if not d.is_dir():
        raise HTTPException(404, "Run not found")
    return d


@router.get("/runs")
async def list_runs() -> list[dict]:
    """List all hospital benchmark run directories, newest first."""
    if not _HOSPITAL_LOG_ROOT.exists():
        return []
    dirs = sorted(
        [d for d in _HOSPITAL_LOG_ROOT.iterdir() if d.is_dir() and d.name != "latest"],
        key=lambda d: d.name,
        reverse=True,
    )
    result = []
    for d in dirs:
        ts = d.name

        # Read session.json for scene/scenario
        scene = "unknown"
        scenario = "unknown"
        session_path = d / "session.json"
        if session_path.exists():
            try:
                sess = json.loads(session_path.read_text())
                scene = sess.get("scene", "unknown")
                scenario = sess.get("scenario", "unknown")
            except Exception:
                pass

        # Read capture_status.json for isaac_runtime/usd_asset
        isaac_runtime = "UNKNOWN"
        usd_asset = "UNKNOWN"
        cs_path = d / "capture_status.json"
        if cs_path.exists():
            try:
                cs = json.loads(cs_path.read_text())
                isaac_runtime = cs.get("isaac_runtime", "UNKNOWN")
                usd_asset = cs.get("usd_asset", "UNKNOWN")
            except Exception:
                pass

        result.append({
            "timestamp": ts,
            "scene": scene,
            "scenario": scenario,
            "has_preview": (d / "procedural_preview.png").exists(),
            "has_screenshot": (d / "screenshot.png").exists(),
            "has_trajectory": (d / "trajectory.csv").exists() and (d / "trajectory.csv").stat().st_size > 0,
            "has_events": (d / "safety_events.jsonl").exists() and (d / "safety_events.jsonl").stat().st_size > 0,
            "isaac_runtime": isaac_runtime,
            "usd_asset": usd_asset,
        })
    return result


@router.get("/run/{timestamp}/session")
async def run_session(timestamp: str) -> dict:
    """Return session.json for a specific run."""
    d = _run_dir(timestamp)
    p = d / "session.json"
    if not p.exists():
        raise HTTPException(404, "session.json not found in this run")
    try:
        return json.loads(p.read_text())
    except Exception as e:
        raise HTTPException(500, f"Could not parse session.json: {e}")


@router.get("/run/{timestamp}/trajectory")
async def run_trajectory(timestamp: str) -> dict:
    """Parse trajectory.csv and return step/x/y points, capped at 2000."""
    d = _run_dir(timestamp)
    p = d / "trajectory.csv"
    if not p.exists() or p.stat().st_size == 0:
        return {"steps": 0, "points": []}
    try:
        reader = csv.DictReader(io.StringIO(p.read_text()))
        rows = list(reader)
        if not rows:
            return {"steps": 0, "points": []}
        # Downsample if more than 2000 points
        if len(rows) > 2000:
            step_size = len(rows) / 2000
            rows = [rows[int(i * step_size)] for i in range(2000)]
        points = []
        for r in rows:
            try:
                points.append([int(r["step"]), float(r["x"]), float(r["y"])])
            except (KeyError, ValueError):
                continue
        return {"steps": len(points), "points": points}
    except Exception as e:
        raise HTTPException(500, f"Could not parse trajectory.csv: {e}")


@router.get("/run/{timestamp}/events")
async def run_events(timestamp: str) -> dict:
    """Parse safety_events.jsonl and return list of events."""
    d = _run_dir(timestamp)
    p = d / "safety_events.jsonl"
    if not p.exists():
        return {"events": []}
    events = []
    try:
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
    except Exception as e:
        raise HTTPException(500, f"Could not parse safety_events.jsonl: {e}")
    return {"events": events}


@router.get("/run/{timestamp}/social")
async def run_social(timestamp: str) -> dict:
    """Parse social_metrics.jsonl and compute aggregate summary."""
    d = _run_dir(timestamp)
    p = d / "social_metrics.jsonl"
    if not p.exists():
        return {"n_steps": 0}
    rows = []
    try:
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except Exception as e:
        raise HTTPException(500, f"Could not parse social_metrics.jsonl: {e}")
    if not rows:
        return {"n_steps": 0}

    def _mean(key: str) -> float | None:
        vals = [r[key] for r in rows if key in r and r[key] is not None]
        return sum(vals) / len(vals) if vals else None

    def _sum(key: str) -> int | None:
        vals = [r[key] for r in rows if key in r and r[key] is not None]
        return sum(vals) if vals else None

    return {
        "n_steps": len(rows),
        "min_interpersonal_dist_mean": _mean("interpersonal_dist"),
        "ttc_mean": _mean("ttc"),
        "stop_count_total": _sum("stop_count"),
        "hesitation_latency_mean": _mean("hesitation_latency"),
    }


@router.get("/run/{timestamp}/preview")
async def run_preview(timestamp: str):
    """Serve procedural_preview.png for a specific run."""
    d = _run_dir(timestamp)
    p = d / "procedural_preview.png"
    if not p.exists():
        raise HTTPException(404, "No preview image for this run")
    return FileResponse(
        str(p),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/run/{timestamp}/capture-status")
async def run_capture_status(timestamp: str) -> dict:
    """Return capture_status.json for a specific run."""
    d = _run_dir(timestamp)
    p = d / "capture_status.json"
    if not p.exists():
        return {"status": "NOT_RUN"}
    try:
        return json.loads(p.read_text())
    except Exception as e:
        raise HTTPException(500, f"Could not parse capture_status.json: {e}")
