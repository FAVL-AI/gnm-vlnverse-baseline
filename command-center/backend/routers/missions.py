"""
Mission router.

  GET    /api/missions             — list missions (optional ?robot_id=)
  POST   /api/missions             — enqueue mission
  GET    /api/missions/{id}        — mission detail
  DELETE /api/missions/{id}        — cancel mission
  PATCH  /api/missions/{id}/status — update mission status
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.mission_manager import mission_manager

router = APIRouter(prefix="/api/missions", tags=["missions"])


class CreateMission(BaseModel):
    robot_id: str
    scene: str
    goal_description: str = ""
    priority: int = 5


class UpdateStatus(BaseModel):
    status: str
    result: dict | None = None


@router.get("")
async def list_missions(robot_id: str | None = None) -> list[dict]:
    return mission_manager.list(robot_id)


@router.post("")
async def create_mission(req: CreateMission) -> dict:
    m = mission_manager.enqueue(
        robot_id=req.robot_id,
        scene=req.scene,
        goal_description=req.goal_description,
        priority=req.priority,
    )
    return m.to_dict()


@router.get("/{mission_id}")
async def get_mission(mission_id: str) -> dict:
    m = mission_manager.get(mission_id)
    if not m:
        raise HTTPException(404)
    return m.to_dict()


@router.delete("/{mission_id}")
async def cancel_mission(mission_id: str) -> dict:
    m = mission_manager.cancel(mission_id)
    if not m:
        raise HTTPException(404)
    return m.to_dict()


@router.patch("/{mission_id}/status")
async def update_status(mission_id: str, req: UpdateStatus) -> dict:
    m = mission_manager.update_status(mission_id, req.status, req.result)
    if not m:
        raise HTTPException(404)
    return m.to_dict()
