"""IntentRouter — selects the right parser for each instruction modality."""
from __future__ import annotations

from fleetsafe_vln.multimodal.instruction_schema import MultimodalInstruction, NormalizedGoal


class IntentRouter:
    """Route a MultimodalInstruction to the appropriate parser."""

    def normalize(self, instruction: MultimodalInstruction) -> NormalizedGoal:
        if instruction.image_goal and not instruction.text:
            from fleetsafe_vln.multimodal.image_goal_parser import parse_image_goal
            return parse_image_goal(instruction)

        if instruction.voice_file:
            from fleetsafe_vln.multimodal.voice_parser import parse_voice
            return parse_voice(instruction)

        from fleetsafe_vln.multimodal.text_parser import parse_text
        return parse_text(instruction)

    def from_task(self, task_instruction) -> NormalizedGoal:
        """Convert a TaskInstruction (from task YAML) to a NormalizedGoal."""
        instr = MultimodalInstruction(
            text=getattr(task_instruction, "text", ""),
            voice_file=getattr(task_instruction, "voice_file", None),
            image_goal=getattr(task_instruction, "image_goal", None),
            semantic_goal=getattr(task_instruction, "semantic_goal", ""),
            constraints=list(getattr(task_instruction, "constraints", [])),
        )
        return self.normalize(instr)
