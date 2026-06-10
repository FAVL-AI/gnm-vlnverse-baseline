"""Parse text instructions into NormalizedGoal using rule-based matching.

No LLM dependency — keywords and regex patterns only. Suitable for
offline/embedded use. For LLM-based grounding, see intent_router.py.
"""
from __future__ import annotations

import re
from typing import List

from fleetsafe_vln.multimodal.instruction_schema import MultimodalInstruction, NormalizedGoal

_SEMANTIC_GOALS = [
    "nurse station", "nurses station",
    "waiting room", "reception",
    "pharmacy", "icu", "intensive care",
    "exit", "entrance", "elevator", "lift",
    "corridor", "hallway", "room",
    "charging station", "dock",
    "warehouse", "shelf", "aisle",
]

_HUMAN_AWARE_KEYWORDS = [
    "carefully", "slowly", "avoid people", "avoid humans",
    "near people", "around people", "human", "person",
    "patient", "staff", "nurse", "doctor",
]

_CONSERVATIVE_KEYWORDS = [
    "very slowly", "stop immediately", "emergency", "urgent",
    "critical", "fragile",
]

_CONSTRAINT_MAP = {
    r"\bavoid\s+humans?\b": "avoid_humans",
    r"\bkeep\s+right\b": "keep_right_side",
    r"\bslow\s+(down|near)\b": "slow_near_doorways",
    r"\bstop\s+at\b": "stop_at_goal",
    r"\bdo\s+not\s+enter\b": "no_entry",
}


def parse_text(instruction: MultimodalInstruction) -> NormalizedGoal:
    text = (instruction.text or instruction.semantic_goal or "").lower()

    goal_label = ""
    for label in _SEMANTIC_GOALS:
        if label in text:
            goal_label = label.replace(" ", "_")
            break

    constraints: List[str] = list(instruction.constraints)
    for pattern, constraint in _CONSTRAINT_MAP.items():
        if re.search(pattern, text) and constraint not in constraints:
            constraints.append(constraint)

    safety_profile = "standard"
    for kw in _CONSERVATIVE_KEYWORDS:
        if kw in text:
            safety_profile = "conservative"
            break
    if safety_profile == "standard":
        for kw in _HUMAN_AWARE_KEYWORDS:
            if kw in text:
                safety_profile = "human_aware"
                break

    goal_type = "semantic_object" if goal_label else "directional"

    return NormalizedGoal(
        goal_type=goal_type,
        goal_label=goal_label or text[:40],
        goal_image_path=instruction.image_goal,
        route_constraints=constraints,
        safety_profile=safety_profile,
        nominal_vx=0.20 if safety_profile == "standard" else 0.10,
        confidence=0.85 if goal_label else 0.40,
        source_modality="text",
        raw_instruction=instruction.text,
    )
