"""
demo_supervisor.py — Live supervisor demo router.

Manages the Isaac Sim (or mock) demo process and streams real-time
telemetry to the frontend via WebSocket.

Endpoints
---------
  POST /api/demo/start            — spawn demo script
  POST /api/demo/stop             — kill demo process
  GET  /api/demo/status           — current state + last telemetry frame
  GET  /api/demo/config           — available models / scenes
  WS   /api/ws/demo               — real-time JSON telemetry stream
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..config import settings

router = APIRouter(prefix="/api/demo", tags=["demo"])

# ── Demo state ────────────────────────────────────────────────────────────────

class DemoState:
    def __init__(self) -> None:
        self.status: str = "idle"          # idle | starting | running | done | error
        self.model: str = "vint"
        self.scene: str = "hospital_corridor"
        self.fleetsafe: bool = True
        self.mock: bool = False
        self.pid: int | None = None
        self.started_at: float | None = None
        self.last_frame: dict | None = None
        self.frame_count: int = 0
        self.intervention_count: int = 0
        self.error_msg: str | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._clients: list[asyncio.Queue] = []
        self._reader_task: asyncio.Task | None = None

    def snapshot(self) -> dict:
        return {
            "status": self.status,
            "model": self.model,
            "scene": self.scene,
            "fleetsafe": self.fleetsafe,
            "mock": self.mock,
            "pid": self.pid,
            "started_at": self.started_at,
            "frame_count": self.frame_count,
            "intervention_count": self.intervention_count,
            "error_msg": self.error_msg,
            "last_frame": self.last_frame,
        }

    async def broadcast(self, msg: dict) -> None:
        dead: list[asyncio.Queue] = []
        for q in self._clients:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._clients.remove(q)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=60)
        self._clients.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._clients:
            self._clients.remove(q)


_demo = DemoState()


# ── Start / stop ──────────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    model: str = "vint"         # gnm | vint | nomad
    scene: str = "hospital_corridor"
    fleetsafe: bool = True
    mock: bool = True           # default True so demo works without Isaac
    stream: bool = False        # enable WebRTC viewport at http://localhost:49100
    seed: int = 0
    max_steps: int = 500        # 500 steps = ~125s at 4 Hz; frontend sends 2000 for Isaac
    control_hz: float = 4.0


@router.post("/start")
async def start_demo(req: StartRequest) -> dict:
    global _demo
    if _demo.status in ("starting", "running"):
        raise HTTPException(409, "Demo already running. POST /api/demo/stop first.")

    # Resolve demo script
    script = settings.repo_root / "scripts" / "demo" / "run_supervisor_demo_isaac.py"
    if not script.exists():
        raise HTTPException(500, f"Demo script not found: {script}")

    # Determine Python interpreter — prefer conda isaac env for full Isaac mode
    if req.mock:
        python = sys.executable
    else:
        conda_python = Path.home() / "miniforge3" / "envs" / "isaac" / "bin" / "python"
        python = str(conda_python) if conda_python.exists() else sys.executable

    cmd = [python, str(script),
           "--model", req.model,
           "--scene", req.scene,
           "--seed", str(req.seed),
           "--max-steps", str(req.max_steps),
           "--control-hz", str(req.control_hz)]
    if req.fleetsafe:
        cmd.append("--fleetsafe")
    else:
        cmd.append("--no-fleetsafe")
    if req.mock:
        cmd.append("--mock")
    if not req.mock:
        # No --headless → Isaac GUI window opens on desktop (default=False in script)
        if req.stream:
            cmd.append("--stream")   # WebRTC also at http://localhost:49100

    _demo.status = "starting"
    _demo.model = req.model
    _demo.scene = req.scene
    _demo.fleetsafe = req.fleetsafe
    _demo.mock = req.mock
    _demo.frame_count = 0
    _demo.intervention_count = 0
    _demo.last_frame = None
    _demo.error_msg = None
    _demo.started_at = time.time()

    env = {**os.environ, "PYTHONUNBUFFERED": "1",
           "FLEETSAFE_REPO_ROOT": str(settings.repo_root)}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(settings.repo_root),
        env=env,
        start_new_session=True,
    )
    _demo._proc = proc
    _demo.pid = proc.pid

    # Start background reader
    if _demo._reader_task and not _demo._reader_task.done():
        _demo._reader_task.cancel()
    _demo._reader_task = asyncio.create_task(_read_demo_output(proc))

    return {"started": True, "pid": proc.pid, "model": req.model, "mock": req.mock}


@router.post("/stop")
async def stop_demo() -> dict:
    global _demo
    if _demo._proc and _demo.status in ("starting", "running"):
        try:
            os.killpg(os.getpgid(_demo._proc.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
    _demo.status = "idle"
    _demo.pid = None
    await _demo.broadcast({"type": "status", "state": "STOPPED", "msg": "Demo stopped by user"})
    return {"stopped": True}


@router.get("/status")
async def demo_status() -> dict:
    return _demo.snapshot()


@router.get("/config")
async def demo_config() -> dict:
    return {
        "models": [
            {"id": "gnm",   "label": "GNM",   "description": "CNN goal-directed navigation model"},
            {"id": "vint",  "label": "ViNT",  "description": "Vision Transformer goal-directed navigation"},
            {"id": "nomad", "label": "NoMaD", "description": "Diffusion-based exploration navigation"},
        ],
        "scenes": [
            {"id": "hospital_corridor",       "label": "Hospital Corridor",       "role": "primary safety"},
            {"id": "hospital_icu_approach",   "label": "ICU Approach",            "role": "do-no-harm"},
            {"id": "hospital_elevator_lobby", "label": "Elevator Lobby",          "role": "do-no-harm"},
        ],
    }


# ── WebSocket stream ───────────────────────────────────────────────────────────

@router.websocket("/ws")
async def demo_ws(websocket: WebSocket) -> None:
    """Stream live demo telemetry to the frontend at 4 Hz."""
    await websocket.accept()
    q = _demo.subscribe()
    # Send current status immediately
    await websocket.send_json(_demo.snapshot())
    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=15.0)
                await websocket.send_json(msg)
            except asyncio.TimeoutError:
                # Heartbeat
                await websocket.send_json({"type": "ping"})
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _demo.unsubscribe(q)


# ── Internal: stdout reader ────────────────────────────────────────────────────

async def _read_demo_output(proc: asyncio.subprocess.Process) -> None:
    """Read JSON lines from demo script stdout and broadcast to WS clients."""
    global _demo

    assert proc.stdout is not None
    async for raw in proc.stdout:
        line = raw.decode(errors="replace").strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            # Forward non-JSON lines as log messages
            msg = {"type": "log", "msg": line}

        # Update internal state
        t = msg.get("type", "")
        if t == "status":
            state = msg.get("state", "")
            if state in ("STARTING", "LOADING"):
                _demo.status = "starting"
            elif state == "RUNNING":
                _demo.status = "running"
        elif t == "frame":
            _demo.status = "running"
            # If the real M3Pro is publishing its camera over ROS2, use that
            # as the camera_b64 — this is the true egocentric forward-facing
            # view that the VLN model receives as visual input on the real robot.
            try:
                from ..services.ros2_bridge import get_camera_b64, is_live
                if is_live():
                    real_cam = get_camera_b64()
                    if real_cam:
                        msg["camera_b64"] = real_cam
                        msg["camera_source"] = "real_robot"
            except Exception:
                pass
            _demo.last_frame = msg
            _demo.frame_count += 1
            if msg.get("intervened"):
                _demo.intervention_count = msg.get("intervention_count", _demo.intervention_count)
        elif t == "done":
            _demo.status = "done"
        elif t == "error":
            _demo.status = "error"
            _demo.error_msg = msg.get("msg", "Unknown error")

        await _demo.broadcast(msg)

    # Process exited
    await proc.wait()
    if _demo.status not in ("done", "error", "idle"):
        _demo.status = "done"
    await _demo.broadcast({"type": "status", "state": "DONE", "msg": "Demo process exited"})
