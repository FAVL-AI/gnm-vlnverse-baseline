"""Tests for VLN instruction schemas — no hardware or ROS2 required."""
from __future__ import annotations

import json
import time

import pytest

from fleet_safe_vla.vln.instruction_schema import (
    ActionType, BackboneChoice, GoalType, GroundedGoal,
    InstructionSource, SafetyConstraint, VLNInstruction, VLNPlan, VLNTrace,
)


class TestVLNInstruction:
    def test_default_construction(self):
        inst = VLNInstruction()
        assert inst.raw_text == ""
        assert inst.source == InstructionSource.TEXT.value
        assert inst.confidence == 1.0

    def test_from_text(self):
        inst = VLNInstruction.from_text("go to the nurse station")
        assert inst.raw_text == "go to the nurse station"
        assert inst.transcript == inst.raw_text
        assert inst.source == InstructionSource.TEXT.value

    def test_unique_instruction_ids(self):
        a = VLNInstruction()
        b = VLNInstruction()
        assert a.instruction_id != b.instruction_id

    def test_auto_timestamp(self):
        before = int(time.time() * 1e9)
        inst = VLNInstruction()
        after = int(time.time() * 1e9)
        assert before <= inst.timestamp_ns <= after

    def test_json_roundtrip(self):
        inst = VLNInstruction(
            raw_text="go left past the door",
            source=InstructionSource.VOICE.value,
            transcript_confidence=0.85,
            constraints=["avoid people"],
        )
        restored = VLNInstruction.from_dict(json.loads(inst.to_json()))
        assert restored.raw_text == inst.raw_text
        assert restored.source == inst.source
        assert abs(restored.transcript_confidence - 0.85) < 1e-9
        assert restored.constraints == ["avoid people"]

    def test_preferred_backbone_optional(self):
        inst = VLNInstruction(preferred_backbone="gnm")
        assert inst.preferred_backbone == "gnm"
        inst2 = VLNInstruction()
        assert inst2.preferred_backbone is None


class TestGroundedGoal:
    def test_actionable_when_confident(self):
        g = GroundedGoal(
            label="hallway",
            confidence=0.8,
            action_type=ActionType.NAVIGATE.value,
        )
        assert g.is_actionable()

    def test_not_actionable_when_low_confidence(self):
        g = GroundedGoal(label="?", confidence=0.1, action_type=ActionType.NAVIGATE.value)
        g.clarification_needed = True
        assert not g.is_actionable()

    def test_not_actionable_when_unknown(self):
        g = GroundedGoal(label="?", confidence=0.9, action_type=ActionType.UNKNOWN.value)
        assert not g.is_actionable()

    def test_not_actionable_when_stop_reason(self):
        g = GroundedGoal(
            label="go", confidence=0.9, action_type=ActionType.NAVIGATE.value,
            stop_reason="stale camera",
        )
        assert not g.is_actionable()

    def test_json_roundtrip(self):
        g = GroundedGoal(
            label="door",
            confidence=0.75,
            goal_type=GoalType.SEMANTIC_REGION.value,
            action_type=ActionType.NAVIGATE.value,
            nominal_vx=0.10,
            safety_constraints=[SafetyConstraint(target="people")],
        )
        d = g.to_dict()
        assert d["label"] == "door"
        assert d["safety_constraints"][0]["target"] == "people"
        json.dumps(d)  # must be serialisable


class TestSafetyConstraint:
    def test_defaults(self):
        c = SafetyConstraint()
        assert c.constraint_type == "avoid"
        assert c.distance_m == 0.5
        assert c.mandatory is True

    def test_to_dict(self):
        c = SafetyConstraint(target="chair", distance_m=0.3, source_text="avoid the chair")
        d = c.to_dict()
        assert d["target"] == "chair"
        assert d["distance_m"] == pytest.approx(0.3)


class TestVLNTrace:
    def test_json_roundtrip(self):
        trace = VLNTrace(
            instruction_source="text",
            raw_instruction="go forward",
            model_name="gnm",
            u_nom=[0.1, 0.0],
            u_safe=[0.08, 0.0],
            cbf_active=True,
            qp_status="optimal",
            min_dist_m=1.2,
            h_min=0.69,
            latency_ms=15.3,
        )
        restored = VLNTrace.from_json(trace.to_json())
        assert restored.raw_instruction == "go forward"
        assert restored.model_name == "gnm"
        assert restored.cbf_active is True
        assert abs(restored.min_dist_m - 1.2) < 1e-9

    def test_stop_reason_optional(self):
        t = VLNTrace()
        assert t.stop_reason is None
        d = t.to_dict()
        assert "stop_reason" in d


class TestBackboneChoice:
    def test_valid_values(self):
        for v in ["gnm", "vint", "nomad", "auto", "mock"]:
            bc = BackboneChoice(v)
            assert bc.value == v

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            BackboneChoice("unknown_backbone")


class TestInstructionSource:
    def test_all_values_parse(self):
        for v in ["text", "voice", "image", "voice_text", "image_text", "multimodal", "stdin"]:
            s = InstructionSource(v)
            assert s.value == v
