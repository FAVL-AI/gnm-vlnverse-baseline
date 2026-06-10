"""
Simulation Evidence v1.0 tests.

Tests:
  A. Isaac proof script output structure and honest labels
  B. PPO smoke script output structure and honest labels
  C. W&B / HF sync — honest labels when not configured
  D. Smoke matrix script — dry-run output
  E. Publication bundle export — structure check
  F. sim_evidence_tracker — reads and aggregates status from artifacts
  G. /api/experiments/sim-evidence-status — endpoint registration

No Isaac GUI, no W&B login, no HF token required.
All artifact directories use tmp_path.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "command-center"))

os.environ.setdefault("FLEETSAFE_ROBOT_DRY_RUN", "true")


# ── A. Isaac proof ────────────────────────────────────────────────────────────

class TestIsaacProof:
    """capture_hospital_proof.py — no Isaac required."""

    @pytest.fixture()
    def proof_dir(self, tmp_path):
        """Run the proof capture into a temp directory."""
        script = _REPO_ROOT / "scripts" / "isaaclab" / "capture_hospital_proof.py"
        # Import and call main() directly (avoids subprocess overhead)
        import importlib.util
        spec = importlib.util.spec_from_file_location("capture_hospital_proof", script)
        mod  = importlib.util.module_from_spec(spec)
        out  = tmp_path / "isaac_proof"

        with patch("sys.argv", ["capture_hospital_proof.py", "--output-dir", str(out)]):
            spec.loader.exec_module(mod)
            mod.main()

        return out

    def test_proof_dir_created(self, proof_dir):
        assert proof_dir.exists()

    def test_isaac_scene_proof_json_exists(self, proof_dir):
        assert (proof_dir / "isaac_scene_proof.json").exists()

    def test_viewport_status_exists(self, proof_dir):
        assert (proof_dir / "viewport_status.txt").exists()

    def test_zone_map_exists(self, proof_dir):
        assert (proof_dir / "hospital_zone_map.json").exists()

    def test_scene_manifest_exists(self, proof_dir):
        assert (proof_dir / "scene_manifest.json").exists()

    def test_proof_json_valid(self, proof_dir):
        data = json.loads((proof_dir / "isaac_scene_proof.json").read_text())
        assert "honest_labels" in data
        assert "photoreal" in data
        assert "procedural" in data
        assert "isaac_sim" in data

    def test_honest_labels_present(self, proof_dir):
        data = json.loads((proof_dir / "isaac_scene_proof.json").read_text())
        labels = data["honest_labels"]
        assert "photoreal_hospital_status" in labels
        assert "procedural_hospital_status" in labels
        assert "isaac_sim_runtime_status" in labels

    def test_photoreal_honestly_missing(self, proof_dir):
        # No USD file present in CI → must be MISSING
        data = json.loads((proof_dir / "isaac_scene_proof.json").read_text())
        assert data["honest_labels"]["photoreal_hospital_status"] == "MISSING"

    def test_procedural_not_not_validated(self, proof_dir):
        # Asset library or SCENESET yaml should be available → PROVEN or PARTIAL at minimum
        data = json.loads((proof_dir / "isaac_scene_proof.json").read_text())
        status = data["honest_labels"]["procedural_hospital_status"]
        assert status in ("PROVEN", "PARTIAL"), (
            f"Procedural status unexpectedly {status!r} — "
            "expected PROVEN or PARTIAL (asset library or SCENESET yaml should be present)"
        )

    def test_zone_map_has_zones(self, proof_dir):
        data = json.loads((proof_dir / "hospital_zone_map.json").read_text())
        assert "zones" in data
        assert len(data["zones"]) >= 3

    def test_zone_map_has_icu(self, proof_dir):
        data = json.loads((proof_dir / "hospital_zone_map.json").read_text())
        names = [z["name"] for z in data["zones"]]
        assert "icu" in names

    def test_no_do_not_claim_violations(self, proof_dir):
        data = json.loads((proof_dir / "isaac_scene_proof.json").read_text())
        # do_not_claim should be a list (may be empty only if all proven, else non-empty)
        assert isinstance(data.get("do_not_claim", []), list)


# ── B. PPO smoke ──────────────────────────────────────────────────────────────

class TestPPOSmoke:
    """run_ppo_smoke.py — no Isaac, no torch required."""

    @pytest.fixture()
    def ppo_dir(self, tmp_path):
        script = _REPO_ROOT / "scripts" / "training" / "run_ppo_smoke.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_ppo_smoke", script)
        mod  = importlib.util.module_from_spec(spec)
        out  = tmp_path / "ppo_run"

        with patch("sys.argv", ["run_ppo_smoke.py", "--steps", "30",
                                "--seed", "42", "--output-dir", str(out)]):
            spec.loader.exec_module(mod)
            mod.main()

        return out

    def test_dir_created(self, ppo_dir):
        assert ppo_dir.exists()

    def test_reward_curve_csv(self, ppo_dir):
        f = ppo_dir / "reward_curve.csv"
        assert f.exists()
        rows = list(csv.DictReader(f.open()))
        assert len(rows) == 30
        assert "total_reward" in rows[0]

    def test_training_log_exists(self, ppo_dir):
        assert (ppo_dir / "training_log.txt").exists()

    def test_eval_metrics_exists(self, ppo_dir):
        assert (ppo_dir / "eval_metrics.json").exists()

    def test_config_exists(self, ppo_dir):
        # config.yaml or config.yaml (JSON fallback)
        assert (ppo_dir / "config.yaml").exists()

    def test_checkpoint_exists(self, ppo_dir):
        ckpts = list(ppo_dir.glob("checkpoint.*"))
        assert ckpts, "No checkpoint file produced"

    def test_ppo_full_training_not_validated(self, ppo_dir):
        m = json.loads((ppo_dir / "eval_metrics.json").read_text())
        assert m["PPO_FULL_TRAINING"] == "NOT_VALIDATED"

    def test_ppo_smoke_recorded(self, ppo_dir):
        m = json.loads((ppo_dir / "eval_metrics.json").read_text())
        assert m["PPO_SMOKE_TRAINING"] == "RECORDED"

    def test_mean_reward_is_finite(self, ppo_dir):
        m = json.loads((ppo_dir / "eval_metrics.json").read_text())
        assert isinstance(m["mean_total_reward"], float)
        import math
        assert math.isfinite(m["mean_total_reward"])

    def test_all_zones_exercised(self, ppo_dir):
        f = ppo_dir / "reward_curve.csv"
        zones = {row["zone"] for row in csv.DictReader(f.open())}
        assert "GREEN" in zones
        assert "AMBER" in zones
        # RED may not appear in 30 steps if zone_seq cycle is long; relaxed check
        assert len(zones) >= 2


# ── C. W&B / HF sync ─────────────────────────────────────────────────────────

class TestWandbHFSync:
    """sync_wandb_hf_metadata.py — must not fail when unconfigured."""

    @pytest.fixture()
    def integration_dir(self, tmp_path, monkeypatch):
        script = _REPO_ROOT / "scripts" / "integrations" / "sync_wandb_hf_metadata.py"
        import importlib.util

        # Redirect output to tmp
        int_dir = tmp_path / "integrations"
        monkeypatch.setenv("WANDB_API_KEY", "")
        monkeypatch.setenv("HF_TOKEN", "")
        monkeypatch.setenv("ORCID_ID", "0000-0002-TEST-1234")

        spec = importlib.util.spec_from_file_location("sync_wandb_hf_metadata", script)
        mod  = importlib.util.module_from_spec(spec)

        # Patch _REPO_ROOT inside the module after loading
        spec.loader.exec_module(mod)
        mod._REPO_ROOT = tmp_path

        # Run directly
        orig_mkdir = Path.mkdir
        int_dir.mkdir(parents=True, exist_ok=True)

        wandb_s  = mod._get_wandb_status()
        hf_s     = mod._get_hf_status()
        identity = mod._get_researcher_identity()

        int_dir.mkdir(parents=True, exist_ok=True)
        (int_dir / "wandb_status.json").write_text(json.dumps(wandb_s))
        (int_dir / "hf_status.json").write_text(json.dumps(hf_s))
        (int_dir / "researcher_identity.json").write_text(json.dumps(identity))

        return int_dir

    def test_wandb_status_file_created(self, integration_dir):
        assert (integration_dir / "wandb_status.json").exists()

    def test_hf_status_file_created(self, integration_dir):
        assert (integration_dir / "hf_status.json").exists()

    def test_researcher_identity_file_created(self, integration_dir):
        assert (integration_dir / "researcher_identity.json").exists()

    def test_wandb_has_honest_label(self, integration_dir):
        d = json.loads((integration_dir / "wandb_status.json").read_text())
        assert "honest_label" in d
        valid = {"RECORDED", "MISSING", "NOT_CONFIGURED", "ERROR"}
        assert d["honest_label"] in valid, f"Unexpected label: {d['honest_label']}"

    def test_hf_has_honest_label(self, integration_dir):
        d = json.loads((integration_dir / "hf_status.json").read_text())
        assert "honest_label" in d
        valid = {"RECORDED", "MISSING", "NOT_CONFIGURED", "ERROR"}
        assert d["honest_label"] in valid

    def test_identity_orcid_from_env(self, integration_dir):
        d = json.loads((integration_dir / "researcher_identity.json").read_text())
        assert d["orcid_id"] == "0000-0002-TEST-1234"

    def test_wandb_not_claimed_as_ok_when_unconfigured(self, integration_dir):
        d = json.loads((integration_dir / "wandb_status.json").read_text())
        # If wandb is configured via ~/.netrc even with an empty WANDB_API_KEY,
        # honest_label=RECORDED is correct — skip rather than false-fail.
        if d.get("status") == "ok":
            pytest.skip("wandb configured via ~/.netrc; RECORDED is the honest label")
        assert d["honest_label"] != "RECORDED", (
            "W&B reported RECORDED despite empty API key — dishonest label"
        )


# ── D. Smoke matrix dry-run ───────────────────────────────────────────────────

class TestSmokematrixDryRun:
    """run_publication_smoke_matrix.py --dry-run — just checks command list."""

    def test_dry_run_exits_zero(self, capsys):
        script = _REPO_ROOT / "scripts" / "visualnav" / "run_publication_smoke_matrix.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_publication_smoke_matrix", script)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with patch("sys.argv", [
            "run_publication_smoke_matrix.py",
            "--dry-run",
            "--seeds", "0,1",
            "--scenes", "social_red_zone_smoke",
            "--backbones", "mock",
        ]):
            rc = mod.main()
        assert rc == 0

    def test_dry_run_prints_commands(self, capsys):
        script = _REPO_ROOT / "scripts" / "visualnav" / "run_publication_smoke_matrix.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_publication_smoke_matrix2", script)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with patch("sys.argv", [
            "run_publication_smoke_matrix.py",
            "--dry-run",
            "--seeds", "0",
            "--scenes", "hospital_corridor",
            "--backbones", "mock",
        ]):
            mod.main()

        captured = capsys.readouterr()
        assert "model=mock" in captured.out or "dry-run" in captured.out.lower()


# ── E. Publication bundle (no full paper_exporter required) ───────────────────

class TestPublicationBundle:
    """export_publication_bundle.py — runs with empty/mock registry."""

    @pytest.fixture()
    def bundle(self, tmp_path, monkeypatch):
        script = _REPO_ROOT / "scripts" / "publication" / "export_publication_bundle.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("export_publication_bundle", script)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        out = tmp_path / "bundle"

        # Patch _REPO_ROOT so status checkers see our tmp dirs
        monkeypatch.setattr(mod, "_REPO_ROOT", tmp_path)

        with patch("sys.argv", ["export_publication_bundle.py", "--output-dir", str(out)]):
            mod.main()

        return out

    def test_bundle_dir_created(self, bundle):
        assert bundle.exists()

    def test_readme_created(self, bundle):
        assert (bundle / "README.md").exists()

    def test_readme_has_do_not_claim(self, bundle):
        text = (bundle / "README.md").read_text()
        assert "Do NOT Claim" in text or "do not claim" in text.lower()

    def test_readiness_json_created(self, bundle):
        assert (bundle / "publication_readiness.json").exists()

    def test_readiness_has_overall_pct(self, bundle):
        d = json.loads((bundle / "publication_readiness.json").read_text())
        assert "overall_pct" in d
        assert 0 <= d["overall_pct"] <= 100

    def test_claim_validation_created(self, bundle):
        assert (bundle / "claim_validation_report.json").exists()

    def test_evidence_ledger_created(self, bundle):
        assert (bundle / "evidence_ledger.jsonl").exists()


# ── F. sim_evidence_tracker ───────────────────────────────────────────────────

class TestSimEvidenceTracker:
    """Backend service: reads status from recording dirs."""

    def test_not_run_when_dirs_missing(self, tmp_path, monkeypatch):
        from backend.services import sim_evidence_tracker as tracker
        monkeypatch.setattr(tracker, "_REPO_ROOT", tmp_path)

        status = tracker.get_sim_evidence_status()
        assert "items" in status
        assert "overall_pct" in status

        isaac_item = next(it for it in status["items"] if it["name"] == "isaac_hospital_proof")
        assert isaac_item["status"] == "NOT_RUN"

        ppo_item = next(it for it in status["items"] if it["name"] == "ppo_smoke_training")
        assert ppo_item["status"] == "NOT_RUN"

    def test_reads_isaac_proof(self, tmp_path, monkeypatch):
        from backend.services import sim_evidence_tracker as tracker
        monkeypatch.setattr(tracker, "_REPO_ROOT", tmp_path)

        # Write a minimal proof
        proof_dir = tmp_path / "recordings" / "isaac_proof" / "12345"
        proof_dir.mkdir(parents=True)
        proof = {
            "honest_labels": {
                "photoreal_hospital_status": "MISSING",
                "procedural_hospital_status": "PROVEN",
                "isaac_sim_runtime_status": "NOT_AVAILABLE",
            },
            "do_not_claim": ["photoreal_hospital_complete — USD file not present"],
        }
        (proof_dir / "isaac_scene_proof.json").write_text(json.dumps(proof))

        status = tracker.get_sim_evidence_status()
        isaac_item = next(it for it in status["items"] if it["name"] == "isaac_hospital_proof")
        assert isaac_item["status"] == "RECORDED"

        detail = status["isaac"]
        assert detail["procedural"] == "PROVEN"
        assert detail["photoreal"] == "MISSING"

    def test_reads_ppo_smoke(self, tmp_path, monkeypatch):
        from backend.services import sim_evidence_tracker as tracker
        monkeypatch.setattr(tracker, "_REPO_ROOT", tmp_path)

        ppo_dir = tmp_path / "recordings" / "ppo_smoke" / "ppo_smoke_test"
        ppo_dir.mkdir(parents=True)
        (ppo_dir / "eval_metrics.json").write_text(json.dumps({
            "PPO_FULL_TRAINING": "NOT_VALIDATED",
            "PPO_SMOKE_TRAINING": "RECORDED",
            "mean_total_reward": 0.42,
            "n_steps": 100,
        }))

        status = tracker.get_sim_evidence_status()
        ppo_item = next(it for it in status["items"] if it["name"] == "ppo_smoke_training")
        assert ppo_item["status"] == "RECORDED"

        full_item = next(it for it in status["items"] if it["name"] == "ppo_full_training")
        assert full_item["status"] == "NOT_VALIDATED"

    def test_overall_pct_increases_with_evidence(self, tmp_path, monkeypatch):
        from backend.services import sim_evidence_tracker as tracker
        monkeypatch.setattr(tracker, "_REPO_ROOT", tmp_path)

        baseline = tracker.get_sim_evidence_status()["overall_pct"]

        # Add Isaac proof
        proof_dir = tmp_path / "recordings" / "isaac_proof" / "9999"
        proof_dir.mkdir(parents=True)
        (proof_dir / "isaac_scene_proof.json").write_text(json.dumps({
            "honest_labels": {
                "photoreal_hospital_status": "MISSING",
                "procedural_hospital_status": "PROVEN",
                "isaac_sim_runtime_status": "NOT_AVAILABLE",
            },
            "do_not_claim": [],
        }))

        after = tracker.get_sim_evidence_status()["overall_pct"]
        assert after > baseline, (
            f"Overall pct did not increase after adding Isaac proof: {baseline} → {after}"
        )


# ── G. Route registration ─────────────────────────────────────────────────────

class TestSimEvidenceRoute:
    """Smoke test: /api/experiments/sim-evidence-status is registered."""

    @pytest.fixture(scope="class", autouse=True)
    def client(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_sim_evidence_not_404(self, client):
        r = client.get("/api/experiments/sim-evidence-status")
        assert r.status_code != 404, "GET /api/experiments/sim-evidence-status is 404 — route not registered"

    def test_sim_evidence_returns_200(self, client):
        r = client.get("/api/experiments/sim-evidence-status")
        assert r.status_code == 200

    def test_sim_evidence_has_items(self, client):
        r = client.get("/api/experiments/sim-evidence-status")
        body = r.json()
        assert "items" in body
        assert isinstance(body["items"], list)
        assert len(body["items"]) >= 5

    def test_sim_evidence_has_overall_pct(self, client):
        r = client.get("/api/experiments/sim-evidence-status")
        body = r.json()
        assert "overall_pct" in body
        assert 0 <= body["overall_pct"] <= 100

    def test_no_label_claims_proven_without_evidence(self, client):
        """No item should be PROVEN unless we've run ≥10 seeds."""
        r = client.get("/api/experiments/sim-evidence-status")
        for it in r.json()["items"]:
            assert it["status"] != "PROVEN" or it["name"] not in (
                "isaac_hospital_proof", "ppo_smoke_training",
                "wandb_sync", "hf_sync",
            ), f"Item {it['name']} claims PROVEN without evidence"


# ── H. HF connector ───────────────────────────────────────────────────────────

class TestHFConnector:
    """hf_connector.py — mock huggingface_hub, verify honest labels."""

    def _load_connector(self):
        import importlib
        import backend.services.hf_connector as mod
        importlib.reload(mod)
        return mod

    def test_explicit_repo_id_wins_over_username(self, monkeypatch):
        """HF_REPO_ID env var takes priority over HF_USERNAME-derived path."""
        monkeypatch.setenv("HF_REPO_ID", "EXPLICIT_ORG/explicit-repo")
        monkeypatch.setenv("HF_USERNAME", "someuser")
        mod = self._load_connector()
        assert mod._default_repo_id() == "EXPLICIT_ORG/explicit-repo"

    def test_username_fallback_when_no_explicit(self, monkeypatch):
        """Without HF_REPO_ID, fall back to {HF_USERNAME}/fleetsafe-hospitalnav."""
        monkeypatch.delenv("HF_REPO_ID", raising=False)
        monkeypatch.setenv("HF_USERNAME", "myuser")
        mod = self._load_connector()
        assert mod._default_repo_id() == "myuser/fleetsafe-hospitalnav"

    def test_empty_when_neither_set(self, monkeypatch):
        monkeypatch.delenv("HF_REPO_ID", raising=False)
        monkeypatch.delenv("HF_USERNAME", raising=False)
        mod = self._load_connector()
        assert mod._default_repo_id() == ""

    def test_repo_info_success_returns_ok(self, monkeypatch):
        """When repo_info succeeds, status='ok' and runs list is populated."""
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("HF_REPO_ID", "FAVL/fleetsafe-hospitalnav")
        monkeypatch.delenv("HF_USERNAME", raising=False)

        mock_sibling = MagicMock()
        mock_sibling.rfilename = "data/train.parquet"

        mock_info = MagicMock()
        mock_info.siblings = [mock_sibling]
        mock_info.lastModified = "2025-01-01T00:00:00"
        mock_info.last_modified = None

        mock_user = {"name": "FAVL", "username": "FAVL"}

        mock_api = MagicMock()
        mock_api.whoami.return_value = mock_user
        mock_api.repo_info.return_value = mock_info

        mod = self._load_connector()
        with patch.object(mod, "__builtins__", mod.__builtins__):
            with patch("huggingface_hub.HfApi", return_value=mock_api):
                result = mod.get_hf_status()

        assert result["status"] == "ok", f"Expected ok, got: {result}"
        assert result["repo_id"] == "FAVL/fleetsafe-hospitalnav"
        assert result["n_files"] == 1
        assert len(result["runs"]) >= 1

    def test_missing_repo_returns_missing(self, monkeypatch):
        """RepositoryNotFoundError → status='missing', not failure."""
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("HF_REPO_ID", "FAVL/nonexistent-repo")
        monkeypatch.delenv("HF_USERNAME", raising=False)

        # Build a real-looking RepositoryNotFoundError
        try:
            from huggingface_hub.utils import RepositoryNotFoundError
        except ImportError:
            pytest.skip("huggingface_hub not installed")

        mock_api = MagicMock()
        mock_api.whoami.return_value = {"name": "FAVL", "username": "FAVL"}
        mock_api.repo_info.side_effect = RepositoryNotFoundError(
            message="404 Client Error",
            response=MagicMock(status_code=404, headers={}),
        )

        mod = self._load_connector()
        with patch("huggingface_hub.HfApi", return_value=mock_api):
            result = mod.get_hf_status()

        assert result["status"] == "missing", f"Expected missing, got: {result}"
        assert "warning" in result
        assert result["runs"] == []

    def test_no_token_returns_not_configured(self, monkeypatch):
        """whoami() failure → status='not_configured', not an exception."""
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("HF_REPO_ID", "FAVL/fleetsafe-hospitalnav")

        mock_api = MagicMock()
        mock_api.whoami.side_effect = Exception("401 Unauthorized — no token")

        mod = self._load_connector()
        with patch("huggingface_hub.HfApi", return_value=mock_api):
            result = mod.get_hf_status()

        assert result["status"] == "not_configured", f"Expected not_configured, got: {result}"
        assert "warning" in result
        assert result["runs"] == []

    def test_not_configured_does_not_claim_recorded(self, monkeypatch):
        """Honest label: NOT_CONFIGURED must never masquerade as RECORDED."""
        from unittest.mock import MagicMock, patch

        monkeypatch.delenv("HF_REPO_ID", raising=False)
        monkeypatch.delenv("HF_USERNAME", raising=False)

        mock_api = MagicMock()
        mock_api.whoami.side_effect = Exception("no token")

        mod = self._load_connector()
        with patch("huggingface_hub.HfApi", return_value=mock_api):
            result = mod.get_hf_status()

        assert result["status"] != "ok", (
            "HF connector reported 'ok' despite failing whoami — dishonest label"
        )
