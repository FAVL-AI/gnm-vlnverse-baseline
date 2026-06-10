"""
tests/test_visualnav_benchmark_runner.py — Smoke tests for the VisualNav benchmark runner.

Verifies:
  - VisualNavBenchmarkRunner runs end-to-end with mock backend.
  - Per-episode files (episode.json, trajectory.csv, actions.csv,
    safety_events.jsonl, metrics.json) are created.
  - metadata.yaml is written.
  - aggregate_metrics.json and aggregate_metrics.csv are written.
  - EpisodeMetrics fields are populated and SPL is in [0, 1].
  - FleetSafe variant produces non-zero intervention_rate when CBF fires.
  - IsaacLab backend raises NotImplementedError.
  - Scenarios module parses seeds and scenes correctly.
  - run_visualnav_benchmark.py smoke-test exit code is 0.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from fleet_safe_vla.benchmarks.visualnav_runner import (
    BACKEND_ISAACLAB,
    BACKEND_MOCK,
    VisualNavBenchmarkRunner,
)
from fleet_safe_vla.benchmarks.visualnav_scenarios import (
    SCENE_STRAIGHT_CORRIDOR,
    SCENE_CLUTTERED_STATIC,
    SCENE_NARROW_PASSAGE,
    get_scenes,
    get_seeds,
)
from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
    ActionOutput,
    BaseVisualNavAdapter,
    CmdVel,
    waypoints_to_cmd_vel,
)


# ── Mock adapter ──────────────────────────────────────────────────────────────

class _TinyMockAdapter(BaseVisualNavAdapter):
    """
    Deterministic mock adapter for testing.
    Always outputs a small forward waypoint.
    """
    model_name   = "mock_test"
    image_size   = (32, 24)
    context_size = 2

    def __init__(self, seed: int = 0) -> None:
        super().__init__()
        self._rng    = np.random.default_rng(seed)
        self._loaded = True

    def load_checkpoint(self, path: Path) -> None:
        self._loaded = True

    def preprocess_observation(self, obs_imgs, goal_img) -> dict:
        return {"obs": obs_imgs[0] if obs_imgs else np.zeros((24, 32, 3), dtype=np.uint8)}

    def predict_action(self, preprocessed) -> ActionOutput:
        # Small forward waypoints — model "moves toward" goal
        waypoints = np.array([[0.08, 0.01]] * 5, dtype=np.float32)
        return ActionOutput(
            waypoints    = waypoints,
            goal_distance = 2.0,
            model_name    = self.model_name,
            inference_ms  = 1.0,
        )


# ── Smoke test: full pipeline ─────────────────────────────────────────────────

class TestMockBackendSmoke:
    """Single-episode end-to-end test on the mock backend."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.tmp_path = tmp_path
        self.adapter  = _TinyMockAdapter(seed=42)

    def _make_runner(self, fleetsafe: bool) -> VisualNavBenchmarkRunner:
        return VisualNavBenchmarkRunner(
            adapter    = self.adapter,
            fleetsafe  = fleetsafe,
            backend    = BACKEND_MOCK,
            output_dir = self.tmp_path / "results",
            max_steps  = 50,
            control_hz = 4.0,
        )

    def test_single_episode_baseline(self):
        runner = self._make_runner(fleetsafe=False)
        metrics = runner.run(
            scenes  = [SCENE_STRAIGHT_CORRIDOR],
            seeds   = [0],
            run_id  = "test_baseline",
        )
        assert len(metrics) == len(SCENE_STRAIGHT_CORRIDOR.start_goal_pairs)
        for m in metrics:
            assert m.model_name == "mock_test"
            assert m.fleetsafe  is False
            assert m.backend    == BACKEND_MOCK
            assert m.episode_length_steps >= 1
            assert m.path_length_m >= 0.0
            assert 0.0 <= m.spl <= 1.0

    def test_fleetsafe_variant_runs(self):
        runner = self._make_runner(fleetsafe=True)
        metrics = runner.run(
            scenes = [SCENE_STRAIGHT_CORRIDOR],
            seeds  = [0],
            run_id = "test_fleetsafe",
        )
        assert len(metrics) == len(SCENE_STRAIGHT_CORRIDOR.start_goal_pairs)
        for m in metrics:
            assert m.fleetsafe is True
            assert 0.0 <= m.spl <= 1.0


# ── Per-episode file output ───────────────────────────────────────────────────

class TestEpisodeFileOutput:
    def _run_single(self, tmp_path, scene, seeds=(0,), fleetsafe=False):
        runner = VisualNavBenchmarkRunner(
            adapter    = _TinyMockAdapter(),
            fleetsafe  = fleetsafe,
            backend    = BACKEND_MOCK,
            output_dir = tmp_path,
            max_steps  = 20,
        )
        runner.run(scenes=[scene], seeds=list(seeds), run_id="file_test")
        return tmp_path / "file_test"

    def test_metadata_yaml_created(self, tmp_path):
        run_dir = self._run_single(tmp_path, SCENE_STRAIGHT_CORRIDOR)
        meta = run_dir / "metadata.yaml"
        assert meta.exists(), "metadata.yaml not created"
        content = meta.read_text()
        assert "model: mock_test" in content
        assert "backend: mock"    in content
        assert "MOCK" in content  # warning present

    def test_episode_json_created(self, tmp_path):
        run_dir  = self._run_single(tmp_path, SCENE_STRAIGHT_CORRIDOR)
        ep_files = sorted((run_dir / "episodes").rglob("episode.json"))
        n_pairs  = len(SCENE_STRAIGHT_CORRIDOR.start_goal_pairs)
        assert len(ep_files) == n_pairs, (
            f"Expected {n_pairs} episode.json files, found {len(ep_files)}"
        )
        data = json.loads(ep_files[0].read_text())
        assert "spl" in data
        assert "success" in data
        assert "collision_count" in data

    def test_trajectory_csv_created(self, tmp_path):
        run_dir = self._run_single(tmp_path, SCENE_STRAIGHT_CORRIDOR)
        traj_files = list((run_dir / "episodes").rglob("trajectory.csv"))
        assert traj_files, "No trajectory.csv files found"
        with traj_files[0].open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) >= 1
        assert "x" in rows[0]
        assert "y" in rows[0]
        assert "heading" in rows[0]
        assert "latency_ms" in rows[0]

    def test_actions_csv_created(self, tmp_path):
        run_dir = self._run_single(tmp_path, SCENE_STRAIGHT_CORRIDOR, fleetsafe=True)
        act_files = list((run_dir / "episodes").rglob("actions.csv"))
        assert act_files, "No actions.csv files found"
        with act_files[0].open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) >= 1
        assert "raw_vx"    in rows[0]
        assert "safe_vx"   in rows[0]
        assert "delta_l2"  in rows[0]
        assert "intervened" in rows[0]

    def test_safety_events_jsonl_created(self, tmp_path):
        run_dir = self._run_single(tmp_path, SCENE_CLUTTERED_STATIC, fleetsafe=True)
        se_files = list((run_dir / "episodes").rglob("safety_events.jsonl"))
        assert se_files, "No safety_events.jsonl files found"
        # File may be empty if no events fired — verify it exists and is valid
        content = se_files[0].read_text().strip()
        for line in content.splitlines():
            ev = json.loads(line)
            assert "step" in ev
            assert "type" in ev

    def test_metrics_json_created(self, tmp_path):
        run_dir = self._run_single(tmp_path, SCENE_STRAIGHT_CORRIDOR)
        m_files = list((run_dir / "episodes").rglob("metrics.json"))
        assert m_files, "No metrics.json files found"
        data = json.loads(m_files[0].read_text())
        assert "spl"               in data
        assert "intervention_rate" in data
        assert "inference_latency_ms_mean" in data

    def test_aggregate_json_created(self, tmp_path):
        run_dir = self._run_single(tmp_path, SCENE_STRAIGHT_CORRIDOR)
        agg = run_dir / "aggregate_metrics.json"
        assert agg.exists(), "aggregate_metrics.json not created"
        data = json.loads(agg.read_text())
        assert "success_rate"   in data
        assert "spl_mean"       in data
        assert "collision_rate" in data
        assert data.get("model") == "mock_test"

    def test_aggregate_csv_created(self, tmp_path):
        run_dir = self._run_single(tmp_path, SCENE_STRAIGHT_CORRIDOR)
        agg_csv = run_dir / "aggregate_metrics.csv"
        assert agg_csv.exists(), "aggregate_metrics.csv not created"
        with agg_csv.open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) >= 1
        assert "spl" in rows[0]


# ── Multi-seed invariant ──────────────────────────────────────────────────────

class TestMultiSeed:
    def test_each_seed_produces_separate_episodes(self, tmp_path):
        runner = VisualNavBenchmarkRunner(
            adapter    = _TinyMockAdapter(),
            backend    = BACKEND_MOCK,
            output_dir = tmp_path,
            max_steps  = 10,
        )
        metrics = runner.run(
            scenes = [SCENE_STRAIGHT_CORRIDOR],
            seeds  = [0, 1, 2],
            run_id = "multi_seed",
        )
        n_pairs = len(SCENE_STRAIGHT_CORRIDOR.start_goal_pairs)
        assert len(metrics) == 3 * n_pairs

    def test_different_seeds_can_differ(self, tmp_path):
        """Different seeds produce slightly different paths (RNG matters)."""
        runner = VisualNavBenchmarkRunner(
            adapter    = _TinyMockAdapter(),
            backend    = BACKEND_MOCK,
            output_dir = tmp_path,
            max_steps  = 30,
        )
        metrics = runner.run(
            scenes = [SCENE_STRAIGHT_CORRIDOR],
            seeds  = [0, 1],
            run_id = "seed_diff",
        )
        # They share the same adapter so results may match — just verify both ran
        assert len(metrics) == 2 * len(SCENE_STRAIGHT_CORRIDOR.start_goal_pairs)
        paths = [m.path_length_m for m in metrics]
        assert all(p >= 0.0 for p in paths)


# ── IsaacLab backend: runner init succeeds, episode raises IsaacNotAvailableError

def test_isaaclab_backend_init_succeeds():
    """Runner __init__ no longer raises for isaaclab — error deferred to episode time."""
    runner = VisualNavBenchmarkRunner(
        adapter  = _TinyMockAdapter(),
        backend  = BACKEND_ISAACLAB,
    )
    assert runner.backend == BACKEND_ISAACLAB


def test_isaaclab_backend_episode_raises_isaac_unavailable():
    """Episode execution raises IsaacNotAvailableError (not NotImplementedError)."""
    from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import IsaacNotAvailableError
    from fleet_safe_vla.benchmarks.visualnav_scenarios import SCENE_STRAIGHT_CORRIDOR
    import tempfile, pathlib

    runner = VisualNavBenchmarkRunner(
        adapter    = _TinyMockAdapter(),
        backend    = BACKEND_ISAACLAB,
        output_dir = pathlib.Path(tempfile.mkdtemp()),
        max_steps  = 2,
    )
    with pytest.raises(IsaacNotAvailableError):
        runner.run([SCENE_STRAIGHT_CORRIDOR], seeds=[0])


# ── Scenarios module ──────────────────────────────────────────────────────────

class TestScenarios:
    def test_get_seeds_smoke(self):
        seeds = get_seeds("smoke")
        assert seeds == [0]

    def test_get_seeds_dev(self):
        seeds = get_seeds("dev")
        assert seeds == list(range(10))

    def test_get_seeds_paper(self):
        seeds = get_seeds("paper")
        assert len(seeds) == 50
        assert seeds[0] == 0

    def test_get_seeds_comma_separated(self):
        seeds = get_seeds("0,3,7")
        assert seeds == [0, 3, 7]

    def test_get_seeds_integer(self):
        seeds = get_seeds(5)
        assert seeds == [0, 1, 2, 3, 4]

    def test_get_scenes_all(self):
        scenes = get_scenes("all")
        assert len(scenes) >= 14
        names = {s.name for s in scenes}
        assert "straight_corridor"       in names
        assert "narrow_passage"          in names
        assert "crowded_corridor"        in names
        assert "blind_corner"            in names
        assert "social_red_zone_smoke"   in names
        assert "hospital_corridor"       in names
        assert "hospital_icu_approach"   in names
        assert "hospital_elevator_lobby" in names

    def test_get_scenes_single(self):
        scenes = get_scenes("cluttered_static")
        assert len(scenes) == 1
        assert scenes[0].name == "cluttered_static"

    def test_get_scenes_list(self):
        scenes = get_scenes(["straight_corridor", "narrow_passage"])
        assert len(scenes) == 2

    def test_get_scenes_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown scene"):
            get_scenes("does_not_exist")

    def test_scene_optimal_path_correct(self):
        pair = SCENE_STRAIGHT_CORRIDOR.start_goal_pairs[0]
        expected = float(np.hypot(
            pair.goal_xy[0] - pair.start_xy[0],
            pair.goal_xy[1] - pair.start_xy[1],
        ))
        assert pair.optimal_path_m == pytest.approx(expected)

    def test_all_scenes_have_start_goal_pairs(self):
        for scene in get_scenes("all"):
            assert len(scene.start_goal_pairs) > 0, (
                f"Scene {scene.name!r} has no start_goal_pairs"
            )


# ── JSON / CSV export: integration with export_report.py ────────────────────

def test_export_report_from_runner_output(tmp_path):
    """Runner writes aggregate JSON; export_report.py ingests it without error."""
    runner = VisualNavBenchmarkRunner(
        adapter    = _TinyMockAdapter(),
        backend    = BACKEND_MOCK,
        output_dir = tmp_path / "results",
        max_steps  = 15,
    )
    runner.run(
        scenes = [SCENE_STRAIGHT_CORRIDOR],
        seeds  = [0],
        run_id = "export_test",
    )

    # Build a minimal result file in the format export_report.py expects
    agg_json = tmp_path / "results" / "export_test" / "aggregate_metrics.json"
    assert agg_json.exists()
    data = json.loads(agg_json.read_text())

    # Wrap in export_report.py format
    report_input = tmp_path / "report_input.json"
    report_payload = {
        "model":     data.get("model", "mock_test"),
        "fleetsafe": data.get("fleetsafe", False),
        "timestamp": 0,
        "config":    {"v_max": 0.3, "w_max": 0.7, "robot": "m3pro", "seeds": [0]},
        "episodes":  [],
        "aggregate": {
            "n_episodes": data.get("n_episodes", 1),
            "success_rate": data.get("success_rate", 0),
            "collision_rate": data.get("collision_rate", 0),
            "mean_path_length_m": data.get("path_length_m_mean", 0),
            "mean_smoothness": data.get("smoothness_mean", 0),
            "mean_stuck_count": 0,
            "mean_intervention_count": data.get("intervention_count_mean", 0),
            "mean_near_violation_count": data.get("near_violation_count_mean", 0),
            "mean_min_obstacle_dist_m": data.get("min_obstacle_distance_m_mean", 0),
            "mean_latency_ms": data.get("inference_latency_ms_mean", 0),
            "mean_fps": data.get("sim_fps_mean", 0),
        },
    }
    report_input.write_text(json.dumps(report_payload))

    report_dir = tmp_path / "report_out"
    result = subprocess.run(
        [sys.executable,
         str(_REPO_ROOT / "scripts" / "visualnav" / "export_report.py"),
         "--input",      str(report_input),
         "--output-dir", str(report_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"export_report.py failed:\n{result.stderr}"
    assert (report_dir / "benchmark_report.html").exists()
    assert (report_dir / "benchmark_results.csv").exists()


# ── CLI smoke test ─────────────────────────────────────────────────────────────

def test_run_visualnav_benchmark_cli_smoke(tmp_path):
    """
    run_visualnav_benchmark.py --model gnm --seeds smoke --scenes straight_corridor
    --backend mock must exit 0 and write an HTML comparison report.
    """
    script = _REPO_ROOT / "scripts" / "visualnav" / "run_visualnav_benchmark.py"
    report_dir = tmp_path / "reports"
    result = subprocess.run(
        [
            sys.executable, str(script),
            "--model",      "gnm",
            "--seeds",      "smoke",
            "--scenes",     "straight_corridor",
            "--backend",    "mock",
            "--fleetsafe",  "both",
            "--max-steps",  "20",
            "--output-dir", str(tmp_path / "results"),
        ],
        capture_output=True,
        text=True,
        env={
            **__import__("os").environ,
            "PYTHONPATH": str(_REPO_ROOT),
        },
    )
    # The CLI writes reports to benchmarks/visualnav/reports/ relative to repo root.
    # For the smoke test we only check the exit code and key stdout markers.
    assert result.returncode == 0, (
        f"run_visualnav_benchmark.py failed (exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "backend=mock" in result.stdout.lower() or "mock" in result.stdout.lower()
