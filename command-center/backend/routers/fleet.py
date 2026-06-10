"""
Fleet operations router.

REST:
  GET  /api/fleet/robots          — list all robots
  GET  /api/fleet/robots/{id}     — robot detail
  POST /api/fleet/robots          — manually register
  DEL  /api/fleet/robots/{id}     — deregister

WebSocket:
  WS   /api/fleet/ws              — 5 Hz fleet snapshot
"""
from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..services.robot_registry import robot_registry, start_mock_fleet
from ..services import ros2_bridge

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


def _boot() -> None:
    ros2_bridge.start()
    start_mock_fleet()


@router.get("/robots")
async def list_robots() -> list[dict]:
    _boot()
    return robot_registry.all()


@router.get("/robots/{robot_id}")
async def get_robot(robot_id: str) -> dict:
    r = robot_registry.get(robot_id)
    if not r:
        raise HTTPException(404, f"Robot {robot_id!r} not found")
    return r.to_dict()


class RegisterBody(BaseModel):
    robot_id: str
    name: str
    robot_type: str = "unknown"


@router.post("/robots")
async def register_robot(req: RegisterBody) -> dict:
    r = robot_registry.register(req.robot_id, req.name, req.robot_type, source="manual")
    return r.to_dict()


@router.delete("/robots/{robot_id}")
async def deregister_robot(robot_id: str) -> dict:
    if not robot_registry.deregister(robot_id):
        raise HTTPException(404)
    return {"deregistered": robot_id}


@router.websocket("/ws")
async def fleet_ws(websocket: WebSocket) -> None:
    _boot()
    await websocket.accept()
    try:
        while True:
            payload = {
                "robots":    robot_registry.all(),
                "estopped":  [],
                "timestamp": time.time(),
            }
            try:
                from ..services.safety_supervisor import safety_supervisor
                payload["estopped"] = safety_supervisor.estopped_robots()
            except Exception:
                pass
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        pass
    finally:
        pass
