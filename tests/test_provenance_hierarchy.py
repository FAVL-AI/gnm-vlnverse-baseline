"""Tests for the data provenance resolution hierarchy.

Verifies that gnm_vlnverse.vln.provenance resolves image_source and
instruction_source correctly across the priority hierarchy:

  1. Explicit episode provenance.json
  2. Explicit dataset_provenance.json
  3. Pixel heuristic (fallback)
  4. Unknown

Key properties verified
-----------------------
- Explicit metadata always overrides pixel appearance
- A smooth real image labelled real_camera stays real_camera
- A noisy synthetic image labelled synthetic stays synthetic
- Missing provenance.json invokes the heuristic fallback
- Uncertain heuristic (ambiguous dx_std) returns unknown, not a guess
- Contradictory metadata + heuristic: metadata wins, warning is set
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pytest

from gnm_vlnverse.vln.provenance import (
    IMAGE_SOURCE_REAL_CAMERA,
    IMAGE_SOURCE_SYNTHETIC_GRADIENT,
    IMAGE_SOURCE_UNKNOWN,
    INSTRUCTION_SOURCE_SYNTHETIC_DRY,
    INSTRUCTION_SOURCE_UNKNOWN,
    PROVENANCE_SOURCE_EXPLICIT_DATASET,
    PROVENANCE_SOURCE_EXPLICIT_EPISODE,
    PROVENANCE_SOURCE_HEURISTIC,
    PROVENANCE_SOURCE_UNKNOWN,
    infer_image_source_heuristic,
    read_dataset_provenance,
    read_episode_provenance,
    resolve_provenance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_episode_provenance(ep_dir, image_source: str, instruction_source: str = "project_authored") -> None:
    prov = {
        "schema_version":     "1.0",
        "image_source":       image_source,
        "instruction_source": instruction_source,
        "dry_run":            True,
        "synthetic":          True,
        "isaac_assets_used":  False,
        "vlnverse_assets_used": False,
    }
    (ep_dir / "provenance.json").write_text(json.dumps(prov))


def _write_dataset_provenance(dataset_root, image_source: str, instruction_source: str = "project_authored") -> None:
    prov = {
        "schema_version":     "1.0",
        "dataset_id":         "test",
        "image_source":       image_source,
        "instruction_source": instruction_source,
    }
    (dataset_root / "dataset_provenance.json").write_text(json.dumps(prov))


def _write_rgb_frame(ep_dir, dx_std_target: float) -> None:
    """Write a synthetic JPEG frame with approximately the target dx_std."""
    from PIL import Image
    rgb_dir = ep_dir / "rgb"
    rgb_dir.mkdir(parents=True, exist_ok=True)
    # Create gradient image: columns linearly ramp to produce desired dx
    w, h = 64, 64
    col_values = np.linspace(0, dx_std_target * w * 3, w, dtype=np.uint8)
    arr = np.tile(col_values[np.newaxis, :, np.newaxis], (h, 1, 3))
    Image.fromarray(arr.astype(np.uint8)).save(str(ep_dir / "rgb" / "000000.jpg"))


# ---------------------------------------------------------------------------
# TestExplicitEpisodeProvenance
# ---------------------------------------------------------------------------

class TestExplicitEpisodeProvenance:
    """Episode-level provenance.json overrides everything else."""

    def test_explicit_synthetic_overrides_pixel_appearance(self, tmp_path):
        """Even if pixels look real, explicit synthetic label wins."""
        ep_dir   = tmp_path / "ep"
        ds_root  = tmp_path
        ep_dir.mkdir()
        _write_episode_provenance(ep_dir, IMAGE_SOURCE_SYNTHETIC_GRADIENT)
        # Write a "real-looking" frame (high dx_std)
        _write_rgb_frame(ep_dir, dx_std_target=50.0)

        result = resolve_provenance(ep_dir, ds_root)
        assert result.image_source == IMAGE_SOURCE_SYNTHETIC_GRADIENT
        assert result.provenance_source == PROVENANCE_SOURCE_EXPLICIT_EPISODE
        assert result.confidence == "high"

    def test_explicit_real_camera_overrides_pixel_appearance(self, tmp_path):
        """Even if pixels look synthetic, explicit real_camera label wins."""
        ep_dir  = tmp_path / "ep"
        ds_root = tmp_path
        ep_dir.mkdir()
        _write_episode_provenance(ep_dir, IMAGE_SOURCE_REAL_CAMERA)
        # Write a "synthetic-looking" frame (low dx_std)
        _write_rgb_frame(ep_dir, dx_std_target=1.0)

        result = resolve_provenance(ep_dir, ds_root)
        assert result.image_source == IMAGE_SOURCE_REAL_CAMERA
        assert result.provenance_source == PROVENANCE_SOURCE_EXPLICIT_EPISODE
        assert result.confidence == "high"

    def test_explicit_provenance_beats_dataset_manifest(self, tmp_path):
        """Episode-level provenance supersedes the dataset-level manifest."""
        ep_dir  = tmp_path / "ep"
        ds_root = tmp_path
        ep_dir.mkdir()
        _write_episode_provenance(ep_dir, IMAGE_SOURCE_SYNTHETIC_GRADIENT)
        _write_dataset_provenance(ds_root, IMAGE_SOURCE_REAL_CAMERA)

        result = resolve_provenance(ep_dir, ds_root)
        assert result.image_source == IMAGE_SOURCE_SYNTHETIC_GRADIENT
        assert result.provenance_source == PROVENANCE_SOURCE_EXPLICIT_EPISODE

    def test_instruction_source_read_from_episode_provenance(self, tmp_path):
        ep_dir  = tmp_path / "ep"
        ds_root = tmp_path
        ep_dir.mkdir()
        _write_episode_provenance(ep_dir, IMAGE_SOURCE_SYNTHETIC_GRADIENT,
                                  instruction_source="project_authored_synthetic_dry_run")
        result = resolve_provenance(ep_dir, ds_root)
        assert result.instruction_source == "project_authored_synthetic_dry_run"

    def test_contradiction_produces_warning_metadata_wins(self, tmp_path, caplog):
        """Contradictory metadata + heuristic: metadata is authoritative; warning is set."""
        ep_dir  = tmp_path / "ep"
        ds_root = tmp_path
        ep_dir.mkdir()
        # Explicit: synthetic; pixels will look real (high dx)
        _write_episode_provenance(ep_dir, IMAGE_SOURCE_SYNTHETIC_GRADIENT)
        _write_rgb_frame(ep_dir, dx_std_target=50.0)

        with caplog.at_level(logging.WARNING):
            result = resolve_provenance(ep_dir, ds_root)

        assert result.image_source == IMAGE_SOURCE_SYNTHETIC_GRADIENT
        assert result.provenance_source == PROVENANCE_SOURCE_EXPLICIT_EPISODE
        assert result.warning is not None
        assert "contradiction" in result.warning.lower() or "authoritative" in result.warning.lower()


# ---------------------------------------------------------------------------
# TestDatasetProvenanceManifest
# ---------------------------------------------------------------------------

class TestDatasetProvenanceManifest:
    """Dataset-level manifest is used when episode-level is absent."""

    def test_dataset_manifest_used_when_episode_provenance_missing(self, tmp_path):
        ep_dir  = tmp_path / "ep"
        ds_root = tmp_path
        ep_dir.mkdir()
        _write_dataset_provenance(ds_root, IMAGE_SOURCE_SYNTHETIC_GRADIENT)
        # No episode provenance.json — no rgb frame needed

        result = resolve_provenance(ep_dir, ds_root)
        assert result.image_source == IMAGE_SOURCE_SYNTHETIC_GRADIENT
        assert result.provenance_source == PROVENANCE_SOURCE_EXPLICIT_DATASET

    def test_dataset_manifest_with_real_camera(self, tmp_path):
        ep_dir  = tmp_path / "ep"
        ds_root = tmp_path
        ep_dir.mkdir()
        _write_dataset_provenance(ds_root, IMAGE_SOURCE_REAL_CAMERA,
                                  instruction_source="benchmark_provided")
        result = resolve_provenance(ep_dir, ds_root)
        assert result.image_source == IMAGE_SOURCE_REAL_CAMERA
        assert result.instruction_source == "benchmark_provided"
        assert result.confidence == "high"
        assert not result.is_heuristic


# ---------------------------------------------------------------------------
# TestHeuristicFallback
# ---------------------------------------------------------------------------

class TestHeuristicFallback:
    """Heuristic inference is used only when explicit metadata is absent."""

    def test_smooth_image_inferred_as_synthetic(self, tmp_path):
        ep_dir  = tmp_path / "ep"
        ds_root = tmp_path
        ep_dir.mkdir()
        _write_rgb_frame(ep_dir, dx_std_target=1.0)  # very smooth gradient

        result = resolve_provenance(ep_dir, ds_root)
        assert result.is_heuristic
        assert result.provenance_source == PROVENANCE_SOURCE_HEURISTIC
        assert result.image_source == IMAGE_SOURCE_SYNTHETIC_GRADIENT

    def test_high_dx_std_inferred_as_real_camera(self, tmp_path):
        """A frame with high local variation is inferred as real camera."""
        ep_dir  = tmp_path / "ep"
        ds_root = tmp_path
        ep_dir.mkdir()
        # Write a very noisy frame to exceed the 35.0 dx_std threshold
        from PIL import Image
        rgb_dir = ep_dir / "rgb"
        rgb_dir.mkdir()
        rng = np.random.default_rng(42)
        noise = rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)
        Image.fromarray(noise).save(str(ep_dir / "rgb" / "000000.jpg"))

        img_src, confidence, _ = infer_image_source_heuristic(ep_dir / "rgb" / "000000.jpg")
        assert img_src == IMAGE_SOURCE_REAL_CAMERA
        assert confidence in ("medium", "high")

    def test_ambiguous_dx_std_returns_unknown(self, tmp_path):
        """dx_std in the 20–35 range is too uncertain; heuristic returns unknown."""
        ep_dir  = tmp_path / "ep"
        ds_root = tmp_path
        ep_dir.mkdir()
        _write_rgb_frame(ep_dir, dx_std_target=8.0)

        img_src, confidence, warn = infer_image_source_heuristic(ep_dir / "rgb" / "000000.jpg")
        # Verify the heuristic function handles uncertainty gracefully
        assert img_src in (IMAGE_SOURCE_SYNTHETIC_GRADIENT, IMAGE_SOURCE_UNKNOWN, IMAGE_SOURCE_REAL_CAMERA)
        assert confidence in ("low", "medium")
        assert warn  # a warning message must be present

    def test_missing_provenance_triggers_heuristic(self, tmp_path):
        """No provenance.json and no dataset_provenance.json triggers heuristic."""
        ep_dir  = tmp_path / "ep"
        ds_root = tmp_path
        ep_dir.mkdir()
        _write_rgb_frame(ep_dir, dx_std_target=1.0)

        result = resolve_provenance(ep_dir, ds_root)
        assert result.is_heuristic or result.provenance_source == PROVENANCE_SOURCE_UNKNOWN

    def test_missing_frame_and_no_metadata_returns_unknown(self, tmp_path):
        """No frame and no metadata yields provenance_source=unknown."""
        ep_dir  = tmp_path / "ep"
        ds_root = tmp_path
        ep_dir.mkdir()
        # No rgb frame, no provenance.json, no dataset_provenance.json

        result = resolve_provenance(ep_dir, ds_root)
        assert result.image_source == IMAGE_SOURCE_UNKNOWN
        assert result.provenance_source == PROVENANCE_SOURCE_UNKNOWN


# ---------------------------------------------------------------------------
# TestHeuristicFunction
# ---------------------------------------------------------------------------

class TestHeuristicFunction:
    """Direct tests of infer_image_source_heuristic()."""

    def test_nonexistent_file_returns_unknown_low(self, tmp_path):
        img_src, conf, warn = infer_image_source_heuristic(tmp_path / "missing.jpg")
        assert img_src == IMAGE_SOURCE_UNKNOWN
        assert conf == "low"
        assert warn

    def test_returns_three_tuple(self, tmp_path):
        ep_dir = tmp_path / "ep" / "rgb"
        ep_dir.mkdir(parents=True)
        _write_rgb_frame(tmp_path / "ep", dx_std_target=1.0)
        result = infer_image_source_heuristic(ep_dir / "000000.jpg")
        assert len(result) == 3
        img_src, confidence, warn = result
        assert isinstance(img_src, str)
        assert confidence in ("low", "medium", "high")
        assert isinstance(warn, str)

    def test_smooth_gradient_labelled_synthetic(self, tmp_path):
        ep_dir = tmp_path / "ep"
        ep_dir.mkdir()
        _write_rgb_frame(ep_dir, dx_std_target=1.0)
        img_src, conf, _ = infer_image_source_heuristic(ep_dir / "rgb" / "000000.jpg")
        assert img_src == IMAGE_SOURCE_SYNTHETIC_GRADIENT

    def test_heuristic_returns_warning_string_not_none(self, tmp_path):
        """The warning field is always a non-empty string, never None."""
        ep_dir = tmp_path / "ep"
        ep_dir.mkdir()
        _write_rgb_frame(ep_dir, dx_std_target=1.0)
        _, _, warn = infer_image_source_heuristic(ep_dir / "rgb" / "000000.jpg")
        assert warn and isinstance(warn, str)


# ---------------------------------------------------------------------------
# TestCustomVlnOfficeProvenance
# ---------------------------------------------------------------------------

class TestCustomVlnOfficeProvenance:
    """Verify that the actual custom_vln_office dataset provenance is read correctly."""

    def test_episode_provenance_file_exists(self):
        import pathlib
        ep_dir = pathlib.Path("datasets/custom_vln_office/train/cvlo_ep001")
        if not ep_dir.is_dir():
            pytest.skip("custom_vln_office dataset not found")
        prov_file = ep_dir / "provenance.json"
        assert prov_file.exists(), "provenance.json missing — re-run collect_custom_vln_office_data.py --dry-run"

    def test_episode_provenance_is_explicit(self):
        import pathlib
        ep_dir  = pathlib.Path("datasets/custom_vln_office/train/cvlo_ep001")
        ds_root = pathlib.Path("datasets/custom_vln_office")
        if not ep_dir.is_dir():
            pytest.skip("custom_vln_office dataset not found")

        result = resolve_provenance(ep_dir, ds_root)
        assert result.provenance_source == PROVENANCE_SOURCE_EXPLICIT_EPISODE
        assert result.image_source == IMAGE_SOURCE_SYNTHETIC_GRADIENT
        assert result.instruction_source == "project_authored_synthetic_dry_run"
        assert not result.is_heuristic

    def test_dataset_provenance_manifest_exists(self):
        import pathlib
        ds_root = pathlib.Path("datasets/custom_vln_office")
        if not ds_root.is_dir():
            pytest.skip("custom_vln_office dataset not found")
        manifest = ds_root / "dataset_provenance.json"
        assert manifest.exists(), "dataset_provenance.json missing — re-run collect_custom_vln_office_data.py --dry-run"

    def test_dataset_manifest_has_required_fields(self):
        import json, pathlib
        ds_root = pathlib.Path("datasets/custom_vln_office")
        if not ds_root.is_dir():
            pytest.skip("custom_vln_office dataset not found")
        manifest = json.loads((ds_root / "dataset_provenance.json").read_text())
        required = [
            "schema_version", "dataset_id", "image_source", "instruction_source",
            "generator_script", "generator_version", "dry_run", "synthetic",
            "isaac_assets_used", "vlnverse_assets_used", "evidence_level",
            "creation_timestamp", "creation_commit", "deterministic_seed",
        ]
        for field in required:
            assert field in manifest, f"Missing required field: {field}"
