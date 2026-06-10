"""
explanation_generator.py — Human-readable explanation synthesis.

Combines a CausalEvent + Counterfactual + SceneGraph into a single
structured Explanation object that is suitable for:
  - audit_trail.json
  - explanation_log.jsonl (one entry per step)
  - dashboard display (natural language + evidence)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fleet_safe_vla.explainability.causal_reasoner import CausalEvent, CausalEventType
from fleet_safe_vla.explainability.counterfactuals import Counterfactual
from fleet_safe_vla.explainability.scene_graph import SceneGraph, SceneRelation


@dataclass
class Explanation:
    """Full explanation record for one episode step."""
    step:                  int
    natural_language:      str
    causal_summary:        str
    counterfactual_summary: str
    action_delta_l2:       float
    safety_margin_m:       float
    active_constraints:    list[str]
    evidence:              dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "step":                   self.step,
            "natural_language":       self.natural_language,
            "causal_summary":         self.causal_summary,
            "counterfactual_summary": self.counterfactual_summary,
            "action_delta_l2":        self.action_delta_l2,
            "safety_margin_m":        self.safety_margin_m,
            "active_constraints":     self.active_constraints,
            "evidence":               self.evidence,
        }


class ExplanationGenerator:
    """
    Synthesises a complete Explanation from component analysis outputs.

    The natural language output is template-based so it is always
    fully traceable — every phrase maps to a specific measured quantity.
    """

    def generate(
        self,
        causal_event:   CausalEvent,
        counterfactual: Counterfactual,
        scene_graph:    SceneGraph,
    ) -> Explanation:
        active_constraints = self._active_constraints(scene_graph)

        # Natural language: one-sentence summary for dashboard / paper
        if causal_event.event_type == CausalEventType.ESTOP:
            nl = (
                f"[Step {causal_event.step}] Emergency stop: "
                f"{causal_event.obstacle_id} detected at "
                f"{causal_event.obstacle_distance_m:.3f} m. "
                f"All motion halted by FleetSafe."
            )
        elif causal_event.event_type == CausalEventType.CBF_INTERVENTION:
            dominant = causal_event.evidence.get("dominant_component", "velocity")
            nl = (
                f"[Step {causal_event.step}] FleetSafe reduced {dominant} "
                f"(Δ={causal_event.action_delta_l2:.3f}) because "
                f"{causal_event.obstacle_id} is {causal_event.obstacle_distance_m:.3f} m away "
                f"(margin {causal_event.safety_margin_m:.2f} m). "
                f"{counterfactual.explanation}"
            )
        elif causal_event.event_type == CausalEventType.NEAR_VIOLATION:
            nl = (
                f"[Step {causal_event.step}] Near-violation: "
                f"{causal_event.obstacle_id} at {causal_event.obstacle_distance_m:.3f} m. "
                f"Action not modified (margin not breached)."
            )
        else:
            nl = (
                f"[Step {causal_event.step}] Normal operation. "
                f"Original action accepted. "
                f"Nearest obstacle: {causal_event.obstacle_id} at "
                f"{causal_event.obstacle_distance_m:.3f} m."
            )

        evidence = {
            **causal_event.evidence,
            "graph_node_count": len(scene_graph.nodes),
            "graph_edge_count": len(scene_graph.edges),
            "active_constraints": active_constraints,
        }

        return Explanation(
            step                   = causal_event.step,
            natural_language       = nl,
            causal_summary         = causal_event.description,
            counterfactual_summary = counterfactual.explanation,
            action_delta_l2        = causal_event.action_delta_l2,
            safety_margin_m        = causal_event.safety_margin_m,
            active_constraints     = active_constraints,
            evidence               = evidence,
        )

    def _active_constraints(self, scene_graph: SceneGraph) -> list[str]:
        """Return list of active constraint descriptions from graph edges."""
        constraints = []
        for edge in scene_graph.edges:
            if edge.relation == SceneRelation.VIOLATES_MARGIN:
                constraints.append(
                    f"violates_margin({edge.source_id},{edge.target_id},"
                    f"d={edge.distance_m:.3f}m)"
                )
            elif edge.relation == SceneRelation.INTERVENTION_CAUSED_BY:
                constraints.append(
                    f"intervention_caused_by(fleet_safe,{edge.target_id},"
                    f"d={edge.distance_m:.3f}m)"
                )
        return constraints
