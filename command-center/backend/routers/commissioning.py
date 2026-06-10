"""
Commissioning router — safe-gate for live robot operations.

  GET  /api/commissioning/status          — current state + checklist
  POST /api/commissioning/connect         — enter MONITOR mode for a robot
  POST /api/commissioning/disconnect      — full reset
  POST /api/commissioning/check           — refresh checklist
  POST /api/commissioning/estop-test      — run e-stop validation cycle
  POST /api/commissioning/arm             — ARMED state (preview mode)
  POST /api/commissioning/disarm          — back to MONITOR
  POST /api/commissioning/relay/enable    — RELAY_ENABLED (commands live)
  POST /api/commissioning/relay/disable   — back to ARMED
  POST /api/commissioning/emergency-stop  — immediate DISARMED from any state
  GET  /api/commissioning/report/{id}     — download incident report for session
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ..services.commissioning import commissioning_manager
from ..services.session_recorder import session_recorder

router = APIRouter(prefix="/api/commissioning", tags=["commissioning"])


class ConnectBody(BaseModel):
    robot_id: str


class SessionBody(BaseModel):
    session_id: str


# ── State transitions ──────────────────────────────────────────────────────────

@router.get("/status")
async def get_status() -> dict:
    return commissioning_manager.get_status()


@router.post("/connect")
async def connect(req: ConnectBody) -> dict:
    return commissioning_manager.connect(req.robot_id)


@router.post("/disconnect")
async def disconnect() -> dict:
    return commissioning_manager.disconnect()


@router.post("/check")
async def run_checks() -> dict:
    return commissioning_manager.run_checks()


@router.post("/estop-test")
async def estop_test() -> dict:
    status = commissioning_manager.get_status()
    if status["state"] not in ("MONITOR", "ESTOP_VALIDATED"):
        raise HTTPException(400, "Must be in MONITOR or ESTOP_VALIDATED state")
    return commissioning_manager.run_estop_test()


@router.post("/arm")
async def arm() -> dict:
    result = commissioning_manager.arm()
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/disarm")
async def disarm() -> dict:
    return commissioning_manager.disarm()


@router.post("/relay/enable")
async def enable_relay() -> dict:
    result = commissioning_manager.enable_relay()
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/relay/disable")
async def disable_relay() -> dict:
    return commissioning_manager.disable_relay()


@router.post("/emergency-stop")
async def emergency_stop() -> dict:
    return commissioning_manager.emergency_stop()


@router.post("/session")
async def link_session(req: SessionBody) -> dict:
    commissioning_manager.set_session(req.session_id)
    return {"ok": True, "session_id": req.session_id}


# ── Incident report ────────────────────────────────────────────────────────────

@router.get("/report/{session_id}", response_class=PlainTextResponse)
async def incident_report(session_id: str) -> str:
    sessions = {s["session_id"]: s for s in session_recorder.list_sessions()}
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id!r} not found")

    trajectory = session_recorder.get_trajectory(session_id)
    events     = session_recorder.get_events(session_id)

    return _generate_report(session, trajectory, events)


def _generate_report(session: dict, trajectory: list[dict], events: list[dict]) -> str:
    sid       = session["session_id"]
    robot_id  = session.get("robot_id", "unknown")
    started   = session.get("started_at", 0)
    stopped   = session.get("stopped_at")
    n_frames  = session.get("n_frames", 0)
    n_events  = session.get("n_events", 0)

    start_dt  = datetime.fromtimestamp(started, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    dur_s     = round((stopped or time.time()) - started)
    duration  = f"{dur_s // 60}m {dur_s % 60}s" if dur_s >= 60 else f"{dur_s}s"

    # Event stats
    ev_types: dict[str, int] = {}
    min_dists: list[float] = []
    risks: list[float] = []
    for ev in events:
        t = ev.get("event_type", "unknown")
        ev_types[t] = ev_types.get(t, 0) + 1
        if ev.get("min_dist_m") is not None:
            min_dists.append(float(ev["min_dist_m"]))
        if ev.get("risk") is not None:
            risks.append(float(ev["risk"]))

    # Trajectory stats
    path_len = 0.0
    if len(trajectory) > 1:
        for i in range(1, len(trajectory)):
            dx = trajectory[i]["x"] - trajectory[i-1]["x"]
            dy = trajectory[i]["y"] - trajectory[i-1]["y"]
            path_len += math.sqrt(dx*dx + dy*dy)

    final_pos = trajectory[-1] if trajectory else None
    avg_latency = sum(p.get("latency_ms", 0) for p in trajectory) / max(len(trajectory), 1)

    # Build report
    lines = [
        "=" * 60,
        "FLEETSAFE INCIDENT REPORT",
        "=" * 60,
        f"Session ID  : {sid}",
        f"Robot ID    : {robot_id}",
        f"Date        : {start_dt}",
        f"Duration    : {duration}",
        f"Frames      : {n_frames}  ({n_frames / dur_s:.1f} Hz avg)" if dur_s > 0 else f"Frames      : {n_frames}",
        "",
        "── SAFETY SUMMARY " + "─" * 42,
        f"Total events        : {n_events}",
    ]
    for etype, count in sorted(ev_types.items()):
        lines.append(f"  {etype:<20}: {count}")

    lines += [
        f"Min distance to obstacle: {min(min_dists):.3f} m" if min_dists else "Min distance        : N/A",
        f"Max risk level      : {max(risks) * 100:.1f}%" if risks else "Max risk level      : N/A",
        "",
        "── TRAJECTORY SUMMARY " + "─" * 38,
        f"Steps recorded      : {len(trajectory)}",
        f"Path length         : {path_len:.3f} m",
        f"Avg inference lat.  : {avg_latency:.1f} ms",
    ]
    if final_pos:
        lines += [
            f"Final position      : ({final_pos['x']:.3f}, {final_pos['y']:.3f})",
            f"Final heading       : {math.degrees(final_pos.get('heading', 0)):.1f}°",
        ]

    lines += ["", "── EVENT TIMELINE " + "─" * 42]
    if not events:
        lines.append("  No events recorded.")
    else:
        for ev in sorted(events, key=lambda e: e.get("timestamp", 0)):
            ts = ev.get("timestamp", 0)
            rel = round(ts - started, 1)
            dt  = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M:%S")
            etype = ev.get("event_type", "?")
            zone  = ev.get("zone", "?")
            risk  = ev.get("risk", 0)
            dist  = ev.get("min_dist_m")
            dist_str = f" | dist {dist:.3f}m" if dist is not None else ""
            lines.append(
                f"  [{dt}] +{rel:>6.1f}s  {etype:<20} zone={zone} risk={risk*100:.0f}%{dist_str}"
            )

    lines += [
        "",
        "── GENERATED BY " + "─" * 44,
        "FleetSafe Command Center v0.5",
        f"Report time: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "=" * 60,
    ]

    return "\n".join(lines)
