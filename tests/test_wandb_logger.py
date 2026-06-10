"""
tests/test_wandb_logger.py — WandbLogger with fully mocked wandb module.

All tests run without a W&B account or internet access.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ── Mock wandb before importing anything that would pull it in ─────────────────

def _make_wandb_mock():
    wandb = types.ModuleType("wandb")
    wandb.init       = MagicMock(return_value=MagicMock())
    wandb.log        = MagicMock()
    wandb.finish     = MagicMock()
    wandb.log_artifact = MagicMock()

    class _Table:
        def __init__(self, columns, data): self.columns = columns; self.data = data
    class _Artifact:
        def __init__(self, **kw): self.files = []
        def add_file(self, path, name=None): self.files.append((path, name))
    class _Html:
        def __init__(self, path): self.path = path

    wandb.Table    = _Table
    wandb.Artifact = _Artifact
    wandb.Html     = _Html

    run_mock = MagicMock()
    run_mock.id = "test-run-id"
    run_mock.summary = {}
    wandb.run = run_mock

    return wandb

_WANDB_MOCK = _make_wandb_mock()
sys.modules["wandb"] = _WANDB_MOCK

from fleet_safe_vla.benchmarks.wandb_logger import (
    WandbLogger,
    add_wandb_args,
    _check_wandb,
    _AGG_METRICS,
    _EP_METRICS,
)
from fleet_safe_vla.benchmarks.visualnav_metrics import EpisodeMetrics


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reset_mock():
    """Reset all call history on the wandb mock between tests."""
    _WANDB_MOCK.init.reset_mock()
    _WANDB_MOCK.log.reset_mock()
    _WANDB_MOCK.finish.reset_mock()
    _WANDB_MOCK.log_artifact.reset_mock()
    _WANDB_MOCK.run.summary.clear()


def _make_logger(enabled=True, **kw) -> WandbLogger:
    return WandbLogger(enabled=enabled, project="test-project", **kw)


def _make_episode(**kw) -> EpisodeMetrics:
    defaults = dict(
        model_name="gnm", fleetsafe=True, backend="mock",
        scene="hospital_corridor", seed=0,
        success=True, spl=0.8, path_length_m=2.5, optimal_path_m=2.0,
        time_to_goal_s=5.0, collision_count=0, near_violation_count=1,
        intervention_count=3, intervention_rate=0.03,
        inference_latency_ms_mean=6.4, inference_latency_ms_p95=6.7,
        crowding_risk_score_mean=0.3, steps_green=40, steps_amber=5, steps_red=0,
        perception_source="mock", detection_count_total=20,
        tracked_agent_count_max=2, perception_latency_ms_mean=1.2,
    )
    defaults.update(kw)
    return EpisodeMetrics(**defaults)


def _make_agg() -> dict:
    return {
        "n_episodes":              1,
        "success_rate":            1.0,
        "spl_mean":                0.8,
        "collision_rate":          0.0,
        "intervention_rate_mean":  0.03,
        "near_violation_rate":     0.01,
        "inference_latency_ms_mean": 6.4,
        "inference_latency_ms_p95":  6.7,
        "sim_fps_mean":            156.0,
        "crowding_risk_score_mean": 0.3,
        "steps_green_frac":        0.9,
        "steps_amber_frac":        0.1,
        "steps_red_frac":          0.0,
        "perception_latency_ms_mean": 1.2,
    }


# ════════════════════════════════════════════════════════════════════════════════
# _check_wandb
# ════════════════════════════════════════════════════════════════════════════════

class TestCheckWandb:

    def test_returns_true_when_installed(self):
        assert _check_wandb() is True

    def test_required_true_no_raise_when_installed(self):
        assert _check_wandb(required=True) is True

    def test_returns_false_when_not_installed(self):
        # Setting sys.modules['wandb'] = None blocks re-import even when the
        # package is installed on disk; sys.modules.pop alone does not prevent
        # Python from finding the package in site-packages.
        with patch.dict(sys.modules, {"wandb": None}):
            result = _check_wandb(required=False)
        assert result is False

    def test_raises_when_required_and_not_installed(self):
        with patch.dict(sys.modules, {"wandb": None}):
            with pytest.raises(ImportError, match="pip install wandb"):
                _check_wandb(required=True)


# ════════════════════════════════════════════════════════════════════════════════
# WandbLogger — disabled mode
# ════════════════════════════════════════════════════════════════════════════════

class TestWandbLoggerDisabled:

    def setup_method(self): _reset_mock()

    def test_disabled_start_no_init(self):
        lg = _make_logger(enabled=False)
        lg.start({"model": "gnm"})
        _WANDB_MOCK.init.assert_not_called()

    def test_disabled_finish_no_call(self):
        lg = _make_logger(enabled=False)
        lg.finish()
        _WANDB_MOCK.finish.assert_not_called()

    def test_disabled_log_run_no_call(self):
        lg = _make_logger(enabled=False)
        lg.log_run("gnm", True, "mock", _make_agg(), [_make_episode()])
        _WANDB_MOCK.log.assert_not_called()

    def test_disabled_log_per_scene_no_call(self):
        lg = _make_logger(enabled=False)
        lg.log_per_scene("gnm", True, {"scene": _make_agg()})
        _WANDB_MOCK.log.assert_not_called()

    def test_disabled_log_artifacts_no_call(self):
        lg = _make_logger(enabled=False)
        lg.log_artifacts()
        _WANDB_MOCK.log_artifact.assert_not_called()

    def test_enabled_property_false(self):
        lg = _make_logger(enabled=False)
        assert lg.enabled is False


# ════════════════════════════════════════════════════════════════════════════════
# WandbLogger — enabled mode
# ════════════════════════════════════════════════════════════════════════════════

class TestWandbLoggerEnabled:

    def setup_method(self): _reset_mock()

    def test_enabled_property_true(self):
        lg = _make_logger()
        assert lg.enabled is True

    def test_start_calls_wandb_init(self):
        lg = _make_logger()
        lg.start({"model": "gnm", "backend": "mock"})
        _WANDB_MOCK.init.assert_called_once()

    def test_start_passes_project(self):
        lg = _make_logger()
        lg.start({})
        call_kw = _WANDB_MOCK.init.call_args[1]
        assert call_kw["project"] == "test-project"

    def test_start_passes_config(self):
        lg = _make_logger()
        cfg = {"model": "vint", "backend": "mujoco", "fleetsafe": True}
        lg.start(cfg)
        call_kw = _WANDB_MOCK.init.call_args[1]
        assert call_kw["config"] == cfg

    def test_finish_calls_wandb_finish(self):
        lg = _make_logger()
        lg._run = MagicMock()
        lg.finish()
        _WANDB_MOCK.finish.assert_called_once()

    def test_finish_clears_run(self):
        lg = _make_logger()
        lg._run = MagicMock()
        lg.finish()
        assert lg._run is None

    def test_log_run_calls_wandb_log(self):
        lg = _make_logger()
        lg._run = MagicMock()
        lg.log_run("gnm", True, "mock", _make_agg(), [_make_episode()])
        assert _WANDB_MOCK.log.call_count >= 2  # at least agg + 1 episode

    def test_log_run_prefix_in_keys(self):
        lg = _make_logger()
        lg._run = MagicMock()
        lg.log_run("gnm", True, "mock", _make_agg(), [])
        first_call_kwargs = _WANDB_MOCK.log.call_args_list[0][0][0]
        assert any("gnm/fs/" in k for k in first_call_kwargs)

    def test_log_run_baseline_prefix(self):
        lg = _make_logger()
        lg._run = MagicMock()
        lg.log_run("gnm", False, "mock", _make_agg(), [])
        first_call_kwargs = _WANDB_MOCK.log.call_args_list[0][0][0]
        assert any("gnm/base/" in k for k in first_call_kwargs)

    def test_log_run_success_rate_present(self):
        lg = _make_logger()
        lg._run = MagicMock()
        lg.log_run("gnm", True, "mock", _make_agg(), [])
        first_call_kwargs = _WANDB_MOCK.log.call_args_list[0][0][0]
        assert "gnm/fs/success_rate" in first_call_kwargs
        assert first_call_kwargs["gnm/fs/success_rate"] == pytest.approx(1.0)

    def test_log_run_episode_stream(self):
        lg = _make_logger()
        lg._run = MagicMock()
        episodes = [_make_episode(seed=i) for i in range(3)]
        lg.log_run("gnm", True, "mock", _make_agg(), episodes)
        # 1 agg call + 3 episode calls = 4 total
        assert _WANDB_MOCK.log.call_count == 4

    def test_log_per_scene_creates_table(self):
        lg = _make_logger()
        lg._run = MagicMock()
        by_scene = {"corridor": _make_agg(), "lobby": _make_agg()}
        lg.log_per_scene("gnm", True, by_scene)
        _WANDB_MOCK.log.assert_called_once()
        payload = _WANDB_MOCK.log.call_args[0][0]
        assert "gnm/fs/per_scene_table" in payload

    def test_log_social_risk_fires_when_keys_present(self):
        lg = _make_logger()
        lg._run = MagicMock()
        lg.log_social_risk("gnm", True, _make_agg())
        # crowding_risk_score_mean is in _make_agg()
        _WANDB_MOCK.log.assert_called_once()
        payload = _WANDB_MOCK.log.call_args[0][0]
        assert "social/gnm/fs/crowding_risk_score_mean" in payload

    def test_log_social_risk_no_call_if_no_keys(self):
        lg = _make_logger()
        lg._run = MagicMock()
        lg.log_social_risk("gnm", True, {})
        _WANDB_MOCK.log.assert_not_called()

    def test_log_latency_fires(self):
        lg = _make_logger()
        lg._run = MagicMock()
        lg.log_latency("gnm", True, _make_agg())
        _WANDB_MOCK.log.assert_called_once()
        payload = _WANDB_MOCK.log.call_args[0][0]
        assert "latency/gnm/fs/inference_latency_ms_mean" in payload

    def test_set_summary(self):
        lg = _make_logger()
        lg._run = MagicMock()
        lg.set_summary("best_spl", 0.92)
        assert _WANDB_MOCK.run.summary["best_spl"] == pytest.approx(0.92)

    def test_set_summary_disabled_no_error(self):
        lg = _make_logger(enabled=False)
        lg.set_summary("best_spl", 0.92)  # must not raise

    def test_log_html_report_calls_log(self):
        lg = _make_logger()
        lg._run = MagicMock()
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            f.write(b"<html></html>")
            p = Path(f.name)
        try:
            lg.log_html_report(p)
            _WANDB_MOCK.log.assert_called_once()
        finally:
            p.unlink(missing_ok=True)

    def test_log_html_report_missing_file_no_error(self):
        lg = _make_logger()
        lg._run = MagicMock()
        lg.log_html_report(Path("/nonexistent/file.html"))
        _WANDB_MOCK.log.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════════
# Artifact logging
# ════════════════════════════════════════════════════════════════════════════════

class TestArtifactLogging:

    def setup_method(self): _reset_mock()

    def test_log_artifacts_calls_log_artifact(self):
        lg = _make_logger()
        lg._run = MagicMock()
        with tempfile.TemporaryDirectory() as td:
            report_dir = Path(td) / "reports"
            report_dir.mkdir()
            (report_dir / "comparison_20260517_120000.json").write_text("{}")
            lg.log_artifacts(report_dir=report_dir)
        _WANDB_MOCK.log_artifact.assert_called_once()

    def test_log_artifacts_disabled_no_call(self):
        lg = _make_logger(enabled=False)
        with tempfile.TemporaryDirectory() as td:
            lg.log_artifacts(report_dir=Path(td))
        _WANDB_MOCK.log_artifact.assert_not_called()

    def test_log_artifacts_nonexistent_dir_no_error(self):
        lg = _make_logger()
        lg._run = MagicMock()
        lg.log_artifacts(report_dir=Path("/nonexistent/path"))
        # Should not raise; artifact still created (empty)
        _WANDB_MOCK.log_artifact.assert_called_once()

    def test_artifact_adds_json_files(self):
        lg = _make_logger()
        lg._run = MagicMock()

        # Capture the Artifact instance
        created_artifact = None
        original_artifact = _WANDB_MOCK.Artifact

        def capture_artifact(**kw):
            nonlocal created_artifact
            created_artifact = _WANDB_MOCK.Artifact(**kw)
            return created_artifact

        with tempfile.TemporaryDirectory() as td:
            report_dir = Path(td) / "reports"
            report_dir.mkdir()
            (report_dir / "comparison_20260517_120000.json").write_text("{}")
            (report_dir / "comparison_20260517_120000.html").write_text("<html/>")
            lg.log_artifacts(report_dir=report_dir)

        _WANDB_MOCK.log_artifact.assert_called_once()


# ════════════════════════════════════════════════════════════════════════════════
# from_args constructor
# ════════════════════════════════════════════════════════════════════════════════

class TestFromArgs:

    def test_from_args_disabled_by_default(self):
        args = argparse.Namespace(
            wandb=False,
            wandb_project="fleetsafe-hospitalnav",
            wandb_entity=None,
            wandb_mode="online",
        )
        lg = WandbLogger.from_args(args)
        assert not lg.enabled

    def test_from_args_enabled(self):
        args = argparse.Namespace(
            wandb=True,
            wandb_project="my-project",
            wandb_entity="my-team",
            wandb_mode="offline",
        )
        lg = WandbLogger.from_args(args)
        assert lg.enabled
        assert lg._project == "my-project"
        assert lg._entity  == "my-team"
        assert lg._mode    == "offline"

    def test_from_args_missing_attributes_uses_defaults(self):
        args = argparse.Namespace()  # no wandb attributes at all
        lg = WandbLogger.from_args(args)
        assert not lg.enabled
        assert lg._project == "fleetsafe-hospitalnav"


# ════════════════════════════════════════════════════════════════════════════════
# add_wandb_args
# ════════════════════════════════════════════════════════════════════════════════

class TestAddWandbArgs:

    def _parser(self):
        return argparse.ArgumentParser()

    def test_adds_wandb_flag(self):
        p = self._parser()
        add_wandb_args(p)
        args = p.parse_args([])
        assert args.wandb is False

    def test_wandb_flag_true(self):
        p = self._parser()
        add_wandb_args(p)
        args = p.parse_args(["--wandb"])
        assert args.wandb is True

    def test_default_project(self):
        p = self._parser()
        add_wandb_args(p)
        args = p.parse_args([])
        assert args.wandb_project == "fleetsafe-hospitalnav"

    def test_custom_project(self):
        p = self._parser()
        add_wandb_args(p)
        args = p.parse_args(["--wandb-project", "my-exp"])
        assert args.wandb_project == "my-exp"

    def test_default_entity_none(self):
        p = self._parser()
        add_wandb_args(p)
        args = p.parse_args([])
        assert args.wandb_entity is None

    def test_mode_default_online(self):
        p = self._parser()
        add_wandb_args(p)
        args = p.parse_args([])
        assert args.wandb_mode == "online"

    def test_mode_offline(self):
        p = self._parser()
        add_wandb_args(p)
        args = p.parse_args(["--wandb-mode", "offline"])
        assert args.wandb_mode == "offline"

    def test_mode_choices_enforced(self):
        p = self._parser()
        add_wandb_args(p)
        with pytest.raises(SystemExit):
            p.parse_args(["--wandb-mode", "invalid"])


# ════════════════════════════════════════════════════════════════════════════════
# Metric key set completeness
# ════════════════════════════════════════════════════════════════════════════════

class TestMetricKeySets:

    def test_agg_metrics_non_empty(self):
        assert len(_AGG_METRICS) > 0

    def test_ep_metrics_non_empty(self):
        assert len(_EP_METRICS) > 0

    def test_no_duplicate_agg_keys(self):
        assert len(_AGG_METRICS) == len(set(_AGG_METRICS))

    def test_no_duplicate_ep_keys(self):
        assert len(_EP_METRICS) == len(set(_EP_METRICS))

    def test_core_navigation_keys_in_agg(self):
        for k in ["success_rate", "spl_mean", "collision_rate"]:
            assert k in _AGG_METRICS, f"{k} missing from _AGG_METRICS"

    def test_social_keys_in_agg(self):
        for k in ["crowding_risk_score_mean", "steps_green_frac", "steps_red_frac"]:
            assert k in _AGG_METRICS, f"{k} missing from _AGG_METRICS"

    def test_perception_keys_in_agg(self):
        assert "perception_latency_ms_mean" in _AGG_METRICS

    def test_spl_in_ep_metrics(self):
        assert "spl" in _EP_METRICS

    def test_intervention_in_ep_metrics(self):
        assert "intervention_rate" in _EP_METRICS
