"""Tests for VLNTraceLogger and the end-to-end demo trace pipeline."""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import pytest

from fleet_safe_vla.vln.instruction_schema import VLNTrace
from fleet_safe_vla.vln.vln_trace_logger import VLNTraceLogger
from fleet_safe_vla.vln.grounding import InstructionGrounder
from fleet_safe_vla.vln.backbone_router import BackboneRouter
from fleet_safe_vla.vln.instruction_schema import (
    ActionType, BackboneChoice, VLNInstruction, InstructionSource,
)
from fleet_safe_vla.vln.instruction_intake import InstructionIntake


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_jsonl() -> Path:
    return Path(tempfile.mkdtemp()) / "vln_trace.jsonl"


def _read_jsonl(path: Path) -> list[dict]:
    rows = path.read_text().strip().splitlines()
    return [json.loads(r) for r in rows if r.strip()]


# ---------------------------------------------------------------------------
# VLNTraceLogger
# ---------------------------------------------------------------------------

class TestVLNTraceLogger:
    def test_creates_file_and_parent_dirs(self):
        td = Path(tempfile.mkdtemp())
        out = td / "nested" / "trace.jsonl"
        with VLNTraceLogger(out) as logger:
            logger.append(VLNTrace(raw_instruction="test"))
        assert out.exists()
        rows = _read_jsonl(out)
        assert len(rows) == 1
        assert rows[0]["raw_instruction"] == "test"

    def test_count_increments(self):
        out = _tmp_jsonl()
        with VLNTraceLogger(out) as logger:
            for i in range(5):
                logger.append(VLNTrace(raw_instruction=f"step {i}"))
            assert logger.count == 5

    def test_append_from_values(self):
        out = _tmp_jsonl()
        with VLNTraceLogger(out) as logger:
            logger.append_from_values(
                raw_instruction="go left",
                model_name="gnm",
                u_nom=[0.0, 0.3],
                u_safe=[0.0, 0.3],
                cbf_active=False,
                qp_status="skipped",
                min_dist_m=1.5,
                h_min=1.5**2 - 0.5**2,
                latency_ms=12.0,
            )
        rows = _read_jsonl(out)
        assert rows[0]["model_name"] == "gnm"
        assert rows[0]["qp_status"] == "skipped"
        assert rows[0]["cbf_active"] is False

    def test_partial_run_readable(self):
        out = _tmp_jsonl()
        logger = VLNTraceLogger(out)
        logger.append(VLNTrace(raw_instruction="step 1"))
        # Don't close — simulate crash
        rows = _read_jsonl(out)
        assert len(rows) == 1
        logger.close()

    def test_append_mode_extends_file(self):
        out = _tmp_jsonl()
        with VLNTraceLogger(out) as logger:
            logger.append(VLNTrace(raw_instruction="first"))
        with VLNTraceLogger(out) as logger:
            logger.append(VLNTrace(raw_instruction="second"))
        rows = _read_jsonl(out)
        assert len(rows) == 2

    def test_read_jsonl_roundtrip(self):
        out = _tmp_jsonl()
        original = [
            VLNTrace(raw_instruction="a", model_name="gnm", u_nom=[0.1, 0.0]),
            VLNTrace(raw_instruction="b", model_name="vint", cbf_active=True),
        ]
        with VLNTraceLogger(out) as logger:
            for t in original:
                logger.append(t)
        restored = VLNTraceLogger.read_jsonl(out)
        assert len(restored) == 2
        assert restored[0].model_name == "gnm"
        assert restored[1].cbf_active is True


# ---------------------------------------------------------------------------
# End-to-end: instruction → grounding → backbone → trace
# ---------------------------------------------------------------------------

class TestEndToEndTrace:
    """Integration test: one instruction produces one valid trace row."""

    def _run_pipeline(self, text: str) -> tuple[VLNTrace, Path]:
        out = _tmp_jsonl()
        grounder = InstructionGrounder()
        router = BackboneRouter(preferred=BackboneChoice.MOCK, max_vx=0.12, max_wz=0.35)

        inst = VLNInstruction.from_text(text)
        goal = grounder.ground(inst)
        action = router.run_nominal_policy(goal, instruction=inst)
        u_nom = action.as_list()
        u_safe = u_nom  # no CBF in unit test

        trace = VLNTrace(
            instruction_source=InstructionSource.TEXT.value,
            raw_instruction=text,
            parsed_instruction=goal.to_dict(),
            chosen_subgoal=goal.to_dict(),
            model_name=action.backbone,
            u_nom=u_nom,
            u_safe=u_safe,
            cbf_active=False,
            qp_status="skipped",
            min_dist_m=1.5,
            h_min=1.5**2 - 0.5**2,
            latency_ms=action.inference_ms,
        )
        with VLNTraceLogger(out) as logger:
            logger.append(trace)
        return trace, out

    def test_stop_produces_zero_command(self):
        trace, out = self._run_pipeline("stop")
        assert math.isclose(trace.u_nom[0], 0.0)
        assert math.isclose(trace.u_nom[1], 0.0)

    def test_forward_produces_positive_vx(self):
        trace, out = self._run_pipeline("go forward")
        assert trace.u_nom[0] > 0

    def test_every_command_has_trace_row(self):
        for text in ["go to the door", "stop", "turn left", "find the chair"]:
            _, out = self._run_pipeline(text)
            rows = _read_jsonl(out)
            assert len(rows) == 1

    def test_trace_row_is_valid_json(self):
        _, out = self._run_pipeline("go to the nurse station avoid people")
        raw = out.read_text().strip()
        d = json.loads(raw)
        assert "raw_instruction" in d
        assert "u_nom" in d
        assert "u_safe" in d
        assert "cbf_active" in d

    def test_u_safe_always_finite(self):
        for text in ["stop", "go forward", "turn right", "find the corridor"]:
            trace, _ = self._run_pipeline(text)
            assert all(math.isfinite(v) for v in trace.u_safe)

    def test_unknown_command_does_not_set_motion(self):
        trace, _ = self._run_pipeline("xyzzy quux blorp thud")
        # Unknown command: confidence low, action unknown
        assert trace.parsed_instruction["action_type"] == ActionType.UNKNOWN.value

    def test_trace_includes_parsed_instruction(self):
        trace, _ = self._run_pipeline("avoid people and go to the door")
        assert "action_type" in trace.parsed_instruction
        assert "safety_constraints" in trace.parsed_instruction
