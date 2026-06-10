"""
Robot console — allowlisted command palette.
POST /api/robot/console/exec  { "command": "<name>" }
GET  /api/robot/console/commands  — list available commands
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..services.robot_ops import robot_ops, _ssh_argv, _ssh_env
from ..services.watchdog import watchdog

router = APIRouter(prefix="/api/robot/console", tags=["robot-console"])

# ── Models ────────────────────────────────────────────────────────────────────

class ExecRequest(BaseModel):
    command: str


class ExecResult(BaseModel):
    command: str
    output: str
    ok: bool
    dry_run: bool = False
    timestamp: str  # ISO


# ── Command map ───────────────────────────────────────────────────────────────

# Shell commands executed via SSH on the robot.
# None means the command is delegated to a service method (handled specially).
COMMAND_MAP: dict[str, str | None] = {
    "start_perception": (
        "nohup ros2 launch fleetsafe_perception perception.launch.py "
        "> /tmp/fs_perception.log 2>&1 &"
    ),
    "stop_perception":  "pkill -f perception.launch || true",
    "start_rosbag": (
        "nohup ros2 bag record -a -o /tmp/fs_$(date +%s) "
        "> /tmp/fs_rosbag.log 2>&1 &"
    ),
    "stop_rosbag":      "pkill -f ros2_bag || true",
    # Delegated commands — handled in exec endpoint
    "run_preflight":    None,
    "arm_watchdog":     None,
    "disarm_watchdog":  None,
    # Pure ROS2 / shell calls via SSH
    "pulse_forward": (
        'ros2 topic pub --once /cmd_vel_raw geometry_msgs/Twist "{linear: {x: 0.1}}"'
    ),
    "zero_velocity": (
        'ros2 topic pub --once /cmd_vel_raw geometry_msgs/Twist "{}"'
    ),
    "show_topics":  "ros2 topic list",
    "show_nodes":   "ros2 node list",
    "tail_logs":    "journalctl -n 50 --no-pager -u fleetsafe",
}

_SSH_COMMANDS = frozenset([
    "start_perception", "stop_perception",
    "start_rosbag", "stop_rosbag",
    "pulse_forward", "zero_velocity",
    "show_topics", "show_nodes", "tail_logs",
])

_DELEGATE_COMMANDS = frozenset([
    "run_preflight", "arm_watchdog", "disarm_watchdog",
])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/commands")
async def list_commands() -> list[str]:
    """Return the list of available allowlisted command names."""
    return list(COMMAND_MAP.keys())


@router.post("/exec", response_model=ExecResult)
async def exec_command(body: ExecRequest) -> ExecResult:
    """Execute an allowlisted robot command by name."""
    name = body.command
    if name not in COMMAND_MAP:
        raise HTTPException(400, f"Unknown command '{name}'. Available: {list(COMMAND_MAP.keys())}")

    dry_run = settings.robot_dry_run

    # ── Delegated commands ────────────────────────────────────────────────────
    if name in _DELEGATE_COMMANDS:
        if dry_run:
            return ExecResult(
                command=name,
                output=f"[DRY RUN] would delegate: {name}",
                ok=True,
                dry_run=True,
                timestamp=_now_iso(),
            )
        if name == "run_preflight":
            result = await robot_ops.preflight()
            return ExecResult(
                command=name,
                output=json.dumps(result, indent=2),
                ok=result.get("pass", False),
                dry_run=False,
                timestamp=_now_iso(),
            )
        if name == "arm_watchdog":
            watchdog.start()
            return ExecResult(
                command=name,
                output=json.dumps({"running": True}),
                ok=True,
                dry_run=False,
                timestamp=_now_iso(),
            )
        if name == "disarm_watchdog":
            watchdog.stop()
            return ExecResult(
                command=name,
                output=json.dumps({"running": False}),
                ok=True,
                dry_run=False,
                timestamp=_now_iso(),
            )

    # ── SSH commands ──────────────────────────────────────────────────────────
    cmd = COMMAND_MAP[name]
    assert cmd is not None  # guaranteed by _SSH_COMMANDS membership

    if dry_run:
        return ExecResult(
            command=name,
            output=f"[DRY RUN] would run: {cmd}",
            ok=True,
            dry_run=True,
            timestamp=_now_iso(),
        )

    import asyncio

    argv = _ssh_argv(settings.robot_ssh, timeout=15.0)
    proc = await asyncio.create_subprocess_exec(
        *argv, cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_ssh_env(),
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=17.0)
    except asyncio.TimeoutError:
        proc.kill()
        return ExecResult(
            command=name,
            output="SSH timeout",
            ok=False,
            dry_run=False,
            timestamp=_now_iso(),
        )

    stdout = stdout_b.decode().strip()
    stderr = stderr_b.decode().strip()
    rc = proc.returncode

    if rc == 0:
        return ExecResult(
            command=name,
            output=stdout or "(no output)",
            ok=True,
            dry_run=False,
            timestamp=_now_iso(),
        )
    return ExecResult(
        command=name,
        output=stderr or stdout or f"rc={rc}",
        ok=False,
        dry_run=False,
        timestamp=_now_iso(),
    )
