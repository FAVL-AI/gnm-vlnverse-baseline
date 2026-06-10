"""
counterfactuals.py — Counterfactual explanations for FleetSafe interventions.

For each intervention step, generates a "what if" explanation:

  "If obstacle_3 were 0.23 m farther away (at 0.41 m instead of 0.18 m),
   the original ViNT action would have been accepted by FleetSafe."

The counterfactual distance shift is the minimum displacement of the nearest
obstacle that would have kept the safety margin satisfied:

    shift = max(0, margin_m + ε - obstacle_distance_m)

where ε is a small buffer to ensure the constraint is strictly satisfied.
"""
from __future__ import annotations

from dataclasses import dataclass

from fleet_safe_vla.explainability.causal_reasoner import CausalEvent, CausalEventType


@dataclass
class Counterfactual:
    """Counterfactual explanation for one episode step."""
    step:                   int
    was_intervention:       bool
    original_obstacle_id:   str
    original_distance_m:    float
    hypothetical_distance_m: float
    distance_shift_m:       float
    original_action:        tuple[float, float, float]   # (vx, vy, wz) nominal
    hypothetical_action:    tuple[float, float, float]   # would have been sent
    action_accepted:        bool
    explanation:            str

    def to_dict(self) -> dict:
        return {
            "step":                    self.step,
            "was_intervention":        self.was_intervention,
            "original_obstacle_id":    self.original_obstacle_id,
            "original_distance_m":     self.original_distance_m,
            "hypothetical_distance_m": self.hypothetical_distance_m,
            "distance_shift_m":        self.distance_shift_m,
            "original_action":         list(self.original_action),
            "hypothetical_action":     list(self.hypothetical_action),
            "action_accepted":         self.action_accepted,
            "explanation":             self.explanation,
        }


class CounterfactualGenerator:
    """
    Generates minimal counterfactual explanations.

    Parameters
    ----------
    margin_m : CBF safety margin (d_safe).  The counterfactual computes the
               minimum obstacle displacement that would satisfy this margin.
    buffer_m : Epsilon buffer so the constraint is strictly satisfied.
    """

    def __init__(self, margin_m: float = 0.30, buffer_m: float = 0.01) -> None:
        self.margin_m = margin_m
        self.buffer_m = buffer_m

    def generate(self, causal_event: CausalEvent) -> Counterfactual:
        """
        Generate a counterfactual for a single step's causal event.

        For non-intervention steps, the counterfactual is trivial (action
        was already accepted).  For intervention and E-STOP steps, it
        computes how far the obstacle would need to move.
        """
        step   = causal_event.step
        obs_id = causal_event.obstacle_id
        cur_d  = causal_event.obstacle_distance_m
        raw    = causal_event.raw_cmd

        is_intervention = causal_event.event_type in (
            CausalEventType.CBF_INTERVENTION,
            CausalEventType.ESTOP,
        )

        if not is_intervention:
            return Counterfactual(
                step                   = step,
                was_intervention       = False,
                original_obstacle_id   = obs_id,
                original_distance_m    = cur_d,
                hypothetical_distance_m = cur_d,
                distance_shift_m       = 0.0,
                original_action        = raw,
                hypothetical_action    = raw,
                action_accepted        = True,
                explanation            = (
                    "No intervention this step; original action was accepted "
                    "without modification."
                ),
            )

        threshold = self.margin_m + self.buffer_m
        shift     = max(0.0, threshold - cur_d)
        hyp_d     = cur_d + shift

        model_hint = causal_event.evidence.get("dominant_component", "velocity")
        event_label = (
            "E-STOP" if causal_event.event_type == CausalEventType.ESTOP
            else "FleetSafe"
        )

        explanation = (
            f"If {obs_id} were {shift:.2f} m farther away "
            f"(at {hyp_d:.2f} m instead of {cur_d:.2f} m), "
            f"the original action (vx={raw[0]:.3f}, vy={raw[1]:.3f}, wz={raw[2]:.3f}) "
            f"would have been accepted by {event_label} "
            f"(safety margin {self.margin_m:.2f} m satisfied with ε={self.buffer_m:.2f} m buffer)."
        )

        return Counterfactual(
            step                   = step,
            was_intervention       = True,
            original_obstacle_id   = obs_id,
            original_distance_m    = cur_d,
            hypothetical_distance_m = hyp_d,
            distance_shift_m       = shift,
            original_action        = raw,
            hypothetical_action    = raw,    # accepted unchanged if obstacle were farther
            action_accepted        = True,
            explanation            = explanation,
        )
