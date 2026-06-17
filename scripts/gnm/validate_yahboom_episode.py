#!/usr/bin/env python3
"""Validate a recorded Yahboom M3 Pro rosbag2 episode.

Checks:
  1. All five canonical topics are present in the bag metadata.
  2. All five have message_count > 0.
  3. No Nova Carter topic names are present.
  4. Episode duration is at least 30 seconds.

Reads:
  <episode_path>/rosbag/metadata.yaml  (written by ros2 bag record)

Writes:
  results/gnm_fleetsafe_v2_4/<episode_name>_validation.json

Exits 0 if all checks pass. Exits non-zero if any check fails.
Without --episode-path (or if the bag directory does not exist), exits 0
in dry-run/CI mode.

Usage:
    python3 scripts/gnm/validate_yahboom_episode.py \\
        --episode-path datasets/gnm_fleetsafe_rosbags/episode_001
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "results" / "gnm_fleetsafe_v2_4"

CANONICAL_TOPICS = {
    "/camera/image_raw",
    "/odom",
    "/tf",
    "/scan",
    "/cmd_vel",
}

NOVA_CARTER_TOPICS = {
    "/front_stereo_camera/left/image_raw",
    "/chassis/odom",
    "/front_3d_lidar/lidar_points",
}

MIN_DURATION_SECONDS = 30


def parse_metadata_yaml(metadata_path: Path) -> dict:
    """Parse rosbag2 metadata.yaml and return a normalised dict."""
    if not YAML_AVAILABLE:
        raise RuntimeError(
            "PyYAML is not installed. Install it with: pip3 install pyyaml"
        )
    raw = yaml.safe_load(metadata_path.read_text())
    info = raw.get("rosbag2_bagfile_information", raw)
    topics_raw = info.get("topics_with_message_count", [])
    topics = {}
    for entry in topics_raw:
        meta = entry.get("topic_metadata", {})
        name = meta.get("name", "")
        count = entry.get("message_count", 0)
        topics[name] = count

    duration_ns = 0
    dur = info.get("duration", {})
    if isinstance(dur, dict):
        duration_ns = dur.get("nanoseconds", 0)
    elif isinstance(dur, int):
        duration_ns = dur

    return {
        "topics": topics,
        "duration_seconds": duration_ns / 1e9,
        "message_count_total": info.get("message_count", 0),
    }


def run_checks(bag_info: dict) -> list[dict]:
    """Return a list of check result dicts. Each has name, passed, detail."""
    checks = []
    topics = bag_info["topics"]
    duration = bag_info["duration_seconds"]

    for topic in sorted(CANONICAL_TOPICS):
        count = topics.get(topic, 0)
        checks.append({
            "name": f"topic_present: {topic}",
            "passed": topic in topics,
            "detail": f"message_count={count}" if topic in topics else "not in bag",
        })
        checks.append({
            "name": f"nonzero_messages: {topic}",
            "passed": count > 0,
            "detail": f"message_count={count}",
        })

    nova_found = NOVA_CARTER_TOPICS & set(topics.keys())
    checks.append({
        "name": "no_nova_carter_topics",
        "passed": len(nova_found) == 0,
        "detail": (
            "no Nova Carter topics detected"
            if not nova_found
            else f"found: {sorted(nova_found)}"
        ),
    })

    checks.append({
        "name": f"min_duration_{MIN_DURATION_SECONDS}s",
        "passed": duration >= MIN_DURATION_SECONDS,
        "detail": f"duration={duration:.1f}s (min={MIN_DURATION_SECONDS}s)",
    })

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a recorded Yahboom rosbag2 episode [v2.4]"
    )
    parser.add_argument(
        "--episode-path",
        help="Path to the episode directory (contains rosbag/ subdir)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(" Yahboom Episode Validator  [v2.4]")
    print("=" * 60)
    print()

    if not args.episode_path:
        print("[INFO] No --episode-path provided.")
        print("[INFO] Skipping validation (dry-run/CI mode).")
        print()
        print("[OK] Exiting 0.")
        return 0

    episode_path = Path(args.episode_path)
    metadata_path = episode_path / "rosbag" / "metadata.yaml"

    if not episode_path.exists():
        print(f"[INFO] Episode path does not exist: {episode_path}")
        print("[INFO] No rosbag recorded yet — this is expected before v2.4 live run.")
        print("[OK] Exiting 0 (no bag to validate).")
        return 0

    if not metadata_path.exists():
        print(f"[FAIL] metadata.yaml not found at: {metadata_path}")
        print("[FAIL] The rosbag may not have been recorded correctly.")
        return 1

    print(f"Episode path : {episode_path}")
    print(f"Metadata     : {metadata_path}")
    print()

    try:
        bag_info = parse_metadata_yaml(metadata_path)
    except Exception as exc:
        print(f"[FAIL] Could not parse metadata.yaml: {exc}")
        return 1

    print(f"Duration     : {bag_info['duration_seconds']:.1f}s")
    print(f"Total msgs   : {bag_info['message_count_total']}")
    print()
    print("Topics in bag:")
    for name, count in sorted(bag_info["topics"].items()):
        marker = "[CANONICAL]" if name in CANONICAL_TOPICS else "[other]    "
        print(f"  {marker}  {name:<45s}  msgs={count}")
    print()

    checks = run_checks(bag_info)

    print("Validation checks:")
    all_passed = True
    for chk in checks:
        status = "[OK]  " if chk["passed"] else "[FAIL]"
        print(f"  {status}  {chk['name']}  —  {chk['detail']}")
        if not chk["passed"]:
            all_passed = False

    episode_name = episode_path.name
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / f"{episode_name}_validation.json"

    report = {
        "episode_name": episode_name,
        "episode_path": str(episode_path),
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "milestone": "v2.4",
        "duration_seconds": bag_info["duration_seconds"],
        "message_count_total": bag_info["message_count_total"],
        "topics": bag_info["topics"],
        "checks": checks,
        "valid": all_passed,
    }
    report_path.write_text(json.dumps(report, indent=2))

    print()
    print(f"Report written: {report_path.relative_to(ROOT)}")
    print()

    if all_passed:
        print("[OK] Episode is valid. Gate A6 condition met.")
        print("[OK] Next: python3 scripts/gnm/convert_rosbag_to_gnm_dataset.py \\")
        print(f"       --rosbag-root datasets/gnm_fleetsafe_rosbags \\")
        print(f"       --output-root datasets/gnm_fleetsafe_converted \\")
        print(f"       --episode-name {episode_name}")
        return 0

    print("[FAIL] Episode is invalid. Do not convert to GNM format.")
    print("[FAIL] Record a new episode and validate again.")
    print()
    failed = [c["name"] for c in checks if not c["passed"]]
    for name in failed:
        print(f"  [FAIL] {name}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
