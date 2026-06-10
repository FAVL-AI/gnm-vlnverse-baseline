"""
scene_graph.py — Scene graph representation for explainable FleetSafe decisions.

Graph structure
---------------
Nodes: robot, goal, obstacle_i, wall_i, dynamic_agent_i, waypoint_i
Edges (directed): near, moving_towards, occludes, blocks_path,
                  violates_margin, intervention_caused_by

The graph is rebuilt at every episode step, giving a per-step snapshot of
spatial relationships that drove any FleetSafe intervention.

All geometry is 2-D world-frame (metres).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence


class SceneNodeType(str, Enum):
    ROBOT         = "robot"
    GOAL          = "goal"
    OBSTACLE      = "obstacle"
    WALL          = "wall"
    DYNAMIC_AGENT = "dynamic_agent"
    WAYPOINT      = "waypoint"
    # Social-awareness additions
    HUMAN         = "human"
    OCCLUSION_ZONE = "occlusion_zone"
    BOTTLENECK    = "bottleneck"
    BLIND_CORNER  = "blind_corner"
    CROWD_CLUSTER = "crowd_cluster"


class SceneRelation(str, Enum):
    NEAR                   = "near"
    MOVING_TOWARDS         = "moving_towards"
    OCCLUDES               = "occludes"
    BLOCKS_PATH            = "blocks_path"
    VIOLATES_MARGIN        = "violates_margin"
    INTERVENTION_CAUSED_BY = "intervention_caused_by"
    # Social-awareness additions
    APPROACHING            = "approaching"
    CROSSING_PATH          = "crossing_path"
    CROWDING               = "crowding"
    OCCLUDES_ZONE          = "occludes_zone"
    SOCIAL_MARGIN_VIOLATION = "social_margin_violation"
    UNCERTAIN_OCCUPANCY    = "uncertain_occupancy"


@dataclass
class SceneNode:
    node_id:   str
    node_type: SceneNodeType
    position:  tuple[float, float]
    radius_m:  float                       = 0.0
    velocity:  tuple[float, float]         = (0.0, 0.0)
    metadata:  dict[str, Any]             = field(default_factory=dict)


@dataclass
class SceneEdge:
    source_id:  str
    target_id:  str
    relation:   SceneRelation
    distance_m: float                      = 0.0
    attributes: dict[str, Any]            = field(default_factory=dict)


@dataclass
class SceneGraphDelta:
    """Structural diff between two consecutive SceneGraph snapshots."""
    added_nodes:         list[str]
    removed_nodes:       list[str]
    changed_attributes:  dict[str, dict]   # node_id → {attr: {"before": v, "after": v}}
    added_edges:         list[dict]        # serialised SceneEdge dicts
    removed_edges:       list[dict]
    changed_edges:       list[dict]        # {key, attr: {"before": v, "after": v}}

    def to_dict(self) -> dict:
        return {
            "added_nodes":        self.added_nodes,
            "removed_nodes":      self.removed_nodes,
            "changed_attributes": self.changed_attributes,
            "added_edges":        self.added_edges,
            "removed_edges":      self.removed_edges,
            "changed_edges":      self.changed_edges,
        }


def diff_scene_graphs(before: "SceneGraph", after: "SceneGraph") -> "SceneGraphDelta":
    """
    Compute the structural delta between two scene graph snapshots.

    Edge identity is (source_id, target_id, relation).
    """
    before_ids = set(before.nodes)
    after_ids  = set(after.nodes)
    added_nodes   = sorted(after_ids - before_ids)
    removed_nodes = sorted(before_ids - after_ids)

    changed_attributes: dict[str, dict] = {}
    for node_id in before_ids & after_ids:
        b = before.nodes[node_id]
        a = after.nodes[node_id]
        changes: dict = {}
        if b.position != a.position:
            changes["position"] = {"before": list(b.position), "after": list(a.position)}
        if b.radius_m != a.radius_m:
            changes["radius_m"] = {"before": b.radius_m, "after": a.radius_m}
        if b.velocity != a.velocity:
            changes["velocity"] = {"before": list(b.velocity), "after": list(a.velocity)}
        if changes:
            changed_attributes[node_id] = changes

    def _edge_key(e: "SceneEdge") -> tuple:
        return (e.source_id, e.target_id, e.relation.value)

    def _edge_to_dict(e: "SceneEdge") -> dict:
        return {
            "source_id":  e.source_id,
            "target_id":  e.target_id,
            "relation":   e.relation.value,
            "distance_m": e.distance_m,
            "attributes": e.attributes,
        }

    before_edge_map = {_edge_key(e): e for e in before.edges}
    after_edge_map  = {_edge_key(e): e for e in after.edges}
    before_keys     = set(before_edge_map)
    after_keys      = set(after_edge_map)

    added_edges   = [_edge_to_dict(after_edge_map[k])  for k in sorted(after_keys  - before_keys)]
    removed_edges = [_edge_to_dict(before_edge_map[k]) for k in sorted(before_keys - after_keys)]

    changed_edges: list[dict] = []
    for k in sorted(before_keys & after_keys):
        b = before_edge_map[k]
        a = after_edge_map[k]
        if b.distance_m != a.distance_m:
            changed_edges.append({
                "key": list(k),
                "distance_m": {"before": b.distance_m, "after": a.distance_m},
            })

    return SceneGraphDelta(
        added_nodes=added_nodes,
        removed_nodes=removed_nodes,
        changed_attributes=changed_attributes,
        added_edges=added_edges,
        removed_edges=removed_edges,
        changed_edges=changed_edges,
    )


class SceneGraph:
    """Snapshot of spatial relationships at one episode step."""

    def __init__(self, step: int, timestamp_s: float) -> None:
        self.step        = step
        self.timestamp_s = timestamp_s
        self.nodes: dict[str, SceneNode] = {}
        self.edges: list[SceneEdge]      = []

    def add_node(self, node: SceneNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: SceneEdge) -> None:
        self.edges.append(edge)

    # ── Queries ────────────────────────────────────────────────────────────────

    def get_edges_for(
        self,
        node_id:  str,
        relation: SceneRelation | None = None,
    ) -> list[SceneEdge]:
        edges = [
            e for e in self.edges
            if e.source_id == node_id or e.target_id == node_id
        ]
        if relation is not None:
            edges = [e for e in edges if e.relation == relation]
        return edges

    def nearest_obstacle(
        self,
        robot_id: str = "robot",
    ) -> tuple[SceneNode | None, float]:
        """Return (nearest obstacle/wall/dynamic-agent node, surface-to-surface distance)."""
        robot = self.nodes.get(robot_id)
        if robot is None:
            return None, float("inf")

        _obstacle_types = {
            SceneNodeType.OBSTACLE,
            SceneNodeType.WALL,
            SceneNodeType.DYNAMIC_AGENT,
        }
        min_dist = float("inf")
        nearest: SceneNode | None = None

        for node in self.nodes.values():
            if node.node_type not in _obstacle_types:
                continue
            d = (
                math.hypot(
                    robot.position[0] - node.position[0],
                    robot.position[1] - node.position[1],
                )
                - node.radius_m
            )
            if d < min_dist:
                min_dist = d
                nearest  = node

        return nearest, min_dist

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "step":        self.step,
            "timestamp_s": self.timestamp_s,
            "nodes": [
                {
                    "node_id":   n.node_id,
                    "node_type": n.node_type.value,
                    "position":  list(n.position),
                    "radius_m":  n.radius_m,
                    "velocity":  list(n.velocity),
                    "metadata":  n.metadata,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "source_id":  e.source_id,
                    "target_id":  e.target_id,
                    "relation":   e.relation.value,
                    "distance_m": e.distance_m,
                    "attributes": e.attributes,
                }
                for e in self.edges
            ],
        }


# ── Builder ────────────────────────────────────────────────────────────────────

class SceneGraphBuilder:
    """
    Constructs a SceneGraph from episode state at a single step.

    Parameters
    ----------
    near_threshold_m   : Distance below which the `near` relation is added.
    margin_threshold_m : Distance below which `violates_margin` is added.
    collision_m        : Contact distance (informational, not used for edges).
    blocks_path_m      : Waypoint-to-obstacle distance for `blocks_path`.
    """

    def __init__(
        self,
        near_threshold_m:   float = 0.45,
        margin_threshold_m: float = 0.30,
        collision_m:        float = 0.10,
        blocks_path_m:      float = 0.20,
    ) -> None:
        self.near_threshold_m   = near_threshold_m
        self.margin_threshold_m = margin_threshold_m
        self.collision_m        = collision_m
        self.blocks_path_m      = blocks_path_m

    def build(
        self,
        step:          int,
        timestamp_s:   float,
        robot_xy:      tuple[float, float],
        robot_heading: float,
        goal_xy:       tuple[float, float],
        obstacles:     Sequence[Any],           # ObstacleSpec or (x, y, radius)
        dynamic_agents: Sequence[Any] | None = None,
        waypoints:     Sequence[tuple[float, float]] | None = None,
        raw_vx:        float = 0.0,
        raw_vy:        float = 0.0,
        intervened:    bool  = False,
    ) -> SceneGraph:
        graph = SceneGraph(step=step, timestamp_s=timestamp_s)

        # ── Robot ──────────────────────────────────────────────────────────────
        cos_h   = math.cos(robot_heading)
        sin_h   = math.sin(robot_heading)
        world_vx = raw_vx * cos_h - raw_vy * sin_h
        world_vy = raw_vx * sin_h + raw_vy * cos_h
        graph.add_node(SceneNode(
            node_id   = "robot",
            node_type = SceneNodeType.ROBOT,
            position  = robot_xy,
            radius_m  = 0.15,
            velocity  = (world_vx, world_vy),
        ))

        # ── Goal ──────────────────────────────────────────────────────────────
        graph.add_node(SceneNode(
            node_id   = "goal",
            node_type = SceneNodeType.GOAL,
            position  = goal_xy,
            radius_m  = 0.20,
        ))

        # ── Obstacles ─────────────────────────────────────────────────────────
        goal_dx  = goal_xy[0] - robot_xy[0]
        goal_dy  = goal_xy[1] - robot_xy[1]
        goal_dist = math.hypot(goal_dx, goal_dy)

        all_obs_info: list[tuple[str, float, float, float, SceneNodeType]] = []

        for i, obs in enumerate(obstacles):
            ox   = float(obs.x)       if hasattr(obs, "x")        else float(obs[0])
            oy   = float(obs.y)       if hasattr(obs, "y")        else float(obs[1])
            orad = float(obs.radius_m) if hasattr(obs, "radius_m") else (
                float(obs[2]) if len(obs) > 2 else 0.15
            )
            obs_id = f"obstacle_{i}"
            all_obs_info.append((obs_id, ox, oy, orad, SceneNodeType.OBSTACLE))

        for i, dyn in enumerate(dynamic_agents or []):
            pos = dyn.position_at(timestamp_s) if hasattr(dyn, "position_at") else (dyn[0], dyn[1])
            orad = float(dyn.obstacle_radius_m) if hasattr(dyn, "obstacle_radius_m") else 0.15
            dyn_id = f"dynamic_agent_{i}"
            all_obs_info.append((dyn_id, float(pos[0]), float(pos[1]), orad, SceneNodeType.DYNAMIC_AGENT))

        nearest_threat_id: str | None = None
        nearest_threat_dist = float("inf")

        for (obs_id, ox, oy, orad, ntype) in all_obs_info:
            graph.add_node(SceneNode(
                node_id   = obs_id,
                node_type = ntype,
                position  = (ox, oy),
                radius_m  = orad,
            ))

            d = math.hypot(robot_xy[0] - ox, robot_xy[1] - oy) - orad

            if d < self.near_threshold_m:
                graph.add_edge(SceneEdge("robot", obs_id, SceneRelation.NEAR, d))

            if d < self.margin_threshold_m:
                graph.add_edge(SceneEdge("robot", obs_id, SceneRelation.VIOLATES_MARGIN, d))

            # moving_towards: robot velocity component toward obstacle > 0
            to_obs_x = ox - robot_xy[0]
            to_obs_y = oy - robot_xy[1]
            dot = world_vx * to_obs_x + world_vy * to_obs_y
            if dot > 0.0 and d < self.near_threshold_m:
                graph.add_edge(SceneEdge("robot", obs_id, SceneRelation.MOVING_TOWARDS, d))

            # occludes_goal: obstacle lies between robot and goal
            if goal_dist > 1e-6:
                t = (to_obs_x * goal_dx + to_obs_y * goal_dy) / (goal_dist ** 2)
                if 0.0 < t < 1.0:
                    proj_x   = robot_xy[0] + t * goal_dx
                    proj_y   = robot_xy[1] + t * goal_dy
                    dist_line = math.hypot(ox - proj_x, oy - proj_y)
                    if dist_line < orad * 2.0:
                        graph.add_edge(SceneEdge(obs_id, "goal", SceneRelation.OCCLUDES, dist_line))

            if d < nearest_threat_dist:
                nearest_threat_dist = d
                nearest_threat_id   = obs_id

        # intervention_caused_by: link FleetSafe → nearest threat when intervened
        if intervened and nearest_threat_id is not None:
            graph.add_node(SceneNode(
                node_id   = "fleet_safe",
                node_type = SceneNodeType.ROBOT,
                position  = robot_xy,
                metadata  = {"role": "safety_filter"},
            ))
            graph.add_edge(SceneEdge(
                "fleet_safe",
                nearest_threat_id,
                SceneRelation.INTERVENTION_CAUSED_BY,
                nearest_threat_dist,
            ))

        # ── Waypoints ─────────────────────────────────────────────────────────
        for j, wp in enumerate(waypoints or []):
            wp_id = f"waypoint_{j}"
            graph.add_node(SceneNode(
                node_id   = wp_id,
                node_type = SceneNodeType.WAYPOINT,
                position  = (float(wp[0]), float(wp[1])),
                radius_m  = 0.05,
            ))
            for (obs_id, ox, oy, orad, _) in all_obs_info:
                d = math.hypot(float(wp[0]) - ox, float(wp[1]) - oy) - orad
                if d < self.blocks_path_m:
                    graph.add_edge(SceneEdge(obs_id, wp_id, SceneRelation.BLOCKS_PATH, d))

        return graph
