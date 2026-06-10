"""GNM trajectory dataset for PyTorch.

How GNM training data works
----------------------------
A training sample is a (observation_stack, goal_image, action, distance) tuple.

  1. Pick a random trajectory.
  2. Pick a random observation index `t_obs`.
  3. Pick a random goal index `t_goal` in [t_obs+1, t_obs+max_goal_dist].
  4. Stack context_size frames ending at t_obs → obs tensor (C×H×W, C=ctx*3).
  5. Use frame at t_goal → goal tensor (3×H×W).
  6. Compute action = (pos[t_goal] - pos[t_obs]) rotated to robot frame.
  7. Compute dist   = (t_goal - t_obs) / max_goal_dist  → [0, 1].

Why rotate to robot frame?
  If the robot is facing North and the goal is East, the raw (Δx, Δy) in world
  coordinates depends on the robot's heading.  Rotating to robot frame gives
  (forward, left) which is the same regardless of world orientation.
  This is the key normalisation that lets GNM generalise across robots.

Why a random goal (not the next step)?
  GNM predicts waypoints up to max_goal_dist steps ahead.  Training with
  diverse distances forces the model to learn both short-range precision
  and long-range planning.

Frame normalisation
-------------------
  mean = [0.485, 0.456, 0.406]   (ImageNet)
  std  = [0.229, 0.224, 0.225]   (ImageNet)

  These constants are used because we initialise from ImageNet-pretrained
  MobileNetV2.  If you train from scratch, compute mean/std from your data.
"""

from __future__ import annotations

import pickle
import random
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from .augmentation import GNMAugmentation

# ImageNet normalisation constants
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Tolerate loading errors up to this fraction of the dataset
_MAX_LOAD_ERROR_FRAC = 0.05


class GNMDataset(Dataset):
    """PyTorch dataset for GNM training.

    Parameters
    ----------
    data_root : Path | str
        Root of converted GNM trajectories (output of VLNTubeConverter).
    context_size : int
        Number of past frames to stack.  Must match the GNM model setting.
    max_goal_dist : int
        Maximum step gap between observation and goal.
    image_size : (int, int)
        (width, height) — must match what the converter produced.
    augment : bool
        Whether to apply colour jitter, random flip, etc.
    action_std : (float, float) | None
        If set, actions are divided by this std before being returned.
        Use the value computed by compute_action_std() on training split.
    split : str
        "train" | "val" | "test"
    """

    def __init__(
        self,
        data_root: Path | str,
        context_size: int = 5,
        max_goal_dist: int = 20,
        image_size: tuple[int, int] = (96, 96),
        augment: bool = True,
        action_std: Optional[tuple[float, float]] = None,
        split: str = "train",
        allow_scenes: Optional[list[str]] = None,
    ) -> None:
        self.data_root      = Path(data_root) / split
        self.context_size   = context_size
        self.max_goal_dist  = max_goal_dist
        self.image_size     = image_size
        self.augment        = augment
        self.action_std     = np.array(action_std, dtype=np.float32) if action_std else None
        self.split          = split
        self.allow_scenes   = set(allow_scenes) if allow_scenes else None
        self.augmenter      = GNMAugmentation() if augment and split == "train" else None

        self.trajectories: list[dict] = []
        self._load_trajectories()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _load_trajectories(self) -> None:
        if not self.data_root.exists():
            raise FileNotFoundError(
                f"Dataset root not found: {self.data_root}\n"
                f"Run: python scripts/gnm/02_convert_data.py"
            )

        all_dirs = sorted(
            d for d in self.data_root.iterdir()
            if d.is_dir() and (d / "traj_data.pkl").exists()
        )
        if self.allow_scenes is not None:
            traj_dirs = [
                d for d in all_dirs
                if "_".join(d.name.split("_")[:2]) in self.allow_scenes
            ]
        else:
            traj_dirs = all_dirs

        errors = 0
        for traj_dir in traj_dirs:
            try:
                self.trajectories.append(self._load_traj_meta(traj_dir))
            except Exception as e:
                errors += 1
                if errors / max(len(traj_dirs), 1) > _MAX_LOAD_ERROR_FRAC:
                    raise RuntimeError(
                        f"Too many trajectory load errors ({errors}/{len(traj_dirs)}). "
                        f"Last: {e}"
                    )

        if not self.trajectories:
            raise RuntimeError(f"No valid trajectories found in {self.data_root}")

    def _load_traj_meta(self, traj_dir: Path) -> dict:
        with open(traj_dir / "traj_data.pkl", "rb") as f:
            data = pickle.load(f)
        positions = data["position"]  # (T, 2)
        yaws      = data["yaw"]       # (T,)
        T         = len(positions)
        return {
            "dir":       traj_dir,
            "positions": positions,
            "yaws":      yaws,
            "length":    T,
        }

    # ── Dataset interface ─────────────────────────────────────────────────────

    def __len__(self) -> int:
        # Each trajectory contributes (T - 1) possible observation steps
        return sum(max(t["length"] - 1, 0) for t in self.trajectories)

    def __getitem__(self, idx: int) -> dict:
        traj, t_obs = self._resolve_index(idx)

        # Sample goal uniformly in [t_obs+1, min(t_obs+max_goal_dist, T-1)]
        t_goal = random.randint(
            t_obs + 1,
            min(t_obs + self.max_goal_dist, traj["length"] - 1),
        )

        obs    = self._load_obs(traj, t_obs)       # (ctx*3, H, W)
        goal   = self._load_frame(traj["dir"], t_goal)  # (3, H, W)
        action = self._compute_action(traj, t_obs, t_goal)  # (2,)
        dist   = (t_goal - t_obs) / self.max_goal_dist      # scalar

        if self.augmenter is not None:
            obs, goal = self.augmenter(obs, goal)

        return {
            "obs":    obs,
            "goal":   goal,
            "action": torch.tensor(action, dtype=torch.float32),
            "dist":   torch.tensor(dist,   dtype=torch.float32).unsqueeze(0),
            "traj_id": traj["dir"].name,
            "t_obs":   t_obs,
            "t_goal":  t_goal,
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _resolve_index(self, idx: int) -> tuple[dict, int]:
        for traj in self.trajectories:
            usable = max(traj["length"] - 1, 0)
            if idx < usable:
                return traj, idx
            idx -= usable
        raise IndexError("Index out of range")

    def _load_obs(self, traj: dict, t_obs: int) -> torch.Tensor:
        """Stack context_size frames ending at t_obs."""
        frames = []
        for i in range(self.context_size):
            t = max(t_obs - (self.context_size - 1 - i), 0)
            frames.append(self._load_frame(traj["dir"], t))
        return torch.cat(frames, dim=0)  # (ctx*3, H, W)

    def _load_frame(self, traj_dir: Path, t: int) -> torch.Tensor:
        img_path = traj_dir / f"{t}.jpg"
        if img_path.exists():
            img = cv2.imread(str(img_path))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        else:
            img = np.zeros((*self.image_size[::-1], 3), dtype=np.uint8)

        h, w = self.image_size[1], self.image_size[0]
        if img.shape[0] != h or img.shape[1] != w:
            img = cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR)

        img = img.astype(np.float32) / 255.0
        img = (img - _MEAN) / _STD
        return torch.from_numpy(img).permute(2, 0, 1)  # (3, H, W)

    def _compute_action(
        self,
        traj: dict,
        t_obs: int,
        t_goal: int,
    ) -> np.ndarray:
        """Compute immediate next-step (Δx, Δy) waypoint in robot frame.

        GNM learns to take one step toward the goal at each inference step.
        The action is therefore t_obs→t_obs+1, not t_obs→t_goal.
        The goal image provides long-range context; the action provides the
        immediate next move.  This keeps action magnitudes to ≈1 normalized
        unit regardless of how far the goal is.
        """
        t_next   = min(t_obs + 1, traj["length"] - 1)
        pos_obs  = traj["positions"][t_obs]
        pos_next = traj["positions"][t_next]
        yaw_obs  = traj["yaws"][t_obs]

        dx_world = pos_next[0] - pos_obs[0]
        dy_world = pos_next[1] - pos_obs[1]

        # Rotate world → robot frame
        cos_y =  np.cos(yaw_obs)
        sin_y =  np.sin(yaw_obs)
        dx_robot =  cos_y * dx_world + sin_y * dy_world
        dy_robot = -sin_y * dx_world + cos_y * dy_world

        action = np.array([dx_robot, dy_robot], dtype=np.float32)

        if self.action_std is not None:
            action = action / self.action_std

        return action


def collate_gnm(batch: list[dict]) -> dict:
    """Custom collate that handles string fields ('traj_id')."""
    keys = batch[0].keys()
    out  = {}
    for k in keys:
        vals = [item[k] for item in batch]
        if isinstance(vals[0], torch.Tensor):
            out[k] = torch.stack(vals, dim=0)
        else:
            out[k] = vals
    return out
