"""
v0.7 Safety Supervisor REST endpoints.

  GET  /api/robot/estop/status         — latch state
  POST /api/robot/estop                — latch e-stop
  POST /api/robot/estop/clear          — clear latch (body: {operator})

  GET  /api/robot/relay/status         — relay manager state
  POST /api/robot/relay/managed-start  — safe relay start (latch-gated)
  POST /api/robot/relay/managed-stop   — safe relay stop (zero enforced)

  GET  /api/robot/watchdog/status      — watchdog health
  POST /api/robot/watchdog/start       — arm watchdog
  POST /api/robot/watchdog/stop        — disarm watchdog

  POST /api/robot/demo/start           — begin demo sequence
  POST /api/robot/demo/abort           — abort demo in progress
  GET  /api/robot/demo/status          — demo state machine

  POST /api/robot/session/start        — start ros2 bag on robot
  POST /api/robot/session/stop/{id}    — stop ros2 bag
  GET  /api/robot/session/list         — list real robot sessions
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.safety_latch import safety_latch
from ..services.relay_manager import relay_manager
from ..services.watchdog import watchdog
from ..services.demo_orchestrator import demo_orchestrator
from ..services.real_session import real_session_recorder
from ..services.yolo_switch import yolo_switch
from ..services.robot_ops import robot_ops

router = APIRouter(prefix="/api/robot", tags=["robot-safety"])


# ── Safe motion preflight ─────────────────────────────────────────────────────

@router.get("/preflight")
async def preflight() -> dict:
    """
    Inspect /cmd_vel publishers and run safe-graph checks before any motion test.
    Returns pass=True only when no blocked publishers are found.
    """
    return await robot_ops.preflight()


class StopLaunchSourceBody(BaseModel):
    node_name: str


@router.post("/preflight/kill")
async def kill_launch_source(body: StopLaunchSourceBody) -> dict:
    """Kill the exact launch source of a named blocked node."""
    return await robot_ops.stop_launch_source(body.node_name)


# ── E-stop latch ──────────────────────────────────────────────────────────────

@router.get("/estop/status")
async def estop_status() -> dict:
    return safety_latch.get_status()


@router.post("/estop")
async def estop_latch(reason: str = "manual") -> dict:
    return safety_latch.latch(reason)


class ClearBody(BaseModel):
    operator: str = "operator"


@router.post("/estop/clear")
async def estop_clear(body: ClearBody) -> dict:
    return safety_latch.clear(body.operator)


# ── Managed relay ─────────────────────────────────────────────────────────────

@router.get("/relay/status")
async def relay_status() -> dict:
    return relay_manager.get_status()


@router.post("/relay/managed-start")
async def relay_managed_start() -> dict:
    return await relay_manager.start()


@router.post("/relay/managed-stop")
async def relay_managed_stop(reason: str = "manual") -> dict:
    return await relay_manager.stop(reason)


# ── Watchdog ──────────────────────────────────────────────────────────────────

@router.get("/watchdog/status")
async def watchdog_status() -> dict:
    return watchdog.get_status()


@router.post("/watchdog/start")
async def watchdog_start() -> dict:
    watchdog.start()
    return {"running": True}


@router.post("/watchdog/stop")
async def watchdog_stop() -> dict:
    watchdog.stop()
    return {"running": False}


# ── Demo mode ─────────────────────────────────────────────────────────────────

@router.post("/demo/start")
async def demo_start() -> dict:
    return await demo_orchestrator.start()


@router.post("/demo/abort")
async def demo_abort() -> dict:
    return await demo_orchestrator.abort()


@router.get("/demo/status")
async def demo_status() -> dict:
    return demo_orchestrator.get_status()


# ── Real robot session recorder ───────────────────────────────────────────────

class SessionStartBody(BaseModel):
    robot_id: str


@router.post("/session/start")
async def session_start(body: SessionStartBody) -> dict:
    return await real_session_recorder.start(body.robot_id)


@router.post("/session/stop/{session_id}")
async def session_stop(session_id: str) -> dict:
    return await real_session_recorder.stop(session_id)


@router.get("/session/list")
async def session_list() -> list[dict]:
    return real_session_recorder.list_sessions()


# ── YOLO mode switch ──────────────────────────────────────────────────────────

@router.get("/yolo/status")
async def yolo_status() -> dict:
    return yolo_switch.get_status()


@router.post("/yolo/start")
async def yolo_start() -> dict:
    return await yolo_switch.start()


@router.post("/yolo/stop")
async def yolo_stop() -> dict:
    return await yolo_switch.stop()


# ── ROS Graph state ───────────────────────────────────────────────────────────

class NodeState(BaseModel):
    id: str
    label: str
    state: Literal["ok", "warn", "err", "unknown"]


class EdgeState(BaseModel):
    id: str
    from_node: str
    to_node: str
    topic: str
    state: Literal["flowing", "blocked", "unknown"]
    hz: float | None = None


class RosGraphState(BaseModel):
    overall: Literal["GREEN", "YELLOW", "RED", "ESTOP"]
    nodes: list[NodeState]
    edges: list[EdgeState]
    intervention_active: bool
    estop_latched: bool
    relay_open: bool
    watchdog_armed: bool
    unsafe_publisher: str | None


@router.get("/ros-graph", response_model=RosGraphState)
async def ros_graph() -> RosGraphState:
    """
    Return CBF-QP safety pipeline node/edge states derived from live service state.
    """
    latch_status = safety_latch.get_status()
    relay_status = relay_manager.get_status()
    wd_status    = watchdog.get_status()

    estop_latched = bool(latch_status.get("latched", False))
    relay_open    = bool(relay_status.get("active", False))
    wd_armed      = bool(wd_status.get("running", False))
    unsafe_pub    = wd_status.get("unsafe_publisher_detail") or None
    intervention_active = (
        wd_status.get("unsafe_publisher_status") == "UNSAFE_CMDVEL_PUBLISHER"
    )

    # ── Overall state ─────────────────────────────────────────────────────────
    if estop_latched:
        overall: Literal["GREEN", "YELLOW", "RED", "ESTOP"] = "ESTOP"
    elif intervention_active:
        overall = "YELLOW"
    elif not relay_open:
        overall = "RED"
    else:
        overall = "GREEN"

    # ── Node states ───────────────────────────────────────────────────────────
    if estop_latched:
        perception_state: Literal["ok", "warn", "err", "unknown"] = "err"
        relay_state:      Literal["ok", "warn", "err", "unknown"] = "err"
    elif intervention_active:
        perception_state = "warn"
        relay_state      = "ok" if relay_open else "err"
    elif relay_open:
        perception_state = "ok"
        relay_state      = "ok"
    else:
        perception_state = "ok" if wd_armed else "unknown"
        relay_state      = "err"

    nodes = [
        NodeState(id="fleetsafe_perception", label="fleetsafe_perception", state=perception_state),
        NodeState(id="relay",                label="relay",                state=relay_state),
    ]

    # ── Edge states ───────────────────────────────────────────────────────────
    if estop_latched:
        e_raw   = "blocked"
        e_safe  = "blocked"
        e_final = "blocked"
    elif relay_open and not intervention_active:
        e_raw   = "flowing"
        e_safe  = "flowing"
        e_final = "flowing"
    elif relay_open and intervention_active:
        e_raw   = "flowing"
        e_safe  = "flowing"   # CBF-QP modifies but still passes
        e_final = "flowing"
    else:
        e_raw   = "unknown"
        e_safe  = "unknown"
        e_final = "blocked"

    edges = [
        EdgeState(id="e_raw",   from_node="joy",                 to_node="fleetsafe_perception", topic="/cmd_vel_raw",  state=e_raw),   # type: ignore[arg-type]
        EdgeState(id="e_safe",  from_node="fleetsafe_perception", to_node="relay",               topic="/cmd_vel_safe", state=e_safe),  # type: ignore[arg-type]
        EdgeState(id="e_final", from_node="relay",               to_node="robot",               topic="/cmd_vel",      state=e_final), # type: ignore[arg-type]
    ]

    return RosGraphState(
        overall=overall,
        nodes=nodes,
        edges=edges,
        intervention_active=intervention_active,
        estop_latched=estop_latched,
        relay_open=relay_open,
        watchdog_armed=wd_armed,
        unsafe_publisher=unsafe_pub if unsafe_pub else None,
    )
