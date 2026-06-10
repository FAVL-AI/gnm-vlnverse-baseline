"""
causal_reasoner.py — Causal event inference for FleetSafe interventions.

For each step, the reasoner analyses the scene graph and action delta to
determine why (or why not) the safety filter modified the nominal action.

Output
------
CausalEvent with:
  - event_type      : ESTOP | CBF_INTERVENTION | NEAR_VIOLATION | GOAL_PURSUIT | NO_EVENT
  - obstacle_id     : which obstacle caused the event
  - description     : human-readable sentence suitable for logs / audit trail
  - evidence        : machine-readable dict linking to graph edges and distances
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from fleet_safe_vla.explainability.scene_graph import SceneGraph, SceneRelation


class CausalEventType(str, Enum):
    ESTOP            = "estop"
    CBF_INTERVENTION = "cbf_intervention"
    NEAR_VIOLATION   = "near_violation"
    GOAL_PURSUIT     = "goal_pursuit"
    NO_EVENT         = "no_event"


@dataclass
class CausalEvent:
    step:                int
    event_type:          CausalEventType
    obstacle_id:         str
    obstacle_distance_m: float
    safety_margin_m:     float
    raw_cmd:             tuple[float, float, float]   # (vx, vy, wz)
    safe_cmd:            tuple[float, float, float]
    action_delta_l2:     float
    description:         str
    evidence:            dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "step":                self.step,
            "event_type":          self.event_type.value,
            "obstacle_id":         self.obstacle_id,
            "obstacle_distance_m": self.obstacle_distance_m,
            "safety_margin_m":     self.safety_margin_m,
            "raw_cmd":             list(self.raw_cmd),
            "safe_cmd":            list(self.safe_cmd),
            "action_delta_l2":     self.action_delta_l2,
            "description":         self.description,
            "evidence":            self.evidence,
        }


# ── Reasoner ───────────────────────────────────────────────────────────────────

class CausalReasoner:
    """
    Infers the causal chain behind each FleetSafe step.

    The reasoning is distance-first: whichever obstacle is nearest and within
    a safety threshold is treated as the cause of any intervention.

    Parameters
    ----------
    near_miss_m  : Threshold below which a step is flagged near_violation.
    collision_m  : Threshold for E-STOP / contact.
    margin_m     : CBF safety margin (d_safe).
    """

    def __init__(
        self,
        near_miss_m: float = 0.45,
        collision_m: float = 0.10,
        margin_m:    float = 0.30,
    ) -> None:
        self.near_miss_m = near_miss_m
        self.collision_m = collision_m
        self.margin_m    = margin_m

    def reason(
        self,
        step:       int,
        scene_graph: SceneGraph,
        raw_vx:     float,
        raw_vy:     float,
        raw_wz:     float,
        safe_vx:    float,
        safe_vy:    float,
        safe_wz:    float,
        intervened: bool,
        estop:      bool,
    ) -> CausalEvent:
        """
        Produce a CausalEvent for one episode step.

        Parameters
        ----------
        step       : Step index.
        scene_graph: Pre-built SceneGraph for this step.
        raw_*      : Nominal cmd_vel components.
        safe_*     : CBF-filtered cmd_vel components.
        intervened : True if CBF modified the action.
        estop      : True if E-STOP was triggered.
        """
        raw_arr  = np.array([raw_vx,  raw_vy,  raw_wz],  dtype=float)
        safe_arr = np.array([safe_vx, safe_vy, safe_wz], dtype=float)
        delta    = float(np.linalg.norm(safe_arr - raw_arr))

        nearest_node, nearest_dist = scene_graph.nearest_obstacle("robot")
        obs_id   = nearest_node.node_id if nearest_node else "none"

        # Build graph-edge summary for evidence
        edge_summary = [
            f"{e.source_id}→{e.target_id}:{e.relation.value}@{e.distance_m:.3f}m"
            for e in scene_graph.edges
        ]

        evidence: dict[str, Any] = {
            "min_dist_m":       nearest_dist,
            "nearest_obstacle": obs_id,
            "raw_vx":           raw_vx,
            "raw_vy":           raw_vy,
            "raw_wz":           raw_wz,
            "safe_vx":          safe_vx,
            "safe_vy":          safe_vy,
            "safe_wz":          safe_wz,
            "delta_l2":         delta,
            "graph_edges":      edge_summary,
        }

        # ── Classify event ────────────────────────────────────────────────────
        if estop:
            description = (
                f"E-STOP triggered: {obs_id} at {nearest_dist:.3f} m "
                f"(threshold {self.collision_m:.2f} m). "
                f"All velocity components zeroed by FleetSafe."
            )
            event_type = CausalEventType.ESTOP

        elif intervened:
            # Dominant modified component
            dvx = abs(safe_vx - raw_vx)
            dvy = abs(safe_vy - raw_vy)
            dwz = abs(safe_wz - raw_wz)
            dominant, dom_raw, dom_safe = max(
                [(dvx, "vx", raw_vx, safe_vx),
                 (dvy, "vy", raw_vy, safe_vy),
                 (dwz, "wz", raw_wz, safe_wz)],
                key=lambda x: x[0],
            )[1:]

            description = (
                f"FleetSafe reduced {dominant} from {dom_raw:.3f} to {dom_safe:.3f} "
                f"because the predicted path entered a near-violation zone "
                f"{nearest_dist:.3f} m from {obs_id}."
            )
            event_type = CausalEventType.CBF_INTERVENTION
            evidence["dominant_component"] = dominant

        elif nearest_dist < self.near_miss_m:
            description = (
                f"Near-violation: robot within {nearest_dist:.3f} m of {obs_id} "
                f"(threshold {self.near_miss_m:.2f} m). No intervention applied."
            )
            event_type = CausalEventType.NEAR_VIOLATION

        elif nearest_dist < float("inf"):
            description = (
                f"No safety event. Nearest obstacle ({obs_id}) at {nearest_dist:.3f} m. "
                f"Original action accepted."
            )
            event_type = CausalEventType.GOAL_PURSUIT

        else:
            description = "No obstacles in scene. Original action accepted."
            event_type  = CausalEventType.NO_EVENT

        return CausalEvent(
            step                = step,
            event_type          = event_type,
            obstacle_id         = obs_id,
            obstacle_distance_m = nearest_dist,
            safety_margin_m     = self.margin_m,
            raw_cmd             = (raw_vx,  raw_vy,  raw_wz),
            safe_cmd            = (safe_vx, safe_vy, safe_wz),
            action_delta_l2     = delta,
            description         = description,
            evidence            = evidence,
        )
