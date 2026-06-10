"""
trajectory_visualizer.py — Trajectory and action vector rendering data.

Produces TrajectoryData and ActionVectorData for visualizing:
  - Robot pose trail (past trajectory)
  - Raw action vector (what the policy wanted)
  - Safe action vector (what FleetSafe executed)
  - Intervention delta vector (difference)
  - Counterfactual rollout paths

No Isaac imports. Importable in CI.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from fleet_safe_vla.envs.isaaclab.replay.replay_scene import ReplayFrame


# ── Action vectors ────────────────────────────────────────────────────────────

@dataclass
class ActionVectorData:
    """
    Rendering data for the raw, safe, and delta action vectors at one frame.

    Vectors are in 2-D world frame, originating at robot_xy.
    wz (angular rate) is visualized as a small arc indicator, not a linear vector.
    """
    robot_x:       float
    robot_y:       float
    robot_heading: float       # radians

    # Raw (unintervened) policy action
    raw_vx_world:  float
    raw_vy_world:  float
    raw_wz:        float
    raw_color:     tuple[float, float, float] = (0.9, 0.2, 0.1)   # red

    # Safe (FleetSafe-corrected) action
    safe_vx_world: float = 0.0
    safe_vy_world: float = 0.0
    safe_wz:       float = 0.0
    safe_color:    tuple[float, float, float] = (0.1, 0.8, 0.2)   # green

    # Intervention delta
    delta_vx_world: float = 0.0
    delta_vy_world: float = 0.0
    delta_color:    tuple[float, float, float] = (0.9, 0.6, 0.0)  # orange

    scale:          float = 1.5    # visual scale multiplier for arrow length

    @property
    def raw_tip_xy(self) -> tuple[float, float]:
        return (
            self.robot_x + self.raw_vx_world * self.scale,
            self.robot_y + self.raw_vy_world * self.scale,
        )

    @property
    def safe_tip_xy(self) -> tuple[float, float]:
        return (
            self.robot_x + self.safe_vx_world * self.scale,
            self.robot_y + self.safe_vy_world * self.scale,
        )

    @property
    def delta_tip_xy(self) -> tuple[float, float]:
        return (
            self.robot_x + self.delta_vx_world * self.scale,
            self.robot_y + self.delta_vy_world * self.scale,
        )


def _body_to_world(
    vx_body: float,
    vy_body: float,
    heading: float,
) -> tuple[float, float]:
    """Convert body-frame velocity to world frame."""
    cos_h = math.cos(heading)
    sin_h = math.sin(heading)
    return (
        vx_body * cos_h - vy_body * sin_h,
        vx_body * sin_h + vy_body * cos_h,
    )


def build_action_vectors(
    frame: ReplayFrame,
    heading: float = 0.0,
    scale: float = 1.5,
) -> ActionVectorData:
    """Build ActionVectorData from a ReplayFrame."""
    raw_vx_w, raw_vy_w  = _body_to_world(frame.raw_action[0],  frame.raw_action[1],  heading)
    safe_vx_w, safe_vy_w = _body_to_world(frame.safe_action[0], frame.safe_action[1], heading)
    delta_vx_w = safe_vx_w - raw_vx_w
    delta_vy_w = safe_vy_w - raw_vy_w

    return ActionVectorData(
        robot_x=frame.robot_x,
        robot_y=frame.robot_y,
        robot_heading=heading,
        raw_vx_world=raw_vx_w,
        raw_vy_world=raw_vy_w,
        raw_wz=frame.raw_action[2],
        safe_vx_world=safe_vx_w,
        safe_vy_world=safe_vy_w,
        safe_wz=frame.safe_action[2],
        delta_vx_world=delta_vx_w,
        delta_vy_world=delta_vy_w,
        scale=scale,
    )


# ── Trajectory trail ──────────────────────────────────────────────────────────

@dataclass
class TrailPoint:
    x:               float
    y:               float
    frame_idx:       int
    intervention:    bool
    color_rgb:       tuple[float, float, float]


@dataclass
class TrajectoryData:
    """
    Full trajectory trail built from all replay frames.

    The trail is colored per-point:
      red    — intervention step
      yellow — near-violation step
      green  — normal step
    """
    points: list[TrailPoint] = field(default_factory=list)

    def add_frame(self, frame: ReplayFrame) -> None:
        if frame.intervention_applied:
            color = (0.9, 0.1, 0.1)   # red
        elif frame.nearest_obstacle_distance_m < 0.45:
            color = (0.9, 0.8, 0.0)   # yellow
        else:
            color = (0.1, 0.8, 0.1)   # green

        self.points.append(TrailPoint(
            x=frame.robot_x,
            y=frame.robot_y,
            frame_idx=frame.frame_idx,
            intervention=frame.intervention_applied,
            color_rgb=color,
        ))

    def get_trail_up_to(self, frame_idx: int) -> list[TrailPoint]:
        """Return all trail points up to and including frame_idx."""
        return [p for p in self.points if p.frame_idx <= frame_idx]

    def intervention_frames(self) -> list[int]:
        return [p.frame_idx for p in self.points if p.intervention]

    @classmethod
    def build(cls, frames: list[ReplayFrame]) -> "TrajectoryData":
        td = cls()
        for frame in frames:
            td.add_frame(frame)
        return td


# ── Timeline ──────────────────────────────────────────────────────────────────

class ReplayTimeline:
    """
    Frame-indexed replay controller.

    Manages playback state (current frame, speed, pause) for use by both
    the Isaac viewer and the matplotlib exporter.
    """

    def __init__(self, frames: list[ReplayFrame]) -> None:
        self._frames         = frames
        self._current_idx    = 0
        self._paused         = False
        self._playback_speed = 1.0
        self._trajectory     = TrajectoryData.build(frames)

    # ── Frame access ───────────────────────────────────────────────────────────

    @property
    def current(self) -> ReplayFrame:
        return self._frames[self._current_idx]

    @property
    def n_frames(self) -> int:
        return len(self._frames)

    @property
    def frame_idx(self) -> int:
        return self._current_idx

    def at(self, idx: int) -> ReplayFrame:
        return self._frames[max(0, min(idx, len(self._frames) - 1))]

    def __len__(self) -> int:
        return len(self._frames)

    # ── Playback controls ──────────────────────────────────────────────────────

    def step_forward(self) -> bool:
        """Advance one frame. Returns False if at end."""
        if self._current_idx < len(self._frames) - 1:
            self._current_idx += 1
            return True
        return False

    def step_back(self) -> bool:
        """Go back one frame. Returns False if at start."""
        if self._current_idx > 0:
            self._current_idx -= 1
            return True
        return False

    def jump_to(self, idx: int) -> None:
        self._current_idx = max(0, min(idx, len(self._frames) - 1))

    def jump_to_next_intervention(self) -> bool:
        """Jump to the next intervention frame after current. Returns False if none."""
        for i, frame in enumerate(self._frames):
            if i > self._current_idx and frame.intervention_applied:
                self._current_idx = i
                return True
        return False

    def jump_to_prev_intervention(self) -> bool:
        """Jump to the previous intervention frame before current."""
        for i in range(self._current_idx - 1, -1, -1):
            if self._frames[i].intervention_applied:
                self._current_idx = i
                return True
        return False

    def toggle_pause(self) -> None:
        self._paused = not self._paused

    @property
    def paused(self) -> bool:
        return self._paused

    def set_speed(self, speed: float) -> None:
        self._playback_speed = max(0.1, speed)

    @property
    def playback_speed(self) -> float:
        return self._playback_speed

    # ── Trajectory data ────────────────────────────────────────────────────────

    @property
    def trajectory(self) -> TrajectoryData:
        return self._trajectory

    def intervention_frames(self) -> list[int]:
        return self._trajectory.intervention_frames()

    def trail_up_to_current(self) -> list[TrailPoint]:
        return self._trajectory.get_trail_up_to(self._current_idx)
