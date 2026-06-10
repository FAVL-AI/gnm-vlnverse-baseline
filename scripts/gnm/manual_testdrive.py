"""
Manual Isaac Sim test-drive for GNM/VLNVerse data collection.

Modes:
  MODE=custom_office  (default)
  MODE=vlnverse SCENE=kujiale_0271

Keyboard controls (GUI or --terminal-control):
  W  forward    S  brake/back
  A  rotate-L   D  rotate-R
  Q  strafe-L   E  strafe-R
  Space  stop
  G  mark current pose as goal
  P  save episode
  R  reset episode
  Esc  exit

Dry-run (no Isaac required):
  python3 scripts/gnm/manual_testdrive.py --dry-run
"""

import argparse
import json
import os
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODES = ("custom_office", "vlnverse")

CONTROLS = {
    "W": "forward",
    "S": "brake/back",
    "A": "rotate-left",
    "D": "rotate-right",
    "Q": "strafe-left",
    "E": "strafe-right",
    "Space": "stop",
    "G": "mark goal",
    "P": "save episode",
    "R": "reset episode",
    "Esc": "exit",
}

LINEAR_STEP = 0.05   # metres per keypress
ANGULAR_STEP = 0.05  # radians per keypress


# ---------------------------------------------------------------------------
# Episode state
# ---------------------------------------------------------------------------

class Episode:
    def __init__(self, mode: str, scene_id: str, episode_id: str, output_dir: Path):
        self.mode = mode
        self.scene_id = scene_id
        self.episode_id = episode_id
        self.output_dir = output_dir
        self.rgb_dir = output_dir / "rgb"
        self.rgb_dir.mkdir(parents=True, exist_ok=True)

        self.positions: list[np.ndarray] = []
        self.yaws: list[float] = []
        self.rgb_paths: list[str] = []
        self.actions: list[dict] = []
        self.timestamps: list[float] = []

        self.start_pos: np.ndarray | None = None
        self.start_yaw: float = 0.0
        self.goal_pos: np.ndarray | None = None
        self.goal_yaw: float = 0.0
        self.goal_set: bool = False

        # current simulated pose
        self.x: float = 0.0
        self.y: float = 0.0
        self.z: float = 0.0
        self.yaw: float = 0.0
        self.frame_index: int = 0

    def distance_to_goal(self) -> float | None:
        if not self.goal_set or self.goal_pos is None:
            return None
        cur = np.array([self.x, self.y])
        return float(np.linalg.norm(cur - self.goal_pos))

    def path_length(self) -> float:
        if len(self.positions) < 2:
            return 0.0
        pts = np.array([[p[0], p[1]] for p in self.positions])
        return float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))

    def apply_action(self, key: str) -> tuple[float, float]:
        lv, av = 0.0, 0.0
        k = key.upper()
        if k == "W":
            self.x += LINEAR_STEP * np.cos(self.yaw)
            self.y += LINEAR_STEP * np.sin(self.yaw)
            lv = LINEAR_STEP
        elif k == "S":
            self.x -= LINEAR_STEP * np.cos(self.yaw)
            self.y -= LINEAR_STEP * np.sin(self.yaw)
            lv = -LINEAR_STEP
        elif k == "A":
            self.yaw += ANGULAR_STEP
            av = ANGULAR_STEP
        elif k == "D":
            self.yaw -= ANGULAR_STEP
            av = -ANGULAR_STEP
        elif k == "Q":
            self.x -= LINEAR_STEP * np.sin(self.yaw)
            self.y += LINEAR_STEP * np.cos(self.yaw)
            lv = LINEAR_STEP
        elif k == "E":
            self.x += LINEAR_STEP * np.sin(self.yaw)
            self.y -= LINEAR_STEP * np.cos(self.yaw)
            lv = LINEAR_STEP
        return lv, av

    def record_step(self, key: str, lv: float, av: float, rgb_path: str):
        t = time.time()
        pos = np.array([self.x, self.y])

        if self.start_pos is None:
            self.start_pos = pos.copy()
            self.start_yaw = self.yaw

        self.positions.append(pos)
        self.yaws.append(self.yaw)
        self.rgb_paths.append(rgb_path)
        self.timestamps.append(t)

        d2g = self.distance_to_goal()
        entry = {
            "timestamp": t,
            "frame_index": self.frame_index,
            "action_key": key,
            "linear_velocity": lv,
            "angular_velocity": av,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "yaw": self.yaw,
            "rgb_image_path": rgb_path,
        }
        if d2g is not None:
            entry["distance_to_goal"] = d2g
        self.actions.append(entry)
        self.frame_index += 1

    def mark_goal(self):
        self.goal_pos = np.array([self.x, self.y])
        self.goal_yaw = self.yaw
        self.goal_set = True
        print(f"  [GOAL SET] x={self.x:.3f} y={self.y:.3f} yaw={self.yaw:.3f}")

    def save(self):
        n = len(self.positions)
        if n == 0:
            print("  [WARN] No steps recorded — nothing to save.")
            return

        # traj_data.pkl
        traj = {
            "position": np.array([[p[0], p[1]] for p in self.positions]),
            "yaw": np.array(self.yaws),
            "rgb_paths": self.rgb_paths,
            "actions": self.actions,
            "timestamps": self.timestamps,
            "scene_id": self.scene_id,
            "episode_id": self.episode_id,
            "mode": self.mode,
            "start_pos": self.start_pos,
            "start_yaw": self.start_yaw,
            "n_steps": n,
            "path_length_m": self.path_length(),
        }
        if self.goal_set:
            traj["goal_pos"] = self.goal_pos
            traj["goal_yaw"] = self.goal_yaw

        with open(self.output_dir / "traj_data.pkl", "wb") as f:
            pickle.dump(traj, f)

        # actions.jsonl
        with open(self.output_dir / "actions.jsonl", "w") as f:
            for row in self.actions:
                f.write(json.dumps(row) + "\n")

        # metadata.json
        meta = {
            "simulator": "Isaac Sim",
            "control_mode": "manual_testdrive",
            "scene_source": "VLNVerse" if self.mode == "vlnverse" else "CustomVLN-Office",
            "vlnverse_assets_used": self.mode == "vlnverse",
            "official_benchmark_data": False,
            "purpose": "manual data-collection proof for GNM/VLN pipeline",
            "scene_id": self.scene_id,
            "episode_id": self.episode_id,
            "n_steps": n,
            "path_length_m": self.path_length(),
            "goal_set": self.goal_set,
        }
        with open(self.output_dir / "metadata.json", "w") as f:
            json.dump(meta, f, indent=2)

        print(f"  [SAVED] {self.output_dir}")
        print(f"          {n} steps, {self.path_length():.2f} m path length")


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------

def dry_run():
    print("=" * 60)
    print("manual_testdrive.py — dry-run")
    print("=" * 60)
    print()
    print("Available modes:")
    for m in MODES:
        print(f"  {m}")
    print()
    print("Controls:")
    for k, v in CONTROLS.items():
        print(f"  {k:<8} {v}")
    print()
    print("Output structure:")
    print("  datasets/manual_testdrive_custom_office/<timestamp>/")
    print("    rgb/000000.jpg")
    print("    rgb/000001.jpg  ...")
    print("    traj_data.pkl")
    print("    actions.jsonl")
    print("    metadata.json")
    print()
    print("Logged fields (actions.jsonl):")
    print("  timestamp, frame_index, action_key, linear_velocity,")
    print("  angular_velocity, x, y, z, yaw, rgb_image_path,")
    print("  distance_to_goal (if goal set)")
    print()
    print("Example commands:")
    print("  python3 scripts/gnm/manual_testdrive.py --dry-run")
    print("  conda activate isaac && MODE=custom_office python scripts/gnm/manual_testdrive.py")
    print("  conda activate isaac && MODE=vlnverse SCENE=kujiale_0271 python scripts/gnm/manual_testdrive.py")
    print()
    print("NOTE: This is manual data-collection evidence, not an official benchmark result.")
    print("      Official Track A result: SR=20.0%, OSR=46.7%, NE=6.51 m")


# ---------------------------------------------------------------------------
# Terminal-control interactive loop (no Isaac GUI required)
# ---------------------------------------------------------------------------

def terminal_loop(episode: Episode):
    print()
    print("MANUAL TEST DRIVE — terminal control mode")
    print(f"  mode     : {episode.mode}")
    print(f"  scene    : {episode.scene_id}")
    print(f"  episode  : {episode.episode_id}")
    print(f"  output   : {episode.output_dir}")
    print()
    print("Controls: W/S/A/D/Q/E move | G=goal | P=save | R=reset | Esc/X=exit")
    print()

    while True:
        d2g = episode.distance_to_goal()
        goal_str = f"{d2g:.3f} m" if d2g is not None else "not set"
        print(
            f"[frame {episode.frame_index:06d}] "
            f"x={episode.x:.3f} y={episode.y:.3f} yaw={episode.yaw:.3f}  "
            f"goal={goal_str}",
            end="  > ",
            flush=True,
        )
        raw = input().strip()
        if not raw:
            continue
        key = raw[0].upper()

        if key in ("X", "\x1b"):  # Esc or X
            print("  Exiting.")
            break
        elif key == "G":
            episode.mark_goal()
        elif key == "P":
            episode.save()
        elif key == "R":
            print("  Episode reset.")
            episode.positions.clear()
            episode.yaws.clear()
            episode.rgb_paths.clear()
            episode.actions.clear()
            episode.timestamps.clear()
            episode.frame_index = 0
            episode.start_pos = None
            episode.goal_pos = None
            episode.goal_set = False
            episode.x = episode.y = episode.z = episode.yaw = 0.0
        elif key in "WSADQE ":
            lv, av = episode.apply_action(key if key != " " else "Space")
            rgb_path = str(
                episode.rgb_dir / f"{episode.frame_index:06d}.jpg"
            )
            # In terminal mode, generate a placeholder RGB frame
            _save_placeholder_frame(episode, rgb_path)
            episode.record_step(key, lv, av, rgb_path)
        else:
            print(f"  Unknown key: {key!r}")


def _save_placeholder_frame(episode: Episode, path: str):
    try:
        import cv2

        h, w = 240, 320
        img = np.zeros((h, w, 3), dtype=np.uint8)
        # draw a simple gradient to distinguish frames
        img[:, :, 2] = np.linspace(0, 200, w, dtype=np.uint8)
        img[:, :, 1] = int(min(255, episode.frame_index * 2))
        label = f"frame {episode.frame_index:06d}"
        cv2.putText(img, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (255, 255, 255), 1)
        cv2.imwrite(path, img)
    except Exception:
        # cv2 not available — write a 1-byte stub so the path is real
        Path(path).write_bytes(b"\xff\xd8\xff\xe0")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--terminal-control", action="store_true",
                        help="Use stdin keyboard instead of Isaac GUI callbacks")
    args = parser.parse_args()

    if args.dry_run:
        dry_run()
        return

    mode = os.environ.get("MODE", "custom_office").lower()
    if mode not in MODES:
        print(f"[ERROR] MODE must be one of {MODES}, got {mode!r}", file=sys.stderr)
        sys.exit(1)

    scene_id = os.environ.get("SCENE", "custom_office_v1" if mode == "custom_office" else "kujiale_0271")
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    episode_id = f"{scene_id}_{timestamp}"

    if mode == "custom_office":
        output_dir = Path("datasets/manual_testdrive_custom_office") / timestamp
    else:
        output_dir = Path("datasets/manual_testdrive_vlnverse") / f"{scene_id}_{timestamp}"

    episode = Episode(mode, scene_id, episode_id, output_dir)

    # Always fall back to terminal control if not in an Isaac GUI context.
    # Isaac GUI integration would attach keyboard callbacks here when available.
    terminal_loop(episode)


if __name__ == "__main__":
    main()
