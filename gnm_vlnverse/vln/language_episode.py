"""Language-annotated navigation episode for Track B evaluation.

Loads episodes from the custom_vln_office format:
    <ep_dir>/
        traj_data.pkl   — dict with keys: position, instruction, goal_pos, ...
        rgb/            — zero-padded JPEG frames  000000.jpg, 000001.jpg, ...
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np


@dataclass
class LanguageEpisode:
    """One language-annotated trajectory episode."""

    episode_id:     str
    instruction:    str
    keyframes:      list   # list of (H, W, 3) uint8 RGB arrays
    positions:      list   # list of (x, y) tuples, one per keyframe
    goal_pos:       tuple  # (x, y) true goal position
    path_length_m:  float
    scene_id:       str = ""

    def __len__(self) -> int:
        return len(self.keyframes)

    def retrieval_error_m(self, retrieved_idx: int) -> float:
        """Euclidean distance between a retrieved keyframe and the true goal."""
        rpos = np.array(self.positions[retrieved_idx])
        gpos = np.array(self.goal_pos)
        return float(np.linalg.norm(rpos - gpos))

    def oracle_idx(self, success_threshold_m: float = 3.0) -> int:
        """Index of the last keyframe within success_threshold_m of the goal.

        This is the best possible retrieval: used as an upper-bound baseline.
        Falls back to the final frame when no keyframe is within threshold.
        """
        goal = np.array(self.goal_pos)
        for i in range(len(self.positions) - 1, -1, -1):
            if np.linalg.norm(np.array(self.positions[i]) - goal) <= success_threshold_m:
                return i
        return len(self.positions) - 1


def load_episode(ep_dir: Path | str, stride: int = 5) -> LanguageEpisode:
    """Load a LanguageEpisode from a custom_vln_office-format directory.

    Parameters
    ----------
    ep_dir : Path
        Episode root containing traj_data.pkl and rgb/.
    stride : int
        Sample every Nth frame for the keyframe map.  Default: 5.
    """
    ep_dir = Path(ep_dir)
    data = pickle.loads((ep_dir / "traj_data.pkl").read_bytes())

    positions_all: np.ndarray = np.asarray(data["position"])
    T = len(positions_all)

    keyframes: list[np.ndarray] = []
    positions: list[tuple[float, float]] = []

    for t in range(0, T, stride):
        rgb_path = ep_dir / "rgb" / f"{t:06d}.jpg"
        if not rgb_path.exists():
            continue
        img = cv2.imread(str(rgb_path))
        if img is None:
            continue
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        keyframes.append(img)
        positions.append((float(positions_all[t][0]), float(positions_all[t][1])))

    goal_raw = data["goal_pos"]
    goal_pos = (float(goal_raw[0]), float(goal_raw[1]))

    return LanguageEpisode(
        episode_id=data.get("episode_id", ep_dir.name),
        instruction=data.get("instruction", ""),
        keyframes=keyframes,
        positions=positions,
        goal_pos=goal_pos,
        path_length_m=float(data.get("path_length_m", 0.0)),
        scene_id=data.get("scene_id", ""),
    )


def load_dataset(
    root: Path | str,
    split: str = "train",
    stride: int = 5,
) -> list[LanguageEpisode]:
    """Load all episodes from a dataset split directory.

    Parameters
    ----------
    root : Path
        Dataset root containing train/ and optionally val/.
    split : str
        Subdirectory name: "train" or "val".
    stride : int
        Keyframe stride forwarded to load_episode.

    Returns
    -------
    List of LanguageEpisode, one per episode directory found.
    """
    split_dir = Path(root) / split
    if not split_dir.is_dir():
        raise FileNotFoundError(f"Split directory not found: {split_dir}")

    episodes: list[LanguageEpisode] = []
    for ep_dir in sorted(split_dir.iterdir()):
        pkl = ep_dir / "traj_data.pkl"
        if not pkl.exists():
            continue
        episodes.append(load_episode(ep_dir, stride=stride))

    return episodes
