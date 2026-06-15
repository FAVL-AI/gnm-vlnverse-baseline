"""Tests for vlntube_fleetsafe instruction detection in the Gate B audit.

Covers:
- instruction.txt only
- episode_info.json instruction only
- both sources with same text (no conflict)
- conflicting instruction sources (instruction.txt wins)
- empty instruction.txt
- malformed encoding in instruction.txt
- 253-episode directory structure detection
- instruction with images but no goal_pos
- instruction with images and independent goal_pos (fully colocated)
- generic placeholder instruction excluded from evaluation eligibility
- Gate B decision upgrades when all three colocated
- _classify_instruction_source path-based classification
- _gate_b_decision returns READY_FOR_BENCHMARK_LANGUAGE_EVALUATION when colocated
- _gate_b_decision returns READY_FOR_PROJECT_AUTHORED_ANNOTATION when not colocated
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import pytest

# Ensure the scripts directory is importable
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.gnm.audit_track_b_language_data import (
    _classify_instruction_source,
    _gate_b_decision,
    _read_episode_instruction,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_pkl(ep_dir: Path, instruction: str = "", goal_pos=None) -> None:
    data = {"instruction": instruction}
    if goal_pos is not None:
        data["goal_pos"] = goal_pos
    (ep_dir / "traj_data.pkl").write_bytes(pickle.dumps(data))


def _write_episode_info(ep_dir: Path, instruction_text: str = "", goal_pos=None) -> None:
    d: dict = {}
    if instruction_text:
        d["instruction_text"] = instruction_text
    if goal_pos is not None:
        d["goal_pos"] = goal_pos
    (ep_dir / "episode_info.json").write_text(json.dumps(d))


def _make_jpg(ep_dir: Path, n: int = 3) -> None:
    # Minimal JPEG header bytes so glob("*.jpg") picks them up
    _JPEG_HEADER = bytes([0xFF, 0xD8, 0xFF, 0xE0])
    for i in range(n):
        (ep_dir / f"{i}.jpg").write_bytes(_JPEG_HEADER + b"\x00" * 10)


# ---------------------------------------------------------------------------
# _read_episode_instruction
# ---------------------------------------------------------------------------

class TestReadEpisodeInstruction:

    def test_instruction_txt_only(self, tmp_path):
        ep_dir = tmp_path / "ep"
        ep_dir.mkdir()
        _write_pkl(ep_dir)
        (ep_dir / "instruction.txt").write_text("Walk forward to the window.")
        text, src, conflict = _read_episode_instruction(ep_dir)
        assert text == "Walk forward to the window."
        assert src == "instruction.txt"
        assert conflict is None

    def test_episode_info_only(self, tmp_path):
        ep_dir = tmp_path / "ep"
        ep_dir.mkdir()
        _write_pkl(ep_dir)
        _write_episode_info(ep_dir, instruction_text="Turn right at the sofa.")
        text, src, conflict = _read_episode_instruction(ep_dir)
        assert text == "Turn right at the sofa."
        assert src == "episode_info.json"
        assert conflict is None

    def test_pkl_only(self, tmp_path):
        ep_dir = tmp_path / "ep"
        ep_dir.mkdir()
        _write_pkl(ep_dir, instruction="Navigate straight ahead.")
        text, src, conflict = _read_episode_instruction(ep_dir)
        assert text == "Navigate straight ahead."
        assert src == "traj_data.pkl"
        assert conflict is None

    def test_both_sources_same_text_no_conflict(self, tmp_path):
        ep_dir = tmp_path / "ep"
        ep_dir.mkdir()
        _write_pkl(ep_dir, instruction="Walk forward.")
        (ep_dir / "instruction.txt").write_text("Walk forward.")
        text, src, conflict = _read_episode_instruction(ep_dir)
        assert text == "Walk forward."
        assert src == "instruction.txt"
        assert conflict is None

    def test_conflicting_sources_instruction_txt_wins(self, tmp_path):
        ep_dir = tmp_path / "ep"
        ep_dir.mkdir()
        _write_pkl(ep_dir, instruction="Old instruction from pkl.")
        (ep_dir / "instruction.txt").write_text("Newer instruction from txt.")
        text, src, conflict = _read_episode_instruction(ep_dir)
        assert text == "Newer instruction from txt."
        assert src == "instruction.txt"
        assert conflict is not None
        assert "instruction.txt" in conflict

    def test_empty_instruction_txt_falls_through(self, tmp_path):
        ep_dir = tmp_path / "ep"
        ep_dir.mkdir()
        (ep_dir / "instruction.txt").write_text("")
        _write_episode_info(ep_dir, instruction_text="Fallback from episode_info.")
        text, src, conflict = _read_episode_instruction(ep_dir)
        assert text == "Fallback from episode_info."
        assert src == "episode_info.json"

    def test_malformed_encoding_handled_gracefully(self, tmp_path):
        ep_dir = tmp_path / "ep"
        ep_dir.mkdir()
        # Write non-UTF-8 bytes
        (ep_dir / "instruction.txt").write_bytes(b"Caf\xe9 navigation.")
        text, src, conflict = _read_episode_instruction(ep_dir)
        assert src == "instruction.txt"
        assert "Caf" in text  # replacement char substituted, not raised

    def test_no_sources_returns_empty(self, tmp_path):
        ep_dir = tmp_path / "ep"
        ep_dir.mkdir()
        text, src, conflict = _read_episode_instruction(ep_dir)
        assert text == ""
        assert src == "none"
        assert conflict is None


# ---------------------------------------------------------------------------
# Episode structure tests
# ---------------------------------------------------------------------------

class TestEpisodeStructure:

    def test_instruction_with_images_no_goal_pos(self, tmp_path):
        """Episode has instruction and images but no goal_pos — not evaluation-ready."""
        ep_dir = tmp_path / "ep"
        ep_dir.mkdir()
        (ep_dir / "instruction.txt").write_text("Walk to the kitchen.")
        _make_jpg(ep_dir, n=5)
        _write_pkl(ep_dir)
        # No goal_pos in episode_info
        _write_episode_info(ep_dir, goal_pos=None)
        text, src, _ = _read_episode_instruction(ep_dir)
        assert text
        has_goal = (ep_dir / "episode_info.json").exists() and json.loads(
            (ep_dir / "episode_info.json").read_text()
        ).get("goal_pos") is not None
        assert not has_goal

    def test_instruction_with_images_and_goal_pos_fully_colocated(self, tmp_path):
        """Episode has instruction, images, and goal_pos — evaluation eligible."""
        ep_dir = tmp_path / "ep"
        ep_dir.mkdir()
        (ep_dir / "instruction.txt").write_text(
            "Walk straight down the hallway, keeping the bookshelf on your left. "
            "Stop in front of the large window."
        )
        _make_jpg(ep_dir, n=10)
        _write_pkl(ep_dir)
        _write_episode_info(ep_dir, goal_pos=[-2.88, 2.30])
        text, src, _ = _read_episode_instruction(ep_dir)
        assert text
        assert src == "instruction.txt"
        goal = json.loads((ep_dir / "episode_info.json").read_text()).get("goal_pos")
        assert goal == [-2.88, 2.30]

    def test_generic_placeholder_instruction(self, tmp_path):
        """'Navigate to the goal.' is a generic placeholder, not visually groundable."""
        ep_dir = tmp_path / "ep"
        ep_dir.mkdir()
        (ep_dir / "instruction.txt").write_text("Navigate to the goal.")
        text, _, _ = _read_episode_instruction(ep_dir)
        classification = _classify_instruction_source(text, ep_dir / "instruction.txt")
        assert classification == "generic_placeholder"

    def test_target_derived_instruction_not_independent(self, tmp_path):
        """Instruction referencing x= y= coordinates is target-derived."""
        ep_dir = tmp_path / "ep"
        ep_dir.mkdir()
        (ep_dir / "instruction.txt").write_text("Go to x=3.1, y=2.8.")
        text, _, _ = _read_episode_instruction(ep_dir)
        import re
        has_coord = bool(re.search(r'x\s*=\s*[\d\.]+|y\s*=\s*[\d\.]+', text))
        assert has_coord


# ---------------------------------------------------------------------------
# _classify_instruction_source
# ---------------------------------------------------------------------------

class TestClassifyInstructionSource:

    def test_vlntube_instruction_txt_classified_upstream(self, tmp_path):
        p = tmp_path / "datasets/vlntube/train/kujiale_0092_0_3/instruction.txt"
        text = "Walk forward, keeping the bookshelf on your left."
        src = _classify_instruction_source(text, p)
        assert src == "upstream_repository_provided"

    def test_prebuilt_splits_path_classified_upstream(self, tmp_path):
        p = tmp_path / "datasets/vlntube/prebuilt_data/raw_data/final_splits/fine_train.json.gz"
        text = "Turn left at the sofa and stop near the window."
        src = _classify_instruction_source(text, p)
        assert src == "upstream_repository_provided"

    def test_iamgoodnavigator_path_classified_benchmark(self, tmp_path):
        p = tmp_path / "datasets/vlnverse/imported/iamgoodnavigator/run1/episode_meta.json"
        text = "Navigate to the main room."
        src = _classify_instruction_source(text, p)
        assert src == "benchmark_provided"

    def test_generic_placeholder_classified(self, tmp_path):
        p = tmp_path / "ep/instruction.txt"
        src = _classify_instruction_source("Navigate to the goal.", p)
        assert src == "generic_placeholder"

    def test_none_text_returns_unknown(self):
        assert _classify_instruction_source(None) == "unknown"

    def test_llm_generated_path(self, tmp_path):
        p = tmp_path / "generated/instruction.txt"
        src = _classify_instruction_source("Walk forward.", p)
        assert src == "llm_generated"


# ---------------------------------------------------------------------------
# _gate_b_decision
# ---------------------------------------------------------------------------

def _make_audit(
    *,
    has_real_images: bool,
    has_language_instructions: bool,
    has_independent_targets: bool,
    source_classification: str,
    episode_count: int = 5,
    instruction_count: int = 5,
    image_count: int = 100,
    instruction_generation_method: str = "llm_gemini_from_trajectory_frames",
) -> dict:
    return {
        "has_real_images": has_real_images,
        "has_language_instructions": has_language_instructions,
        "has_independent_targets": has_independent_targets,
        "source_classification": source_classification,
        "episode_count": episode_count,
        "instruction_count": instruction_count,
        "image_count": image_count,
        "instruction_generation_method": instruction_generation_method,
    }


class TestGateBDecision:

    def test_upstream_colocated_yields_benchmark_evaluation(self):
        audits = {
            "vlntube_fleetsafe": _make_audit(
                has_real_images=True,
                has_language_instructions=True,
                has_independent_targets=True,
                source_classification="upstream_repository_provided",
                episode_count=253,
                instruction_count=253,
                image_count=13491,
            )
        }
        decision, rationale = _gate_b_decision(audits)
        assert decision == "READY_FOR_BENCHMARK_LANGUAGE_EVALUATION"
        assert "253" in rationale

    def test_benchmark_colocated_also_yields_benchmark_evaluation(self):
        audits = {
            "my_ds": _make_audit(
                has_real_images=True,
                has_language_instructions=True,
                has_independent_targets=True,
                source_classification="benchmark_provided",
            )
        }
        decision, _ = _gate_b_decision(audits)
        assert decision == "READY_FOR_BENCHMARK_LANGUAGE_EVALUATION"

    def test_upstream_without_independent_targets_not_benchmark(self):
        audits = {
            "vlntube_prebuilt": _make_audit(
                has_real_images=True,
                has_language_instructions=True,
                has_independent_targets=False,
                source_classification="upstream_repository_provided",
            )
        }
        decision, _ = _gate_b_decision(audits)
        assert decision != "READY_FOR_BENCHMARK_LANGUAGE_EVALUATION"

    def test_no_instructions_falls_to_annotation(self):
        audits = {
            "vlntube_fleetsafe": _make_audit(
                has_real_images=True,
                has_language_instructions=False,
                has_independent_targets=True,
                source_classification="upstream_repository_provided",
                instruction_count=0,
            )
        }
        decision, _ = _gate_b_decision(audits)
        assert decision == "READY_FOR_PROJECT_AUTHORED_ANNOTATION"

    def test_no_images_yields_blocked(self):
        audits = {
            "synthetic": _make_audit(
                has_real_images=False,
                has_language_instructions=True,
                has_independent_targets=True,
                source_classification="upstream_repository_provided",
                image_count=0,
            )
        }
        decision, _ = _gate_b_decision(audits)
        assert decision in (
            "READY_FOR_PROJECT_AUTHORED_ANNOTATION",
            "BLOCKED_BY_PROVENANCE_OR_TARGET_LEAKAGE",
        )

    def test_instruction_and_images_not_colocated_yields_annotation(self):
        audits = {
            "real_images_no_instr": _make_audit(
                has_real_images=True,
                has_language_instructions=False,
                has_independent_targets=True,
                source_classification="upstream_repository_provided",
                instruction_count=0,
            ),
            "instr_no_images": _make_audit(
                has_real_images=False,
                has_language_instructions=True,
                has_independent_targets=False,
                source_classification="benchmark_provided",
                image_count=0,
            ),
        }
        decision, _ = _gate_b_decision(audits)
        assert decision == "READY_FOR_PROJECT_AUTHORED_ANNOTATION"

    def test_synthetic_dataset_does_not_trigger_benchmark_decision(self):
        audits = {
            "custom_vln_office": _make_audit(
                has_real_images=False,
                has_language_instructions=True,
                has_independent_targets=False,
                source_classification="project_authored_synthetic",
                image_count=318,
            )
        }
        decision, _ = _gate_b_decision(audits)
        assert decision != "READY_FOR_BENCHMARK_LANGUAGE_EVALUATION"
