"""
Safety router.

REST:
  GET  /api/safety/events          — recent safety events
  GET  /api/safety/estop           — estopped robots list
  POST /api/safety/estop/{id}      — e-stop robot
  POST /api/safety/estop/all       — e-stop all robots
  POST /api/safety/clear/{id}      — clear e-stop

WebSocket:
  WS   /api/safety/ws              — live event stream (history + new events)
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.safety_supervisor import safety_supervisor

router = APIRouter(prefix="/api/safety", tags=["safety"])


@router.get("/events")
async def get_events(n: int = 100) -> list[dict]:
    return safety_supervisor.get_history(n)


@router.get("/estop")
async def get_estopped() -> dict:
    return {"estopped": safety_supervisor.estopped_robots()}


@router.post("/estop/{robot_id}")
async def estop_robot(robot_id: str) -> dict:
    ev = safety_supervisor.estop(robot_id)
    return {"robot_id": robot_id, "event": ev}


@router.post("/estop/all")
async def estop_all() -> dict:
    ids = safety_supervisor.estop_all()
    return {"estopped": ids}


@router.post("/clear/{robot_id}")
async def clear_estop(robot_id: str) -> dict:
    safety_supervisor.clear_estop(robot_id)
    return {"robot_id": robot_id, "cleared": True}


@router.websocket("/ws")
async def safety_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        # Send history on connect
        await websocket.send_text(json.dumps({
            "type": "history",
            "events": safety_supervisor.get_history(100),
        }))
        last_version = safety_supervisor.get_version()

        while True:
            await asyncio.sleep(0.2)
            v, new_events = safety_supervisor.get_since(last_version)
            if new_events:
                for ev in new_events:
                    await websocket.send_text(json.dumps({"type": "event", "event": ev}))
            last_version = v
    except WebSocketDisconnect:
        pass
    finally:
        pass
