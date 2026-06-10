"""GNMEvaluator — run GNM inference episodes and collect VLNVerse metrics.

How an evaluation episode works
---------------------------------
  1. Reset Isaac Sim to the episode's start position.
  2. Load the goal image (for Track A/C) or instruction (for Track B).
  3. For each step:
       a. Capture current RGB observation.
       b. Stack with context buffer.
       c. Forward pass through GNM → (dist_pred, action_pred).
       d. Denormalize action_pred by action_std.
       e. Convert (Δx, Δy) → velocity command → send to robot.
       f. Step Isaac Sim.
       g. Log position, collision flag.
  4. Stop when dist_pred < stop_threshold OR max_steps reached.
  5. Compute all metrics for this episode.

Stopping condition
  The robot stops when predicted distance < stop_threshold.
  This is the only information it has about "am I at the goal?"
  Do NOT use ground-truth goal position at test time.

Track separation (critical for reviewers)
  Track A: goal = final frame from the reference trajectory
  Track B: goal = retrieved subgoal from history/topo map
  Track C: goal = Track A or B, plus LoRA-adapted weights

  These must NOT be mixed. The track is logged in every output file.
"""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import torch

from .metrics import Episode, NavigationMetrics, compute_all_metrics

logger = logging.getLogger(__name__)


class GNMEvaluator:
    """Run GNM inference and compute VLNVerse evaluation metrics.

    Parameters
    ----------
    model : torch.nn.Module
        Trained GNM (or LoRA-GNM).
    action_std : (float, float)
        Action denormalization standard deviation.
    context_size : int
        Must match training context_size.
    image_size : (int, int)
        (width, height) of input images.
    stop_threshold : float
        Predicted normalised distance below which the robot stops.
    max_steps : int
        Hard limit per episode.
    device : str
        "cuda" | "cpu".
    track : str
        "A" | "B" | "C" (for logging/output naming).
    """

    def __init__(
        self,
        model: torch.nn.Module,
        action_std: tuple[float, float],
        context_size: int = 5,
        image_size: tuple[int, int] = (96, 96),
        stop_threshold: float = 0.15,
        max_steps: int = 500,
        device: str = "cuda",
        track: str = "A",
    ) -> None:
        self.model          = model
        self.action_std     = np.array(action_std, dtype=np.float32)
        self.context_size   = context_size
        self.image_size     = image_size
        self.stop_threshold = stop_threshold
        self.max_steps      = max_steps
        self.device         = torch.device(device if torch.cuda.is_available() else "cpu")
        self.track          = track

        self.model.to(self.device)
        self.model.eval()

        # Circular context buffer: list of frame tensors (3, H, W)
        self._context: list[torch.Tensor] = []

    # ── Context management ────────────────────────────────────────────────────

    def reset_context(self, first_frame: np.ndarray) -> None:
        """Fill context buffer with copies of the first frame."""
        frame = self._preprocess(first_frame)
        self._context = [frame.clone() for _ in range(self.context_size)]

    def push_frame(self, frame: np.ndarray) -> None:
        self._context.pop(0)
        self._context.append(self._preprocess(frame))

    def get_obs_tensor(self) -> torch.Tensor:
        """Stack context into (1, ctx*3, H, W) tensor on device."""
        stacked = torch.cat(self._context, dim=0).unsqueeze(0)
        return stacked.to(self.device)

    # ── Inference ─────────────────────────────────────────────────────────────

    @torch.no_grad()
    def predict(
        self,
        obs: np.ndarray,
        goal: np.ndarray,
    ) -> tuple[float, np.ndarray]:
        """Single GNM forward pass.

        Parameters
        ----------
        obs  : (H, W, 3) current RGB frame (uint8)
        goal : (H, W, 3) goal RGB frame (uint8)

        Returns
        -------
        dist_pred    : float — normalised predicted distance
        action_pred  : (2,) array — Δx, Δy in robot frame (real units)
        """
        self.push_frame(obs)
        obs_t  = self.get_obs_tensor()                            # (1, ctx*3, H, W)
        goal_t = self._preprocess(goal).unsqueeze(0).to(self.device)  # (1, 3, H, W)

        dist_t, action_t = self.model(obs_t, goal_t)

        dist_val   = float(dist_t.squeeze().cpu())
        action_val = action_t.squeeze().cpu().numpy() * self.action_std

        return dist_val, action_val

    # ── Episode evaluation (file-based, no Isaac) ─────────────────────────────

    def evaluate_from_files(
        self,
        traj_dir: Path | str,
        goal_idx: int = -1,
        output_path: Optional[Path] = None,
    ) -> Episode:
        """Run GNM inference on a saved trajectory (for offline evaluation).

        Useful for reproducible benchmark runs without a live Isaac instance.
        The reference path and ground-truth positions are read from traj_data.pkl;
        GNM predicts actions and we simulate a simple single-integrator robot
        (no physics — for physics evaluation, use evaluate_in_isaac()).

        Parameters
        ----------
        traj_dir : Path
            GNM-format trajectory directory.
        goal_idx : int
            Index of the goal frame.  -1 = last frame.
        output_path : Path, optional
            Where to write episode_result.json.
        """
        traj_dir = Path(traj_dir)
        with open(traj_dir / "traj_data.pkl", "rb") as f:
            data = pickle.load(f)

        positions_gt = data["position"]  # (T, 2)
        yaws_gt      = data["yaw"]       # (T,)
        T            = len(positions_gt)

        if goal_idx == -1:
            goal_idx = T - 1

        goal_frame   = self._load_frame(traj_dir, goal_idx)
        goal_pos     = tuple(positions_gt[goal_idx].tolist())

        # ── Simulate offline rollout ──────────────────────────────────────────
        start_frame = self._load_frame_np(traj_dir, 0)
        self.reset_context(start_frame)

        sim_pos  = np.array(positions_gt[0], dtype=np.float32)
        sim_yaw  = float(yaws_gt[0])
        actual_path: list[tuple[float, float]] = [tuple(sim_pos.tolist())]
        collisions: list[bool] = []

        for step in range(min(T - 1, self.max_steps)):
            frame_np   = self._load_frame_np(traj_dir, min(step, T - 1))
            goal_np    = self._load_frame_np(traj_dir, goal_idx)
            dist_pred, action_pred = self.predict(frame_np, goal_np)

            # Single-integrator simulation (no physics)
            cos_y = np.cos(sim_yaw)
            sin_y = np.sin(sim_yaw)
            dx_world = cos_y * action_pred[0] - sin_y * action_pred[1]
            dy_world = sin_y * action_pred[0] + cos_y * action_pred[1]
            sim_pos  = sim_pos + np.array([dx_world, dy_world])
            actual_path.append(tuple(sim_pos.tolist()))
            collisions.append(False)  # no physics collision in offline mode

            if dist_pred < self.stop_threshold:
                logger.debug(f"Stopped at step {step} (dist_pred={dist_pred:.3f})")
                break

        ref_path = [tuple(p.tolist()) for p in positions_gt]
        episode  = Episode(
            actual_path=actual_path,
            reference_path=ref_path,
            goal_pos=goal_pos,
            collisions=collisions,
        )

        if output_path:
            self._save_result(episode, output_path)

        return episode

    def evaluate_dataset(
        self,
        data_root: Path | str,
        split: str = "val",
        output_dir: Optional[Path] = None,
        allow_scenes: Optional[list[str]] = None,
    ) -> NavigationMetrics:
        """Evaluate on all trajectories in a split, optionally filtered to specific scenes."""
        data_root = Path(data_root) / split
        all_dirs  = sorted(d for d in data_root.iterdir() if d.is_dir())
        if allow_scenes is not None:
            scene_set = set(allow_scenes)
            traj_dirs = [d for d in all_dirs
                         if "_".join(d.name.split("_")[:2]) in scene_set]
        else:
            traj_dirs = all_dirs
        episodes  = []

        for traj_dir in traj_dirs:
            try:
                out = (output_dir / traj_dir.name / "episode_result.json"
                       if output_dir else None)
                if out:
                    out.parent.mkdir(parents=True, exist_ok=True)
                ep = self.evaluate_from_files(traj_dir, output_path=out)
                episodes.append(ep)
            except Exception as e:
                logger.warning(f"Skipping {traj_dir.name}: {e}")

        metrics = compute_all_metrics(episodes)
        logger.info(f"Track {self.track} [{split}]: {metrics}")
        return metrics

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _preprocess(self, img: np.ndarray) -> torch.Tensor:
        """(H, W, 3) uint8 → (3, H, W) float normalised tensor."""
        import cv2
        _MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        _STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img = cv2.resize(img, self.image_size)
        img = img.astype(np.float32) / 255.0
        img = (img - _MEAN) / _STD
        return torch.from_numpy(img).permute(2, 0, 1)

    def _load_frame(self, traj_dir: Path, idx: int) -> torch.Tensor:
        import cv2
        p = traj_dir / f"{idx}.jpg"
        img = cv2.imread(str(p)) if p.exists() else np.zeros((*self.image_size[::-1], 3), np.uint8)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return self._preprocess(img)

    def _load_frame_np(self, traj_dir: Path, idx: int) -> np.ndarray:
        import cv2
        p = traj_dir / f"{idx}.jpg"
        img = cv2.imread(str(p)) if p.exists() else np.zeros((*self.image_size[::-1], 3), np.uint8)
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    def _save_result(self, episode: Episode, path: Path) -> None:
        from .metrics import (nav_error, success, oracle_success, spl,
                               ndtw, cls, collision_rate, path_length)
        ne   = nav_error(episode.actual_path, episode.goal_pos)
        s    = success(ne)
        osr  = oracle_success(episode.actual_path, episode.goal_pos)
        ref_len = path_length(episode.reference_path)
        result = {
            "track":    self.track,
            "SR":       float(s),
            "OSR":      float(osr),
            "SPL":      spl(s, episode.actual_path, ref_len),
            "NE":       ne,
            "TL":       path_length(episode.actual_path),
            "nDTW":     ndtw(episode.actual_path, episode.reference_path),
            "CLS":      cls(episode.actual_path, episode.reference_path),
            "CR":       collision_rate(episode.collisions),
            "n_steps":  len(episode.actual_path),
        }
        path.write_text(json.dumps(result, indent=2))
