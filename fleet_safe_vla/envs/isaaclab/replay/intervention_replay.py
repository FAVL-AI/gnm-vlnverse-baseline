"""
intervention_replay.py — Orchestrator for the intervention evidence replay viewer.

InterventionReplayViewer ties together:
  ArtifactLoader       — loads evidence from episode directory
  ReplayTimeline       — manages frame stepping and playback state
  SceneGraphRenderer   — produces edge/node render data per frame
  OverlayData          — produces text overlay per frame
  CounterfactualRenderData — produces rollout visualization data

This module is backend-neutral. The Isaac Sim backend is in:
  scripts/isaaclab/replay_intervention.py

The matplotlib/headless backend is in:
  scripts/visualnav/export_intervention_video.py

No Isaac imports here. Importable in CI.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fleet_safe_vla.envs.isaaclab.replay.replay_scene import (
    ArtifactLoader,
    ArtifactManifest,
    ReplayFrame,
)
from fleet_safe_vla.envs.isaaclab.replay.replay_overlay import (
    OverlayData,
    build_overlay,
)
from fleet_safe_vla.envs.isaaclab.replay.scene_graph_visualizer import (
    SceneGraphRenderer,
    GraphEdgeRenderData,
    NodeRenderData,
    SafetyZoneRenderData,
    CounterfactualRenderData,
)
from fleet_safe_vla.envs.isaaclab.replay.trajectory_visualizer import (
    ReplayTimeline,
    TrajectoryData,
    ActionVectorData,
    build_action_vectors,
)


class InterventionReplayViewer:
    """
    Load benchmark episode artifacts and drive frame-by-frame replay.

    Usage
    -----
        viewer = InterventionReplayViewer(episode_dir)
        viewer.load()
        print(viewer.manifest.summary())
        print(viewer.version_warnings())

        for frame in viewer.frames:
            overlay = viewer.overlay_for(frame)
            edges   = viewer.graph_edges_for(frame)
            cf      = viewer.counterfactual_for(frame)
            print(overlay.to_terminal_string())

        # Stepping
        while not viewer.at_end:
            viewer.step_forward()
            print(viewer.current_overlay.to_terminal_string())
    """

    def __init__(
        self,
        episode_dir:    Path,
        run_dir:        Path | None = None,
        safety_margin_m: float = 0.30,
        collision_m:    float  = 0.10,
        scene_id:       str    = "",
    ) -> None:
        self.episode_dir    = Path(episode_dir)
        self.run_dir        = Path(run_dir) if run_dir else None
        self.scene_id       = scene_id
        self._loader        = ArtifactLoader(self.episode_dir, self.run_dir)
        self._renderer      = SceneGraphRenderer(safety_margin_m, collision_m)
        self._timeline: ReplayTimeline | None = None
        self._manifest: ArtifactManifest | None = None
        self._version_info: dict[str, str] = {}

    def load(self) -> "InterventionReplayViewer":
        """Load artifacts. Must be called before any other method."""
        frames, manifest = self._loader.load()
        self._manifest     = manifest
        self._timeline     = ReplayTimeline(frames)
        self._version_info = self._loader.version_info()
        return self

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def manifest(self) -> ArtifactManifest:
        self._require_loaded()
        return self._manifest  # type: ignore[return-value]

    @property
    def frames(self) -> list[ReplayFrame]:
        self._require_loaded()
        return self._timeline._frames  # type: ignore[union-attr]

    @property
    def timeline(self) -> ReplayTimeline:
        self._require_loaded()
        return self._timeline  # type: ignore[return-value]

    @property
    def n_frames(self) -> int:
        self._require_loaded()
        return len(self._timeline)  # type: ignore[arg-type]

    @property
    def intervention_count(self) -> int:
        self._require_loaded()
        return sum(1 for f in self.frames if f.intervention_applied)

    @property
    def at_end(self) -> bool:
        self._require_loaded()
        return self._timeline.frame_idx == len(self._timeline) - 1  # type: ignore[arg-type]

    # ── Playback ──────────────────────────────────────────────────────────────

    def step_forward(self) -> bool:
        self._require_loaded()
        return self._timeline.step_forward()  # type: ignore[union-attr]

    def step_back(self) -> bool:
        self._require_loaded()
        return self._timeline.step_back()  # type: ignore[union-attr]

    def jump_to(self, idx: int) -> None:
        self._require_loaded()
        self._timeline.jump_to(idx)  # type: ignore[union-attr]

    def jump_to_next_intervention(self) -> bool:
        self._require_loaded()
        return self._timeline.jump_to_next_intervention()  # type: ignore[union-attr]

    def jump_to_prev_intervention(self) -> bool:
        self._require_loaded()
        return self._timeline.jump_to_prev_intervention()  # type: ignore[union-attr]

    # ── Per-frame render data ─────────────────────────────────────────────────

    def overlay_for(self, frame: ReplayFrame) -> OverlayData:
        return build_overlay(
            frame=frame,
            total_frames=self.n_frames,
            git_commit=self._version_info.get("git_commit", "unknown"),
            scene_id=self.scene_id,
            missing_artifacts=self._manifest.missing_required if self._manifest else [],
        )

    @property
    def current_overlay(self) -> OverlayData:
        self._require_loaded()
        return self.overlay_for(self._timeline.current)  # type: ignore[union-attr]

    def graph_edges_for(self, frame: ReplayFrame) -> list[GraphEdgeRenderData]:
        return self._renderer.render_edges(frame)

    def graph_nodes_for(self, frame: ReplayFrame) -> list[NodeRenderData]:
        return self._renderer.render_nodes(frame)

    def safety_zones_for(self, frame: ReplayFrame) -> SafetyZoneRenderData:
        return self._renderer.render_safety_zones(frame)

    def counterfactual_for(self, frame: ReplayFrame) -> CounterfactualRenderData:
        return self._renderer.build_counterfactual(frame)

    def action_vectors_for(
        self, frame: ReplayFrame, heading: float = 0.0
    ) -> ActionVectorData:
        return build_action_vectors(frame, heading=heading)

    # ── Validation ────────────────────────────────────────────────────────────

    def version_info(self) -> dict[str, str]:
        """Return version metadata dict (benchmark_version, protocol_version, git_commit, etc.)."""
        self._require_loaded()
        return self._version_info

    def version_warnings(self) -> list[str]:
        """Return version mismatch warnings (empty list if all match)."""
        return self._loader.check_version_mismatch()

    def is_valid(self) -> bool:
        """True if all required artifacts are present and loaded."""
        if self._manifest is None:
            return False
        return self._manifest.is_valid and len(self.frames) > 0

    def print_summary(self) -> None:
        """Print a human-readable summary to stdout."""
        self._require_loaded()
        print(self._manifest.summary())  # type: ignore[union-attr]
        print(f"Frames loaded     : {self.n_frames}")
        print(f"Interventions     : {self.intervention_count}")
        print(f"Intervention frames: {self.timeline.intervention_frames()[:10]}")
        for w in self.version_warnings():
            print(f"VERSION WARNING: {w}")
        if not self.manifest.is_valid:
            print("⚠ ARTIFACT INVALID — required files missing, replay may be incomplete")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _require_loaded(self) -> None:
        if self._timeline is None:
            raise RuntimeError(
                "Call load() before accessing viewer state."
            )
