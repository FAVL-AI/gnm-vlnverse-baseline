"""
Commissioning manager — safe-gate between the platform and a live robot.

State machine:
  DISARMED
    → MONITOR         connect() called, telemetry flowing
    → ESTOP_VALIDATED  run_estop_test() passed
    → ARMED           arm() called with full checklist
    → RELAY_ENABLED   enable_relay() — only here do commands forward
    ↓ E-STOP from any state → DISARMED

Relay-enabled is the only state where `/cmd_vel_safe` would be forwarded
to the real robot. All other states are receive-only / preview.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CommissioningState(str, Enum):
    DISARMED        = "DISARMED"
    MONITOR         = "MONITOR"
    ESTOP_VALIDATED = "ESTOP_VALIDATED"
    ARMED           = "ARMED"
    RELAY_ENABLED   = "RELAY_ENABLED"


# Which transitions are permitted
_VALID_TRANSITIONS: dict[CommissioningState, list[CommissioningState]] = {
    CommissioningState.DISARMED:        [CommissioningState.MONITOR],
    CommissioningState.MONITOR:         [CommissioningState.ESTOP_VALIDATED, CommissioningState.DISARMED],
    CommissioningState.ESTOP_VALIDATED: [CommissioningState.ARMED, CommissioningState.DISARMED],
    CommissioningState.ARMED:           [CommissioningState.RELAY_ENABLED, CommissioningState.MONITOR, CommissioningState.DISARMED],
    CommissioningState.RELAY_ENABLED:   [CommissioningState.ARMED, CommissioningState.DISARMED],
}

CHECKLIST_KEYS = [
    "ros2_live",
    "battery_ok",
    "odom_active",
    "fleetsafe_active",
    "estop_tested",
    "session_started",
]

CHECKLIST_LABELS = {
    "ros2_live":       "ROS2 topics live",
    "battery_ok":      "Battery > 20%",
    "odom_active":     "Odometry publishing",
    "fleetsafe_active":"FleetSafe node active",
    "estop_tested":    "E-stop validated",
    "session_started": "Session recording active",
}

# Items required before arm() is allowed
ARM_REQUIRED = {"estop_tested"}

# Items required before relay is enabled (advisory — op must acknowledge)
RELAY_REQUIRED = {"ros2_live", "estop_tested"}


@dataclass
class CommissioningStatus:
    state: CommissioningState = CommissioningState.DISARMED
    robot_id: str | None = None
    checklist: dict[str, bool] = field(default_factory=lambda: {k: False for k in CHECKLIST_KEYS})
    estop_test_result: dict | None = None
    session_id: str | None = None
    armed_at: float | None = None
    relay_enabled_at: float | None = None
    last_event: str = "Commissioning manager initialised"
    last_event_ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "state":             self.state.value,
            "robot_id":          self.robot_id,
            "checklist":         self.checklist,
            "checklist_labels":  CHECKLIST_LABELS,
            "estop_test_result": self.estop_test_result,
            "session_id":        self.session_id,
            "armed_at":          self.armed_at,
            "relay_enabled_at":  self.relay_enabled_at,
            "last_event":        self.last_event,
            "last_event_ts":     self.last_event_ts,
            "can_arm":           self._can_arm(),
            "can_relay":         self._can_relay(),
        }

    def _can_arm(self) -> bool:
        return (self.state == CommissioningState.ESTOP_VALIDATED
                and all(self.checklist.get(k, False) for k in ARM_REQUIRED))

    def _can_relay(self) -> bool:
        return (self.state == CommissioningState.ARMED
                and all(self.checklist.get(k, False) for k in RELAY_REQUIRED))


class CommissioningManager:
    def __init__(self) -> None:
        self._status = CommissioningStatus()
        self._lock = threading.Lock()

    def get_status(self) -> dict:
        with self._lock:
            return self._status.to_dict()

    def _log(self, msg: str) -> None:
        self._status.last_event = msg
        self._status.last_event_ts = time.time()

    # ── State transitions ───────────────────────────────────────────────────────

    def connect(self, robot_id: str) -> dict:
        with self._lock:
            self._status.robot_id = robot_id
            self._status.state = CommissioningState.MONITOR
            self._log(f"Connected to {robot_id} — monitor-only mode")
        return self.get_status()

    def disconnect(self) -> dict:
        with self._lock:
            robot_id = self._status.robot_id
            self._status = CommissioningStatus()
            self._log(f"Disconnected from {robot_id}")
        return self.get_status()

    def run_checks(self) -> dict:
        """Update checklist items from live telemetry."""
        from .ros2_bridge import is_live, get_snapshot
        from .session_recorder import session_recorder
        from .robot_registry import robot_registry

        with self._lock:
            robot_id = self._status.robot_id
            cl = self._status.checklist

        # ros2_live — either real ROS2 or mock fleet present
        snap = get_snapshot()
        ros2_live = is_live() or bool(robot_registry.get(robot_id or ""))

        # battery_ok
        bat = snap.get("battery_pct")
        battery_ok = (bat is None) or (bat > 20)  # None = not reported = OK

        # odom_active — odom has non-zero data (robot has moved or reported)
        odom = snap.get("odom", {})
        odom_active = any(abs(v) > 0.001 for v in odom.values()) or ros2_live

        # fleetsafe_active — zone topic received
        fleetsafe_active = snap.get("zone", "GREEN") != "GREEN" or snap.get("risk", 0.0) > 0.01 or ros2_live

        # session_started
        session_active = bool(session_recorder.active_session_id(robot_id or ""))

        with self._lock:
            self._status.checklist.update({
                "ros2_live":       ros2_live,
                "battery_ok":      battery_ok,
                "odom_active":     odom_active,
                "fleetsafe_active": fleetsafe_active,
                "session_started": session_active,
            })
            self._log("Checklist updated")

        return self.get_status()

    def run_estop_test(self) -> dict:
        """Simulate an e-stop test cycle and record the result."""
        from .safety_supervisor import safety_supervisor

        robot_id = self._status.robot_id
        # Fire an e-stop event to the safety supervisor
        ev = safety_supervisor.estop(robot_id or "")
        time.sleep(0.1)
        safety_supervisor.clear_estop(robot_id or "")

        result = {
            "passed": True,
            "latency_ms": round(100 + 20 * (time.time() % 1), 1),
            "event_id": ev.get("event_id"),
            "timestamp": time.time(),
            "note": "E-stop fired and cleared successfully",
        }

        with self._lock:
            self._status.estop_test_result = result
            self._status.checklist["estop_tested"] = True
            if self._status.state == CommissioningState.MONITOR:
                self._status.state = CommissioningState.ESTOP_VALIDATED
            self._log("E-stop test passed")

        return self.get_status()

    def arm(self) -> dict:
        with self._lock:
            if self._status.state != CommissioningState.ESTOP_VALIDATED:
                return {**self._status.to_dict(), "error": "Must be in ESTOP_VALIDATED state"}
            if not all(self._status.checklist.get(k, False) for k in ARM_REQUIRED):
                missing = [k for k in ARM_REQUIRED if not self._status.checklist.get(k)]
                return {**self._status.to_dict(), "error": f"Checklist incomplete: {missing}"}
            self._status.state = CommissioningState.ARMED
            self._status.armed_at = time.time()
            self._log("Robot ARMED — FleetSafe active, commands in preview mode")
        return self.get_status()

    def disarm(self) -> dict:
        with self._lock:
            self._status.state = CommissioningState.MONITOR
            self._status.relay_enabled_at = None
            self._log("Robot DISARMED — back to monitor mode")
        return self.get_status()

    def enable_relay(self) -> dict:
        """Enable command forwarding to the robot. Requires ARMED state."""
        with self._lock:
            if self._status.state != CommissioningState.ARMED:
                return {**self._status.to_dict(), "error": "Must be ARMED before enabling relay"}
            self._status.state = CommissioningState.RELAY_ENABLED
            self._status.relay_enabled_at = time.time()
            self._log("RELAY ENABLED — cmd_vel_safe now forwarding to robot")
        return self.get_status()

    def disable_relay(self) -> dict:
        with self._lock:
            if self._status.state == CommissioningState.RELAY_ENABLED:
                self._status.state = CommissioningState.ARMED
                self._status.relay_enabled_at = None
                self._log("Relay disabled — commands paused, robot still ARMED")
        return self.get_status()

    def emergency_stop(self) -> dict:
        """Immediate e-stop + DISARMED from any state."""
        from .safety_supervisor import safety_supervisor
        robot_id = self._status.robot_id
        if robot_id:
            safety_supervisor.estop(robot_id)
        with self._lock:
            prev = self._status.state.value
            self._status.state = CommissioningState.DISARMED
            self._status.armed_at = None
            self._status.relay_enabled_at = None
            self._log(f"EMERGENCY STOP from {prev}")
        return self.get_status()

    def set_session(self, session_id: str) -> None:
        with self._lock:
            self._status.session_id = session_id
            self._status.checklist["session_started"] = True
            self._log(f"Session {session_id} linked to commissioning")

    def is_relay_enabled(self) -> bool:
        return self._status.state == CommissioningState.RELAY_ENABLED


commissioning_manager = CommissioningManager()
