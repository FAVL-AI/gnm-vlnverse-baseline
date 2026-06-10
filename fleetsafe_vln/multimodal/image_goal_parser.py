"""Image goal parser — maps an image goal to a NormalizedGoal with goal_type=image."""
from __future__ import annotations

from fleetsafe_vln.multimodal.instruction_schema import MultimodalInstruction, NormalizedGoal


def parse_image_goal(instruction: MultimodalInstruction) -> NormalizedGoal:
    """Use the image_goal path directly as the navigation target for ViNT."""
    if not instruction.image_goal:
        raise ValueError("instruction.image_goal is required for image goal parsing")

    return NormalizedGoal(
        goal_type="image",
        goal_label="image_goal",
        goal_image_path=instruction.image_goal,
        route_constraints=list(instruction.constraints),
        safety_profile=instruction.safety_profile or "standard",
        nominal_vx=0.20,
        confidence=0.95,
        source_modality="image",
        raw_instruction=instruction.text or f"[image goal: {instruction.image_goal}]",
    )
