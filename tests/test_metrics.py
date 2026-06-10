"""
Metrics Tests — no GPU required.

Tests robot-lab metric modules and fleet-safe extensions.
"""
from __future__ import annotations

import importlib.util

import numpy as np
import pytest

_has_robot_lab = importlib.util.find_spec("robot_lab") is not None
_skip_robot_lab = pytest.mark.skipif(not _has_robot_lab, reason="robot_lab not installed")


@_skip_robot_lab
class TestEpisodeBuffer:
    """Tests for robot-lab EpisodeBuffer."""

    def _make_buffer(self, T: int = 100, fell: bool = False) -> "EpisodeBuffer":
        from robot_lab.eval.metrics import EpisodeBuffer
        return EpisodeBuffer(
            cmd_vel_xy=np.ones((T, 2), dtype=np.float32) * 0.5,
            base_vel_xy=np.ones((T, 2), dtype=np.float32) * 0.45,
            cmd_yaw_rate=np.zeros(T, dtype=np.float32),
            base_yaw_rate=np.zeros(T, dtype=np.float32),
            joint_torques=np.ones((T, 18), dtype=np.float32) * 10.0,
            joint_vel=np.ones((T, 18), dtype=np.float32) * 0.5,
            foot_contacts=np.tile([[1, 0], [0, 1]], (T // 2 + 1, 1))[:T].astype(np.float32),
            base_height=np.ones(T, dtype=np.float32) * 0.9,
            dt=0.02,
            fell=fell,
        )

    def test_import(self):
        from robot_lab.eval.metrics import EpisodeBuffer
        assert EpisodeBuffer is not None

    def test_duration(self):
        buf = self._make_buffer(T=50)
        assert abs(buf.duration_s - 1.0) < 0.01

    def test_T_property(self):
        buf = self._make_buffer(T=200)
        assert buf.T == 200


@_skip_robot_lab
class TestMetricFunctions:
    """Tests for robot-lab metric computation functions."""

    def _make_buffer(self, T: int = 100, fell: bool = False):
        from robot_lab.eval.metrics import EpisodeBuffer
        return EpisodeBuffer(
            cmd_vel_xy=np.ones((T, 2), dtype=np.float32) * 0.5,
            base_vel_xy=np.ones((T, 2), dtype=np.float32) * 0.4,
            cmd_yaw_rate=np.zeros(T, dtype=np.float32),
            base_yaw_rate=np.zeros(T, dtype=np.float32),
            joint_torques=np.ones((T, 18), dtype=np.float32) * 15.0,
            joint_vel=np.ones((T, 18), dtype=np.float32) * 0.3,
            foot_contacts=np.tile([[1, 0], [0, 1]], (T // 2 + 1, 1))[:T].astype(np.float32),
            base_height=np.ones(T, dtype=np.float32) * 0.95,
            dt=0.02,
            fell=fell,
        )

    def test_velocity_tracking_error(self):
        from robot_lab.eval.metrics import velocity_tracking_error, EpisodeBuffer
        buf = self._make_buffer()
        result = velocity_tracking_error(buf)
        assert "vel_track_rms_xy" in result
        assert result["vel_track_rms_xy"] > 0  # some error expected

    def test_survival_metrics(self):
        from robot_lab.eval.metrics import survival_metrics
        buf = self._make_buffer(T=100, fell=False)
        result = survival_metrics(buf)
        assert "episode_duration_s" in result
        assert abs(result["episode_duration_s"] - 2.0) < 0.1
        assert result["fell"] == 0.0

    def test_survival_metrics_fell(self):
        from robot_lab.eval.metrics import survival_metrics
        buf = self._make_buffer(fell=True)
        result = survival_metrics(buf)
        assert result["fell"] == 1.0

    def test_energy_efficiency(self):
        from robot_lab.eval.metrics import energy_efficiency
        buf = self._make_buffer()
        result = energy_efficiency(buf)
        assert "energy_J" in result
        assert "cost_of_transport" in result
        assert result["energy_J"] > 0

    def test_gait_metrics(self):
        from robot_lab.eval.metrics import gait_metrics
        buf = self._make_buffer()
        result = gait_metrics(buf)
        assert "step_freq_hz" in result
        assert "duty_cycle" in result
        assert "gait_symmetry" in result
        assert 0.0 <= result["gait_symmetry"] <= 1.0

    def test_compute_all_metrics(self):
        from robot_lab.eval.metrics import compute_all_metrics
        buf = self._make_buffer()
        result = compute_all_metrics(buf)
        # Must contain metrics from all groups
        assert "vel_track_rms_xy" in result
        assert "episode_duration_s" in result
        assert "energy_J" in result
        assert "step_freq_hz" in result


@_skip_robot_lab
class TestAggregateMetrics:
    """Tests for robot-lab AggregateMetrics aggregation."""

    def test_import(self):
        from robot_lab.eval.metrics import AggregateMetrics
        assert AggregateMetrics is not None

    def test_update_and_summarize(self):
        from robot_lab.eval.metrics import AggregateMetrics
        agg = AggregateMetrics()
        for i in range(5):
            agg.update({"success": float(i % 2 == 0), "reward": float(i)})
        summary = agg.summarize()
        assert "success/mean" in summary
        assert "reward/mean" in summary
        assert abs(summary["reward/mean"] - 2.0) < 0.01  # mean of [0,1,2,3,4]

    def test_empty_summarize(self):
        from robot_lab.eval.metrics import AggregateMetrics
        agg = AggregateMetrics()
        result = agg.summarize()
        assert result == {}

    def test_n_episodes(self):
        from robot_lab.eval.metrics import AggregateMetrics
        agg = AggregateMetrics()
        for _ in range(7):
            agg.update({"x": 1.0})
        assert agg.summarize()["n_episodes"] == 7


@_skip_robot_lab
class TestFleetMetrics:
    """Tests for fleet_safe metric extensions."""

    def test_fleet_aggregate_import(self):
        from fleet_safe_vla.eval.metrics.metrics import FleetAggregateMetrics
        assert FleetAggregateMetrics is not None

    def test_fleet_aggregate_per_robot(self):
        from fleet_safe_vla.eval.metrics.metrics import FleetAggregateMetrics
        agg = FleetAggregateMetrics()
        for rid in range(3):
            for ep in range(5):
                agg.update_robot(rid, {"success": 1.0, "fall_rate": 0.0})
        per_robot = agg.per_robot_summary()
        assert len(per_robot) == 3
        for rid in range(3):
            assert "success/mean" in per_robot[rid]

    def test_fleet_safety_metrics(self):
        from fleet_safe_vla.eval.metrics.metrics import fleet_safety_metrics
        result = fleet_safety_metrics(
            cbf_intervention_rate=0.05,
            safety_state_history=["NOMINAL"] * 90 + ["EMERGENCY"] * 10,
            fall_count=2,
            recovery_count=1,
            episode_count=10,
        )
        assert "cbf_intervention_rate" in result
        assert abs(result["cbf_intervention_rate"] - 0.05) < 1e-6
        assert abs(result["fall_rate"] - 0.2) < 1e-6

    def test_reexport_symbols(self):
        """Fleet metrics module re-exports robot-lab symbols."""
        from fleet_safe_vla.eval.metrics.metrics import (
            EpisodeBuffer, AggregateMetrics, compute_all_metrics
        )
        assert EpisodeBuffer is not None
        assert AggregateMetrics is not None
        assert compute_all_metrics is not None


@_skip_robot_lab
class TestBenchmarkScenarios:
    """Tests for fleet_safe_benchmark_v0 scenario definitions."""

    def test_scenario_count(self):
        from fleet_safe_vla.eval.benchmark_suite.fleet_benchmark import SCENARIOS
        assert len(SCENARIOS) == 11, f"Expected 11 scenarios, got {len(SCENARIOS)}"

    def test_scenario_names(self):
        from fleet_safe_vla.eval.benchmark_suite.fleet_benchmark import SCENARIOS
        names = {s.name for s in SCENARIOS}
        required = {
            "flat", "rough", "stairs", "slopes", "low_friction",
            "actuator_weakness", "payload_shift", "sensor_noise",
            "latency", "push", "obstacle"
        }
        assert names == required, f"Missing scenarios: {required - names}"

    def test_metric_names(self):
        from fleet_safe_vla.eval.benchmark_suite.fleet_benchmark import METRIC_NAMES
        assert len(METRIC_NAMES) >= 6, f"Expected ≥6 metrics, got {len(METRIC_NAMES)}"
        required = {"success_rate", "safety_cost", "fall_rate", "intervention_count",
                    "tracking_error", "energy_per_meter"}
        assert required.issubset(set(METRIC_NAMES)), f"Missing: {required - set(METRIC_NAMES)}"

    def test_benchmark_instantiation(self):
        """FleetBenchmark can be instantiated with zero policy."""
        from fleet_safe_vla.eval.benchmark_suite.fleet_benchmark import FleetBenchmark
        bench = FleetBenchmark(policy=None, n_episodes=1)
        assert bench is not None

    def test_benchmark_run_single_scenario(self):
        """Run one scenario with zero policy and 1 episode."""
        from fleet_safe_vla.eval.benchmark_suite.fleet_benchmark import (
            FleetBenchmark, SCENARIOS
        )
        flat_scenario = next(s for s in SCENARIOS if s.name == "flat")
        bench = FleetBenchmark(policy=None, n_episodes=1, seed=0)
        report = bench.run(scenarios=[flat_scenario], verbose=False)

        assert "benchmark" in report
        assert report["benchmark"] == "fleet_safe_benchmark_v0"
        assert "flat" in report["scenarios"]
        assert report["summary"]["n_scenarios"] == 1
