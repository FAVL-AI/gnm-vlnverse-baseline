"""
tests/test_transparency_contract.py
Unit tests for fleet_safe_vla.explainability.transparency_contract.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fleet_safe_vla.explainability.transparency_contract import (
    REQUIRED_ACTION_COLUMNS,
    REQUIRED_EPISODE_FILES,
    TransparencyViolation,
    validate_mock_backend_labelled,
    validate_transparency_artifacts,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _write_complete_episode(ep_dir: Path, backend: str = "mock") -> None:
    """Write a complete, contract-satisfying episode directory."""
    ep_dir.mkdir(parents=True, exist_ok=True)

    # episode.json
    ep = {
        "model":   "gnm",
        "backend": backend,
        "seed":    0,
        "scene":   "straight_corridor",
        "success": False,
        "steps": [
            {
                "step":                   0,
                "x":                      0.0,
                "y":                      0.0,
                "min_dist_m":             1.5,
                "depth":                  None,
                "depth_missing_reason":  "sensor_not_available_in_this_backend",
                "lidar":                  None,
                "lidar_missing_reason":  "sensor_not_available_in_this_backend",
            }
        ],
    }
    (ep_dir / "episode.json").write_text(json.dumps(ep))

    # trajectory.csv
    with (ep_dir / "trajectory.csv").open("w", newline="") as fh:
        csv.DictWriter(fh, fieldnames=["step", "x", "y", "heading", "latency_ms"]).writeheader()

    # actions.csv (all required columns present + delta_l2 value)
    with (ep_dir / "actions.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "step", "raw_vx", "raw_vy", "raw_wz",
            "safe_vx", "safe_vy", "safe_wz",
            "delta_l2", "intervened", "min_dist_m",
        ])
        writer.writeheader()
        writer.writerow({
            "step": 0,
            "raw_vx": 0.2, "raw_vy": 0.0, "raw_wz": 0.0,
            "safe_vx": 0.2, "safe_vy": 0.0, "safe_wz": 0.0,
            "delta_l2": 0.0, "intervened": False, "min_dist_m": 1.5,
        })

    # safety_events.jsonl
    (ep_dir / "safety_events.jsonl").write_text("")

    # metrics.json
    (ep_dir / "metrics.json").write_text(json.dumps({"success": False}))

    # scene_graphs.jsonl
    (ep_dir / "scene_graphs.jsonl").write_text(
        json.dumps({"step": 0, "timestamp_s": 0.0, "nodes": [], "edges": []}) + "\n"
    )

    # explanation_log.jsonl
    (ep_dir / "explanation_log.jsonl").write_text(
        json.dumps({
            "step": 0, "natural_language": "Normal operation.",
            "causal_summary": "No event.", "counterfactual_summary": "N/A",
            "action_delta_l2": 0.0, "safety_margin_m": 0.30,
            "active_constraints": [],
        }) + "\n"
    )

    # counterfactuals.jsonl
    (ep_dir / "counterfactuals.jsonl").write_text(
        json.dumps({
            "step": 0, "was_intervention": False,
            "original_obstacle_id": "none", "original_distance_m": 1.5,
            "hypothetical_distance_m": 1.5, "distance_shift_m": 0.0,
            "original_action": [0.2, 0.0, 0.0], "hypothetical_action": [0.2, 0.0, 0.0],
            "action_accepted": True, "explanation": "No intervention.",
        }) + "\n"
    )

    # audit_trail.json
    backend_label = (
        "ENGINEERING_ONLY — not publication evidence"
        if backend == "mock"
        else backend
    )
    audit = {
        "model":               "gnm",
        "fleetsafe":           False,
        "backend":             backend,
        "backend_label":       backend_label,
        "scene":               "straight_corridor",
        "seed":                0,
        "checkpoint_path":     "",
        "checkpoint_hash":     "unknown",
        "total_steps":         1,
        "intervention_steps":  0,
        "transparency_status": "PASS",
    }
    (ep_dir / "audit_trail.json").write_text(json.dumps(audit))


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestTransparencyContract:
    def test_passes_on_complete_episode(self, tmp_path):
        ep_dir = tmp_path / "episode_0001"
        _write_complete_episode(ep_dir, backend="mock")
        result = validate_transparency_artifacts(ep_dir)
        assert result["status"] == "PASS"

    def test_passes_on_mujoco_backend(self, tmp_path):
        ep_dir = tmp_path / "episode_0001"
        _write_complete_episode(ep_dir, backend="mujoco")
        result = validate_transparency_artifacts(ep_dir)
        assert result["status"] == "PASS"

    def test_fails_when_explanation_log_missing(self, tmp_path):
        ep_dir = tmp_path / "episode_0001"
        _write_complete_episode(ep_dir)
        (ep_dir / "explanation_log.jsonl").unlink()
        with pytest.raises(TransparencyViolation, match="explanation_log.jsonl"):
            validate_transparency_artifacts(ep_dir)

    def test_fails_when_scene_graphs_missing(self, tmp_path):
        ep_dir = tmp_path / "episode_0001"
        _write_complete_episode(ep_dir)
        (ep_dir / "scene_graphs.jsonl").unlink()
        with pytest.raises(TransparencyViolation, match="scene_graphs.jsonl"):
            validate_transparency_artifacts(ep_dir)

    def test_fails_when_counterfactuals_missing(self, tmp_path):
        ep_dir = tmp_path / "episode_0001"
        _write_complete_episode(ep_dir)
        (ep_dir / "counterfactuals.jsonl").unlink()
        with pytest.raises(TransparencyViolation, match="counterfactuals.jsonl"):
            validate_transparency_artifacts(ep_dir)

    def test_fails_when_audit_trail_missing(self, tmp_path):
        ep_dir = tmp_path / "episode_0001"
        _write_complete_episode(ep_dir)
        (ep_dir / "audit_trail.json").unlink()
        with pytest.raises(TransparencyViolation, match="audit_trail.json"):
            validate_transparency_artifacts(ep_dir)

    def test_fails_when_episode_json_missing(self, tmp_path):
        ep_dir = tmp_path / "episode_0001"
        _write_complete_episode(ep_dir)
        (ep_dir / "episode.json").unlink()
        with pytest.raises(TransparencyViolation, match="episode.json"):
            validate_transparency_artifacts(ep_dir)

    def test_fails_when_actions_csv_missing_required_column(self, tmp_path):
        ep_dir = tmp_path / "episode_0001"
        _write_complete_episode(ep_dir)
        # Overwrite with actions.csv missing delta_l2
        with (ep_dir / "actions.csv").open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=[
                "step", "raw_vx", "raw_vy", "raw_wz",
                "safe_vx", "safe_vy", "safe_wz",
                "intervened", "min_dist_m",
                # delta_l2 intentionally omitted
            ])
            writer.writeheader()
            writer.writerow({
                "step": 0,
                "raw_vx": 0.2, "raw_vy": 0.0, "raw_wz": 0.0,
                "safe_vx": 0.2, "safe_vy": 0.0, "safe_wz": 0.0,
                "intervened": False, "min_dist_m": 1.5,
            })
        with pytest.raises(TransparencyViolation, match="delta_l2"):
            validate_transparency_artifacts(ep_dir)

    def test_fails_when_mock_backend_not_labelled(self, tmp_path):
        ep_dir = tmp_path / "episode_0001"
        _write_complete_episode(ep_dir, backend="mock")
        # Overwrite audit_trail with wrong label
        audit_path = ep_dir / "audit_trail.json"
        audit = json.loads(audit_path.read_text())
        audit["backend_label"] = "mock_backend"   # missing "engineering"
        audit_path.write_text(json.dumps(audit))
        with pytest.raises(TransparencyViolation, match="ENGINEERING_ONLY"):
            validate_transparency_artifacts(ep_dir)

    def test_mujoco_backend_does_not_require_engineering_label(self, tmp_path):
        ep_dir = tmp_path / "episode_0001"
        _write_complete_episode(ep_dir, backend="mujoco")
        # Should pass without the engineering-only label
        result = validate_transparency_artifacts(ep_dir)
        assert result["status"] == "PASS"

    def test_fails_when_episode_json_missing_required_key(self, tmp_path):
        ep_dir = tmp_path / "episode_0001"
        _write_complete_episode(ep_dir)
        ep_path = ep_dir / "episode.json"
        ep = json.loads(ep_path.read_text())
        del ep["model"]   # remove required key
        ep_path.write_text(json.dumps(ep))
        with pytest.raises(TransparencyViolation, match="model"):
            validate_transparency_artifacts(ep_dir)

    def test_missing_sensor_allowed_with_missing_reason(self, tmp_path):
        ep_dir = tmp_path / "episode_0001"
        _write_complete_episode(ep_dir)
        # default fixture already has missing_reason → should PASS
        result = validate_transparency_artifacts(ep_dir)
        assert result["status"] == "PASS"

    def test_missing_sensor_fails_without_missing_reason(self, tmp_path):
        ep_dir = tmp_path / "episode_0001"
        _write_complete_episode(ep_dir)
        ep_path = ep_dir / "episode.json"
        ep = json.loads(ep_path.read_text())
        # Remove the missing_reason for lidar
        del ep["steps"][0]["lidar_missing_reason"]
        ep_path.write_text(json.dumps(ep))
        with pytest.raises(TransparencyViolation, match="lidar_missing_reason"):
            validate_transparency_artifacts(ep_dir)

    def test_checks_passed_count_positive(self, tmp_path):
        ep_dir = tmp_path / "episode_0001"
        _write_complete_episode(ep_dir)
        result = validate_transparency_artifacts(ep_dir)
        assert result["checks_passed"] > 0


class TestMockBackendLabelling:
    def test_mock_backend_correctly_labelled_passes(self):
        audit = {
            "backend":       "mock",
            "backend_label": "ENGINEERING_ONLY — not publication evidence",
        }
        assert validate_mock_backend_labelled(audit) is True

    def test_mock_backend_not_labelled_raises(self):
        audit = {
            "backend":       "mock",
            "backend_label": "development backend",
        }
        with pytest.raises(TransparencyViolation):
            validate_mock_backend_labelled(audit)

    def test_non_mock_backend_always_passes(self):
        for backend in ("mujoco", "isaaclab", "real"):
            audit = {"backend": backend, "backend_label": backend}
            assert validate_mock_backend_labelled(audit) is True
