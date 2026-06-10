"""Instruction generator — produce multi-granularity natural language instructions.

Rule-based templates. Optionally routes to VLNTube instube if available.
"""
from __future__ import annotations

import random
from typing import List, Optional


_FINE_TEMPLATES = [
    "Go {direction} and stop near the {goal}.",
    "Navigate {direction} to the {goal}.",
    "Move {direction} along the corridor until you reach the {goal}.",
    "Head {direction} and locate the {goal}.",
]

_COARSE_TEMPLATES = [
    "Find the {goal}.",
    "Go to the {goal}.",
    "Bring me to the {goal}.",
    "Navigate to the {goal}.",
]

_CONSTRAINED_TEMPLATES = [
    "Carefully go {direction} and stop near the {goal}, avoiding people.",
    "Slowly navigate {direction} to the {goal}, keeping to the right side.",
    "Go {direction} to the {goal}, slowing down near doorways.",
]

_DIRECTIONS = ["straight", "forward", "down the corridor", "ahead", "to the left", "to the right"]


class InstructionGenerator:
    """Generate navigation instructions for a given goal label."""

    def __init__(self, seed: int = 0):
        self._rng = random.Random(seed)

    def generate(
        self,
        goal_label: str,
        n_fine: int = 3,
        n_coarse: int = 2,
        n_constrained: int = 2,
    ) -> List[str]:
        label = goal_label.replace("_", " ")
        direction = self._rng.choice(_DIRECTIONS)
        instructions = []

        for tmpl in self._rng.choices(_FINE_TEMPLATES, k=n_fine):
            instructions.append(tmpl.format(direction=direction, goal=label))

        for tmpl in self._rng.choices(_COARSE_TEMPLATES, k=n_coarse):
            instructions.append(tmpl.format(goal=label))

        for tmpl in self._rng.choices(_CONSTRAINED_TEMPLATES, k=n_constrained):
            instructions.append(tmpl.format(direction=direction, goal=label))

        return instructions

    def try_vlntube(
        self,
        goal_label: str,
        scene_graph_path: Optional[str] = None,
    ) -> Optional[List[str]]:
        """Attempt to use VLNTube instube for richer instruction diversity."""
        try:
            import sys
            import importlib.util
            vlntube_root = "third_party/VLNTube"
            spec = importlib.util.spec_from_file_location(
                "instube", f"{vlntube_root}/instube/generate.py"
            )
            if spec is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod.generate_instructions(goal=goal_label, scene_graph=scene_graph_path)
        except Exception:
            return None
