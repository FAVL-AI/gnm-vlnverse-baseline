"""
scene_graph_visualizer.py — Scene graph rendering data for the intervention replay viewer.

Produces GraphEdgeRenderData objects that map scene graph edges to visual
properties (color, line style, label) for rendering in Isaac Sim or matplotlib.

Color contract (matches docs/visualnav_reproduction/INTERVENTION_EVIDENCE_REPLAY.md):
  green  (0.1, 0.8, 0.1) — normal operation, no safety concern
  yellow (0.9, 0.8, 0.0) — near or occludes (proximity warning)
  orange (0.9, 0.5, 0.0) — moving_towards or blocks_path (directional risk)
  red    (0.9, 0.1, 0.1) — violates_margin or intervention_caused_by (active cause)

No Isaac imports. Importable in CI.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from fleet_safe_vla.envs.isaaclab.replay.replay_scene import (
    GraphEdgeState,
    ObstacleState,
    ReplayFrame,
)


# ── Color scheme ──────────────────────────────────────────────────────────────

EDGE_COLOR_MAP: dict[str, tuple[float, float, float]] = {
    "near":                    (0.9, 0.8, 0.0),   # yellow — proximity warning
    "moving_towards":          (0.9, 0.5, 0.0),   # orange — directional risk
    "occludes":                (0.9, 0.8, 0.0),   # yellow — visibility concern
    "blocks_path":             (0.9, 0.5, 0.0),   # orange — path obstruction
    "violates_margin":         (0.9, 0.1, 0.1),   # red    — active CBF trigger
    "intervention_caused_by":  (0.9, 0.1, 0.1),   # red    — causal link
    # Social-awareness relations
    "approaching":             (0.9, 0.5, 0.0),   # orange — directional risk
    "crossing_path":           (0.9, 0.4, 0.0),   # orange-red
    "crowding":                (0.9, 0.8, 0.0),   # yellow — density warning
    "occludes_zone":           (0.9, 0.8, 0.0),   # yellow — occlusion chain
    "social_margin_violation": (0.9, 0.1, 0.1),   # red    — social boundary
    "uncertain_occupancy":     (0.8, 0.8, 0.8),   # grey   — epistemic uncertainty
}

DEFAULT_EDGE_COLOR = (0.4, 0.4, 0.4)             # grey  — unknown relation

NODE_COLOR_MAP: dict[str, tuple[float, float, float]] = {
    "robot":          (0.2, 0.6, 1.0),   # blue
    "goal":           (0.1, 0.9, 0.2),   # green
    "obstacle":       (0.9, 0.2, 0.1),   # red
    "wall":           (0.6, 0.3, 0.1),   # brown
    "dynamic_agent":  (0.2, 0.4, 0.9),   # blue-purple
    "waypoint":       (0.8, 0.8, 0.2),   # yellow
    "fleet_safe":     (0.9, 0.1, 0.1),   # red (safety filter node)
    # Social-awareness node types
    "human":          (0.2, 0.8, 0.4),   # green — human agent
    "occlusion_zone": (0.8, 0.8, 0.1),   # dark yellow — uncertain shadow zone
    "bottleneck":     (0.9, 0.5, 0.0),   # orange — narrow passage
    "blind_corner":   (0.9, 0.3, 0.0),   # orange-red — occlusion hazard
    "crowd_cluster":  (0.9, 0.7, 0.0),   # amber — high-density region
}

# Traffic-light zone background colours (RGBA for matplotlib/Isaac patches)
TRAFFIC_ZONE_COLOR: dict[str, tuple[float, float, float, float]] = {
    "GREEN": (0.1, 0.8, 0.1, 0.10),   # faint green ring
    "AMBER": (0.9, 0.7, 0.0, 0.18),   # faint amber ring
    "RED":   (0.9, 0.1, 0.1, 0.28),   # stronger red ring
}

SAFETY_MARGIN_COLOR   = (0.9, 0.8, 0.0, 0.25)   # semi-transparent yellow ring
COLLISION_ZONE_COLOR  = (0.9, 0.1, 0.1, 0.25)   # semi-transparent red ring


# ── Render data structures ────────────────────────────────────────────────────

@dataclass
class GraphEdgeRenderData:
    """Rendering specification for one scene graph edge."""
    source_xy:     tuple[float, float]
    target_xy:     tuple[float, float]
    relation:      str
    distance_m:    float
    color_rgb:     tuple[float, float, float]
    line_width:    float
    label:         str
    is_causal:     bool     # True if relation triggers or annotates an intervention

    @property
    def color_rgba(self) -> tuple[float, float, float, float]:
        alpha = 0.9 if self.is_causal else 0.65
        return (*self.color_rgb, alpha)


@dataclass
class NodeRenderData:
    """Rendering specification for one scene graph node."""
    node_id:    str
    node_type:  str
    x:          float
    y:          float
    radius_m:   float
    color_rgb:  tuple[float, float, float]
    label:      str


@dataclass
class SafetyZoneRenderData:
    """Safety and collision margin rings around the robot."""
    robot_x:          float
    robot_y:          float
    safety_margin_m:  float                        # outer yellow ring
    collision_m:      float                        # inner red ring
    traffic_zone:     str   = "GREEN"              # GREEN / AMBER / RED

    def safety_color(self) -> tuple[float, float, float, float]:
        return SAFETY_MARGIN_COLOR

    def collision_color(self) -> tuple[float, float, float, float]:
        return COLLISION_ZONE_COLOR

    def traffic_zone_color(self) -> tuple[float, float, float, float]:
        """RGBA background patch for the active traffic-light zone."""
        return TRAFFIC_ZONE_COLOR.get(self.traffic_zone, SAFETY_MARGIN_COLOR)


@dataclass
class CounterfactualRenderData:
    """Rendering data for raw vs safe counterfactual rollout paths."""
    raw_trajectory:       list[tuple[float, float]]   # (x, y) world frame
    safe_trajectory:      list[tuple[float, float]]
    raw_color:            tuple[float, float, float] = (0.9, 0.2, 0.1)   # red
    safe_color:           tuple[float, float, float] = (0.1, 0.8, 0.2)   # green
    raw_collision:        bool = False
    safe_collision:       bool = False
    raw_min_distance:     float = float("inf")
    safe_min_distance:    float = float("inf")
    rollout_id:           str = ""
    is_mock:              bool = True


# ── Node position lookup ──────────────────────────────────────────────────────

def _build_node_positions(
    graph_dict: dict[str, Any],
) -> dict[str, tuple[float, float]]:
    positions: dict[str, tuple[float, float]] = {}
    for node in graph_dict.get("nodes", []):
        pos = node.get("position", [0.0, 0.0])
        positions[node["node_id"]] = (float(pos[0]), float(pos[1]))
    return positions


# ── Main renderer ─────────────────────────────────────────────────────────────

class SceneGraphRenderer:
    """
    Converts a scene graph dict into rendering data for one replay frame.

    Parameters
    ----------
    safety_margin_m : CBF safety margin (yellow ring radius).
    collision_m     : Collision threshold (red ring radius).
    """

    def __init__(
        self,
        safety_margin_m: float = 0.30,
        collision_m:     float = 0.10,
    ) -> None:
        self.safety_margin_m = safety_margin_m
        self.collision_m     = collision_m

    def render_edges(self, frame: ReplayFrame) -> list[GraphEdgeRenderData]:
        """Return rendering data for all scene graph edges in the frame."""
        node_positions = _build_node_positions(frame.scene_graph_before)
        result: list[GraphEdgeRenderData] = []

        causal_relations = {"violates_margin", "intervention_caused_by"}

        for edge in frame.edges:
            src_xy = node_positions.get(edge.source_id)
            tgt_xy = node_positions.get(edge.target_id)
            if src_xy is None or tgt_xy is None:
                continue

            color    = EDGE_COLOR_MAP.get(edge.relation, DEFAULT_EDGE_COLOR)
            is_causal = (
                edge.relation in causal_relations
                and frame.intervention_applied
            )
            line_width = 2.5 if is_causal else 1.5

            result.append(GraphEdgeRenderData(
                source_xy=src_xy,
                target_xy=tgt_xy,
                relation=edge.relation,
                distance_m=edge.distance_m,
                color_rgb=color,
                line_width=line_width,
                label=f"{edge.relation} {edge.distance_m:.2f}m",
                is_causal=is_causal,
            ))

        return result

    def render_nodes(self, frame: ReplayFrame) -> list[NodeRenderData]:
        """Return rendering data for all scene graph nodes in the frame."""
        result: list[NodeRenderData] = []
        for node in frame.scene_graph_before.get("nodes", []):
            pos      = node.get("position", [0.0, 0.0])
            ntype    = node.get("node_type", "obstacle")
            color    = NODE_COLOR_MAP.get(ntype, (0.5, 0.5, 0.5))
            result.append(NodeRenderData(
                node_id=node["node_id"],
                node_type=ntype,
                x=float(pos[0]),
                y=float(pos[1]),
                radius_m=float(node.get("radius_m", 0.15)),
                color_rgb=color,
                label=node["node_id"],
            ))
        return result

    def render_safety_zones(self, frame: ReplayFrame) -> SafetyZoneRenderData:
        return SafetyZoneRenderData(
            robot_x=frame.robot_x,
            robot_y=frame.robot_y,
            safety_margin_m=self.safety_margin_m,
            collision_m=self.collision_m,
            traffic_zone=getattr(frame, "active_safety_zone", "GREEN"),
        )

    def build_counterfactual(
        self,
        frame: ReplayFrame,
        rollout_horizon_s: float = 2.0,
        dt_s: float = 0.25,
    ) -> CounterfactualRenderData:
        """
        Build counterfactual render data from the evidence record.

        Uses the pre-computed counterfactual from the evidence file.
        For live rollout, use CounterfactualRolloutEngine directly.
        """
        from fleet_safe_vla.explainability.counterfactual_rollout import (
            CounterfactualRolloutEngine,
            CounterfactualRolloutRequest,
        )

        obstacles = [
            (obs.x, obs.y, obs.radius_m) for obs in frame.obstacles
        ]
        req = CounterfactualRolloutRequest(
            raw_action=frame.raw_action,
            safe_action=frame.safe_action,
            robot_xy=(frame.robot_x, frame.robot_y),
            robot_heading=0.0,
            obstacles=obstacles,
            rollout_horizon_s=rollout_horizon_s,
            dt_s=dt_s,
        )
        engine = CounterfactualRolloutEngine(backend="mock")
        result = engine.rollout(req)

        return CounterfactualRenderData(
            raw_trajectory=[tuple(p) for p in result.raw_action_rollout],
            safe_trajectory=[tuple(p) for p in result.safe_action_rollout],
            raw_collision=result.raw_collision_predicted,
            safe_collision=result.safe_collision_predicted,
            raw_min_distance=result.raw_min_distance,
            safe_min_distance=result.safe_min_distance,
            rollout_id=result.rollout_id,
            is_mock=True,
        )


# ── Delta-edge highlighter ────────────────────────────────────────────────────

def highlight_delta_edges(
    scene_graph_delta: dict[str, Any],
    node_positions: dict[str, tuple[float, float]],
) -> list[GraphEdgeRenderData]:
    """
    Produce render data for edges that *changed* between step N and step N+1.

    Added edges are shown bright; removed edges are shown with dashed styling
    (encoded as line_width < 0 as a convention the caller interprets).
    """
    result: list[GraphEdgeRenderData] = []

    for edge_dict in scene_graph_delta.get("added_edges", []):
        src = node_positions.get(edge_dict.get("source_id", ""))
        tgt = node_positions.get(edge_dict.get("target_id", ""))
        if src and tgt:
            relation = edge_dict.get("relation", "")
            color    = EDGE_COLOR_MAP.get(relation, DEFAULT_EDGE_COLOR)
            result.append(GraphEdgeRenderData(
                source_xy=src, target_xy=tgt,
                relation=relation,
                distance_m=float(edge_dict.get("distance_m", 0.0)),
                color_rgb=color,
                line_width=3.0,    # thick = newly appeared
                label=f"+{relation}",
                is_causal=relation in {"violates_margin", "intervention_caused_by"},
            ))

    for edge_dict in scene_graph_delta.get("removed_edges", []):
        src = node_positions.get(edge_dict.get("source_id", ""))
        tgt = node_positions.get(edge_dict.get("target_id", ""))
        if src and tgt:
            relation = edge_dict.get("relation", "")
            result.append(GraphEdgeRenderData(
                source_xy=src, target_xy=tgt,
                relation=relation,
                distance_m=float(edge_dict.get("distance_m", 0.0)),
                color_rgb=(0.5, 0.5, 0.5),
                line_width=-1.0,   # negative = dashed (caller interprets)
                label=f"-{relation}",
                is_causal=False,
            ))

    return result
