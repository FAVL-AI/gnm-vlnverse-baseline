"""
replay_scene.py — Frame data structures and artifact loader for intervention replay.

All classes are pure Python (no Isaac imports). Importable in CI without the
isaac conda environment.

Artifact contract
-----------------
Required files in an episode directory:
  intervention_evidence.jsonl  — one record per step (primary replay source)
  metadata.yaml                — run-level metadata (version fields, backend)

Optional files (loaded when present):
  scene_graphs.jsonl           — supplementary graph data
  trajectory.csv               — x,y,heading per step
  actions.csv                  — raw/safe cmd_vel per step

Missing required files produce explicit ArtifactWarning records; no silent
fallback is performed.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Artifact manifest ─────────────────────────────────────────────────────────

REQUIRED_ARTIFACT_FILES = [
    "intervention_evidence.jsonl",
    "metadata.yaml",
]

OPTIONAL_ARTIFACT_FILES = [
    "scene_graphs.jsonl",
    "trajectory.csv",
    "actions.csv",
    "safety_events.jsonl",
    "audit_trail.json",
]


@dataclass
class ArtifactManifest:
    """Which artifact files are present or missing in the episode directory."""
    episode_dir:       Path
    present:           list[str]  = field(default_factory=list)
    missing_required:  list[str]  = field(default_factory=list)
    missing_optional:  list[str]  = field(default_factory=list)
    warnings:          list[str]  = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.missing_required) == 0

    def summary(self) -> str:
        lines = [f"Artifact manifest for {self.episode_dir}:"]
        for f in self.present:
            lines.append(f"  [OK]     {f}")
        for f in self.missing_required:
            lines.append(f"  [MISS!]  {f}  (REQUIRED)")
        for f in self.missing_optional:
            lines.append(f"  [miss]   {f}  (optional)")
        for w in self.warnings:
            lines.append(f"  [WARN]   {w}")
        return "\n".join(lines)


# ── Per-frame replay data ─────────────────────────────────────────────────────

@dataclass
class ObstacleState:
    """State of one obstacle at a replay frame."""
    node_id:   str
    node_type: str
    x:         float
    y:         float
    radius_m:  float


@dataclass
class GraphEdgeState:
    """One scene graph edge at a replay frame."""
    source_id:  str
    target_id:  str
    relation:   str
    distance_m: float
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReplayFrame:
    """All replay data for one episode step."""
    frame_idx:                   int
    timestamp:                   float
    robot_x:                     float
    robot_y:                     float
    robot_vx:                    float             # world-frame velocity from graph
    robot_vy:                    float
    raw_action:                  tuple[float, float, float]   # (vx, vy, wz)
    safe_action:                 tuple[float, float, float]
    action_delta:                tuple[float, float, float]
    intervention_applied:        bool
    intervention_reason:         str
    safety_margin_before:        float
    safety_margin_after:         float
    nearest_obstacle_id:         str
    nearest_obstacle_distance_m: float
    active_constraints:          list[str]
    causal_explanation:          str
    counterfactual_explanation:  str
    counterfactual_rollout_id:   str
    scene_graph_before:          dict[str, Any]
    scene_graph_after:           dict[str, Any]
    scene_graph_delta:           dict[str, Any]
    obstacles:                   list[ObstacleState]
    edges:                       list[GraphEdgeState]
    goal_xy:                     tuple[float, float] | None
    reproducibility_hash:        str
    backend:                     str
    model_name:                  str
    benchmark_version:           str
    # Social-risk zone (populated when social_awareness layer active; default=GREEN)
    active_safety_zone:          str   = "GREEN"
    safety_zone_reason:          str   = ""
    crowding_risk_score:         float = 0.0
    occlusion_risk_score:        float = 0.0
    rare_event_count:            int   = 0
    environment_profile:         str   = "default"

    @property
    def robot_xy(self) -> tuple[float, float]:
        return (self.robot_x, self.robot_y)

    @property
    def action_delta_l2(self) -> float:
        return (
            self.action_delta[0] ** 2 +
            self.action_delta[1] ** 2 +
            self.action_delta[2] ** 2
        ) ** 0.5


# ── Metadata parser ───────────────────────────────────────────────────────────

def _parse_metadata_yaml(path: Path) -> dict[str, str]:
    """Parse the simple key: value metadata.yaml (no PyYAML required)."""
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


# ── Graph node/edge extractor ─────────────────────────────────────────────────

def _extract_obstacles(graph_dict: dict) -> list[ObstacleState]:
    obstacle_types = {"obstacle", "wall", "dynamic_agent"}
    result = []
    for node in graph_dict.get("nodes", []):
        if node.get("node_type") in obstacle_types:
            pos = node.get("position", [0.0, 0.0])
            result.append(ObstacleState(
                node_id=node["node_id"],
                node_type=node["node_type"],
                x=float(pos[0]),
                y=float(pos[1]),
                radius_m=float(node.get("radius_m", 0.15)),
            ))
    return result


def _extract_goal(graph_dict: dict) -> tuple[float, float] | None:
    for node in graph_dict.get("nodes", []):
        if node.get("node_type") == "goal":
            pos = node.get("position", [0.0, 0.0])
            return (float(pos[0]), float(pos[1]))
    return None


def _extract_edges(graph_dict: dict) -> list[GraphEdgeState]:
    result = []
    for edge in graph_dict.get("edges", []):
        result.append(GraphEdgeState(
            source_id=edge.get("source_id", ""),
            target_id=edge.get("target_id", ""),
            relation=edge.get("relation", ""),
            distance_m=float(edge.get("distance_m", 0.0)),
            attributes=edge.get("attributes", {}),
        ))
    return result


def _robot_velocity_from_graph(graph_dict: dict) -> tuple[float, float]:
    for node in graph_dict.get("nodes", []):
        if node.get("node_id") == "robot":
            vel = node.get("velocity", [0.0, 0.0])
            return (float(vel[0]), float(vel[1]))
    return (0.0, 0.0)


def _robot_xy_from_graph(graph_dict: dict) -> tuple[float, float]:
    for node in graph_dict.get("nodes", []):
        if node.get("node_id") == "robot":
            pos = node.get("position", [0.0, 0.0])
            return (float(pos[0]), float(pos[1]))
    return (0.0, 0.0)


# ── Artifact loader ───────────────────────────────────────────────────────────

class ArtifactLoader:
    """
    Load and parse all episode artifacts into a list of ReplayFrames.

    Parameters
    ----------
    episode_dir : Path to an episode directory (contains intervention_evidence.jsonl etc.)
    run_dir     : Optional path to the run-level directory (contains metadata.yaml).
                  If None, looks for metadata.yaml in episode_dir and its parent.
    """

    def __init__(self, episode_dir: Path, run_dir: Path | None = None) -> None:
        self.episode_dir = Path(episode_dir)
        self.run_dir = Path(run_dir) if run_dir else self._find_run_dir()

    def _find_run_dir(self) -> Path:
        """Walk up from episode_dir to find metadata.yaml."""
        for parent in [self.episode_dir, self.episode_dir.parent, self.episode_dir.parent.parent]:
            if (parent / "metadata.yaml").exists():
                return parent
        return self.episode_dir

    def check_manifest(self) -> ArtifactManifest:
        """Return the artifact manifest without loading data."""
        manifest = ArtifactManifest(episode_dir=self.episode_dir)
        for fname in REQUIRED_ARTIFACT_FILES:
            search_dirs = [self.episode_dir, self.run_dir]
            found = any((d / fname).exists() for d in search_dirs)
            if found:
                manifest.present.append(fname)
            else:
                manifest.missing_required.append(fname)
        for fname in OPTIONAL_ARTIFACT_FILES:
            if (self.episode_dir / fname).exists():
                manifest.present.append(fname)
            else:
                manifest.missing_optional.append(fname)
        return manifest

    def load(self) -> tuple[list[ReplayFrame], ArtifactManifest]:
        """
        Load all artifacts and return (frames, manifest).

        If required files are missing, manifest.is_valid is False and frames
        may be incomplete.  Callers must check manifest.is_valid.
        """
        manifest = self.check_manifest()
        meta = self._load_metadata()
        frames = self._load_evidence_frames(meta)
        return frames, manifest

    def _load_metadata(self) -> dict[str, str]:
        for d in [self.run_dir, self.episode_dir]:
            p = d / "metadata.yaml"
            if p.exists():
                return _parse_metadata_yaml(p)
        return {}

    def _load_evidence_frames(self, meta: dict[str, str]) -> list[ReplayFrame]:
        ev_path = self.episode_dir / "intervention_evidence.jsonl"
        if not ev_path.exists():
            return []

        backend      = meta.get("backend", "unknown")
        model_name   = meta.get("model", "unknown")
        bench_ver    = meta.get("benchmark_version", "unknown")

        frames: list[ReplayFrame] = []
        for line in ev_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            graph_before = ev.get("scene_graph_before", {})
            graph_after  = ev.get("scene_graph_after",  {})

            robot_xy = _robot_xy_from_graph(graph_before)
            robot_vx, robot_vy = _robot_velocity_from_graph(graph_before)

            raw = tuple(float(x) for x in ev.get("raw_action",  [0.0, 0.0, 0.0]))
            safe = tuple(float(x) for x in ev.get("safe_action", [0.0, 0.0, 0.0]))
            delta = tuple(float(x) for x in ev.get("action_delta", [0.0, 0.0, 0.0]))

            frame = ReplayFrame(
                frame_idx=int(ev.get("step_idx", len(frames))),
                timestamp=float(ev.get("timestamp", 0.0)),
                robot_x=robot_xy[0],
                robot_y=robot_xy[1],
                robot_vx=robot_vx,
                robot_vy=robot_vy,
                raw_action=raw,
                safe_action=safe,
                action_delta=delta,
                intervention_applied=bool(ev.get("intervention_applied", False)),
                intervention_reason=str(ev.get("intervention_reason", "")),
                safety_margin_before=float(ev.get("safety_margin_before", float("inf"))),
                safety_margin_after=float(ev.get("safety_margin_after", float("inf"))),
                nearest_obstacle_id=str(ev.get("nearest_obstacle_id", "none")),
                nearest_obstacle_distance_m=float(ev.get("nearest_obstacle_distance_m", float("inf"))),
                active_constraints=list(ev.get("active_constraints", [])),
                causal_explanation=str(ev.get("causal_explanation", "")),
                counterfactual_explanation=str(ev.get("counterfactual_explanation", "")),
                counterfactual_rollout_id=str(ev.get("counterfactual_rollout_id", "")),
                scene_graph_before=graph_before,
                scene_graph_after=graph_after,
                scene_graph_delta=ev.get("scene_graph_delta", {}),
                obstacles=_extract_obstacles(graph_before),
                edges=_extract_edges(graph_before),
                goal_xy=_extract_goal(graph_before),
                reproducibility_hash=str(ev.get("reproducibility_hash", "")),
                backend=backend or str(ev.get("backend", "unknown")),
                model_name=model_name or str(ev.get("model_name", "unknown")),
                benchmark_version=bench_ver or str(ev.get("benchmark_version", "unknown")),
                # Social-risk zone fields (present when social_awareness layer wrote them)
                active_safety_zone=str(ev.get("active_safety_zone", "GREEN")),
                safety_zone_reason=str(ev.get("safety_zone_reason", "")),
                crowding_risk_score=float(ev.get("crowding_risk_score", 0.0)),
                occlusion_risk_score=float(ev.get("occlusion_risk_score", 0.0)),
                rare_event_count=int(ev.get("rare_event_count", 0)),
                environment_profile=str(ev.get("environment_profile", "default")),
            )
            frames.append(frame)

        return sorted(frames, key=lambda f: f.frame_idx)

    def version_info(self) -> dict[str, str]:
        """Return version fields from metadata."""
        meta = self._load_metadata()
        return {
            "benchmark_version": meta.get("benchmark_version", "unknown"),
            "protocol_version":  meta.get("protocol_version",  "unknown"),
            "git_commit":        meta.get("git_commit",        "unknown"),
            "backend":           meta.get("backend",           "unknown"),
            "model":             meta.get("model",             "unknown"),
        }

    def expected_version(self) -> dict[str, str]:
        """Return current repo version for mismatch checking."""
        try:
            from fleet_safe_vla.benchmark_version import BENCHMARK_VERSION, PROTOCOL_VERSION, GIT_COMMIT
            return {
                "benchmark_version": BENCHMARK_VERSION,
                "protocol_version":  PROTOCOL_VERSION,
                "git_commit":        GIT_COMMIT,
            }
        except ImportError:
            return {}

    def check_version_mismatch(self) -> list[str]:
        """Return list of version mismatch warnings."""
        artifact = self.version_info()
        expected = self.expected_version()
        warnings: list[str] = []
        for key in ("benchmark_version", "protocol_version"):
            av = artifact.get(key, "unknown")
            ev = expected.get(key, "unknown")
            if av != "unknown" and ev != "unknown" and av != ev:
                warnings.append(
                    f"Version mismatch: {key} artifact={av!r} repo={ev!r}"
                )
        return warnings
