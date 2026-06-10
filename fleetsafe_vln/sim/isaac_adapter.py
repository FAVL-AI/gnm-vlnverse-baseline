"""Isaac Sim adapter for FleetSafe-VLN — with ROS 2 topic health checks.

Re-exports IsaacSimAdapter from fleetsafe_vln.simulators and adds:
  check_ros2_topics()      — one-shot topic availability check
  wait_for_ros2_topics()   — blocking wait with timeout
  load_robot_topics()      — load expected topics from robot YAML config

Robot
-----
  Target: Yahboom ROSMASTER M3 Pro (real and Isaac Sim digital twin).
  Topic defaults are read from configs/robots/yahboom_m3_pro.yaml.
  Do NOT substitute TurtleBot3, JetBot, Carter, or other robots.

Usage:
    from fleetsafe_vln.sim.isaac_adapter import check_ros2_topics
    ok, report = check_ros2_topics()
    if not ok:
        print(report)
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Re-export the full simulator adapter
from fleetsafe_vln.simulators.isaac_adapter import IsaacSimAdapter  # noqa: F401

# ── Default robot config path ─────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ROBOT_CONFIG = _REPO_ROOT / "configs" / "robots" / "yahboom_m3_pro.yaml"

# ── Fallback topic list (used when YAML is unavailable) ───────────────────────
_FALLBACK_REQUIRED: List[str] = [
    "/camera/image_raw",
    "/odom",
    "/tf",
    "/cmd_vel",
]

_FALLBACK_RECOMMENDED: List[str] = [
    "/camera/depth/image_raw",
    "/scan",
    "/imu/data",
]


def load_robot_topics(
    robot_config: Optional[str | Path] = None,
) -> Tuple[List[str], List[str]]:
    """Load required and recommended topics from the robot YAML config.

    Parameters
    ----------
    robot_config : path to robot YAML; defaults to yahboom_m3_pro.yaml

    Returns
    -------
    (required_topics, recommended_topics)
    """
    config_path = Path(robot_config) if robot_config else _DEFAULT_ROBOT_CONFIG

    if not config_path.exists():
        return _FALLBACK_REQUIRED, _FALLBACK_RECOMMENDED

    try:
        import yaml  # type: ignore
    except ImportError:
        return _FALLBACK_REQUIRED, _FALLBACK_RECOMMENDED

    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        topics_cfg = cfg.get("ros2_topics", {})
        required = [v for v in [
            topics_cfg.get("rgb"),
            topics_cfg.get("odom"),
            topics_cfg.get("tf"),
            topics_cfg.get("cmd_vel"),
        ] if v]
        recommended = [v for v in [
            topics_cfg.get("depth"),
            topics_cfg.get("scan"),
            topics_cfg.get("imu"),
        ] if v]

        return required or _FALLBACK_REQUIRED, recommended or _FALLBACK_RECOMMENDED

    except Exception:
        return _FALLBACK_REQUIRED, _FALLBACK_RECOMMENDED


# ── Module-level defaults loaded from robot config ────────────────────────────
REQUIRED_TOPICS, RECOMMENDED_TOPICS = load_robot_topics()


def check_ros2_topics(
    topics: Optional[List[str]] = None,
    timeout_s: float = 5.0,
    robot_config: Optional[str | Path] = None,
) -> Tuple[bool, Dict[str, bool]]:
    """Check which ROS 2 topics are currently publishing.

    Parameters
    ----------
    topics       : explicit topic list; if None, loaded from robot YAML config
    timeout_s    : per-topic timeout in seconds
    robot_config : path to robot YAML (overrides default yahboom_m3_pro.yaml)

    Returns
    -------
    (all_ok, status_dict)
    """
    if topics is None:
        topics, _ = load_robot_topics(robot_config)

    status: Dict[str, bool] = {}
    for topic in topics:
        status[topic] = _topic_is_publishing(topic, timeout_s)

    return all(status.values()), status


def wait_for_ros2_topics(
    topics: Optional[List[str]] = None,
    total_timeout_s: float = 30.0,
    poll_interval_s: float = 2.0,
    robot_config: Optional[str | Path] = None,
) -> Tuple[bool, Dict[str, bool]]:
    """Block until all topics are publishing or timeout expires.

    Parameters
    ----------
    topics           : topics to wait for; if None, loaded from robot YAML
    total_timeout_s  : give up after this many seconds
    poll_interval_s  : seconds between retries
    robot_config     : path to robot YAML (overrides default)

    Returns
    -------
    Same as check_ros2_topics().
    """
    if topics is None:
        topics, _ = load_robot_topics(robot_config)

    deadline = time.time() + total_timeout_s
    status: Dict[str, bool] = {t: False for t in topics}

    while time.time() < deadline:
        remaining = [t for t, ok in status.items() if not ok]
        for topic in remaining:
            status[topic] = _topic_is_publishing(topic, poll_interval_s)

        if all(status.values()):
            return True, status

        missing = [t for t, ok in status.items() if not ok]
        print(f"[ros2_topics] Waiting for: {missing}  "
              f"({int(deadline - time.time())}s remaining)")
        time.sleep(poll_interval_s)

    return all(status.values()), status


def print_topic_report(
    status: Dict[str, bool],
    recommended_status: Optional[Dict[str, bool]] = None,
    robot_config: Optional[str | Path] = None,
) -> None:
    """Print a human-readable topic health report for the Yahboom M3 Pro."""
    cfg_path = Path(robot_config) if robot_config else _DEFAULT_ROBOT_CONFIG
    robot_name = "Yahboom ROSMASTER M3 Pro"
    try:
        import yaml  # type: ignore
        if cfg_path.exists():
            with open(cfg_path) as f:
                robot_name = yaml.safe_load(f).get("name", robot_name)
    except Exception:
        pass

    print(f"\n=== ROS 2 Topic Health — {robot_name} ===")
    print("Required:")
    for topic, ok in status.items():
        mark = "✓" if ok else "⚠"
        print(f"  {mark} {topic}")

    if recommended_status:
        print("Recommended:")
        for topic, ok in recommended_status.items():
            mark = "✓" if ok else "—"
            print(f"  {mark} {topic}")

    if all(status.values()):
        print("\nAll required topics publishing. GNM can start.")
    else:
        missing = [t for t, ok in status.items() if not ok]
        print(f"\n⚠️  Missing required topics: {missing}")
        print("   Check Isaac Sim ROS 2 bridge: ros2 topic list")
        print(f"   Expected robot: {robot_name}")
        print(f"   Config: {cfg_path}")
    print()


# ── Internal helpers ───────────────────────────────────────────────────────────

def _topic_is_publishing(topic: str, timeout_s: float) -> bool:
    """Return True if a topic is currently publishing."""
    try:
        result = subprocess.run(
            ["ros2", "topic", "hz", topic, "--once"],
            capture_output=True,
            text=True,
            timeout=timeout_s + 1,
        )
        return "average rate" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    except Exception:
        return False
