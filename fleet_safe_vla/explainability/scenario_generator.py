"""
scenario_generator.py — Generate new test scenarios from existing scene graphs.

Uses the spatial structure of a recorded scene graph to synthesise variants
for stress-testing or expanding the benchmark scenario pool.

Mutations available
-------------------
translate_obstacle  : Move one obstacle by (dx, dy).
remove_obstacle     : Remove one obstacle entirely.
add_noise_obstacles : Insert N random obstacles within scene bounds.
scale_scene         : Scale all non-robot positions by a factor.
"""
from __future__ import annotations

import copy
import math
import random
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from fleet_safe_vla.explainability.scene_graph import (
    SceneGraph,
    SceneGraphBuilder,
    SceneNode,
    SceneNodeType,
    SceneRelation,
)


@dataclass
class ScenarioMutation:
    """Describes one mutation applied to a scene graph."""
    mutation_type:  str
    parameters:     dict[str, Any]
    original_scene: str
    description:    str


class ScenarioGenerator:
    """
    Generate scene variants from an existing SceneGraph.

    All mutated graphs are independent copies of the original — the source
    graph is never modified in place.
    """

    def __init__(self, rng_seed: int = 0) -> None:
        self.rng = np.random.default_rng(rng_seed)

    # ── Public API ─────────────────────────────────────────────────────────────

    def from_scene_graph(
        self,
        graph:      SceneGraph,
        n_variants: int = 5,
    ) -> list[tuple[SceneGraph, ScenarioMutation]]:
        """
        Generate `n_variants` mutated copies of `graph`.

        Mutations are chosen randomly from the available set.  Returns a list
        of (mutated_graph, mutation_record) pairs.
        """
        obstacle_ids = [
            nid for nid, node in graph.nodes.items()
            if node.node_type in (SceneNodeType.OBSTACLE, SceneNodeType.DYNAMIC_AGENT)
        ]

        variants: list[tuple[SceneGraph, ScenarioMutation]] = []
        for _ in range(n_variants):
            choice = int(self.rng.integers(0, 4))

            if choice == 0 and obstacle_ids:
                obs_id  = str(self.rng.choice(obstacle_ids))
                dx, dy  = float(self.rng.uniform(-0.5, 0.5)), float(self.rng.uniform(-0.5, 0.5))
                new_g, mut = self.translate_obstacle(graph, obs_id, dx, dy)

            elif choice == 1 and obstacle_ids:
                obs_id  = str(self.rng.choice(obstacle_ids))
                new_g, mut = self.remove_obstacle(graph, obs_id)

            elif choice == 2:
                n = int(self.rng.integers(1, 4))
                new_g, mut = self.add_noise_obstacles(graph, n)

            else:
                factor  = float(self.rng.uniform(0.7, 1.4))
                new_g, mut = self.scale_scene(graph, factor)

            variants.append((new_g, mut))

        return variants

    def translate_obstacle(
        self,
        graph:      SceneGraph,
        obstacle_id: str,
        dx:          float,
        dy:          float,
    ) -> tuple[SceneGraph, ScenarioMutation]:
        """Move `obstacle_id` by (dx, dy) metres."""
        new_graph = self._copy_graph(graph)
        if obstacle_id in new_graph.nodes:
            node = new_graph.nodes[obstacle_id]
            new_graph.nodes[obstacle_id] = SceneNode(
                node_id   = node.node_id,
                node_type = node.node_type,
                position  = (node.position[0] + dx, node.position[1] + dy),
                radius_m  = node.radius_m,
                velocity  = node.velocity,
                metadata  = dict(node.metadata),
            )
        mutation = ScenarioMutation(
            mutation_type  = "translate_obstacle",
            parameters     = {"obstacle_id": obstacle_id, "dx": dx, "dy": dy},
            original_scene = f"step_{graph.step}",
            description    = f"Translated {obstacle_id} by ({dx:.2f}, {dy:.2f}) m.",
        )
        return new_graph, mutation

    def remove_obstacle(
        self,
        graph:      SceneGraph,
        obstacle_id: str,
    ) -> tuple[SceneGraph, ScenarioMutation]:
        """Remove an obstacle node and all its edges."""
        new_graph = self._copy_graph(graph)
        new_graph.nodes.pop(obstacle_id, None)
        new_graph.edges = [
            e for e in new_graph.edges
            if e.source_id != obstacle_id and e.target_id != obstacle_id
        ]
        mutation = ScenarioMutation(
            mutation_type  = "remove_obstacle",
            parameters     = {"obstacle_id": obstacle_id},
            original_scene = f"step_{graph.step}",
            description    = f"Removed obstacle {obstacle_id} from scene.",
        )
        return new_graph, mutation

    def add_noise_obstacles(
        self,
        graph: SceneGraph,
        n:     int = 1,
    ) -> tuple[SceneGraph, ScenarioMutation]:
        """Insert N random obstacles within the bounding box of existing objects."""
        new_graph = self._copy_graph(graph)

        positions = [node.position for node in graph.nodes.values()]
        xs = [p[0] for p in positions] or [0.0]
        ys = [p[1] for p in positions] or [0.0]
        x_lo, x_hi = min(xs) - 0.5, max(xs) + 0.5
        y_lo, y_hi = min(ys) - 0.5, max(ys) + 0.5

        existing_obs = [
            nid for nid in graph.nodes
            if graph.nodes[nid].node_type == SceneNodeType.OBSTACLE
        ]
        next_idx = len(existing_obs)

        added = []
        for i in range(n):
            obs_id = f"obstacle_{next_idx + i}"
            ox = float(self.rng.uniform(x_lo, x_hi))
            oy = float(self.rng.uniform(y_lo, y_hi))
            new_graph.add_node(SceneNode(
                node_id   = obs_id,
                node_type = SceneNodeType.OBSTACLE,
                position  = (ox, oy),
                radius_m  = float(self.rng.uniform(0.10, 0.25)),
            ))
            added.append(obs_id)

        mutation = ScenarioMutation(
            mutation_type  = "add_noise_obstacles",
            parameters     = {"n": n, "added_ids": added},
            original_scene = f"step_{graph.step}",
            description    = f"Added {n} random obstacle(s): {added}.",
        )
        return new_graph, mutation

    def scale_scene(
        self,
        graph:  SceneGraph,
        factor: float,
    ) -> tuple[SceneGraph, ScenarioMutation]:
        """Scale all non-robot node positions by `factor` around the robot."""
        new_graph = self._copy_graph(graph)
        robot = new_graph.nodes.get("robot")
        cx = robot.position[0] if robot else 0.0
        cy = robot.position[1] if robot else 0.0

        for nid, node in list(new_graph.nodes.items()):
            if nid == "robot":
                continue
            nx = cx + (node.position[0] - cx) * factor
            ny = cy + (node.position[1] - cy) * factor
            new_graph.nodes[nid] = SceneNode(
                node_id   = node.node_id,
                node_type = node.node_type,
                position  = (nx, ny),
                radius_m  = node.radius_m * factor,
                velocity  = node.velocity,
                metadata  = dict(node.metadata),
            )

        mutation = ScenarioMutation(
            mutation_type  = "scale_scene",
            parameters     = {"factor": factor},
            original_scene = f"step_{graph.step}",
            description    = f"Scaled scene by factor {factor:.2f} around robot.",
        )
        return new_graph, mutation

    # ── Internal ───────────────────────────────────────────────────────────────

    def _copy_graph(self, graph: SceneGraph) -> SceneGraph:
        new_g = SceneGraph(step=graph.step, timestamp_s=graph.timestamp_s)
        for nid, node in graph.nodes.items():
            new_g.nodes[nid] = SceneNode(
                node_id   = node.node_id,
                node_type = node.node_type,
                position  = node.position,
                radius_m  = node.radius_m,
                velocity  = node.velocity,
                metadata  = dict(node.metadata),
            )
        new_g.edges = [
            type(e)(
                source_id  = e.source_id,
                target_id  = e.target_id,
                relation   = e.relation,
                distance_m = e.distance_m,
                attributes = dict(e.attributes),
            )
            for e in graph.edges
        ]
        return new_g
