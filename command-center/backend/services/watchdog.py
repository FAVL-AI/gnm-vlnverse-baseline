"""
Safety watchdog — background thread that monitors the robot while relay is active.

Checks every INTERVAL_S seconds:
  1. fleetsafe_perception node is alive (ros2 node list via SSH).
  2. No unexpected publishers on /cmd_vel (joy/teleop conflict detection).
     Blocked list includes: joy_node, teleop_twist, ackermann_controller,
     joy_ctrl, autostart_node.

On any failure while relay is active:
  1. Publish zero to /cmd_vel_raw + /cmd_vel via subprocess (sync, no asyncio).
  2. Latch the e-stop.
  3. Mark relay as inactive (relay_manager._set_inactive).
  4. Stop any active real-robot recording session.

When an unsafe /cmd_vel publisher is detected the watchdog sets
unsafe_publisher_status = "UNSAFE_CMDVEL_PUBLISHER" which is exposed via
get_status() for the UI.

In dry_run mode the SSH probe is skipped and the watchdog always reports OK.
"""
from __future__ import annotations

import subprocess
import threading
import time

from ..config import settings
from .robot_ops import _audit, _ssh_argv, _ssh_env, robot_ops
from .safety_latch import safety_latch
from .relay_manager import relay_manager

INTERVAL_S = 3.0
MAX_FAILURES = 2  # consecutive failures before triggering

# Node names whose presence as /cmd_vel publishers blocks motion
_BLOCKED_PUBLISHERS = frozenset([
    "joy_node",
    "teleop_twist",
    "ackermann_controller",
    "joy_ctrl",
    "autostart_node",
])


def _ssh_sync(cmd: str, timeout: float = 5.0) -> tuple[int, str]:
    """Synchronous SSH helper for use from the watchdog thread.

    Uses the same key-vs-sshpass selection as the async _ssh() helper.
    Password is passed via SSHPASS env var only — never in argv.
    """
    argv = _ssh_argv(settings.robot_ssh, timeout)
    try:
        r = subprocess.run(
            argv + [cmd],
            capture_output=True, text=True, timeout=timeout + 2,
            env=_ssh_env(),
        )
        return r.returncode, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return -1, ""
    except Exception:
        return -1, ""


def _zero_sync() -> None:
    """Publish zero twist to both topics without asyncio."""
    if robot_ops.dry_run:
        _audit("watchdog_zero", {}, "DRY_RUN", dry_run=True)
        return
    for topic in ["/cmd_vel_raw", "/cmd_vel"]:
        _ssh_sync(f"ros2 topic pub --once {topic} geometry_msgs/msg/Twist '{{}}'")
    _audit("watchdog_zero", {}, "EXECUTED", dry_run=False)


class Watchdog:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        self._last_check: float | None = None
        self._last_ok: float | None = None
        self._consecutive_failures = 0
        self._total_triggers = 0
        self._log: list[dict] = []
        # Set to "UNSAFE_CMDVEL_PUBLISHER" when a blocked node is detected,
        # "OK" when clear, None when not yet checked.
        self._unsafe_publisher_status: str | None = None
        self._unsafe_publisher_detail: str = ""

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name="watchdog")
            self._thread.start()
            self._running = True

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._running = False

    def get_status(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "last_check": self._last_check,
                "last_ok": self._last_ok,
                "consecutive_failures": self._consecutive_failures,
                "total_triggers": self._total_triggers,
                "log": list(self._log[-10:]),
                "unsafe_publisher_status": self._unsafe_publisher_status,
                "unsafe_publisher_detail": self._unsafe_publisher_detail,
            }

    def _loop(self) -> None:
        while not self._stop_event.wait(INTERVAL_S):
            self._tick()

    def _tick(self) -> None:
        with self._lock:
            self._last_check = time.time()

        # Only intervene when relay is active
        if not relay_manager.is_active:
            with self._lock:
                self._consecutive_failures = 0
                self._last_ok = time.time()
            return

        ok, detail = self._probe()

        if ok:
            with self._lock:
                self._consecutive_failures = 0
                self._last_ok = time.time()
        else:
            with self._lock:
                self._consecutive_failures += 1
                failures = self._consecutive_failures

            self._log_event("probe_fail", detail)

            if failures >= MAX_FAILURES:
                self._trigger(detail)

    def _probe(self) -> tuple[bool, str]:
        """Return (ok, detail_string). In dry_run always OK."""
        if robot_ops.dry_run:
            with self._lock:
                self._unsafe_publisher_status = "OK"
                self._unsafe_publisher_detail = "dry_run"
            return True, "dry_run"

        rc, out = _ssh_sync("ros2 node list 2>/dev/null")
        if rc != 0:
            return False, f"SSH failed rc={rc}"

        if "/fleetsafe_perception" not in out:
            return False, "fleetsafe_perception not in node list"

        # Conflict check: unexpected /cmd_vel publishers
        _, info = _ssh_sync("ros2 topic info /cmd_vel 2>/dev/null")
        for conflict in _BLOCKED_PUBLISHERS:
            if conflict in info:
                detail = f"unsafe /cmd_vel publisher: {conflict}"
                with self._lock:
                    self._unsafe_publisher_status = "UNSAFE_CMDVEL_PUBLISHER"
                    self._unsafe_publisher_detail = detail
                return False, detail

        with self._lock:
            self._unsafe_publisher_status = "OK"
            self._unsafe_publisher_detail = ""
        return True, "ok"

    def _trigger(self, reason: str) -> None:
        with self._lock:
            self._total_triggers += 1
            self._consecutive_failures = 0

        self._log_event("emergency_stop", reason)
        _zero_sync()
        safety_latch.latch(f"watchdog: {reason}")
        relay_manager._set_inactive(f"watchdog: {reason}")
        self._stop_active_recording(reason)

    def _stop_active_recording(self, reason: str) -> None:
        """Stop any active real-robot recording session (sync, best-effort)."""
        try:
            from .real_session import real_session_recorder
            active = real_session_recorder.active_session_id()
            if active:
                import asyncio
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(real_session_recorder.stop(active))
                finally:
                    loop.close()
                _audit("watchdog_stop_recording", {"session_id": active, "reason": reason},
                       "stopped", dry_run=robot_ops.dry_run)
        except Exception:
            pass

    def _log_event(self, event: str, detail: str) -> None:
        entry = {"ts": time.time(), "event": event, "detail": detail}
        with self._lock:
            self._log.append(entry)
        _audit(f"watchdog_{event}", {"detail": detail}, detail, dry_run=robot_ops.dry_run)


watchdog = Watchdog()
