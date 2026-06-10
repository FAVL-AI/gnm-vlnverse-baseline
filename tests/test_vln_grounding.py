"""Tests for the deterministic VLN instruction grounder."""
from __future__ import annotations

import pytest

from fleet_safe_vla.vln.instruction_schema import (
    ActionType, GoalType, VLNInstruction, InstructionSource,
)
from fleet_safe_vla.vln.grounding import InstructionGrounder


@pytest.fixture
def grounder():
    return InstructionGrounder(min_confidence=0.30)


class TestStopCommands:
    @pytest.mark.parametrize("text", [
        "stop", "halt", "freeze", "emergency stop", "hold", "abort",
    ])
    def test_stop_words_always_stop(self, grounder, text):
        inst = VLNInstruction.from_text(text)
        goal = grounder.ground(inst)
        assert goal.action_type == ActionType.STOP.value
        assert goal.nominal_vx == pytest.approx(0.0)
        assert goal.nominal_wz == pytest.approx(0.0)
        assert goal.confidence == pytest.approx(1.0)
        assert goal.is_actionable()

    def test_stop_has_zero_command(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text("stop the robot"))
        assert goal.nominal_vx == 0.0
        assert goal.nominal_wz == 0.0


class TestDirectionalCommands:
    def test_go_forward(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text("go forward slowly"))
        assert goal.action_type in (ActionType.NAVIGATE.value, ActionType.MOVE_FORWARD.value)
        assert goal.nominal_vx > 0

    def test_turn_left(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text("turn left"))
        assert goal.action_type == ActionType.TURN_LEFT.value
        assert goal.nominal_wz > 0
        assert goal.nominal_vx == pytest.approx(0.0)

    def test_turn_right(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text("turn right"))
        assert goal.action_type == ActionType.TURN_RIGHT.value
        assert goal.nominal_wz < 0
        assert goal.nominal_vx == pytest.approx(0.0)

    def test_go_back(self, grounder):
        # "reverse" or "move backward" — unambiguous back words
        goal = grounder.ground(VLNInstruction.from_text("reverse slowly"))
        assert goal.action_type == ActionType.MOVE_BACK.value
        assert goal.nominal_vx < 0

    def test_return_home(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text("return home"))
        assert goal.action_type == ActionType.RETURN_HOME.value

    def test_slow_modifier_reduces_speed(self, grounder):
        fast = grounder.ground(VLNInstruction.from_text("go forward"))
        slow = grounder.ground(VLNInstruction.from_text("go forward slowly"))
        assert slow.nominal_vx <= fast.nominal_vx


class TestLandmarkExtraction:
    def test_nurse_station(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text("go to the nurse station"))
        assert "station" in goal.label or goal.relative_hint is not None
        assert goal.action_type == ActionType.NAVIGATE.value

    def test_hallway(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text("follow the hallway"))
        assert goal.action_type in (ActionType.FOLLOW.value, ActionType.NAVIGATE.value)

    def test_door(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text("go toward the doorway"))
        assert goal.relative_hint is not None
        assert "door" in goal.relative_hint

    def test_search(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text("find the chair"))
        assert goal.action_type == ActionType.SEARCH.value


class TestSafetyConstraints:
    def test_avoid_people(self, grounder):
        goal = grounder.ground(
            VLNInstruction.from_text("go to the end of the corridor but avoid people")
        )
        targets = [c.target for c in goal.safety_constraints]
        assert any("people" in t or "person" in t for t in targets)

    def test_avoid_obstacles(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text("move forward and avoid obstacles"))
        assert len(goal.safety_constraints) > 0
        assert all(c.mandatory for c in goal.safety_constraints)

    def test_no_avoid_word_no_constraint(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text("go to the door"))
        assert len(goal.safety_constraints) == 0


class TestConfidenceAndClarification:
    def test_empty_instruction_needs_clarification(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text(""))
        assert goal.clarification_needed
        assert not goal.is_actionable()

    def test_low_asr_confidence_reduces_goal_confidence(self, grounder):
        inst = VLNInstruction(raw_text="go forward", transcript="go forward",
                              transcript_confidence=0.2)
        goal = grounder.ground(inst)
        assert goal.confidence < 0.4

    def test_unknown_action_low_confidence(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text("xyzzy quux blorp"))
        assert goal.action_type == ActionType.UNKNOWN.value
        assert goal.confidence < 0.5

    def test_grounding_candidates_logged(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text("go to the door"))
        assert isinstance(goal.grounding_candidates, list)
        assert len(goal.grounding_candidates) >= 1


class TestFullPipeline:
    def test_complex_instruction(self, grounder):
        # Use "avoid" without "stop" to avoid the stop override
        goal = grounder.ground(VLNInstruction.from_text(
            "go past the lift and continue near the red trolley but avoid people"
        ))
        # Must navigate
        assert goal.action_type == ActionType.NAVIGATE.value
        # Must have safety constraint from "avoid people"
        assert len(goal.safety_constraints) > 0

    def test_actionable_result_has_nonzero_command_or_is_stop(self, grounder):
        goal = grounder.ground(VLNInstruction.from_text("move forward slowly"))
        if goal.is_actionable():
            total_vel = abs(goal.nominal_vx) + abs(goal.nominal_wz)
            assert total_vel > 0 or goal.action_type == ActionType.STOP.value
