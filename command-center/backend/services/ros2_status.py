"""
ROS2 / DDS status via SSH.

Probes the robot for:
  - ROS_DOMAIN_ID
  - Active nodes
  - Topic list
  - Approximate rates for key topics (1s sample)

In dry_run mode returns mock data — never claims robot is live when it isn't.
"""
from __future__ import annotations

import subprocess

from ..config import settings
from .robot_ops import robot_ops

EXPECTED_NODES   = ["/YB_Node", "/fleetsafe_perception"]
EXPECTED_TOPICS  = ["/cmd_vel_raw", "/cmd_vel_safe", "/cmd_vel", "/odom_raw", "/scan0"]


def _ssh_sync(cmd: str, timeout: float = 8.0) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={int(timeout)}",
             settings.robot_ssh, cmd],
            capture_output=True, text=True, timeout=timeout + 2,
        )
        return r.returncode, r.stdout.strip()
    except Exception:
        return -1, ""


def get_ros2_status() -> dict:
    if robot_ops.dry_run:
        return {
            "mode": "dry_run",
            "online": False,
            "warning": "Dry-run mode — no SSH probe performed",
            "domain_id": None,
            "nodes": [],
            "topics": [],
            "missing_nodes": EXPECTED_NODES,
            "missing_topics": EXPECTED_TOPICS,
            "rates_hz": {},
        }

    # Domain ID
    rc, domain_out = _ssh_sync("echo $ROS_DOMAIN_ID")
    online = rc == 0
    domain_id = domain_out.strip() or "0"

    if not online:
        return {
            "mode": "live",
            "online": False,
            "warning": f"SSH to {settings.robot_ssh} failed — robot may be offline",
            "domain_id": None,
            "nodes": [],
            "topics": [],
            "missing_nodes": EXPECTED_NODES,
            "missing_topics": EXPECTED_TOPICS,
            "rates_hz": {},
        }

    # Nodes
    _, nodes_out = _ssh_sync("ros2 node list 2>/dev/null")
    nodes = [n.strip() for n in nodes_out.splitlines() if n.strip()]

    # Topics
    _, topics_out = _ssh_sync("ros2 topic list 2>/dev/null")
    topics = [t.strip() for t in topics_out.splitlines() if t.strip()]

    # Rates for key topics (non-blocking — just check last received)
    rates: dict[str, float | str] = {}
    for topic in ["/odom_raw", "/scan0", "/cmd_vel_raw"]:
        if topic in topics:
            _, hz_out = _ssh_sync(
                f"timeout 2 ros2 topic hz {topic} --window 5 2>/dev/null | head -3", timeout=5.0,
            )
            # Parse "average rate: X.XXX"
            for line in hz_out.splitlines():
                if "average rate" in line.lower():
                    try:
                        rates[topic] = float(line.split(":")[-1].strip())
                    except ValueError:
                        rates[topic] = "parse_error"
                    break
            else:
                rates[topic] = "no_data"
        else:
            rates[topic] = "not_present"

    missing_nodes  = [n for n in EXPECTED_NODES  if n not in nodes]
    missing_topics = [t for t in EXPECTED_TOPICS if t not in topics]

    return {
        "mode": "live",
        "online": True,
        "host": settings.robot_ssh,
        "domain_id": domain_id,
        "nodes": nodes,
        "topics": topics,
        "missing_nodes": missing_nodes,
        "missing_topics": missing_topics,
        "rates_hz": rates,
        "warning": (
            f"Missing nodes: {missing_nodes}" if missing_nodes else
            f"Missing topics: {missing_topics}" if missing_topics else None
        ),
    }
