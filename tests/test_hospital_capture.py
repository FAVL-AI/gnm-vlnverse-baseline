"""
tests/test_hospital_capture.py

Tests for the hospital benchmark capture utilities.
NO Isaac Sim / omni / GPU / conda dependency required.
All tests operate on the pure-Python hospital_capture_utils module.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.isaaclab.hospital_capture_utils import (
    HOSPITAL_ZONES,
    HOSPITAL_WALLS,
    SCENARIO_AGENT_COUNTS,
    SCENARIO_WAYPOINTS,
    parse_degrade,
    update_latest_symlink,
    write_capture_status,
    write_photoreal_status,
    write_procedural_preview,
    write_viewport_status,
)


# ── parse_degrade ──────────────────────────────────────────────────────────────

class TestParseDegrade:
    def test_empty_string_returns_all_zeros(self):
        cfg = parse_degrade("")
        assert cfg["motion_blur"] == 0
        assert cfg["low_light"] == 0
        assert cfg["lidar_dropout_rate"] == 0
        assert cfg["depth_corruption"] is False

    def test_single_numeric_field(self):
        cfg = parse_degrade("motion_blur=40")
        assert cfg["motion_blur"] == 40.0
        assert cfg["low_light"] == 0

    def test_multiple_fields(self):
        cfg = parse_degrade("motion_blur=30,low_light=50,lidar_dropout=10")
        assert cfg["motion_blur"] == 30.0
        assert cfg["low_light"] == 50.0
        assert cfg["lidar_dropout_rate"] == 10.0

    def test_boolean_flag_no_value(self):
        cfg = parse_degrade("depth_corruption")
        assert cfg["depth_corruption"] is True

    def test_boolean_flag_with_numeric_fields(self):
        cfg = parse_degrade("motion_blur=20,depth_corruption")
        assert cfg["motion_blur"] == 20.0
        assert cfg["depth_corruption"] is True

    def test_alias_lidar_dropout(self):
        cfg = parse_degrade("lidar_dropout=15")
        assert cfg["lidar_dropout_rate"] == 15.0

    def test_alias_packet_loss(self):
        cfg = parse_degrade("packet_loss=5")
        assert cfg["camera_packet_loss"] == 5.0

    def test_alias_latency_jitter(self):
        cfg = parse_degrade("latency_jitter=100")
        assert cfg["latency_jitter_ms"] == 100.0

    def test_alias_blur(self):
        cfg = parse_degrade("blur=60")
        assert cfg["motion_blur"] == 60.0

    def test_whitespace_tolerant(self):
        cfg = parse_degrade("  motion_blur=30 , low_light=10  ")
        assert cfg["motion_blur"] == 30.0
        assert cfg["low_light"] == 10.0

    def test_unknown_key_ignored(self):
        cfg = parse_degrade("not_a_real_key=99")
        assert cfg["motion_blur"] == 0  # unchanged


# ── Scenario / agent config ───────────────────────────────────────────────────

class TestScenarioConfig:
    def test_all_valid_scenarios_have_waypoints_entry(self):
        for scenario in ["none", "crossing", "occlusion", "congestion", "yield", "corridor_rush"]:
            assert scenario in SCENARIO_WAYPOINTS

    def test_none_scenario_has_no_waypoints(self):
        assert SCENARIO_WAYPOINTS["none"] == []

    def test_crossing_has_one_agent(self):
        assert SCENARIO_AGENT_COUNTS["crossing"] == 1

    def test_congestion_has_six_agents(self):
        assert SCENARIO_AGENT_COUNTS["congestion"] == 6

    def test_corridor_rush_has_eight_agents(self):
        assert SCENARIO_AGENT_COUNTS["corridor_rush"] == 8

    def test_all_waypoints_are_2d_tuples(self):
        for scenario, wps in SCENARIO_WAYPOINTS.items():
            for wp in wps:
                assert len(wp) == 2, f"waypoint in '{scenario}' must be (x, y)"


# ── Hospital floor-plan geometry ──────────────────────────────────────────────

class TestFloorPlan:
    def test_five_zones_defined(self):
        assert len(HOSPITAL_ZONES) == 5

    def test_zone_tuple_structure(self):
        for zone in HOSPITAL_ZONES:
            x0, x1, y0, y1, rgb, label = zone
            assert x0 < x1, f"zone '{label}': x0 must be < x1"
            assert y0 < y1, f"zone '{label}': y0 must be < y1"
            assert len(rgb) == 3
            assert all(0.0 <= c <= 1.0 for c in rgb)

    def test_corridor_spans_full_width(self):
        corridors = [z for z in HOSPITAL_ZONES if "Corridor" in z[5]]
        assert len(corridors) == 1
        x0, x1 = corridors[0][0], corridors[0][1]
        assert x0 <= -10 and x1 >= 10

    def test_walls_are_line_segments(self):
        for wall in HOSPITAL_WALLS:
            assert len(wall) == 4


# ── write_viewport_status ─────────────────────────────────────────────────────

class TestWriteViewportStatus:
    def test_writes_status_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            write_viewport_status(d, "PROCEDURAL")
            txt = (d / "viewport_status.txt").read_text().strip()
            assert txt == "PROCEDURAL"

    def test_missing_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            write_viewport_status(d, "MISSING")
            assert (d / "viewport_status.txt").read_text().strip() == "MISSING"

    def test_not_run_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            write_viewport_status(d, "NOT_RUN")
            assert (d / "viewport_status.txt").read_text().strip() == "NOT_RUN"


# ── write_capture_status ──────────────────────────────────────────────────────

class TestWriteCaptureStatus:
    def _make_status(self, tmp: Path, **overrides) -> dict:
        defaults = dict(
            scene="hospital_corridor",
            scenario="crossing",
            isaac_runtime="RECORDED",
            usd_asset="MISSING",
            screenshot="MISSING",
            procedural_preview="RECORDED",
            method="matplotlib",
            timestamp="2026-05-19T00:00:00Z",
            isaac_version="0.54.3",
        )
        defaults.update(overrides)
        return write_capture_status(tmp, **defaults)

    def test_writes_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._make_status(d)
            assert (d / "capture_status.json").exists()

    def test_required_keys_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            status = self._make_status(d)
            for key in ("isaac_runtime", "usd_asset", "screenshot",
                        "procedural_preview", "scene", "scenario",
                        "method", "timestamp", "isaac_version"):
                assert key in status, f"missing key: {key}"

    def test_isaac_runtime_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            status = self._make_status(d)
            assert status["isaac_runtime"] == "RECORDED"

    def test_usd_asset_missing_when_no_usd(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            status = self._make_status(d, usd_asset="MISSING")
            assert status["usd_asset"] == "MISSING"

    def test_json_is_valid_and_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            written = self._make_status(d)
            loaded = json.loads((d / "capture_status.json").read_text())
            assert loaded == written


# ── write_photoreal_status ────────────────────────────────────────────────────

class TestWritePhotorealStatus:
    def _write(self, tmp: Path, **overrides) -> dict:
        defaults = dict(
            render_status="PROCEDURAL",
            usd_loaded=False,
            usd_path=None,
            screenshot_path="/tmp/preview.png",
            method="matplotlib",
            scene="hospital_corridor",
            scenario="crossing",
            timestamp="2026-05-19T00:00:00Z",
            isaac_version="0.54.3",
        )
        defaults.update(overrides)
        write_photoreal_status(tmp, **defaults)
        return json.loads((tmp / "photoreal_status.json").read_text())

    def test_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._write(d)
            assert (d / "photoreal_status.json").exists()

    def test_status_field_correct(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            result = self._write(d, render_status="MISSING")
            assert result["status"] == "MISSING"

    def test_usd_loaded_false_when_no_usd(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            result = self._write(d, usd_loaded=False)
            assert result["usd_loaded"] is False

    def test_dashboard_keys_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            result = self._write(d)
            for key in ("status", "usd_loaded", "usd_path", "screenshot",
                        "capture_method", "scene", "scenario", "timestamp"):
                assert key in result, f"dashboard key missing: {key}"


# ── write_procedural_preview ──────────────────────────────────────────────────

class TestWriteProceduralPreview:
    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("matplotlib"),
        reason="matplotlib not installed",
    )
    def test_creates_png_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            result = write_procedural_preview(d, "hospital_corridor", "crossing")
            assert result is not None
            assert result.exists()
            assert result.suffix == ".png"
            assert result.stat().st_size > 5000  # real PNG, not empty

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("matplotlib"),
        reason="matplotlib not installed",
    )
    def test_none_scenario_still_produces_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            result = write_procedural_preview(d, "hospital_corridor", "none")
            assert result is not None and result.exists()

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("matplotlib"),
        reason="matplotlib not installed",
    )
    def test_all_scenarios_produce_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for scenario in SCENARIO_WAYPOINTS:
                result = write_procedural_preview(d, "hospital_corridor", scenario)
                assert result is not None and result.exists(), f"failed for scenario: {scenario}"

    def test_returns_none_gracefully_without_matplotlib(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "matplotlib":
                raise ImportError("no matplotlib")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with tempfile.TemporaryDirectory() as tmp:
            result = write_procedural_preview(Path(tmp), "hospital_corridor", "none")
            assert result is None


# ── update_latest_symlink ─────────────────────────────────────────────────────

class TestUpdateLatestSymlink:
    def test_creates_symlink_to_run_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "hospital_benchmark"
            run = base / "20260519T000000Z"
            run.mkdir(parents=True)
            update_latest_symlink(run)
            latest = base / "latest"
            assert latest.is_symlink()
            assert latest.resolve() == run.resolve()

    def test_updates_existing_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "hospital_benchmark"
            run1 = base / "20260519T000000Z"
            run2 = base / "20260519T010000Z"
            run1.mkdir(parents=True)
            run2.mkdir(parents=True)
            update_latest_symlink(run1)
            update_latest_symlink(run2)
            latest = base / "latest"
            assert latest.resolve() == run2.resolve()
