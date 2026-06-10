"""
Fleet-Safe Latency Compensator — wraps robot-lab LatencyCompensator.

Extends the base compensator with:
  - Auto-calibration from timing measurements
  - Fleet-wide latency statistics aggregation
  - Integration with FleetRiskMonitor alerts

Usage:
    from fleet_safe_vla.sim2real.latency_compensation.compensator import FleetLatencyCompensator
    comp = FleetLatencyCompensator(latency_ms=20.0)
    pred_pos, pred_vel = comp.predict(joint_pos, joint_vel)
"""
from __future__ import annotations

import time
from collections import deque

import numpy as np

from robot_lab.sim2real.latency_compensation import (
    LatencyCompensator,
    JointAccelerationEstimator,
)


class FleetLatencyCompensator:
    """
    Extended latency compensator with auto-calibration and telemetry.

    Wraps robot-lab's LatencyCompensator and adds:
      - Latency measurement from command→feedback round trip
      - Adaptive latency estimate (exponential moving average)
      - Per-robot latency statistics for fleet monitoring

    Args:
        latency_ms:   Initial latency estimate (ms)
        control_hz:   Control loop rate (Hz)
        adaptive:     Enable adaptive latency estimation
    """

    def __init__(
        self,
        latency_ms: float = 20.0,
        control_hz: float = 50.0,
        adaptive: bool = True,
    ) -> None:
        self._nominal_latency_ms = latency_ms
        self._current_latency_ms = latency_ms
        self._control_hz = control_hz
        self._adaptive = adaptive

        # robot-lab core compensator
        self._comp = LatencyCompensator(
            latency_ms=latency_ms,
            control_hz=control_hz,
            strategy="constant_extrapolation",
        )
        self._acc_est = JointAccelerationEstimator(control_hz=control_hz)

        # Latency measurement
        self._send_times: deque[float] = deque(maxlen=50)
        self._recv_times: deque[float] = deque(maxlen=50)
        self._measured_latencies: deque[float] = deque(maxlen=200)

    def predict(
        self,
        joint_pos: np.ndarray,
        joint_vel: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Predict joint state forward by current latency estimate.

        Args:
            joint_pos: (N,) current joint positions
            joint_vel: (N,) current joint velocities

        Returns:
            (pred_pos, pred_vel): predicted future state
        """
        joint_acc = self._acc_est.update(joint_vel)
        return self._comp.predict_state(joint_pos, joint_vel, joint_acc)

    def record_send(self) -> None:
        """Record timestamp when command is sent to actuators."""
        self._send_times.append(time.monotonic())

    def record_receive(self) -> None:
        """Record timestamp when feedback is received from actuators."""
        self._recv_times.append(time.monotonic())
        self._update_latency_estimate()

    def _update_latency_estimate(self) -> None:
        if not self._adaptive:
            return
        if len(self._send_times) == 0 or len(self._recv_times) == 0:
            return

        # Latest measured round-trip latency (half = one-way)
        rtt = (self._recv_times[-1] - self._send_times[-1]) * 1000.0  # ms
        one_way = rtt / 2.0

        if 1.0 < one_way < 100.0:  # sanity check
            self._measured_latencies.append(one_way)
            # EMA update
            alpha = 0.05
            self._current_latency_ms = (
                (1 - alpha) * self._current_latency_ms + alpha * one_way
            )
            # Update underlying compensator
            self._comp = LatencyCompensator(
                latency_ms=self._current_latency_ms,
                control_hz=self._control_hz,
                strategy="constant_extrapolation",
            )

    @property
    def latency_ms(self) -> float:
        """Current latency estimate in milliseconds."""
        return self._current_latency_ms

    def get_stats(self) -> dict:
        """Return latency statistics dict."""
        if self._measured_latencies:
            arr = np.array(list(self._measured_latencies))
            return {
                "latency_ms_current": self._current_latency_ms,
                "latency_ms_mean": float(arr.mean()),
                "latency_ms_std": float(arr.std()),
                "latency_ms_p95": float(np.percentile(arr, 95)),
                "n_measurements": len(self._measured_latencies),
            }
        return {
            "latency_ms_current": self._current_latency_ms,
            "n_measurements": 0,
        }

    def reset(self) -> None:
        self._comp.reset()
        self._acc_est.reset()
        self._send_times.clear()
        self._recv_times.clear()
