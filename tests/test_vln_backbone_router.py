"""Tests for BackboneRouter — no GPU or model checkpoints required."""
from __future__ import annotations

import math

import pytest

from fleet_safe_vla.vln.backbone_router import BackboneRouter, NominalAction
from fleet_safe_vla.vln.instruction_schema import (
    ActionType, BackboneChoice, GoalType, GroundedGoal, VLNInstruction,
)


@pytest.fixture
def router():
    return BackboneRouter(preferred=BackboneChoice.MOCK, max_vx=0.12, max_wz=0.35)


@pytest.fixture
def stop_goal():
    return GroundedGoal(
        label="stop",
        confidence=1.0,
        action_type=ActionType.STOP.value,
        goal_type=GoalType.STOP.value,
        nominal_vx=0.0,
        nominal_wz=0.0,
    )


@pytest.fixture
def navigate_goal():
    return GroundedGoal(
        label="hallway",
        confidence=0.8,
        action_type=ActionType.NAVIGATE.value,
        goal_type=GoalType.SEMANTIC_REGION.value,
        nominal_vx=0.10,
        nominal_wz=0.0,
    )


class TestBackboneChoice:
    def test_mock_selected_for_stop(self, router, stop_goal):
        choice = router.choose_backbone(stop_goal)
        assert choice == BackboneChoice.MOCK

    def test_preferred_backbone_used_when_set(self, navigate_goal):
        r = BackboneRouter(preferred=BackboneChoice.VINT, max_vx=0.12, max_wz=0.35)
        choice = r.choose_backbone(navigate_goal)
        assert choice == BackboneChoice.VINT

    def test_instruction_preferred_backbone_overrides(self, router, navigate_goal):
        inst = VLNInstruction(preferred_backbone="nomad")
        choice = router.choose_backbone(navigate_goal, instruction=inst)
        assert choice == BackboneChoice.NOMAD

    def test_image_goal_selects_vint(self, navigate_goal):
        r = BackboneRouter(preferred=BackboneChoice.AUTO, max_vx=0.12, max_wz=0.35)
        navigate_goal.target_image_path = "/tmp/goal.jpg"
        choice = r.choose_backbone(navigate_goal)
        assert choice == BackboneChoice.VINT


class TestNominalAction:
    def test_stop_goal_gives_zero(self, router, stop_goal):
        action = router.run_nominal_policy(stop_goal)
        assert math.isclose(action.vx, 0.0)
        assert math.isclose(action.wz, 0.0)

    def test_navigate_goal_gives_positive_vx(self, router, navigate_goal):
        action = router.run_nominal_policy(navigate_goal)
        assert action.vx > 0
        assert action.vx <= 0.12

    def test_action_clipped_to_max(self):
        r = BackboneRouter(preferred=BackboneChoice.MOCK, max_vx=0.05, max_wz=0.20)
        goal = GroundedGoal(nominal_vx=0.99, nominal_wz=0.99,
                            action_type=ActionType.NAVIGATE.value, confidence=0.9)
        action = r.run_nominal_policy(goal)
        assert action.vx <= 0.05
        assert action.wz <= 0.20

    def test_as_list_length(self, router, navigate_goal):
        action = router.run_nominal_policy(navigate_goal)
        lst = action.as_list()
        assert len(lst) == 2
        assert all(math.isfinite(v) for v in lst)

    def test_explanation_non_empty(self, router, navigate_goal):
        action = router.run_nominal_policy(navigate_goal)
        assert isinstance(action.explanation, str)
        assert len(action.explanation) > 0

    def test_inference_ms_logged(self, router, navigate_goal):
        action = router.run_nominal_policy(navigate_goal)
        assert action.inference_ms >= 0

    def test_real_adapter_unavailable_falls_back_gracefully(self, navigate_goal):
        """When a real adapter raises, router falls back to mock without crashing."""
        r = BackboneRouter(preferred=BackboneChoice.GNM, max_vx=0.12, max_wz=0.35)
        # GNM adapter will likely be unavailable (no checkpoint) — should fall back
        action = r.run_nominal_policy(navigate_goal)
        assert math.isfinite(action.vx)
        assert math.isfinite(action.wz)


class TestActuatorLimits:
    @pytest.mark.parametrize("vx,wz,exp_vx,exp_wz", [
        (0.05, 0.0, 0.05, 0.0),
        (0.20, 0.0, 0.12, 0.0),    # clipped
        (-0.20, 0.0, -0.12, 0.0),  # negative clipped
        (0.0, 0.50, 0.0, 0.35),    # wz clipped
    ])
    def test_clip(self, vx, wz, exp_vx, exp_wz):
        r = BackboneRouter(preferred=BackboneChoice.MOCK, max_vx=0.12, max_wz=0.35)
        goal = GroundedGoal(nominal_vx=vx, nominal_wz=wz,
                            action_type=ActionType.NAVIGATE.value, confidence=0.9)
        action = r.run_nominal_policy(goal)
        assert math.isclose(action.vx, exp_vx, abs_tol=1e-9)
        assert math.isclose(action.wz, exp_wz, abs_tol=1e-9)
