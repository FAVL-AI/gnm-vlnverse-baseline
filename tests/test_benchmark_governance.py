"""
tests/test_benchmark_governance.py

Tests for benchmark governance, versioning, and artifact validation.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── 1. Version constants ───────────────────────────────────────────────────────

class TestVersionConstants:
    def test_benchmark_version_exists(self):
        from fleet_safe_vla.benchmark_version import BENCHMARK_VERSION
        assert isinstance(BENCHMARK_VERSION, str)
        assert BENCHMARK_VERSION.count(".") == 2

    def test_protocol_version_exists(self):
        from fleet_safe_vla.benchmark_version import PROTOCOL_VERSION
        assert isinstance(PROTOCOL_VERSION, str)
        assert PROTOCOL_VERSION.count(".") == 2

    def test_sceneset_version_exists(self):
        from fleet_safe_vla.benchmark_version import SCENESET_VERSION
        assert isinstance(SCENESET_VERSION, str)

    def test_metricset_version_exists(self):
        from fleet_safe_vla.benchmark_version import METRICSET_VERSION
        assert isinstance(METRICSET_VERSION, str)

    def test_explainability_version_exists(self):
        from fleet_safe_vla.benchmark_version import EXPLAINABILITY_VERSION
        assert isinstance(EXPLAINABILITY_VERSION, str)

    def test_governance_version_exists(self):
        from fleet_safe_vla.benchmark_version import GOVERNANCE_VERSION
        assert isinstance(GOVERNANCE_VERSION, str)

    def test_version_block_returns_all_six(self):
        from fleet_safe_vla.benchmark_version import version_block
        block = version_block()
        assert "benchmark_version" in block
        assert "protocol_version" in block
        assert "sceneset_version" in block
        assert "metricset_version" in block
        assert "explainability_version" in block
        assert "governance_version" in block
        assert len(block) == 6

    def test_git_commit_is_string(self):
        from fleet_safe_vla.benchmark_version import GIT_COMMIT
        assert isinstance(GIT_COMMIT, str)
        # Must be non-empty (either a hash or "unknown")
        assert len(GIT_COMMIT) > 0


# ── 2. Protocol YAML ──────────────────────────────────────────────────────────

class TestProtocolYAML:
    PROTOCOL_PATH = Path("benchmarks/protocols/visualnav_v0.1.yaml")

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def test_protocol_file_exists(self):
        p = self._repo_root() / self.PROTOCOL_PATH
        assert p.exists(), f"Protocol file missing: {p}"

    def test_protocol_file_parses(self):
        p = self._repo_root() / self.PROTOCOL_PATH
        try:
            import yaml
            data = yaml.safe_load(p.read_text())
        except ImportError:
            # Fallback: just check it is non-empty text
            data = p.read_text()
        assert data

    def test_protocol_contains_required_keys(self):
        p = self._repo_root() / self.PROTOCOL_PATH
        text = p.read_text()
        for key in ("protocol_version", "models", "backends", "scenes", "episode"):
            assert key in text, f"Protocol missing key: {key}"

    def test_protocol_lists_mock_backend_excluded(self):
        p = self._repo_root() / self.PROTOCOL_PATH
        text = p.read_text()
        assert "publication_allowed: false" in text
        assert "mock" in text

    def test_protocol_lists_four_scenes(self):
        p = self._repo_root() / self.PROTOCOL_PATH
        text = p.read_text()
        for scene in ("straight_corridor", "cluttered_static", "narrow_passage", "dynamic_obstacle"):
            assert scene in text, f"Protocol missing scene: {scene}"

    def test_protocol_has_seed_modes(self):
        p = self._repo_root() / self.PROTOCOL_PATH
        text = p.read_text()
        assert "smoke" in text
        assert "dev" in text
        assert "paper" in text
        assert "n_seeds: 50" in text


# ── 3. Scene manifest ─────────────────────────────────────────────────────────

class TestSceneManifest:
    MANIFEST_PATH = Path("benchmarks/scenes/canonical/SCENESET_v0.1.yaml")

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def test_manifest_file_exists(self):
        p = self._repo_root() / self.MANIFEST_PATH
        assert p.exists(), f"Scene manifest missing: {p}"

    def test_manifest_file_parses(self):
        p = self._repo_root() / self.MANIFEST_PATH
        text = p.read_text()
        assert len(text) > 100

    def test_manifest_has_four_scenes(self):
        p = self._repo_root() / self.MANIFEST_PATH
        text = p.read_text()
        for scene in ("straight_corridor", "cluttered_static", "narrow_passage", "dynamic_obstacle"):
            assert scene in text, f"Manifest missing scene: {scene}"

    def test_manifest_scenes_frozen(self):
        p = self._repo_root() / self.MANIFEST_PATH
        text = p.read_text()
        assert "frozen: true" in text

    def test_manifest_has_hash_fields(self):
        p = self._repo_root() / self.MANIFEST_PATH
        text = p.read_text()
        assert "hash:" in text


# ── 4. Metric spec docs ───────────────────────────────────────────────────────

class TestMetricSpecDocs:
    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def test_metric_specification_exists(self):
        p = self._repo_root() / "docs/metrics/METRIC_SPECIFICATION.md"
        assert p.exists()

    def test_safety_metrics_exists(self):
        p = self._repo_root() / "docs/metrics/SAFETY_METRICS.md"
        assert p.exists()

    def test_explainability_metrics_exists(self):
        p = self._repo_root() / "docs/metrics/EXPLAINABILITY_METRICS.md"
        assert p.exists()

    def test_statistical_tests_exists(self):
        p = self._repo_root() / "docs/metrics/STATISTICAL_TESTS.md"
        assert p.exists()

    def test_metric_spec_contains_spl_formula(self):
        p = self._repo_root() / "docs/metrics/METRIC_SPECIFICATION.md"
        assert "SPL" in p.read_text()

    def test_safety_metrics_contains_collision_rate(self):
        p = self._repo_root() / "docs/metrics/SAFETY_METRICS.md"
        assert "collision_rate" in p.read_text()


# ── 5 & 6 & 7. Artifact validator ────────────────────────────────────────────

def _write_minimal_valid_run(run_dir: Path, backend: str = "mock") -> None:
    """Create a minimal valid benchmark run directory."""
    run_dir.mkdir(parents=True, exist_ok=True)
    ep_dir = run_dir / "episodes" / "episode_0001"
    ep_dir.mkdir(parents=True, exist_ok=True)

    claim_scope = (
        "engineering_only_not_publication_evidence" if backend == "mock"
        else f"simulation_{backend}"
    )

    # metadata.yaml
    meta_lines = [
        f"run_id: test_run_001",
        f"model: gnm",
        f"backend: {backend}",
        f"benchmark_version: 0.1.0",
        f"protocol_version: 0.1.0",
        f"sceneset_version: 0.1.0",
        f"metricset_version: 0.1.0",
        f"git_commit: abc1234",
        f"claim_scope: {claim_scope}",
    ]
    (run_dir / "metadata.yaml").write_text("\n".join(meta_lines) + "\n")

    # aggregate_metrics.json
    agg = {
        "run_id": "test_run_001",
        "model": "gnm",
        "backend": backend,
        "benchmark_version": "0.1.0",
        "protocol_version": "0.1.0",
        "git_commit": "abc1234",
        "success_rate": 0.5,
    }
    (run_dir / "aggregate_metrics.json").write_text(json.dumps(agg))

    # aggregate_metrics.csv
    (run_dir / "aggregate_metrics.csv").write_text("scene,success_rate\n")

    # aggregate_by_scene.json
    (run_dir / "aggregate_by_scene.json").write_text(json.dumps({"by_scene": {}}))

    # episode.json
    ep_payload = {
        "model": "gnm", "backend": backend, "seed": 0,
        "scene": "straight_corridor", "success": False,
        "claim_scope": claim_scope,
    }
    (ep_dir / "episode.json").write_text(json.dumps(ep_payload))

    # trajectory.csv
    (ep_dir / "trajectory.csv").write_text("step,x,y,heading,latency_ms\n")

    # actions.csv (all required columns)
    with (ep_dir / "actions.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "step", "raw_vx", "raw_vy", "raw_wz",
            "safe_vx", "safe_vy", "safe_wz",
            "delta_l2", "intervened", "min_dist_m",
        ])
        writer.writeheader()

    # safety_events.jsonl
    (ep_dir / "safety_events.jsonl").write_text("")

    # intervention_evidence.jsonl (empty: intervention_count == 0)
    (ep_dir / "intervention_evidence.jsonl").write_text("")

    # metrics.json
    (ep_dir / "metrics.json").write_text(json.dumps({
        "success": False, "benchmark_version": "0.1.0", "intervention_count": 0,
    }))


class TestArtifactValidator:
    def test_passes_on_valid_mock_artifact(self, tmp_path):
        from scripts.visualnav.validate_benchmark_artifact import validate_run_directory
        run_dir = tmp_path / "test_run"
        _write_minimal_valid_run(run_dir, backend="mock")
        result = validate_run_directory(run_dir)
        assert result["status"] == "PASS"

    def test_passes_on_valid_mujoco_artifact(self, tmp_path):
        from scripts.visualnav.validate_benchmark_artifact import validate_run_directory
        run_dir = tmp_path / "test_run"
        _write_minimal_valid_run(run_dir, backend="mujoco")
        result = validate_run_directory(run_dir)
        assert result["status"] == "PASS"

    def test_fails_missing_metadata_yaml(self, tmp_path):
        from scripts.visualnav.validate_benchmark_artifact import (
            validate_run_directory, ArtifactViolation
        )
        run_dir = tmp_path / "test_run"
        _write_minimal_valid_run(run_dir, backend="mock")
        (run_dir / "metadata.yaml").unlink()
        with pytest.raises(ArtifactViolation, match="metadata.yaml"):
            validate_run_directory(run_dir)

    def test_fails_missing_aggregate_metrics(self, tmp_path):
        from scripts.visualnav.validate_benchmark_artifact import (
            validate_run_directory, ArtifactViolation
        )
        run_dir = tmp_path / "test_run"
        _write_minimal_valid_run(run_dir, backend="mock")
        (run_dir / "aggregate_metrics.json").unlink()
        with pytest.raises(ArtifactViolation):
            validate_run_directory(run_dir)

    def test_fails_mock_without_engineering_label(self, tmp_path):
        from scripts.visualnav.validate_benchmark_artifact import (
            validate_run_directory, ArtifactViolation
        )
        run_dir = tmp_path / "test_run"
        _write_minimal_valid_run(run_dir, backend="mock")
        # Overwrite metadata with wrong claim_scope
        meta_path = run_dir / "metadata.yaml"
        text = meta_path.read_text().replace(
            "engineering_only_not_publication_evidence",
            "publication_valid_run",
        )
        meta_path.write_text(text)
        with pytest.raises(ArtifactViolation, match="engineering_only"):
            validate_run_directory(run_dir)

    def test_checks_passed_positive_on_valid(self, tmp_path):
        from scripts.visualnav.validate_benchmark_artifact import validate_run_directory
        run_dir = tmp_path / "test_run"
        _write_minimal_valid_run(run_dir, backend="mujoco")
        result = validate_run_directory(run_dir)
        assert result["checks_passed"] > 0

    def test_fails_missing_episode_actions_csv(self, tmp_path):
        from scripts.visualnav.validate_benchmark_artifact import (
            validate_run_directory, ArtifactViolation
        )
        run_dir = tmp_path / "test_run"
        _write_minimal_valid_run(run_dir, backend="mock")
        (run_dir / "episodes" / "episode_0001" / "actions.csv").unlink()
        with pytest.raises(ArtifactViolation):
            validate_run_directory(run_dir)

    def test_fails_actions_csv_missing_required_column(self, tmp_path):
        from scripts.visualnav.validate_benchmark_artifact import (
            validate_run_directory, ArtifactViolation
        )
        run_dir = tmp_path / "test_run"
        _write_minimal_valid_run(run_dir, backend="mujoco")
        # Overwrite actions.csv without delta_l2
        actions_path = run_dir / "episodes" / "episode_0001" / "actions.csv"
        with actions_path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=[
                "step", "raw_vx", "raw_vy", "raw_wz",
                "safe_vx", "safe_vy", "safe_wz",
                "intervened", "min_dist_m",   # delta_l2 intentionally omitted
            ])
            writer.writeheader()
        with pytest.raises(ArtifactViolation, match="delta_l2"):
            validate_run_directory(run_dir)


# ── 8. Freeze script ──────────────────────────────────────────────────────────

class TestFreezeScript:
    def test_freeze_creates_manifest(self, tmp_path):
        from scripts.visualnav.freeze_benchmark_run import freeze_run
        run_dir = tmp_path / "test_run"
        _write_minimal_valid_run(run_dir, backend="mujoco")
        frozen_base = tmp_path / "frozen"
        frozen_dir = freeze_run(run_dir, frozen_base)
        assert (frozen_dir / "MANIFEST.json").exists()
        assert (frozen_dir / "SHA256SUMS").exists()
        assert (frozen_dir / "GIT_STATE.txt").exists()
        assert (frozen_dir / "ENVIRONMENT.txt").exists()

    def test_freeze_refuses_overwrite_without_force(self, tmp_path):
        from scripts.visualnav.freeze_benchmark_run import freeze_run
        run_dir = tmp_path / "test_run"
        _write_minimal_valid_run(run_dir, backend="mujoco")
        frozen_base = tmp_path / "frozen"
        # First freeze succeeds
        freeze_run(run_dir, frozen_base)
        # Second freeze without --force must exit
        with pytest.raises(SystemExit):
            freeze_run(run_dir, frozen_base, force=False)

    def test_freeze_allows_overwrite_with_force(self, tmp_path):
        from scripts.visualnav.freeze_benchmark_run import freeze_run
        run_dir = tmp_path / "test_run"
        _write_minimal_valid_run(run_dir, backend="mujoco")
        frozen_base = tmp_path / "frozen"
        freeze_run(run_dir, frozen_base)
        # Second freeze with --force must succeed
        frozen_dir = freeze_run(run_dir, frozen_base, force=True)
        assert (frozen_dir / "MANIFEST.json").exists()

    def test_freeze_manifest_contains_version(self, tmp_path):
        from scripts.visualnav.freeze_benchmark_run import freeze_run
        run_dir = tmp_path / "test_run"
        _write_minimal_valid_run(run_dir, backend="mujoco")
        frozen_base = tmp_path / "frozen"
        frozen_dir = freeze_run(run_dir, frozen_base)
        manifest = json.loads((frozen_dir / "MANIFEST.json").read_text())
        assert "benchmark_version" in manifest
        assert "git_commit" in manifest

    def test_freeze_sha256sums_nonempty(self, tmp_path):
        from scripts.visualnav.freeze_benchmark_run import freeze_run
        run_dir = tmp_path / "test_run"
        _write_minimal_valid_run(run_dir, backend="mujoco")
        frozen_base = tmp_path / "frozen"
        frozen_dir = freeze_run(run_dir, frozen_base)
        sums = (frozen_dir / "SHA256SUMS").read_text()
        assert len(sums.splitlines()) > 0


# ── 9. Runner embeds version fields ───────────────────────────────────────────

class TestRunnerVersionFields:
    """Verify that the benchmark runner embeds version fields in metadata.yaml."""

    def test_metadata_written_by_runner_has_version_fields(self, tmp_path):
        """
        The runner's _write_metadata method must write all six version keys
        plus git_commit to metadata.yaml.
        """
        from unittest.mock import MagicMock
        from fleet_safe_vla.benchmarks.visualnav_runner import VisualNavBenchmarkRunner
        from fleet_safe_vla.benchmarks.visualnav_scenarios import SceneSpec, StartGoalPair

        adapter = MagicMock()
        adapter.model_name = "gnm"
        runner = VisualNavBenchmarkRunner(adapter=adapter, backend="mock", output_dir=tmp_path)

        scene = SceneSpec(
            name="straight_corridor",
            description="Test corridor.",
            arena_size_m=8.0,
            start_goal_pairs=(
                StartGoalPair((0., 0.), (4., 0.), "forward"),
            ),
            obstacles=(),
            dynamic_agents=(),
        )

        run_dir = tmp_path / "test_meta_run"
        run_dir.mkdir()
        runner._write_metadata(run_dir, "test_run_001", [scene], [0])

        from scripts.visualnav.validate_benchmark_artifact import _parse_metadata_yaml
        meta = _parse_metadata_yaml(run_dir / "metadata.yaml")

        assert "benchmark_version" in meta
        assert "protocol_version" in meta
        assert "sceneset_version" in meta
        assert "metricset_version" in meta
        assert "git_commit" in meta
