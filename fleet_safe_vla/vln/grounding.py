"""InstructionGrounder — deterministic rule-based VLN instruction grounding.

Converts a VLNInstruction into a GroundedGoal with waypoint intent, safety
constraints, and an explanation trace. Fully auditable — no black-box LLM
required for the baseline. A hook for LLM/VLM grounding is provided but
disabled by default.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from fleet_safe_vla.vln.instruction_schema import (
    ActionType,
    GoalType,
    GroundedGoal,
    SafetyConstraint,
    VLNInstruction,
)


# ---------------------------------------------------------------------------
# Keyword tables
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "stop", "halt", "freeze", "pause", "wait", "emergency stop", "estop",
    "hold", "stand still", "abort",
}

_FORWARD_WORDS = {
    "forward", "ahead", "straight", "go", "move", "advance", "continue",
    "proceed", "walk", "drive", "navigate",
}

_BACK_WORDS = {"back", "backward", "reverse", "retreat", "return", "come back"}

_LEFT_WORDS  = {"left", "turn left", "go left", "rotate left", "counterclockwise"}
_RIGHT_WORDS = {"right", "turn right", "go right", "rotate right", "clockwise"}

_FOLLOW_WORDS = {"follow", "track", "keep up", "stay behind", "trail"}
_SEARCH_WORDS = {"find", "search", "look for", "locate", "seek", "where is"}

_RETURN_WORDS = {"home", "return home", "go home", "come home", "base", "start"}

_LANDMARK_WORDS = {
    "door", "doorway", "entrance", "exit", "hallway", "corridor", "passage",
    "room", "ward", "station", "nurse station", "reception", "desk",
    "elevator", "lift", "stairs", "staircase",
    "chair", "seat", "table", "bed", "trolley", "cart",
    "person", "people", "human", "nurse", "doctor", "patient",
    "wall", "window", "pillar", "column",
    "end", "corner", "junction", "intersection",
    "open", "closed", "red", "green", "blue",
}

_AVOID_WORDS = {
    "avoid", "dodge", "bypass", "stay away from", "keep away from",
    "don't touch", "go around", "clear of",
}

_SLOW_WORDS  = {"slowly", "slow", "careful", "cautiously", "gently", "easy"}
_FAST_WORDS  = {"fast", "quickly", "hurry", "speed up", "faster"}

_SPATIAL = {
    "left": (-0.5, 0.2),     # (dx_hint, dy_hint) in robot frame
    "right": (0.5, -0.2),
    "forward": (0.0, 0.0),
    "back": (-1.0, 0.0),
}

# Default speeds (m/s, rad/s)
_SPEED_NORMAL = (0.10, 0.0)
_SPEED_SLOW   = (0.06, 0.0)
_SPEED_TURN_LEFT  = (0.0,  0.30)
_SPEED_TURN_RIGHT = (0.0, -0.30)


# ---------------------------------------------------------------------------
# Grounding result
# ---------------------------------------------------------------------------

@dataclass
class GroundingTrace:
    """Explanation record for one grounding decision."""
    matched_action:    str = ""
    matched_landmarks: List[str] = field(default_factory=list)
    matched_avoid:     List[str] = field(default_factory=list)
    speed_modifier:    str = "normal"
    confidence_notes:  str = ""


# ---------------------------------------------------------------------------
# Grounder
# ---------------------------------------------------------------------------

class InstructionGrounder:
    """Convert VLNInstruction into GroundedGoal using deterministic rules.

    Future upgrades: replace or augment the `ground()` method with
    an LLM/VLM grounding call while keeping the same return type.
    """

    def __init__(
        self,
        topomap_dir: Optional[str] = None,
        min_confidence: float = 0.30,
    ):
        self._topomap_dir = topomap_dir
        self._min_confidence = min_confidence

    # ── Public API ────────────────────────────────────────────────────────────

    def ground(self, instruction: VLNInstruction) -> GroundedGoal:
        """Main entry point — returns a GroundedGoal from any VLNInstruction."""
        text = (instruction.transcript or instruction.raw_text or "").lower()
        trace = GroundingTrace()

        # Confidence floor from ASR
        base_conf = instruction.transcript_confidence or 1.0
        if not text.strip():
            return GroundedGoal(
                label="empty instruction",
                confidence=0.0,
                clarification_needed=True,
                stop_reason="empty instruction",
            )

        # 1. Safety-critical override: stop
        if self._match_any(text, _STOP_WORDS):
            trace.matched_action = "stop"
            return GroundedGoal(
                label="stop",
                confidence=1.0,
                source="rule_based",
                goal_type=GoalType.STOP.value,
                action_type=ActionType.STOP.value,
                nominal_vx=0.0,
                nominal_wz=0.0,
                stop_reason=None,
                grounding_candidates=[trace.__dict__],
            )

        # 2. Extract safety constraints ("avoid X")
        safety_constraints = self._extract_safety_constraints(text, trace)

        # 3. Extract landmarks
        landmarks = self._extract_landmarks(text, trace)

        # 4. Determine action type
        action, nominal_vx, nominal_wz, goal_type = self._extract_action(text, trace)

        # 5. Speed modifier
        if self._match_any(text, _SLOW_WORDS):
            nominal_vx  = min(nominal_vx, 0.06)
            trace.speed_modifier = "slow"
        elif self._match_any(text, _FAST_WORDS):
            nominal_vx  = min(nominal_vx * 1.3, 0.15)
            trace.speed_modifier = "fast"

        # 6. Confidence: lower if unknown action or low ASR confidence
        confidence = base_conf
        if action == ActionType.UNKNOWN:
            confidence *= 0.4
            trace.confidence_notes = "action type unknown"
        if not landmarks and action in (ActionType.NAVIGATE, ActionType.SEARCH):
            confidence *= 0.7
            trace.confidence_notes += " no landmark found"

        label = (
            landmarks[0] if landmarks
            else action.value.replace("_", " ")
        )

        goal = GroundedGoal(
            label=label,
            confidence=round(confidence, 3),
            source="rule_based",
            goal_type=goal_type.value,
            action_type=action.value,
            relative_hint=", ".join(landmarks) if landmarks else None,
            nominal_vx=nominal_vx,
            nominal_wz=nominal_wz,
            safety_constraints=safety_constraints,
            clarification_needed=confidence < self._min_confidence,
            stop_reason=None,
            grounding_candidates=[trace.__dict__],
        )
        if goal.clarification_needed:
            goal.stop_reason = f"low grounding confidence ({confidence:.2f})"
        return goal

    # ── Landmark scoring for topomap ──────────────────────────────────────────

    def score_landmark_against_topomap(
        self,
        landmark: str,
        topomap_dir: Optional[str] = None,
    ) -> List[dict]:
        """Score topomap nodes against a landmark label.

        Returns a ranked list of {node_id, score, image_path}.
        Stub: returns empty list until CLIP/VLM grounding is wired in.
        """
        tdir = topomap_dir or self._topomap_dir
        if not tdir:
            return []
        import os
        candidates = []
        for fname in os.listdir(tdir):
            if fname.endswith((".jpg", ".png")):
                node_id = fname.rsplit(".", 1)[0]
                score = 0.1  # placeholder until CLIP
                if landmark.lower() in node_id.lower():
                    score = 0.6
                candidates.append({
                    "node_id": node_id,
                    "score": score,
                    "image_path": os.path.join(tdir, fname),
                })
        return sorted(candidates, key=lambda x: x["score"], reverse=True)[:5]

    def select_subgoal(
        self,
        parsed: GroundedGoal,
        current_rgb=None,
        topomap_dir: Optional[str] = None,
        goal_image=None,
    ) -> GroundedGoal:
        """Refine a grounded goal using topomap/image evidence if available."""
        if goal_image is not None:
            parsed.target_image_path = str(goal_image)
            parsed.source = "goal_image"
            parsed.confidence = min(parsed.confidence + 0.2, 1.0)
        elif parsed.relative_hint and (topomap_dir or self._topomap_dir):
            candidates = self.score_landmark_against_topomap(
                parsed.relative_hint, topomap_dir
            )
            if candidates:
                best = candidates[0]
                parsed.target_node_id = best["node_id"]
                parsed.target_image_path = best["image_path"]
                parsed.source = "topomap"
                parsed.confidence = min(parsed.confidence + best["score"] * 0.3, 1.0)
        return parsed

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _match_any(text: str, wordset: set) -> bool:
        for w in wordset:
            if w in text:
                return True
        return False

    def _extract_safety_constraints(
        self, text: str, trace: GroundingTrace
    ) -> List[SafetyConstraint]:
        constraints = []
        for word in _AVOID_WORDS:
            if word in text:
                after = text[text.index(word) + len(word):].strip()
                for lm in _LANDMARK_WORDS:
                    if lm in after[:40]:
                        c = SafetyConstraint(
                            constraint_type="avoid",
                            target=lm,
                            distance_m=0.5,
                            mandatory=True,
                            source_text=f"{word} {lm}",
                        )
                        constraints.append(c)
                        trace.matched_avoid.append(lm)
                if not constraints:
                    c = SafetyConstraint(
                        constraint_type="avoid",
                        target="obstacles",
                        distance_m=0.5,
                        mandatory=True,
                        source_text=word,
                    )
                    constraints.append(c)
                    trace.matched_avoid.append("obstacles")
                break
        return constraints

    def _extract_landmarks(
        self, text: str, trace: GroundingTrace
    ) -> List[str]:
        found = []
        for lm in _LANDMARK_WORDS:
            if lm in text:
                found.append(lm)
                trace.matched_landmarks.append(lm)
        return found

    def _extract_action(
        self, text: str, trace: GroundingTrace
    ) -> tuple[ActionType, float, float, GoalType]:
        if self._match_any(text, _RETURN_WORDS):
            trace.matched_action = "return_home"
            return ActionType.RETURN_HOME, 0.08, 0.0, GoalType.WAYPOINT

        if self._match_any(text, _SEARCH_WORDS):
            trace.matched_action = "search"
            return ActionType.SEARCH, 0.06, 0.0, GoalType.SEMANTIC_REGION

        if self._match_any(text, _FOLLOW_WORDS):
            trace.matched_action = "follow"
            return ActionType.FOLLOW, 0.08, 0.0, GoalType.WAYPOINT

        has_left  = self._match_any(text, _LEFT_WORDS)
        has_right = self._match_any(text, _RIGHT_WORDS)
        has_fwd   = self._match_any(text, _FORWARD_WORDS)
        has_back  = self._match_any(text, _BACK_WORDS)

        if has_left and not has_right:
            trace.matched_action = "turn_left"
            return ActionType.TURN_LEFT, 0.0, 0.30, GoalType.DIRECTIONAL

        if has_right and not has_left:
            trace.matched_action = "turn_right"
            return ActionType.TURN_RIGHT, 0.0, -0.30, GoalType.DIRECTIONAL

        if has_back and not has_fwd:
            trace.matched_action = "move_back"
            return ActionType.MOVE_BACK, -0.06, 0.0, GoalType.DIRECTIONAL

        if has_fwd or self._match_any(text, list(_LANDMARK_WORDS)):
            trace.matched_action = "navigate"
            return ActionType.NAVIGATE, 0.10, 0.0, GoalType.SEMANTIC_REGION

        trace.matched_action = "unknown"
        return ActionType.UNKNOWN, 0.0, 0.0, GoalType.UNKNOWN
