"""
Session recorder router.

  GET  /api/sessions                        — list sessions
  POST /api/sessions/start                  — start recording for robot
  POST /api/sessions/{id}/stop              — stop recording
  GET  /api/sessions/{id}                   — session metadata
  GET  /api/sessions/{id}/trajectory        — odom trajectory (replay-compatible)
  GET  /api/sessions/{id}/events            — recorded safety events
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.session_recorder import session_recorder

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class StartRecording(BaseModel):
    robot_id: str


@router.get("")
async def list_sessions() -> list[dict]:
    return session_recorder.list_sessions()


@router.post("/start")
async def start_session(req: StartRecording) -> dict:
    session = session_recorder.start(req.robot_id)
    return session.to_dict()


@router.post("/{session_id}/stop")
async def stop_session(session_id: str) -> dict:
    session = session_recorder.stop(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id!r} not found or already stopped")
    return session.to_dict()


@router.get("/{session_id}")
async def get_session(session_id: str) -> dict:
    sessions = {s["session_id"]: s for s in session_recorder.list_sessions()}
    if session_id not in sessions:
        raise HTTPException(404)
    return sessions[session_id]


@router.get("/{session_id}/trajectory")
async def session_trajectory(session_id: str) -> list[dict]:
    return session_recorder.get_trajectory(session_id)


@router.get("/{session_id}/events")
async def session_events(session_id: str) -> list[dict]:
    return session_recorder.get_events(session_id)


@router.get("/{session_id}/recording-status")
async def recording_status(session_id: str) -> dict:
    sessions = {s["session_id"]: s for s in session_recorder.list_sessions()}
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(404)
    return {
        "session_id": session_id,
        "is_active":  s.get("is_active", False),
        "n_frames":   s.get("n_frames", 0),
        "n_events":   s.get("n_events", 0),
    }
