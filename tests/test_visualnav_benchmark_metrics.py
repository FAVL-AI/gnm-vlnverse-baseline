"""
tests/test_visualnav_benchmark_metrics.py — Unit tests for visualnav_metrics.py.

Tests are pure Python: no simulator, no ML, no filesystem I/O (where avoidable).
All metric functions accept numbers/arrays and return numbers/dicts.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import pytest

from fleet_safe_vla.benchmarks.visualnav_metrics import (
    EpisodeMetrics,
    aggregate_by_scene,
    aggregate_episodes,
    build_comparison_table,
    compute_delta_l2_mean,
    compute_intervention_rate,
    compute_latency_stats,
    compute_near_violation_count,
    compute_spl,
    compute_stuck_rate,
    episodes_to_csv_rows,
    write_aggregate_json,
    write_episodes_csv,
)


# ── SPL ────────────────────────────────────────────────────────────────────────

class TestSPL:
    def test_success_optimal_path(self):
        """Perfect navigation: success, path == optimal."""
        spl = compute_spl(success=True, path_length_m=4.0, optimal_path_m=4.0)
        assert spl == pytest.approx(1.0)

    def test_success_longer_path(self):
        """Success with detour: SPL < 1."""
        spl = compute_spl(success=True, path_length_m=6.0, optimal_path_m=4.0)
        assert spl == pytest.approx(4.0 / 6.0)

    def test_success_shorter_path_impossible(self):
        """Path < optimal is impossible but formula clamps: max(p, L*)."""
        spl = compute_spl(success=True, path_length_m=2.0, optimal_path_m=4.0)
        # max(2, 4) = 4 → 4/4 = 1.0
        assert spl == pytest.approx(1.0)

    def test_failure_returns_zero(self):
        """Failure always returns SPL = 0."""
        spl = compute_spl(success=False, path_length_m=3.0, optimal_path_m=4.0)
        assert spl == 0.0

    def test_zero_optimal_path(self):
        """Optimal path == 0 avoids division by zero."""
        spl = compute_spl(success=True, path_length_m=0.0, optimal_path_m=0.0)
        assert spl == 0.0

    def test_mean_spl_formula(self):
        """mean SPL across 3 episodes matches manual calculation."""
        # ep1: success, path=4, opt=4 → 1.0
        # ep2: failure             → 0.0
        # ep3: success, path=6, opt=4 → 0.667
        spls = [
            compute_spl(True,  4.0, 4.0),
            compute_spl(False, 3.0, 4.0),
            compute_spl(True,  6.0, 4.0),
        ]
        assert np.mean(spls) == pytest.approx((1.0 + 0.0 + 4.0/6.0) / 3, rel=1e-5)


# ── Intervention rate ─────────────────────────────────────────────────────────

class TestInterventionRate:
    def test_no_interventions(self):
        assert compute_intervention_rate(0, 100) == 0.0

    def test_all_steps_intervened(self):
        assert compute_intervention_rate(100, 100) == 1.0

    def test_half_steps(self):
        assert compute_intervention_rate(50, 100) == pytest.approx(0.5)

    def test_zero_steps(self):
        """Zero total steps avoids division by zero."""
        assert compute_intervention_rate(0, 0) == 0.0

    def test_fractional(self):
        assert compute_intervention_rate(3, 10) == pytest.approx(0.3)


# ── Near-violation count ───────────────────────────────────────────────────────

class TestNearViolationCount:
    def test_no_violations(self):
        dists = [1.0, 0.8, 0.6, 0.5]
        assert compute_near_violation_count(dists, threshold_m=0.45) == 0

    def test_all_violations(self):
        dists = [0.1, 0.2, 0.3]
        assert compute_near_violation_count(dists, threshold_m=0.45) == 3

    def test_boundary_exclusive(self):
        """Exactly at threshold is NOT a violation (strict <)."""
        assert compute_near_violation_count([0.45], threshold_m=0.45) == 0

    def test_boundary_below(self):
        assert compute_near_violation_count([0.449], threshold_m=0.45) == 1

    def test_mixed(self):
        dists = [1.0, 0.3, 0.6, 0.2, 0.5]
        # 0.3 and 0.2 are below 0.45
        assert compute_near_violation_count(dists, threshold_m=0.45) == 2

    def test_empty(self):
        assert compute_near_violation_count([], threshold_m=0.45) == 0


# ── Latency stats ─────────────────────────────────────────────────────────────

class TestLatencyStats:
    def test_empty(self):
        mean, p95 = compute_latency_stats([])
        assert mean == 0.0
        assert p95  == 0.0

    def test_single(self):
        mean, p95 = compute_latency_stats([10.0])
        assert mean == pytest.approx(10.0)
        assert p95  == pytest.approx(10.0)

    def test_known_values(self):
        latencies = [10.0, 20.0, 30.0, 40.0, 50.0]
        mean, p95 = compute_latency_stats(latencies)
        assert mean == pytest.approx(30.0)
        # np.percentile([10,20,30,40,50], 95) ≈ 48.0
        assert p95  == pytest.approx(np.percentile(latencies, 95))


# ── Delta L2 mean ─────────────────────────────────────────────────────────────

class TestDeltaL2Mean:
    def test_identical_commands_zero_delta(self):
        raw  = [(0.3, 0.0, 0.5), (0.2, 0.1, 0.3)]
        safe = [(0.3, 0.0, 0.5), (0.2, 0.1, 0.3)]
        assert compute_delta_l2_mean(raw, safe) == pytest.approx(0.0)

    def test_single_step_known(self):
        raw  = [(1.0, 0.0, 0.0)]
        safe = [(0.0, 0.0, 0.0)]
        assert compute_delta_l2_mean(raw, safe) == pytest.approx(1.0)

    def test_mismatched_lengths_zero(self):
        assert compute_delta_l2_mean([(1.0, 0.0, 0.0)], []) == 0.0

    def test_empty(self):
        assert compute_delta_l2_mean([], []) == 0.0


# ── Stuck rate ────────────────────────────────────────────────────────────────

class TestStuckRate:
    def test_no_stuck(self):
        assert compute_stuck_rate(100, 0) == 0.0

    def test_half_stuck(self):
        assert compute_stuck_rate(100, 50) == pytest.approx(0.5)

    def test_zero_steps(self):
        assert compute_stuck_rate(0, 0) == 0.0


# ── EpisodeMetrics / aggregation ──────────────────────────────────────────────

def _make_episode(**kwargs) -> EpisodeMetrics:
    defaults = dict(
        model_name="gnm", fleetsafe=False, backend="mock",
        scene="straight_corridor", seed=0,
        start_xy=(0.0, 0.0), goal_xy=(4.0, 0.0),
        success=True, episode_length_steps=100,
        path_length_m=4.2, optimal_path_m=4.0,
        time_to_goal_s=25.0,
        spl=compute_spl(True, 4.2, 4.0),
        collision_count=0, near_violation_count=1,
        min_obstacle_distance_m=0.5,
        intervention_count=5, intervention_rate=0.05,
        raw_vs_safe_action_delta_l2_mean=0.02,
        stuck_rate=0.01, smoothness=0.03,
        recovery_success=False,
        inference_latency_ms_mean=15.0,
        inference_latency_ms_p95=22.0,
        sim_fps=66.7,
    )
    defaults.update(kwargs)
    return EpisodeMetrics(**defaults)


class TestAggregation:
    def test_empty_returns_empty(self):
        assert aggregate_episodes([]) == {}

    def test_single_episode_success_rate(self):
        ep = _make_episode(success=True)
        agg = aggregate_episodes([ep])
        assert agg["success_rate"] == pytest.approx(1.0)
        assert agg["n_episodes"] == 1

    def test_two_episodes_success_rate(self):
        eps = [
            _make_episode(success=True),
            _make_episode(success=False, spl=0.0, collision_count=1),
        ]
        agg = aggregate_episodes(eps)
        assert agg["success_rate"] == pytest.approx(0.5)
        assert agg["collision_rate"] == pytest.approx(0.5)

    def test_spl_mean(self):
        eps = [
            _make_episode(spl=0.8, success=True),
            _make_episode(spl=0.6, success=True),
        ]
        agg = aggregate_episodes(eps)
        assert agg["spl_mean"] == pytest.approx(0.7)
        assert agg["spl_std"]  == pytest.approx(0.1)

    def test_aggregate_by_scene_keys(self):
        eps = [
            _make_episode(scene="straight_corridor"),
            _make_episode(scene="cluttered_static"),
            _make_episode(scene="straight_corridor", seed=1),
        ]
        by_scene = aggregate_by_scene(eps)
        assert set(by_scene.keys()) == {"straight_corridor", "cluttered_static"}
        assert by_scene["straight_corridor"]["n_episodes"] == 2
        assert by_scene["cluttered_static"]["n_episodes"]  == 1

    def test_intervention_rate_mean(self):
        eps = [
            _make_episode(intervention_rate=0.1),
            _make_episode(intervention_rate=0.3),
        ]
        agg = aggregate_episodes(eps)
        assert agg["intervention_rate_mean"] == pytest.approx(0.2)


# ── CSV / JSON serialisation ───────────────────────────────────────────────────

class TestSerialisation:
    def test_episodes_to_csv_rows_keys(self):
        ep   = _make_episode()
        rows = episodes_to_csv_rows([ep])
        assert len(rows) == 1
        r = rows[0]
        assert "start_x" in r and "start_y" in r
        assert "goal_x"  in r and "goal_y"  in r
        assert "start_xy" not in r
        assert "goal_xy"  not in r
        assert r["start_x"] == pytest.approx(0.0)
        assert r["goal_x"]  == pytest.approx(4.0)

    def test_write_episodes_csv(self, tmp_path):
        eps = [_make_episode(seed=i) for i in range(3)]
        out = tmp_path / "test_episodes.csv"
        write_episodes_csv(eps, out)
        assert out.exists()
        with out.open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 3
        assert "spl" in rows[0]
        assert "intervention_count" in rows[0]

    def test_write_episodes_csv_creates_parent(self, tmp_path):
        eps = [_make_episode()]
        nested = tmp_path / "deep" / "nested" / "episodes.csv"
        write_episodes_csv(eps, nested)
        assert nested.exists()

    def test_write_aggregate_json(self, tmp_path):
        ep  = _make_episode()
        agg = aggregate_episodes([ep])
        out = tmp_path / "agg.json"
        write_aggregate_json(agg, out, extra={"model": "gnm", "backend": "mock"})
        data = json.loads(out.read_text())
        assert data["model"]   == "gnm"
        assert data["backend"] == "mock"
        assert "success_rate" in data
        assert "spl_mean"     in data

    def test_write_aggregate_json_creates_parent(self, tmp_path):
        out = tmp_path / "sub" / "agg.json"
        write_aggregate_json({"n_episodes": 1}, out)
        assert out.exists()


# ── Comparison table ──────────────────────────────────────────────────────────

class TestComparisonTable:
    def test_builds_rows(self):
        summaries = [
            {"model": "gnm",  "fleetsafe": False, "backend": "mock",
             "n_episodes": 10, "success_rate": 0.8, "spl_mean": 0.72,
             "collision_rate": 0.1, "near_violation_count_mean": 2.0,
             "min_obstacle_distance_m_mean": 0.6,
             "intervention_rate_mean": 0.0, "raw_vs_safe_delta_l2_mean": 0.0,
             "inference_latency_ms_mean": 15.0, "sim_fps_mean": 66.7},
            {"model": "gnm",  "fleetsafe": True, "backend": "mock",
             "n_episodes": 10, "success_rate": 0.75, "spl_mean": 0.68,
             "collision_rate": 0.0, "near_violation_count_mean": 0.5,
             "min_obstacle_distance_m_mean": 0.8,
             "intervention_rate_mean": 0.12, "raw_vs_safe_delta_l2_mean": 0.04,
             "inference_latency_ms_mean": 16.0, "sim_fps_mean": 62.5},
        ]
        rows = build_comparison_table(summaries)
        assert len(rows) == 2
        assert rows[0]["Model"]    == "gnm"
        assert rows[0]["FleetSafe"] == "—"
        assert rows[1]["FleetSafe"] == "✓"
        # Collision rates as percentages
        assert "0.0" in rows[1]["Collision %"]

    def test_empty_input(self):
        assert build_comparison_table([]) == []
