"""Script launcher router — POST /api/launch, WS /ws/logs/{job_id}."""
from __future__ import annotations

import shlex
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from ..config import ALLOWED_SCRIPTS, settings
from ..models import JobStatus, LaunchRequest, ScriptInfo
from ..services.process_manager import process_manager

router = APIRouter(prefix="/api", tags=["launcher"])


@router.get("/scripts", response_model=list[ScriptInfo])
async def list_scripts() -> list[ScriptInfo]:
    return [
        ScriptInfo(key=k, **{kk: v[kk] for kk in ScriptInfo.model_fields if kk != "key" and kk in v})
        for k, v in ALLOWED_SCRIPTS.items()
    ]


@router.post("/launch", response_model=JobStatus)
async def launch(req: LaunchRequest) -> JobStatus:
    script_cfg = ALLOWED_SCRIPTS.get(req.script_key)
    if not script_cfg:
        raise HTTPException(404, f"Unknown script key: {req.script_key!r}")

    script_path = settings.repo_root / script_cfg["path"]
    if not script_path.exists():
        raise HTTPException(404, f"Script not found: {script_path}")

    # Build command — scripts can be .sh or .py
    if script_path.suffix == ".py":
        cmd = ["python3", str(script_path)] + script_cfg["args"] + req.extra_args
    else:
        cmd = ["bash", str(script_path)] + script_cfg["args"] + req.extra_args

    job = await process_manager.launch(
        script_key=req.script_key,
        label=script_cfg["label"],
        cmd=cmd,
        cwd=settings.repo_root,
    )
    return JobStatus(**job.as_dict())


@router.get("/jobs", response_model=list[JobStatus])
async def list_jobs() -> list[JobStatus]:
    return [JobStatus(**j) for j in process_manager.list_jobs()]


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job(job_id: str) -> JobStatus:
    job = process_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id!r} not found")
    return JobStatus(**job.as_dict())


@router.get("/jobs/{job_id}/tail")
async def get_tail(job_id: str, n: int = 200) -> dict:
    job = process_manager.get_job(job_id)
    if not job:
        raise HTTPException(404)
    return {"lines": job.tail(n)}


@router.delete("/jobs/{job_id}")
async def kill_job(job_id: str) -> dict:
    ok = await process_manager.kill(job_id)
    if not ok:
        raise HTTPException(404, f"Job {job_id!r} not found or already finished")
    return {"killed": True}


# ── WebSocket log stream ───────────────────────────────────────────────────────

@router.websocket("/ws/logs/{job_id}")
async def ws_logs(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    try:
        async for line in process_manager.subscribe(job_id):
            await websocket.send_text(line)
    except WebSocketDisconnect:
        pass
    finally:
        pass
