"""Unit tests for VLNVerse navigation metrics.

Tests verify correctness of all metric implementations against
analytically-known values, including edge cases.
"""
import sys
import math
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from gnm_vlnverse.evaluation.metrics import (
    Episode,
    NavigationMetrics,
    cls,
    collision_rate,
    compute_all_metrics,
    nav_error,
    ndtw,
    oracle_success,
    path_length,
    spl,
    srn,
    success,
)


class TestPathLength:
    def test_straight_line(self):
        path = [(0.0, 0.0), (3.0, 4.0)]
        assert math.isclose(path_length(path), 5.0, rel_tol=1e-6)

    def test_empty_path(self):
        assert path_length([]) == 0.0

    def test_single_point(self):
        assert path_length([(1.0, 2.0)]) == 0.0

    def test_manhattan_path(self):
        path = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
        assert math.isclose(path_length(path), 2.0, rel_tol=1e-6)


class TestNavError:
    def test_at_goal(self):
        assert nav_error([(5.0, 5.0)], (5.0, 5.0)) == 0.0

    def test_3_4_5_triangle(self):
        assert math.isclose(nav_error([(3.0, 4.0)], (0.0, 0.0)), 5.0, rel_tol=1e-6)

    def test_empty_path(self):
        assert nav_error([], (1.0, 1.0)) == math.inf


class TestSuccess:
    def test_success_at_threshold(self):
        assert success(3.0, threshold=3.0) is True

    def test_success_within_threshold(self):
        assert success(2.9, threshold=3.0) is True

    def test_failure_beyond_threshold(self):
        assert success(3.1, threshold=3.0) is False


class TestOracleSuccess:
    def test_oracle_hit(self):
        path = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)]
        assert oracle_success(path, (5.0, 0.0), threshold=1.0) is True

    def test_oracle_miss(self):
        path = [(0.0, 0.0), (10.0, 0.0)]
        assert oracle_success(path, (5.0, 5.0), threshold=1.0) is False

    def test_oracle_at_end(self):
        path = [(0.0, 0.0), (3.0, 4.0)]
        assert oracle_success(path, (3.0, 4.0), threshold=0.1) is True


class TestSPL:
    def test_perfect_navigation(self):
        path     = [(0.0, 0.0), (3.0, 0.0), (5.0, 0.0)]
        ref_len  = 5.0
        val      = spl(True, path, ref_len)
        assert math.isclose(val, 1.0, rel_tol=1e-5)

    def test_failed_episode(self):
        path = [(0.0, 0.0), (10.0, 0.0)]
        val  = spl(False, path, 5.0)
        assert val == 0.0

    def test_detour_penalty(self):
        # Actual path is twice the shortest path
        path = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (5.0, 0.0)]
        val  = spl(True, path, 5.0)
        actual_len = path_length(path)
        expected   = 5.0 / actual_len
        assert math.isclose(val, expected, rel_tol=1e-5)


class TestCollisionRate:
    def test_no_collisions(self):
        assert collision_rate([False, False, False]) == 0.0

    def test_all_collisions(self):
        assert collision_rate([True, True, True]) == 1.0

    def test_half_collisions(self):
        assert collision_rate([True, False, True, False]) == 0.5

    def test_empty(self):
        assert collision_rate([]) == 0.0


class TestNDTW:
    def test_identical_paths(self):
        path = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        score = ndtw(path, path)
        assert math.isclose(score, 1.0, rel_tol=1e-5)

    def test_empty_paths(self):
        assert ndtw([], [(0.0, 0.0)]) == 0.0
        assert ndtw([(0.0, 0.0)], []) == 0.0

    def test_parallel_paths(self):
        actual = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        ref    = [(0.0, 1.0), (1.0, 1.0), (2.0, 1.0)]
        score  = ndtw(actual, ref)
        # Should be less than 1 but > 0 (parallel but offset by 1m)
        assert 0.0 < score < 1.0

    def test_score_decreases_with_deviation(self):
        ref    = [(0.0, 0.0), (5.0, 0.0)]
        close  = [(0.0, 0.0), (5.0, 0.1)]   # close to reference
        far    = [(0.0, 0.0), (5.0, 5.0)]   # far from reference
        score_close = ndtw(close, ref)
        score_far   = ndtw(far, ref)
        assert score_close > score_far


class TestCLS:
    def test_perfect_coverage(self):
        path = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        ref  = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        score = cls(path, ref, pc=0.5)
        assert math.isclose(score, 1.0, rel_tol=1e-5)

    def test_no_coverage(self):
        path = [(10.0, 10.0), (11.0, 10.0)]
        ref  = [(0.0, 0.0), (1.0, 0.0)]
        score = cls(path, ref, pc=1.0)
        assert score == 0.0

    def test_empty(self):
        assert cls([], [(0.0, 0.0)]) == 0.0


class TestSRn:
    def test_all_goals_reached(self):
        path = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)]
        goals = [(5.0, 0.0), (10.0, 0.0)]
        assert math.isclose(srn(path, goals, threshold=0.5), 1.0)

    def test_no_goals(self):
        path = [(0.0, 0.0)]
        assert srn(path, []) == 0.0

    def test_partial_goals(self):
        path  = [(0.0, 0.0), (5.0, 0.0)]
        goals = [(5.0, 0.0), (20.0, 0.0)]
        val   = srn(path, goals, threshold=0.5)
        assert math.isclose(val, 0.5)


class TestComputeAllMetrics:
    def _make_episode(self, success: bool) -> Episode:
        if success:
            return Episode(
                actual_path    = [(0.0, 0.0), (2.0, 0.0), (5.0, 0.0)],
                reference_path = [(0.0, 0.0), (5.0, 0.0)],
                goal_pos       = (5.0, 0.0),
                collisions     = [False, False],
            )
        else:
            return Episode(
                actual_path    = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)],
                reference_path = [(0.0, 0.0), (10.0, 0.0)],
                goal_pos       = (10.0, 0.0),
                collisions     = [False, False],
            )

    def test_empty_episodes(self):
        m = compute_all_metrics([])
        assert m.SR == 0.0
        assert m.n_episodes == 0

    def test_all_success(self):
        episodes = [self._make_episode(True)] * 10
        m        = compute_all_metrics(episodes)
        assert math.isclose(m.SR, 1.0, rel_tol=1e-5)
        assert m.SPL > 0.0
        assert m.NE < 3.0
        assert m.n_episodes == 10

    def test_all_failure(self):
        episodes = [self._make_episode(False)] * 5
        m        = compute_all_metrics(episodes)
        assert m.SR  == 0.0
        assert m.SPL == 0.0
        assert m.NE  > 3.0

    def test_mixed(self):
        episodes = [self._make_episode(True), self._make_episode(False)]
        m        = compute_all_metrics(episodes)
        assert math.isclose(m.SR, 0.5, rel_tol=1e-5)

    def test_metrics_range(self):
        episodes = [self._make_episode(True), self._make_episode(False)]
        m        = compute_all_metrics(episodes)
        assert 0.0 <= m.SR   <= 1.0
        assert 0.0 <= m.OSR  <= 1.0
        assert 0.0 <= m.SPL  <= 1.0
        assert m.NE  >= 0.0
        assert m.TL  >= 0.0
        assert 0.0 <= m.nDTW <= 1.0
        assert 0.0 <= m.CLS  <= 1.0
        assert 0.0 <= m.CR   <= 1.0

    def test_to_dict_keys(self):
        episodes = [self._make_episode(True)]
        m        = compute_all_metrics(episodes)
        d        = m.to_dict()
        for key in ["SR", "OSR", "SPL", "NE", "TL", "nDTW", "CLS", "CR", "SRn"]:
            assert key in d
