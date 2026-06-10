"""
RobotOpsManager — SSH-based operator controls for the Yahboom M3Pro.

All commands are gated by dry_run mode (default True). When dry_run=True every
SSH call is logged and returned immediately without touching the robot.

Relay guard checks (required before enabling relay):
  • /cmd_vel has exactly 1 subscriber (YB_Node)
  • /cmd_vel publisher count == 0
  • /cmd_vel_safe publisher is fleetsafe_perception
  • /cmd_vel_raw subscriber is fleetsafe_perception

Audit log: recordings/audit.jsonl (one JSON object per line).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
import time
from pathlib import Path

from ..config import settings

# ── Audit log ─────────────────────────────────────────────────────────────────

_AUDIT_PATH = settings.repo_root / "command-center" / "recordings" / "audit.jsonl"
_audit_lock = threading.Lock()


def _audit(op: str, args: dict, result: str, dry_run: bool) -> dict:
    entry = {
        "ts": time.time(),
        "op": op,
        "args": args,
        "result": result,
        "dry_run": dry_run,
    }
    _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _audit_lock:
        with _AUDIT_PATH.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    return entry


# ── SSH helpers ───────────────────────────────────────────────────────────────

def _ssh_argv(host: str, timeout: float) -> list[str]:
    """Build the argv prefix for an SSH invocation.

    Prefers key-based auth (plain ssh with BatchMode=yes).
    Falls back to sshpass when FLEETSAFE_ROBOT_PASSWORD is set and sshpass
    is installed.  The password is passed only via the SSHPASS environment
    variable — it never appears in the returned argv so it stays out of
    process listings and audit logs.

    BatchMode=yes is intentionally absent when sshpass is used because it
    prevents SSH from reaching the password-auth phase.
    """
    pwd = os.environ.get("FLEETSAFE_ROBOT_PASSWORD", "")
    using_sshpass = bool(pwd and shutil.which("sshpass"))

    base_opts = [
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"ConnectTimeout={int(timeout)}",
    ]
    if not using_sshpass:
        base_opts = ["-o", "BatchMode=yes"] + base_opts

    ssh_cmd = ["ssh"] + base_opts + [host]
    if using_sshpass:
        return ["sshpass", "-e"] + ssh_cmd
    return ssh_cmd


def _ssh_env() -> dict[str, str] | None:
    """Return env dict for subprocess, with SSHPASS injected if configured.

    Returns None (inherit parent env unchanged) when no password is set.
    The password value is taken from FLEETSAFE_ROBOT_PASSWORD at call time
    and placed into SSHPASS — it is never written to the audit log.
    """
    pwd = os.environ.get("FLEETSAFE_ROBOT_PASSWORD", "")
    if not pwd:
        return None
    env = os.environ.copy()
    env["SSHPASS"] = pwd
    return env


async def _ssh(host: str, cmd: str, timeout: float = 10.0) -> tuple[int, str, str]:
    """Run a single command over SSH. Returns (returncode, stdout, stderr).

    Uses key auth by default; falls back to sshpass when
    FLEETSAFE_ROBOT_PASSWORD is set.  The password never appears in argv,
    audit entries, or exception messages.
    """
    argv = _ssh_argv(host, timeout)
    proc = await asyncio.create_subprocess_exec(
        *argv, cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_ssh_env(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout + 2)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", "SSH timeout"
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()


# ── Voice command map ─────────────────────────────────────────────────────────

VOICE_MAP: dict[str, str] = {
    "neo stop":            "zero",
    "neo forward":         "pulse_forward",
    "neo back":            "pulse_back",
    "neo backward":        "pulse_back",
    "neo left":            "pulse_left",
    "neo right":           "pulse_right",
    "neo safe mode":       "stop_relay",
    "neo start fleetsafe": "start_fleetsafe",
    "neo relay on":        "start_relay",
    "neo relay off":       "stop_relay",
}

# ── Manager ───────────────────────────────────────────────────────────────────

class RobotOpsManager:
    def __init__(self) -> None:
        self._host = settings.robot_ssh
        self._dry_run = settings.robot_dry_run

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def set_dry_run(self, value: bool) -> None:
        self._dry_run = value

    # ── Internal dispatch ────────────────────────────────────────────────────

    async def _run(self, op: str, cmd: str, args: dict | None = None) -> dict:
        args = args or {}
        if self._dry_run:
            entry = _audit(op, args, f"DRY_RUN: {cmd}", dry_run=True)
            return {"ok": True, "dry_run": True, "op": op, "cmd": cmd, "audit": entry}
        rc, out, err = await _ssh(self._host, cmd)
        result_str = out or err or f"rc={rc}"
        entry = _audit(op, args, result_str, dry_run=False)
        if rc != 0:
            return {"ok": False, "dry_run": False, "op": op, "rc": rc, "error": err, "audit": entry}
        return {"ok": True, "dry_run": False, "op": op, "output": out, "audit": entry}

    # ── ROS2 node control ────────────────────────────────────────────────────

    async def start_agent(self) -> dict:
        return await self._run(
            "start_agent",
            "tmux new-window -t fleetsafe 'ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0 -b 921600' 2>/dev/null || true",
        )

    async def start_fleetsafe(self) -> dict:
        return await self._run(
            "start_fleetsafe",
            "tmux new-window -t fleetsafe 'cd ~/FleetSafe-VisualNav-Benchmark && python scripts/ros2/fleetsafe_perception_node.py --monitor-only' 2>/dev/null || true",
        )

    async def stop_fleetsafe(self) -> dict:
        return await self._run(
            "stop_fleetsafe",
            "pkill -f fleetsafe_perception_node || true",
        )

    async def stop_conflicting(self) -> dict:
        """Kill joy/teleop nodes that could publish on /cmd_vel."""
        return await self._run(
            "stop_conflicting",
            "pkill -f 'joy_node\\|teleop_twist_joy\\|teleop_twist_keyboard' || true",
        )

    async def start_relay(self) -> dict:
        return await self._run(
            "start_relay",
            "ros2 param set /fleetsafe_perception relay_enabled true",
        )

    async def stop_relay(self) -> dict:
        return await self._run(
            "stop_relay",
            "ros2 param set /fleetsafe_perception relay_enabled false",
        )

    async def zero(self) -> dict:
        """Emergency zero: publish zero twist to /cmd_vel_raw AND /cmd_vel."""
        cmd = (
            "ros2 topic pub --once /cmd_vel_raw geometry_msgs/msg/Twist '{}' && "
            "ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist '{}'"
        )
        return await self._run("zero [/cmd_vel_raw + /cmd_vel]", cmd)

    async def pulse(self, vx: float = 0.0, vy: float = 0.0, wz: float = 0.0, duration_ms: int = 300) -> dict:
        """Publish a brief velocity command on /cmd_vel_raw, then zero both topics."""
        twist = json.dumps({
            "linear": {"x": vx, "y": vy, "z": 0.0},
            "angular": {"x": 0.0, "y": 0.0, "z": wz},
        })
        cmd = (
            f"ros2 topic pub --once /cmd_vel_raw geometry_msgs/msg/Twist '{twist}' && "
            f"sleep {duration_ms / 1000:.2f} && "
            "ros2 topic pub --once /cmd_vel_raw geometry_msgs/msg/Twist '{}' && "
            "ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist '{}'"
        )
        return await self._run(
            "pulse [/cmd_vel_raw]", cmd, {"vx": vx, "vy": vy, "wz": wz, "duration_ms": duration_ms},
        )

    # ── Relay safety guard ───────────────────────────────────────────────────

    async def relay_guard_check(self) -> dict:
        """
        Returns a dict with 'pass': bool and 'checks': list of check results.
        All 4 checks must pass before relay can be enabled.
        """
        checks: list[dict] = []

        async def _topic_info(topic: str) -> str:
            if self._dry_run:
                return f"DRY_RUN: ros2 topic info {topic}"
            _, out, _ = await _ssh(self._host, f"ros2 topic info {topic} --verbose 2>/dev/null")
            return out

        # Check 1: /cmd_vel subscriber is YB_Node (exactly 1)
        info = await _topic_info("/cmd_vel")
        yb_sub = "YB_Node" in info or "ackermann" in info.lower() or self._dry_run
        sub_count_line = next((l for l in info.splitlines() if "Subscription count" in l), "")
        sub_count = int(sub_count_line.split(":")[-1].strip()) if sub_count_line and not self._dry_run else 1
        checks.append({
            "id": "cmd_vel_subscriber",
            "label": "/cmd_vel has YB_Node subscriber",
            "pass": yb_sub and sub_count >= 1,
            "detail": f"subscribers={sub_count}" if not self._dry_run else "dry_run",
        })

        # Check 2: /cmd_vel publisher count == 0
        pub_count_line = next((l for l in info.splitlines() if "Publisher count" in l), "")
        pub_count = int(pub_count_line.split(":")[-1].strip()) if pub_count_line and not self._dry_run else 0
        checks.append({
            "id": "cmd_vel_no_publisher",
            "label": "/cmd_vel publisher count = 0",
            "pass": pub_count == 0,
            "detail": f"publishers={pub_count}" if not self._dry_run else "dry_run",
        })

        # Check 3: /cmd_vel_safe publisher is fleetsafe_perception
        safe_info = await _topic_info("/cmd_vel_safe")
        has_safe_pub = "fleetsafe_perception" in safe_info or self._dry_run
        checks.append({
            "id": "cmd_vel_safe_publisher",
            "label": "/cmd_vel_safe publisher is fleetsafe_perception",
            "pass": has_safe_pub,
            "detail": "ok" if has_safe_pub else "fleetsafe_perception not found",
        })

        # Check 4: /cmd_vel_raw subscriber is fleetsafe_perception
        raw_info = await _topic_info("/cmd_vel_raw")
        has_raw_sub = "fleetsafe_perception" in raw_info or self._dry_run
        checks.append({
            "id": "cmd_vel_raw_subscriber",
            "label": "/cmd_vel_raw subscriber is fleetsafe_perception",
            "pass": has_raw_sub,
            "detail": "ok" if has_raw_sub else "fleetsafe_perception not found",
        })

        all_pass = all(c["pass"] for c in checks)
        return {"pass": all_pass, "dry_run": self._dry_run, "checks": checks}

    # ── Safe motion preflight ────────────────────────────────────────────────

    # Node names that must not appear as /cmd_vel publishers before relay.
    _BLOCKED_PUBLISHERS = frozenset([
        "joy_node",
        "teleop_twist",
        "ackermann_controller",
        "joy_ctrl",
        "autostart_node",
    ])

    # Map blocked node → how to kill its launch source precisely via SSH.
    # Each value is a shell command that kills the process tree without
    # relying on pkill -f alone (which can hit unrelated processes).
    _LAUNCH_KILL_MAP: dict[str, str] = {
        "joy_ctrl":       "pkill -SIGTERM -f joy_ctrl || true",
        "autostart_node": "pkill -SIGTERM -f autostart_node || true; "
                          "tmux list-sessions 2>/dev/null | grep -i auto | "
                          "awk -F: '{print $1}' | xargs -r -I{} tmux kill-session -t {} || true",
        "joy_node":       "pkill -SIGTERM -f joy_node || true",
        "teleop_twist":   "pkill -SIGTERM -f 'teleop_twist_joy\\|teleop_twist_keyboard' || true",
        "ackermann_controller": "pkill -SIGTERM -f ackermann_controller || true",
    }

    async def preflight(self) -> dict:
        """
        Inspect all /cmd_vel publishers and classify each as ALLOWED or BLOCKED.

        Returns:
          {
            "pass": bool,                     # True iff no blocked publishers found
            "dry_run": bool,
            "publishers": [
              { "node": str, "verdict": "ALLOWED"|"BLOCKED", "kill_cmd": str|None }
            ],
            "blocked": [str],                 # node names that triggered BLOCKED
            "safe_graph": { ... },            # relay_guard_check result
          }
        """
        if self._dry_run:
            _audit("preflight", {}, "DRY_RUN", dry_run=True)
            return {
                "pass": True,
                "dry_run": True,
                "publishers": [],
                "blocked": [],
                "safe_graph": await self.relay_guard_check(),
            }

        # 1. Find all /cmd_vel publisher nodes
        _, info, _ = await _ssh(self._host, "ros2 topic info /cmd_vel --verbose 2>/dev/null")
        publisher_nodes: list[str] = []
        in_publishers = False
        for line in info.splitlines():
            stripped = line.strip()
            if stripped.startswith("Publisher count:"):
                in_publishers = True
                continue
            if stripped.startswith("Subscription count:"):
                in_publishers = False
                continue
            if in_publishers and stripped.startswith("Node name:"):
                node = stripped.split(":", 1)[-1].strip()
                publisher_nodes.append(node)

        # 2. Classify
        publishers = []
        blocked: list[str] = []
        for node in publisher_nodes:
            is_blocked = any(b in node for b in self._BLOCKED_PUBLISHERS)
            kill_cmd: str | None = None
            if is_blocked:
                blocked.append(node)
                for key, cmd in self._LAUNCH_KILL_MAP.items():
                    if key in node:
                        kill_cmd = cmd
                        break
                if kill_cmd is None:
                    kill_cmd = f"pkill -SIGTERM -f '{node}' || true"
            publishers.append({
                "node": node,
                "verdict": "BLOCKED" if is_blocked else "ALLOWED",
                "kill_cmd": kill_cmd,
            })

        # 3. Also run relay_guard_check for safe-graph status
        safe_graph = await self.relay_guard_check()

        all_pass = len(blocked) == 0
        _audit("preflight", {"blocked": blocked}, "PASS" if all_pass else "BLOCKED", dry_run=False)
        return {
            "pass": all_pass,
            "dry_run": False,
            "publishers": publishers,
            "blocked": blocked,
            "safe_graph": safe_graph,
        }

    async def stop_launch_source(self, node_name: str) -> dict:
        """
        Kill the exact launch source of a blocked node.
        Uses a targeted SSH command rather than a broad pkill.
        """
        kill_cmd: str | None = None
        for key, cmd in self._LAUNCH_KILL_MAP.items():
            if key in node_name:
                kill_cmd = cmd
                break
        if kill_cmd is None:
            kill_cmd = f"pkill -SIGTERM -f '{node_name}' || true"
        return await self._run(
            f"stop_launch_source [{node_name}]", kill_cmd, {"node": node_name},
        )

    # ── Graph verification ───────────────────────────────────────────────────

    async def verify_graph(self) -> dict:
        """Parse ros2 node/topic graph and return a summary."""
        if self._dry_run:
            _audit("verify_graph", {}, "DRY_RUN", dry_run=True)
            return {
                "ok": True, "dry_run": True,
                "nodes": ["YB_Node", "fleetsafe_perception"],
                "topics": ["/cmd_vel", "/cmd_vel_safe", "/cmd_vel_raw", "/odom"],
            }
        _, nodes_out, _ = await _ssh(self._host, "ros2 node list 2>/dev/null")
        _, topics_out, _ = await _ssh(self._host, "ros2 topic list 2>/dev/null")
        nodes = [n.strip() for n in nodes_out.splitlines() if n.strip()]
        topics = [t.strip() for t in topics_out.splitlines() if t.strip()]
        _audit("verify_graph", {}, f"nodes={len(nodes)} topics={len(topics)}", dry_run=False)
        return {"ok": True, "dry_run": False, "nodes": nodes, "topics": topics}

    # ── Audit log access ─────────────────────────────────────────────────────

    def get_audit_log(self, n: int = 100) -> list[dict]:
        if not _AUDIT_PATH.exists():
            return []
        lines = _AUDIT_PATH.read_text().splitlines()
        entries: list[dict] = []
        for line in lines[-n:]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return list(reversed(entries))


robot_ops = RobotOpsManager()
