#!/usr/bin/env python3
"""
inspect_lidar_clearance.py — Live LiDAR sanitization inspector.

Reads one message from /scan0 and /scan1, runs the same LidarSanitizer
logic used by run_vln_m3pro.py, and prints a human-readable audit table.

Usage:
    source /opt/ros/humble/setup.bash
    export ROS_DOMAIN_ID=30
    python3 scripts/live/inspect_lidar_clearance.py
    python3 scripts/live/inspect_lidar_clearance.py --safety-radius 0.35
    python3 scripts/live/inspect_lidar_clearance.py --topics /scan0  # single topic

Output example:
    ┌──────────────────────────────────────────────────────────────────┐
    │  FleetSafe-VLN  LiDAR Sanitization Report                        │
    ├──────────────────────────────────────────────────────────────────┤
    │  Topic   raw_min  valid_min  p05  invalid  effective  status      │
    │  /scan0  0.05 m   0.84 m    0.82   12     0.82 m     OK          │
    │  /scan1  0.05 m   0.76 m    0.73   18     0.73 m     OK          │
    ├──────────────────────────────────────────────────────────────────┤
    │  Combined effective clearance: 0.73 m  (safety radius: 0.30 m)   │
    │  CBF decision: ALLOW motion                                       │
    └──────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fleet_safe_vla.safety.lidar_sanitizer import sanitize, LidarSample

# ── Argument parsing ──────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(
    description="Inspect live LiDAR clearance using the same sanitizer as run_vln_m3pro.py"
)
parser.add_argument(
    "--topics", nargs="+", default=["/scan0", "/scan1"],
    help="ROS2 LaserScan topics to inspect (default: /scan0 /scan1)",
)
parser.add_argument(
    "--safety-radius", type=float, default=0.30,
    help="Safety radius in metres (default: 0.30)",
)
parser.add_argument(
    "--timeout", type=float, default=5.0,
    help="Seconds to wait for each topic message (default: 5.0)",
)
parser.add_argument(
    "--percentile", type=int, default=5,
    help="Percentile for effective clearance (default: 5)",
)
parser.add_argument(
    "--epsilon", type=float, default=0.02,
    help="Dead-zone epsilon added to range_min (default: 0.02 m)",
)
args = parser.parse_args()


# ── ROS2 import ───────────────────────────────────────────────────────────────
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from sensor_msgs.msg import LaserScan
    _HAS_ROS2 = True
except ImportError:
    _HAS_ROS2 = False


def _fmt(v: float, unit: str = "m", decimals: int = 2) -> str:
    if not math.isfinite(v):
        return "inf"
    return f"{v:.{decimals}f} {unit}"


def _status_str(eff: float, d_safe: float) -> str:
    if eff < d_safe:
        return "E-STOP (below radius)"
    if eff < d_safe + 0.20:
        return "WARN (close)"
    return "OK"


def _print_report(
    results: list[tuple[str, LidarSample | None]],
    d_safe: float,
) -> None:
    W = 70
    print()
    print("┌" + "─" * (W - 2) + "┐")
    print(f"│  FleetSafe-VLN  LiDAR Sanitization Report{' ' * (W - 45)}│")
    print("├" + "─" * (W - 2) + "┤")

    hdr = (
        f"  {'Topic':<8}  {'raw_min':>8}  {'valid_min':>9}  "
        f"{'p05':>6}  {'invalid':>7}  {'effective':>9}  {'status':<22}"
    )
    print(f"│{hdr:<{W - 2}}│")
    print("│" + "─" * (W - 2) + "│")

    samples: list[LidarSample] = []
    for topic, sample in results:
        if sample is None:
            row = f"  {topic:<8}  {'(no data)':<55}"
        else:
            status = _status_str(sample.effective_clearance_m, d_safe)
            raw_str = _fmt(sample.raw_min_m)
            vmin    = _fmt(sample.valid_min_m)
            p05     = _fmt(sample.valid_p05_m)
            eff     = _fmt(sample.effective_clearance_m)
            inv     = str(sample.invalid_count)
            row = (
                f"  {topic:<8}  {raw_str:>8}  {vmin:>9}  "
                f"{p05:>6}  {inv:>7}  {eff:>9}  {status:<22}"
            )
            samples.append(sample)
        print(f"│{row:<{W - 2}}│")

    print("├" + "─" * (W - 2) + "┤")

    if samples:
        combined_eff = min(s.effective_clearance_m for s in samples)
        decision = "ALLOW motion" if combined_eff >= d_safe else "BLOCK (CBF e-stop)"
        l1 = f"  Combined effective clearance: {_fmt(combined_eff)}  (safety radius: {d_safe:.2f} m)"
        l2 = f"  CBF decision: {decision}"
        print(f"│{l1:<{W - 2}}│")
        print(f"│{l2:<{W - 2}}│")
    else:
        print(f"│  {'No scan data received — cannot determine clearance':<{W - 3}}│")

    print("└" + "─" * (W - 2) + "┘")
    print()


# ── ROS2-backed reader ────────────────────────────────────────────────────────

class _InspectorNode(Node if _HAS_ROS2 else object):  # type: ignore[misc]
    def __init__(self, topics: list[str], timeout: float,
                 percentile: int, epsilon: float):
        if not _HAS_ROS2:
            return
        super().__init__("fleetsafe_lidar_inspector")
        self._pending: dict[str, LidarSample | None] = {t: None for t in topics}
        self._received: dict[str, bool] = {t: False for t in topics}
        self._percentile = percentile
        self._epsilon    = epsilon
        self._timeout    = timeout
        self._deadline   = time.time() + timeout

        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        for topic in topics:
            self.create_subscription(
                LaserScan, topic,
                lambda msg, t=topic: self._cb(msg, t),
                sensor_qos,
            )

    def _cb(self, msg: "LaserScan", topic: str) -> None:
        if self._received[topic]:
            return
        sample = sanitize(
            ranges    = list(msg.ranges),
            range_min = float(msg.range_min),
            range_max = float(msg.range_max),
            percentile = self._percentile,
            epsilon    = self._epsilon,
        )
        self._pending[topic]  = sample
        self._received[topic] = True

    def all_received(self) -> bool:
        return all(self._received.values())

    def timed_out(self) -> bool:
        return time.time() >= self._deadline

    def results(self) -> list[tuple[str, LidarSample | None]]:
        return [(t, self._pending[t]) for t in self._pending]


# ── Non-ROS2 fallback: run sanitizer on synthetic data for syntax check ───────

def _offline_demo() -> None:
    print("[INFO] ROS2 not available — running offline demo with synthetic data.")
    import random
    results = []
    for topic in args.topics:
        random.seed(hash(topic) % 2**31)
        fake_ranges = (
            [0.05] * 10                                   # dead-zone artifacts
            + [0.05 + random.uniform(0, 0.01) for _ in range(5)]
            + [random.uniform(0.5, 3.0) for _ in range(100)]
            + [float("inf")] * 20
        )
        sample = sanitize(
            ranges     = fake_ranges,
            range_min  = 0.05,
            range_max  = 12.0,
            percentile = args.percentile,
            epsilon    = args.epsilon,
        )
        results.append((topic, sample))
    _print_report(results, args.safety_radius)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not _HAS_ROS2:
        _offline_demo()
        return

    print(f"\n[LiDAR Inspector] Reading from {args.topics} (timeout={args.timeout}s)...")

    rclpy.init()
    node = _InspectorNode(
        topics     = args.topics,
        timeout    = args.timeout,
        percentile = args.percentile,
        epsilon    = args.epsilon,
    )

    while rclpy.ok() and not node.all_received() and not node.timed_out():
        rclpy.spin_once(node, timeout_sec=0.1)

    results = node.results()
    node.destroy_node()
    rclpy.shutdown()

    _print_report(results, args.safety_radius)

    # Exit code: 0 if combined clearance ≥ radius, 1 otherwise
    samples = [s for _, s in results if s is not None]
    if samples:
        combined_eff = min(s.effective_clearance_m for s in samples)
        sys.exit(0 if combined_eff >= args.safety_radius else 1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
