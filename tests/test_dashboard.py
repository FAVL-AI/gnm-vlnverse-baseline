"""
test_dashboard.py — FleetSafe dashboard data pipeline unit tests.

Covers:
  - load_reports reads JSON reports and returns flat list of dicts
  - load_reports handles Infinity in JSON without crashing
  - deduplicate_latest keeps newest entry per (model, fleetsafe, backend)
  - filter_summaries applies model / backend / scene filters
  - render_terminal does not raise on empty or populated summaries
  - render_html returns valid HTML string
  - render_html writes a file when out_path is given
  - _fmt handles float, bool, None, inf, 1e308
  - _zone_bar returns a string of correct visual length (ignoring ANSI)
  - _html_table handles empty and populated summaries
  - _html_kpi_cards returns non-empty string for populated summaries
  - deduplicate_latest picks the latest timestamp when filenames differ
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import pytest

# Add scripts to path so we can import the module
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "dashboard"))
from fleetsafe_dashboard import (
    load_reports,
    filter_summaries,
    deduplicate_latest,
    render_terminal,
    render_html,
    _fmt,
    _zone_bar,
    _html_table,
    _html_kpi_cards,
    _has_social_data,
    _INF_THRESHOLD,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_BASE_SUMMARY = {
    "model": "gnm",
    "fleetsafe": False,
    "backend": "mock",
    "n_episodes": 4,
    "spl_mean": 0.42,
    "success_rate": 0.75,
    "collision_rate": 0.0,
    "near_violation_count_mean": 1.5,
    "intervention_rate_mean": 0.0,
    "raw_vs_safe_delta_l2_mean": 0.0,
    "inference_latency_ms_mean": 5.0,
    "inference_latency_ms_p95_mean": 7.0,
    "sim_fps_mean": 200.0,
    "steps_green_mean": 60.0,
    "steps_amber_mean": 20.0,
    "steps_red_mean": 10.0,
    "crowding_risk_score_mean": 0.0,
    "occlusion_risk_score_mean": 0.0,
    "social_margin_violation_count_mean": 0.0,
    "min_human_distance_m_mean": float("inf"),
}

_FS_SUMMARY = {**_BASE_SUMMARY, "fleetsafe": True, "intervention_rate_mean": 0.15,
               "raw_vs_safe_delta_l2_mean": 0.40}


def _make_report(tmp_path: Path, name: str, entries: list[dict]) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(entries))
    return p


# ── load_reports ──────────────────────────────────────────────────────────────

def test_load_reports_empty_dir(tmp_path):
    result = load_reports(tmp_path)
    assert result == []


def test_load_reports_reads_json(tmp_path):
    _make_report(tmp_path, "comparison_20260517_120000.json", [_BASE_SUMMARY])
    result = load_reports(tmp_path)
    assert len(result) == 1
    assert result[0]["model"] == "gnm"


def test_load_reports_handles_infinity_json(tmp_path):
    text = json.dumps([_BASE_SUMMARY]).replace('"inf"', 'Infinity')
    # Write a JSON with a bare Infinity value
    p = tmp_path / "comparison_20260517_130000.json"
    data = [dict(_BASE_SUMMARY, min_human_distance_m_mean=None)]
    p.write_text('[{"model":"gnm","fleetsafe":false,"backend":"mock",'
                 '"min_obstacle_distance_m_mean": Infinity}]')
    result = load_reports(tmp_path)
    assert len(result) == 1
    # Should not raise; large float substituted for Infinity
    mhd = result[0].get("min_obstacle_distance_m_mean")
    assert mhd is None or isinstance(mhd, float)


def test_load_reports_skips_invalid_json(tmp_path):
    (tmp_path / "bad.json").write_text("{not valid json}")
    result = load_reports(tmp_path)
    assert result == []


def test_load_reports_skips_entries_without_model(tmp_path):
    _make_report(tmp_path, "comparison_20260517_140000.json",
                 [{"something_else": True}])
    result = load_reports(tmp_path)
    assert result == []


def test_load_reports_attaches_source_filename(tmp_path):
    _make_report(tmp_path, "comparison_20260517_150000.json", [_BASE_SUMMARY])
    result = load_reports(tmp_path)
    assert result[0]["_source"] == "comparison_20260517_150000.json"


def test_load_reports_extra_files(tmp_path):
    p = _make_report(tmp_path / ".." / "extra.json", "extra.json",
                     [_FS_SUMMARY]) if False else None
    extra = tmp_path / "extra.json"
    extra.write_text(json.dumps([_FS_SUMMARY]))
    result = load_reports(tmp_path, extra_files=[extra])
    assert any(s.get("fleetsafe") for s in result)


# ── deduplicate_latest ────────────────────────────────────────────────────────

def test_deduplicate_latest_keeps_one_per_key():
    entries = [
        {**_BASE_SUMMARY, "_source": "comparison_20260516_120000.json"},
        {**_BASE_SUMMARY, "_source": "comparison_20260517_120000.json"},
    ]
    result = deduplicate_latest(entries)
    assert len(result) == 1


def test_deduplicate_latest_picks_newer_timestamp():
    older = {**_BASE_SUMMARY, "spl_mean": 0.1, "_source": "comparison_20260516_120000.json"}
    newer = {**_BASE_SUMMARY, "spl_mean": 0.9, "_source": "comparison_20260517_120000.json"}
    result = deduplicate_latest([older, newer])
    assert result[0]["spl_mean"] == 0.9


def test_deduplicate_latest_separate_keys_both_kept():
    entries = [
        {**_BASE_SUMMARY, "model": "gnm", "_source": "comparison_20260517_120000.json"},
        {**_BASE_SUMMARY, "model": "vint", "_source": "comparison_20260517_120000.json"},
    ]
    result = deduplicate_latest(entries)
    assert len(result) == 2


def test_deduplicate_latest_fs_and_no_fs_both_kept():
    entries = [
        {**_BASE_SUMMARY, "fleetsafe": False, "_source": "comparison_20260517_120000.json"},
        {**_FS_SUMMARY,   "fleetsafe": True,  "_source": "comparison_20260517_120000.json"},
    ]
    result = deduplicate_latest(entries)
    assert len(result) == 2


# ── filter_summaries ──────────────────────────────────────────────────────────

def test_filter_by_model():
    entries = [_BASE_SUMMARY, {**_BASE_SUMMARY, "model": "vint"}]
    result = filter_summaries(entries, model="gnm", scene=None, backend=None, latest=False)
    assert all(s["model"] == "gnm" for s in result)


def test_filter_by_backend():
    entries = [_BASE_SUMMARY, {**_BASE_SUMMARY, "backend": "mujoco"}]
    result = filter_summaries(entries, model=None, scene=None, backend="mujoco", latest=False)
    assert all(s["backend"] == "mujoco" for s in result)


def test_filter_latest_true_deduplicates():
    entries = [
        {**_BASE_SUMMARY, "_source": "comparison_20260516_120000.json"},
        {**_BASE_SUMMARY, "_source": "comparison_20260517_120000.json"},
    ]
    result = filter_summaries(entries, model=None, scene=None, backend=None, latest=True)
    assert len(result) == 1


def test_filter_latest_false_keeps_all():
    entries = [
        {**_BASE_SUMMARY, "_source": "comparison_20260516_120000.json"},
        {**_BASE_SUMMARY, "_source": "comparison_20260517_120000.json"},
    ]
    result = filter_summaries(entries, model=None, scene=None, backend=None, latest=False)
    assert len(result) == 2


# ── _fmt ─────────────────────────────────────────────────────────────────────

def test_fmt_none():
    assert "—" in _fmt(None)


def test_fmt_bool_true():
    assert "✓" in _fmt(True)


def test_fmt_bool_false():
    assert "—" in _fmt(False)


def test_fmt_float_inf():
    assert "∞" in _fmt(float("inf"))


def test_fmt_float_large_treated_as_inf():
    assert "∞" in _fmt(1e300)


def test_fmt_float_normal():
    result = _fmt(0.42345)
    assert "0.423" in result


def test_fmt_float_pct():
    result = _fmt(0.756, pct=True)
    assert "75.6%" in result


def test_fmt_int():
    assert _fmt(42) == "42"


# ── _zone_bar ─────────────────────────────────────────────────────────────────

def test_zone_bar_strips_to_correct_length():
    bar = _zone_bar(60, 20, 20, width=20)
    # Strip ANSI escape codes
    clean = re.sub(r'\033\[[0-9;]*m', '', bar)
    assert len(clean) == 20


def test_zone_bar_all_zero_returns_dimmed():
    bar = _zone_bar(0, 0, 0, width=10)
    clean = re.sub(r'\033\[[0-9;]*m', '', bar)
    assert len(clean) == 10
    assert "░" in clean


# ── render_terminal ───────────────────────────────────────────────────────────

def test_render_terminal_empty(capsys, tmp_path):
    render_terminal([], tmp_path)
    out = capsys.readouterr().out
    assert "No results" in out


def test_render_terminal_populated(capsys, tmp_path):
    render_terminal([_BASE_SUMMARY, _FS_SUMMARY], tmp_path)
    out = capsys.readouterr().out
    assert "gnm" in out
    assert "SPL" in out


def test_render_terminal_shows_zone_section(capsys, tmp_path):
    render_terminal([_BASE_SUMMARY], tmp_path)
    out = capsys.readouterr().out
    assert "Zone" in out


def test_render_terminal_no_social_section_when_no_data(capsys, tmp_path):
    render_terminal([_BASE_SUMMARY], tmp_path)
    out = capsys.readouterr().out
    assert "Social Risk" not in out


def test_render_terminal_shows_social_section_when_data(capsys, tmp_path):
    social_entry = {**_BASE_SUMMARY,
                    "crowding_risk_score_mean": 0.3,
                    "occlusion_risk_score_mean": 0.2,
                    "social_margin_violation_count_mean": 5.0,
                    "min_human_distance_m_mean": 0.45}
    render_terminal([social_entry], tmp_path)
    out = capsys.readouterr().out
    assert "Social" in out


# ── render_html ───────────────────────────────────────────────────────────────

def test_render_html_returns_string():
    html = render_html([_BASE_SUMMARY], Path("/tmp"))
    assert isinstance(html, str)
    assert "<!DOCTYPE html>" in html


def test_render_html_contains_model_name():
    html = render_html([_BASE_SUMMARY], Path("/tmp"))
    assert "gnm" in html


def test_render_html_writes_file(tmp_path):
    out = tmp_path / "test_dashboard.html"
    render_html([_BASE_SUMMARY], Path("/tmp"), out_path=out)
    assert out.exists()
    assert out.stat().st_size > 100


def test_render_html_mock_warning_present():
    html = render_html([_BASE_SUMMARY], Path("/tmp"))
    assert "MOCK" in html


def test_render_html_no_mock_warning_for_real_backend():
    entry = {**_BASE_SUMMARY, "backend": "isaaclab"}
    html = render_html([entry], Path("/tmp"))
    assert "MOCK" not in html


def test_render_html_contains_chart_canvas():
    html = render_html([_BASE_SUMMARY], Path("/tmp"))
    assert "canvas" in html
    assert "drawBar" in html


def test_render_html_refresh_tag_when_watch():
    html = render_html([_BASE_SUMMARY], Path("/tmp"), refresh_s=5)
    assert 'http-equiv="refresh"' in html


def test_render_html_no_refresh_tag_by_default():
    html = render_html([_BASE_SUMMARY], Path("/tmp"), refresh_s=0)
    assert 'http-equiv="refresh"' not in html


# ── _html_table ───────────────────────────────────────────────────────────────

def test_html_table_empty():
    result = _html_table([])
    assert "<table>" in result
    assert "<tbody></tbody>" in result or "<tbody>\n</tbody>" in result or result.count("<tr") == 1


def test_html_table_populated():
    result = _html_table([_BASE_SUMMARY, _FS_SUMMARY])
    assert result.count("<tr") >= 3  # header + 2 data rows


def test_html_table_fleetsafe_badge():
    result = _html_table([_FS_SUMMARY])
    assert "badge-fs" in result


# ── _html_kpi_cards ───────────────────────────────────────────────────────────

def test_kpi_cards_empty():
    result = _html_kpi_cards([])
    assert result == ""


def test_kpi_cards_populated():
    result = _html_kpi_cards([_BASE_SUMMARY])
    assert "metric-card" in result
    assert "SPL" in result or "spl" in result.lower()
    assert "episodes" in result.lower()


# ── _has_social_data ─────────────────────────────────────────────────────────

def test_has_social_data_false_for_zero():
    assert not _has_social_data(_BASE_SUMMARY)


def test_has_social_data_true_for_nonzero():
    entry = {**_BASE_SUMMARY, "crowding_risk_score_mean": 0.1,
             "social_margin_violation_count_mean": 3.0,
             "min_human_distance_m_mean": 0.5}
    assert _has_social_data(entry)


def test_has_social_data_false_for_inf_human_dist():
    entry = {**_BASE_SUMMARY, "crowding_risk_score_mean": 0.1,
             "min_human_distance_m_mean": float("inf")}
    assert not _has_social_data(entry)
