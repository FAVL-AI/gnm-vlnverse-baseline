"""
Robot operator controls router.

All mutating endpoints require relay_guard to have been checked (stateless —
caller must pass the guard on the frontend or call /relay-guard first).

REST:
  GET  /api/robot/status           — dry_run flag + connection info
  POST /api/robot/dry-run          — toggle dry_run (body: {enabled: bool})
  GET  /api/robot/relay-guard      — run relay safety checks
  GET  /api/robot/graph            — ros2 node/topic list
  GET  /api/robot/audit            — recent audit log

  POST /api/robot/start-agent      — start micro-ROS agent
  POST /api/robot/start-fleetsafe  — start fleetsafe perception node
  POST /api/robot/stop-fleetsafe   — kill fleetsafe perception node
  POST /api/robot/stop-conflicting — kill joy/teleop publishers
  POST /api/robot/relay/start      — ros2 param set relay_enabled true
  POST /api/robot/relay/stop       — ros2 param set relay_enabled false

  POST /api/robot/zero             — publish zero twist
  POST /api/robot/pulse            — body: {vx,vy,wz,duration_ms}

  GET  /api/robot/voice-map        — voice command → op mapping
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.robot_ops import robot_ops, VOICE_MAP
from ..services.safety_latch import safety_latch
from ..services.relay_manager import relay_manager

router = APIRouter(prefix="/api/robot", tags=["robot"])


# ── Status / config ──────────────────────────────────────────────────────────

@router.get("/status")
async def get_status() -> dict:
    from ..config import settings
    return {
        "host": settings.robot_ssh,
        "dry_run": robot_ops.dry_run,
        "estop_latched": safety_latch.is_latched,
        "relay_active": relay_manager.is_active,
    }


class DryRunBody(BaseModel):
    enabled: bool


@router.post("/dry-run")
async def set_dry_run(body: DryRunBody) -> dict:
    robot_ops.set_dry_run(body.enabled)
    return {"dry_run": robot_ops.dry_run}


# ── Safety checks ────────────────────────────────────────────────────────────

@router.get("/relay-guard")
async def relay_guard() -> dict:
    return await robot_ops.relay_guard_check()


@router.get("/graph")
async def graph() -> dict:
    return await robot_ops.verify_graph()


@router.get("/audit")
async def audit_log(n: int = 100) -> list[dict]:
    return robot_ops.get_audit_log(n)


# ── Node control ─────────────────────────────────────────────────────────────

@router.post("/start-agent")
async def start_agent() -> dict:
    return await robot_ops.start_agent()


@router.post("/start-fleetsafe")
async def start_fleetsafe() -> dict:
    return await robot_ops.start_fleetsafe()


@router.post("/stop-fleetsafe")
async def stop_fleetsafe() -> dict:
    return await robot_ops.stop_fleetsafe()


@router.post("/stop-conflicting")
async def stop_conflicting() -> dict:
    return await robot_ops.stop_conflicting()


# ── Relay (now gated through relay_manager) ───────────────────────────────────

@router.post("/relay/start")
async def relay_start() -> dict:
    return await relay_manager.start()


@router.post("/relay/stop")
async def relay_stop() -> dict:
    return await relay_manager.stop("manual")


# ── Motion ───────────────────────────────────────────────────────────────────

@router.post("/zero")
async def zero() -> dict:
    return await robot_ops.zero()


class PulseBody(BaseModel):
    vx: float = 0.0
    vy: float = 0.0
    wz: float = 0.0
    duration_ms: int = 300


@router.post("/pulse")
async def pulse(body: PulseBody) -> dict:
    return await robot_ops.pulse(body.vx, body.vy, body.wz, body.duration_ms)


# Convenience pulse endpoints (keyboard shortcuts)
@router.post("/pulse/forward")
async def pulse_forward() -> dict:
    return await robot_ops.pulse(vx=0.1, duration_ms=400)


@router.post("/pulse/back")
async def pulse_back() -> dict:
    return await robot_ops.pulse(vx=-0.1, duration_ms=400)


@router.post("/pulse/left")
async def pulse_left() -> dict:
    return await robot_ops.pulse(wz=0.3, duration_ms=400)


@router.post("/pulse/right")
async def pulse_right() -> dict:
    return await robot_ops.pulse(wz=-0.3, duration_ms=400)


# ── Voice ────────────────────────────────────────────────────────────────────

@router.get("/voice-map")
async def voice_map() -> dict:
    return {"map": VOICE_MAP}
