"""
v0.8 Evidence Ledger & Dataset Provenance tests.

Invariants tested:
  A. Ledger: append-only, SHA256 deterministic, entries never modified.
  B. Manifest: categories always honest — missing → missing_warning, present → count > 0.
  C. Connectors: HF + W&B always return explicit status; never claim ok when empty/missing.
  D. Ground truth taxonomy: claim scopes match their expected GT type.
  E. No false claims: manifest never marks categories present when files don't exist.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "command-center"))
os.environ.setdefault("FLEETSAFE_ROBOT_DRY_RUN", "true")


# ── Helpers ────────────────────────────────────────────────────────────────────

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """EvidenceLedger writing to a temp file."""
    import backend.services.evidence_ledger as mod
    ledger_path = tmp_path / "evidence_ledger.jsonl"
    monkeypatch.setattr(mod, "LEDGER_PATH", ledger_path)
    from backend.services.evidence_ledger import EvidenceLedger
    ledger = EvidenceLedger.__new__(EvidenceLedger)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    return ledger, ledger_path


@pytest.fixture()
def tmp_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """dataset_manifest pointing to tmp dirs."""
    import backend.services.dataset_manifest as mod
    monkeypatch.setattr(mod, "MANIFEST_PATH", tmp_path / "dataset_manifest.json")
    monkeypatch.setattr(mod, "RESULTS_DIR",    tmp_path / "results")
    monkeypatch.setattr(mod, "RECORDINGS_DIR", tmp_path / "recordings")
    return mod, tmp_path


# ── A. Ledger invariants ───────────────────────────────────────────────────────

class TestLedgerAppendOnly:
    def test_first_record_creates_file(self, tmp_ledger):
        ledger, path = tmp_ledger
        assert not path.exists()
        ledger.record(
            claim_scope="dashboard_audit",
            source="dashboard",
            ground_truth_type="none",
            description="test entry",
        )
        assert path.exists()

    def test_each_record_appends_one_line(self, tmp_ledger):
        ledger, path = tmp_ledger
        for i in range(5):
            ledger.record("dashboard_audit", "dashboard", "none", description=f"entry {i}")
        lines = path.read_text().splitlines()
        assert len(lines) == 5

    def test_past_lines_immutable_after_new_record(self, tmp_ledger):
        ledger, path = tmp_ledger
        ledger.record("dashboard_audit", "dashboard", "none", description="first")
        first_content = path.read_text()
        ledger.record("dashboard_audit", "dashboard", "none", description="second")
        new_content = path.read_text()
        assert new_content.startswith(first_content), "Existing lines were modified"

    def test_record_returns_entry_with_id(self, tmp_ledger):
        ledger, path = tmp_ledger
        entry = ledger.record("sim_benchmark_result", "mujoco", "perfect_sim_state",
                               description="run finished")
        assert "id" in entry
        assert len(entry["id"]) == 16

    def test_record_captures_timestamp(self, tmp_ledger):
        ledger, path = tmp_ledger
        before = time.time()
        entry = ledger.record("dashboard_audit", "dashboard", "none", description="ts test")
        after = time.time()
        assert before <= entry["timestamp"] <= after

    def test_record_captures_host_and_git(self, tmp_ledger):
        ledger, path = tmp_ledger
        entry = ledger.record("dashboard_audit", "dashboard", "none", description="meta test")
        assert "host" in entry
        assert "git_commit" in entry

    def test_query_returns_most_recent_n(self, tmp_ledger):
        ledger, path = tmp_ledger
        for i in range(20):
            ledger.record("dashboard_audit", "dashboard", "none", description=f"e{i}")
        results = ledger.query(n=10)
        assert len(results) == 10
        assert results[-1]["description"] == "e19"

    def test_query_filters_by_source(self, tmp_ledger):
        ledger, path = tmp_ledger
        ledger.record("sim_benchmark_result", "mujoco", "perfect_sim_state", description="sim")
        ledger.record("dashboard_audit", "dashboard", "none", description="dash")
        mujoco = ledger.query(source="mujoco")
        assert all(e["source"] == "mujoco" for e in mujoco)
        assert len(mujoco) == 1

    def test_query_filters_by_claim_scope(self, tmp_ledger):
        ledger, path = tmp_ledger
        ledger.record("sim_benchmark_result", "mujoco", "perfect_sim_state", description="run")
        ledger.record("dashboard_audit", "dashboard", "none", description="audit")
        audits = ledger.query(claim_scope="dashboard_audit")
        assert all(e["claim_scope"] == "dashboard_audit" for e in audits)

    def test_get_stats_counts_hashed(self, tmp_ledger, tmp_path):
        ledger, path = tmp_ledger
        artifact = tmp_path / "artifact.json"
        artifact.write_text('{"result": 1}')
        ledger.record("sim_benchmark_result", "mujoco", "perfect_sim_state",
                       description="with artifact", artifact_path=artifact)
        ledger.record("dashboard_audit", "dashboard", "none", description="no artifact")
        stats = ledger.get_stats()
        assert stats["total"] == 2
        assert stats["hashed"] == 1

    def test_get_stats_by_source(self, tmp_ledger):
        ledger, path = tmp_ledger
        for _ in range(3):
            ledger.record("sim_benchmark_result", "mujoco", "perfect_sim_state", description="m")
        for _ in range(2):
            ledger.record("dashboard_audit", "dashboard", "none", description="d")
        stats = ledger.get_stats()
        assert stats["by_source"]["mujoco"] == 3
        assert stats["by_source"]["dashboard"] == 2


# ── B. SHA256 determinism ──────────────────────────────────────────────────────

class TestSha256:
    def test_sha256_file_is_deterministic(self, tmp_path):
        from backend.services.evidence_ledger import sha256_file
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        h1 = sha256_file(f)
        h2 = sha256_file(f)
        assert h1 == h2
        assert h1 == sha256_bytes(b"hello world")

    def test_sha256_file_returns_none_for_missing(self, tmp_path):
        from backend.services.evidence_ledger import sha256_file
        assert sha256_file(tmp_path / "nonexistent.bin") is None

    def test_artifact_sha256_stored_in_ledger(self, tmp_ledger, tmp_path):
        ledger, path = tmp_ledger
        artifact = tmp_path / "model.pt"
        content = b"fake model weights " * 100
        artifact.write_bytes(content)
        entry = ledger.record("training_checkpoint", "wandb", "none",
                               description="checkpoint", artifact_path=artifact)
        expected = sha256_bytes(content)
        assert entry["sha256"] == expected

    def test_same_file_same_hash_across_records(self, tmp_ledger, tmp_path):
        ledger, path = tmp_ledger
        artifact = tmp_path / "same.bin"
        artifact.write_bytes(b"deterministic content")
        e1 = ledger.record("training_checkpoint", "wandb", "none",
                            description="first", artifact_path=artifact)
        e2 = ledger.record("training_checkpoint", "wandb", "none",
                            description="second", artifact_path=artifact)
        assert e1["sha256"] == e2["sha256"]


# ── C. Manifest honesty ────────────────────────────────────────────────────────

class TestManifestHonesty:
    def test_empty_filesystem_yields_all_missing(self, tmp_manifest):
        mod, tmp = tmp_manifest
        manifest = mod.build_manifest()
        cats = manifest["categories"]
        # Nothing in tmp dirs → these must be not-present
        # (video_evidence may still be present if the real repo has GIFs — that's honest)
        for key in ("synthetic_sim", "real_robot", "manual_labels"):
            assert cats[key]["present"] is False, f"{key} should be absent"
            assert cats[key]["missing_warning"] is not None, f"{key} should have missing_warning"

    def test_missing_categories_have_warning_strings(self, tmp_manifest):
        mod, tmp = tmp_manifest
        manifest = mod.build_manifest()
        # model_outputs is derived and intentionally has no warning (it mirrors sim runs)
        skip = {"model_outputs"}
        for key, cat in manifest["categories"].items():
            if key in skip:
                continue
            if not cat["present"]:
                assert isinstance(cat["missing_warning"], str), \
                    f"Missing category '{key}' must have a string warning"
                assert len(cat["missing_warning"]) > 10, \
                    f"Warning for '{key}' is too short to be useful"

    def test_present_categories_have_no_false_warning(self, tmp_manifest):
        mod, tmp = tmp_manifest
        results = tmp / "results" / "run_001"
        results.mkdir(parents=True)
        (results / "aggregate_metrics.json").write_text(json.dumps({
            "backend": "mujoco", "model": "test", "fleetsafe": True,
            "n_episodes": 10, "success_rate": 0.8,
        }))
        manifest = mod.build_manifest()
        cat = manifest["categories"]["synthetic_sim"]
        assert cat["present"] is True
        assert cat["count"] == 1
        # missing_warning can be None or absent when present
        assert not cat.get("missing_warning"), "Present category should not have a warning"

    def test_defensibility_score_reflects_present_count(self, tmp_manifest):
        mod, tmp = tmp_manifest
        manifest = mod.build_manifest()
        score = manifest["summary"]["defensibility_score"]
        present = manifest["summary"]["categories_present"]
        total = len(manifest["categories"])
        assert score == f"{present}/{total}"

    def test_real_robot_absent_when_no_sessions(self, tmp_manifest):
        mod, tmp = tmp_manifest
        manifest = mod.build_manifest()
        assert manifest["categories"]["real_robot"]["present"] is False

    def test_manual_labels_always_absent(self, tmp_manifest):
        mod, tmp = tmp_manifest
        # Even with real runs, manual labels should be absent (no annotation pipeline)
        results = tmp / "results" / "run_A"
        results.mkdir(parents=True)
        (results / "aggregate_metrics.json").write_text('{"backend":"mujoco","model":"x"}')
        manifest = mod.build_manifest()
        assert manifest["categories"]["manual_labels"]["present"] is False
        assert manifest["categories"]["manual_labels"]["missing_warning"] is not None

    def test_photoreal_always_absent(self, tmp_manifest):
        mod, tmp = tmp_manifest
        manifest = mod.build_manifest()
        assert manifest["categories"]["photoreal_sim"]["present"] is False
        assert manifest["categories"]["photoreal_sim"]["missing_warning"] is not None

    def test_manifest_saved_to_disk(self, tmp_manifest):
        mod, tmp = tmp_manifest
        mod.build_manifest()
        assert (tmp / "dataset_manifest.json").exists()

    def test_load_manifest_returns_none_when_absent(self, tmp_manifest):
        mod, tmp = tmp_manifest
        assert mod.load_manifest() is None

    def test_load_manifest_matches_build(self, tmp_manifest):
        mod, tmp = tmp_manifest
        built = mod.build_manifest()
        loaded = mod.load_manifest()
        assert loaded is not None
        assert loaded["summary"]["defensibility_score"] == built["summary"]["defensibility_score"]


# ── D. Connectors: no false claims ────────────────────────────────────────────

class TestHfConnector:
    def test_returns_not_configured_when_import_fails(self):
        with patch.dict("sys.modules", {"huggingface_hub": None}):
            # Force reimport with broken module
            import importlib
            import backend.services.hf_connector as mod
            # Patch the import inside the function
            with patch("builtins.__import__", side_effect=ImportError):
                result = mod.get_hf_status()
            # Should return not_configured or error — never "ok"
            assert result["status"] in ("not_configured", "error", "no_runs")

    def test_returns_not_configured_when_token_missing(self):
        mock_api = MagicMock()
        mock_api.return_value.whoami.side_effect = Exception("not logged in")
        with patch.dict("sys.modules", {"huggingface_hub": MagicMock(HfApi=mock_api, list_models=MagicMock(return_value=[]))}):
            import importlib
            import backend.services.hf_connector as mod
            importlib.reload(mod)
            result = mod.get_hf_status()
            assert result["status"] == "not_configured"
            assert "runs" in result
            assert isinstance(result["runs"], list)
        # Remove cached mock-reloaded module so next test gets a fresh import
        sys.modules.pop("backend.services.hf_connector", None)

    def test_returns_no_runs_when_empty_model_list(self):
        mock_hf = MagicMock()
        mock_hf.HfApi.return_value.whoami.return_value = {"name": "testuser"}
        mock_hf.list_models.return_value = []
        mock_hf.list_datasets.return_value = []
        with patch.dict("sys.modules", {"huggingface_hub": mock_hf}):
            import importlib
            import backend.services.hf_connector as mod
            importlib.reload(mod)
            result = mod.get_hf_status()
            assert result["status"] == "no_runs"
            assert result["runs"] == []
            assert "warning" in result
        # Remove cached mock-reloaded module so subsequent tests get a fresh import
        sys.modules.pop("backend.services.hf_connector", None)

    def test_status_always_present(self):
        """Every code path must return a status field."""
        from backend.services.hf_connector import get_hf_status
        result = get_hf_status()  # runs against real env (not configured in CI)
        assert "status" in result
        assert result["status"] in ("ok", "not_configured", "no_runs", "error")


class TestWandbConnector:
    def test_returns_not_configured_when_import_fails(self):
        with patch.dict("sys.modules", {"wandb": None}):
            import importlib
            import backend.services.wandb_connector as mod
            importlib.reload(mod)
            result = mod.get_wandb_status()
            assert result["status"] == "not_configured"
            assert "runs" in result
        sys.modules.pop("backend.services.wandb_connector", None)

    def test_returns_no_runs_when_project_empty(self):
        mock_wandb = MagicMock()
        mock_wandb.Api.return_value.runs.return_value = []
        with patch.dict("sys.modules", {"wandb": mock_wandb}):
            import importlib
            import backend.services.wandb_connector as mod
            importlib.reload(mod)
            result = mod.get_wandb_status()
            assert result["status"] == "no_runs"
            assert result["runs"] == []
        sys.modules.pop("backend.services.wandb_connector", None)

    def test_status_always_present(self):
        from backend.services.wandb_connector import get_wandb_status
        result = get_wandb_status()
        assert "status" in result
        assert result["status"] in ("ok", "not_configured", "no_runs", "error")


# ── E. Ground truth taxonomy ───────────────────────────────────────────────────

class TestGroundTruthTaxonomy:
    """
    Verify that each claim scope maps to the correct ground truth type
    in the manifest and that no sim result claims human_labeled GT.
    """

    def test_synthetic_sim_is_perfect_sim_state(self, tmp_manifest):
        mod, tmp = tmp_manifest
        manifest = mod.build_manifest()
        assert manifest["categories"]["synthetic_sim"]["ground_truth_type"] == "perfect_sim_state"

    def test_real_robot_is_sensor_derived(self, tmp_manifest):
        mod, tmp = tmp_manifest
        manifest = mod.build_manifest()
        assert manifest["categories"]["real_robot"]["ground_truth_type"] == "sensor_derived"

    def test_manual_labels_is_human_labeled(self, tmp_manifest):
        mod, tmp = tmp_manifest
        manifest = mod.build_manifest()
        assert manifest["categories"]["manual_labels"]["ground_truth_type"] == "human_labeled"

    def test_dashboard_audit_is_none_gt(self, tmp_manifest):
        mod, tmp = tmp_manifest
        manifest = mod.build_manifest()
        assert manifest["categories"]["dashboard_audit"]["ground_truth_type"] == "none"

    def test_model_outputs_is_none_gt(self, tmp_manifest):
        mod, tmp = tmp_manifest
        manifest = mod.build_manifest()
        assert manifest["categories"]["model_outputs"]["ground_truth_type"] == "none"

    def test_ledger_stores_correct_gt_type(self, tmp_ledger):
        ledger, path = tmp_ledger
        entry = ledger.record(
            "sim_benchmark_result", "mujoco", "perfect_sim_state",
            description="sim run"
        )
        assert entry["ground_truth_type"] == "perfect_sim_state"
        # Verify it's also in the file
        lines = path.read_text().splitlines()
        stored = json.loads(lines[0])
        assert stored["ground_truth_type"] == "perfect_sim_state"


# ── F. Ledger JSON validity ────────────────────────────────────────────────────

class TestLedgerJson:
    def test_every_line_is_valid_json(self, tmp_ledger):
        ledger, path = tmp_ledger
        for i in range(10):
            ledger.record("dashboard_audit", "dashboard", "none", description=f"e{i}",
                           metadata={"i": i, "nested": {"ok": True}})
        for line in path.read_text().splitlines():
            parsed = json.loads(line)
            assert isinstance(parsed, dict)

    def test_metadata_field_preserved(self, tmp_ledger):
        ledger, path = tmp_ledger
        meta = {"run_id": "abc123", "episodes": 50, "flags": ["fleetsafe"]}
        entry = ledger.record("sim_benchmark_result", "mujoco", "perfect_sim_state",
                               description="with meta", metadata=meta)
        assert entry["metadata"]["run_id"] == "abc123"
        stored = json.loads(path.read_text().splitlines()[0])
        assert stored["metadata"]["episodes"] == 50

    def test_query_returns_empty_list_when_no_ledger(self, tmp_ledger):
        ledger, path = tmp_ledger
        results = ledger.query()
        assert results == []
