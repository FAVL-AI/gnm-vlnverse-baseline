"""
Replay a saved manual test-drive episode.

Usage:
  python3 scripts/gnm/replay_manual_testdrive.py \\
      --episode datasets/manual_testdrive_custom_office/<episode>

Dry-run:
  python3 scripts/gnm/replay_manual_testdrive.py --dry-run
"""

import argparse
import json
import pickle
import sys
from pathlib import Path


def dry_run():
    print("=" * 60)
    print("replay_manual_testdrive.py — dry-run")
    print("=" * 60)
    print()
    print("Usage:")
    print("  python3 scripts/gnm/replay_manual_testdrive.py \\")
    print("    --episode datasets/manual_testdrive_custom_office/<episode>")
    print()
    print("What it shows:")
    print("  - Episode metadata (mode, scene, n_steps, path_length_m)")
    print("  - START / GOAL pose")
    print("  - Per-frame: x/y/yaw, action_key, distance_to_goal")
    print("  - Summary stats")


def load_episode(episode_dir: Path) -> dict:
    traj_path = episode_dir / "traj_data.pkl"
    actions_path = episode_dir / "actions.jsonl"
    meta_path = episode_dir / "metadata.json"

    if not traj_path.exists():
        print(f"[ERROR] traj_data.pkl not found in {episode_dir}", file=sys.stderr)
        sys.exit(1)

    with open(traj_path, "rb") as f:
        traj = pickle.load(f)

    actions = []
    if actions_path.exists():
        with open(actions_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    actions.append(json.loads(line))

    meta = {}
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)

    return {"traj": traj, "actions": actions, "meta": meta}


def replay(episode_dir: Path):
    data = load_episode(episode_dir)
    traj = data["traj"]
    actions = data["actions"]
    meta = data["meta"]

    print("=" * 60)
    print(f"Episode: {episode_dir.name}")
    print("=" * 60)
    print(f"  mode            : {traj.get('mode', 'unknown')}")
    print(f"  scene_id        : {traj.get('scene_id', 'unknown')}")
    print(f"  n_steps         : {traj.get('n_steps', len(traj.get('position', [])))}")
    print(f"  path_length_m   : {traj.get('path_length_m', 0.0):.3f}")
    print()

    start = traj.get("start_pos")
    if start is not None:
        print(f"  START pos       : x={start[0]:.3f} y={start[1]:.3f} yaw={traj.get('start_yaw', 0.0):.3f}")
    goal = traj.get("goal_pos")
    if goal is not None:
        print(f"  GOAL pos        : x={goal[0]:.3f} y={goal[1]:.3f} yaw={traj.get('goal_yaw', 0.0):.3f}")
    else:
        print("  GOAL pos        : not set")
    print()

    if meta:
        print("  Metadata:")
        for k, v in meta.items():
            print(f"    {k:<30} {v}")
        print()

    if actions:
        print(f"  Action log ({len(actions)} steps):")
        print(f"  {'frame':>6}  {'key':<6}  {'x':>8}  {'y':>8}  {'yaw':>8}  {'d2g':>10}")
        print(f"  {'-'*6}  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*10}")
        for row in actions[:10]:
            d2g = row.get("distance_to_goal", None)
            d2g_str = f"{d2g:.3f}" if d2g is not None else "n/a"
            print(
                f"  {row.get('frame_index', 0):>6}  "
                f"{row.get('action_key', '?'):<6}  "
                f"{row.get('x', 0.0):>8.3f}  "
                f"{row.get('y', 0.0):>8.3f}  "
                f"{row.get('yaw', 0.0):>8.3f}  "
                f"{d2g_str:>10}"
            )
        if len(actions) > 10:
            print(f"  ... ({len(actions) - 10} more steps)")
    print()
    print(f"  RGB frames in   : {episode_dir / 'rgb'}")
    rgb_count = len(list((episode_dir / "rgb").glob("*.jpg"))) if (episode_dir / "rgb").exists() else 0
    print(f"  RGB count       : {rgb_count}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, help="Path to episode folder")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        dry_run()
        return

    if not args.episode:
        parser.print_help()
        sys.exit(1)

    replay(args.episode)


if __name__ == "__main__":
    main()
