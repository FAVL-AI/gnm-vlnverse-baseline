"""High-level VLN planner: language instruction → sequence of GNM goals.

For Track B, the planner decomposes a long-horizon instruction into a
sequence of subgoals that GNM can navigate to one-by-one.

Example
────────
  Instruction: "Exit the room, turn left at the junction, and stop at
                the vending machine."

  Subgoal decomposition:
    Step 1: goal = image of door
    Step 2: goal = image of junction
    Step 3: goal = image of vending machine

  For each subgoal, GNM navigates until dist_pred < stop_threshold,
  then the planner advances to the next subgoal.

Implementation
───────────────
  The current implementation uses:
    1. SubgoalSelector.select() to find ONE best-matching subgoal
       from the topological map.
    2. For multi-step plans: decompose instruction using Gemini API
       into sub-instructions, then retrieve a keyframe per sub-instruction.

  This is the RETRIEVAL-BASED approach (no hallucination, no generation).
  Every subgoal image is a real frame from the reference trajectory.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from .subgoal_selector import SubgoalSelector

logger = logging.getLogger(__name__)


class VLNPlanner:
    """Language-conditioned navigation planner for Track B.

    Parameters
    ----------
    selector : SubgoalSelector
        Retrieves goal images given text instructions.
    multi_step : bool
        If True, decompose instruction into sub-steps using LLM.
        If False, retrieve a single subgoal (simpler, more reliable).
    """

    def __init__(
        self,
        selector: SubgoalSelector,
        multi_step: bool = False,
    ) -> None:
        self.selector   = selector
        self.multi_step = multi_step

    def plan(
        self,
        instruction: str,
    ) -> list[tuple[np.ndarray, tuple[float, float]]]:
        """Return a list of (goal_image, goal_position) pairs.

        For multi_step=False: returns one goal.
        For multi_step=True:  returns one goal per sub-instruction.

        Parameters
        ----------
        instruction : str
            Full VLN instruction.

        Returns
        -------
        list of (goal_image, goal_position) — in order of execution.
        """
        if not self.multi_step:
            img, pos, _ = self.selector.select(instruction)
            return [(img, pos)]

        sub_instructions = self._decompose(instruction)
        logger.info(f"Decomposed into {len(sub_instructions)} sub-steps")

        goals = []
        for sub in sub_instructions:
            img, pos, _ = self.selector.select(sub)
            goals.append((img, pos))
            logger.debug(f"  Subgoal: '{sub[:60]}...' → pos={pos}")

        return goals

    def _decompose(self, instruction: str) -> list[str]:
        """Use Gemini (or fallback) to split instruction into sub-steps.

        Returns list of sub-instruction strings.
        Fallback: return the whole instruction as one step.
        """
        try:
            return self._decompose_gemini(instruction)
        except Exception as e:
            logger.warning(f"Instruction decomposition failed ({e}) — using single step")
            return [instruction]

    def _decompose_gemini(self, instruction: str) -> list[str]:
        """Call Gemini API to decompose instruction into waypoint sub-steps."""
        import os
        import json
        import urllib.request

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set")

        prompt = (
            "Split this robot navigation instruction into sequential waypoint "
            "sub-instructions.  Each sub-instruction should describe one "
            "landmark or stopping point.  Return a JSON array of strings.\n\n"
            f"Instruction: {instruction}"
        )

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}]
        }).encode("utf-8")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-pro:generateContent?key={api_key}"
        )
        req  = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=10)
        body = json.loads(resp.read())

        text = body["candidates"][0]["content"]["parts"][0]["text"]

        # Parse JSON from response (handle markdown code blocks)
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        sub_instructions = json.loads(text)
        if not isinstance(sub_instructions, list):
            raise ValueError("Expected JSON array")
        return [str(s) for s in sub_instructions]

    @classmethod
    def from_traj_dir(
        cls,
        traj_dir: Path | str,
        stride: int = 5,
        multi_step: bool = False,
        **kwargs,
    ) -> "VLNPlanner":
        """Convenience factory: build planner from a trajectory directory."""
        selector = SubgoalSelector.from_trajectory(traj_dir, stride=stride, **kwargs)
        return cls(selector=selector, multi_step=multi_step)
