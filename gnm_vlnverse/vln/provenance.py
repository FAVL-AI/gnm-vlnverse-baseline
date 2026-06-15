"""Data provenance resolution for Track B language-grounding evaluation.

Priority hierarchy for determining image_source and instruction_source:

  1. Explicit episode provenance  — <ep_dir>/provenance.json
  2. Explicit dataset manifest    — <dataset_root>/dataset_provenance.json
  3. CLI override                 — caller-supplied string
  4. Heuristic inference          — pixel statistics on sample frame
  5. Unknown                      — returned when heuristic confidence is low

This module never treats pixel appearance as authoritative provenance.
The heuristic is a diagnostic fallback only; it logs a warning and marks
provenance_source as "heuristic_fallback".
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"

# Canonical image_source values
IMAGE_SOURCE_SYNTHETIC_GRADIENT   = "synthetic_gradient_dry_run"
IMAGE_SOURCE_REAL_CAMERA          = "real_camera"
IMAGE_SOURCE_UNKNOWN              = "unknown"

# Canonical instruction_source values
INSTRUCTION_SOURCE_BENCHMARK      = "benchmark_provided"
INSTRUCTION_SOURCE_UPSTREAM       = "upstream_repository_provided"
INSTRUCTION_SOURCE_PROJECT        = "project_authored"
INSTRUCTION_SOURCE_SYNTHETIC_DRY  = "project_authored_synthetic_dry_run"
INSTRUCTION_SOURCE_TEMPLATED      = "templated"
INSTRUCTION_SOURCE_SYNTHETIC      = "synthetic"
INSTRUCTION_SOURCE_UNKNOWN        = "unknown"

# How the provenance value was determined
PROVENANCE_SOURCE_EXPLICIT_EPISODE  = "explicit_metadata"
PROVENANCE_SOURCE_EXPLICIT_DATASET  = "explicit_dataset_manifest"
PROVENANCE_SOURCE_CLI               = "cli_override"
PROVENANCE_SOURCE_HEURISTIC         = "heuristic_fallback"
PROVENANCE_SOURCE_UNKNOWN           = "unknown"


@dataclass
class ProvenanceResult:
    """Resolved data provenance for one episode or dataset."""

    image_source:        str
    instruction_source:  str
    provenance_source:   str
    confidence:          str                  # "high" | "medium" | "low"
    warning:             Optional[str] = None
    raw_metadata:        dict = field(default_factory=dict)

    @property
    def is_heuristic(self) -> bool:
        return self.provenance_source == PROVENANCE_SOURCE_HEURISTIC


def _load_json(path: Path) -> dict | None:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as exc:
        logger.warning("Failed to read provenance file %s: %s", path, exc)
    return None


def read_episode_provenance(ep_dir: Path) -> dict | None:
    """Read explicit per-episode provenance from <ep_dir>/provenance.json."""
    return _load_json(Path(ep_dir) / "provenance.json")


def read_dataset_provenance(dataset_root: Path) -> dict | None:
    """Read dataset-level provenance manifest from <dataset_root>/dataset_provenance.json."""
    return _load_json(Path(dataset_root) / "dataset_provenance.json")


def infer_image_source_heuristic(sample_path: Path) -> tuple[str, str, str]:
    """Infer image_source from pixel statistics.  Diagnostic fallback only.

    Returns
    -------
    (image_source, confidence, warning)
        image_source : one of IMAGE_SOURCE_* constants or "unknown"
        confidence   : "medium" (synthetic with clear evidence) or "low" (uncertain)
        warning      : human-readable explanation
    """
    sample_path = Path(sample_path)
    if not sample_path.exists():
        return (
            IMAGE_SOURCE_UNKNOWN,
            "low",
            f"Sample frame not found: {sample_path}",
        )

    try:
        import cv2
        import numpy as np

        img = cv2.imread(str(sample_path))
        if img is None:
            return IMAGE_SOURCE_UNKNOWN, "low", f"cv2 could not read: {sample_path}"

        gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(float)
        dx_std = float(np.diff(gray, axis=1).std())

        if dx_std < 20.0:
            return (
                IMAGE_SOURCE_SYNTHETIC_GRADIENT,
                "medium",
                f"Heuristic: dx_std={dx_std:.2f} < 20.0 → synthetic gradient inferred. "
                "This is a fallback; prefer explicit provenance.json.",
            )
        if dx_std > 35.0:
            return (
                IMAGE_SOURCE_REAL_CAMERA,
                "medium",
                f"Heuristic: dx_std={dx_std:.2f} > 35.0 → real camera inferred. "
                "This is a fallback; prefer explicit provenance.json.",
            )
        # Ambiguous range 20–35: return unknown
        return (
            IMAGE_SOURCE_UNKNOWN,
            "low",
            f"Heuristic inconclusive: dx_std={dx_std:.2f} falls in ambiguous range "
            "(20.0–35.0). Could be smooth real image or noisy synthetic. "
            "Provide explicit provenance.json to resolve.",
        )
    except ImportError:
        return IMAGE_SOURCE_UNKNOWN, "low", "cv2 not available; cannot run heuristic"
    except Exception as exc:
        return IMAGE_SOURCE_UNKNOWN, "low", f"Heuristic error: {exc}"


def resolve_provenance(
    ep_dir: Path,
    dataset_root: Path,
    cli_image_source: str | None = None,
    cli_instruction_source: str | None = None,
) -> ProvenanceResult:
    """Resolve image_source and instruction_source using the priority hierarchy.

    Priority (highest to lowest):
      1. Episode-level provenance.json
      2. Dataset-level dataset_provenance.json
      3. CLI override values
      4. Pixel heuristic (fallback, with warning)
      5. Unknown

    Contradiction between metadata and heuristic: metadata wins; warning logged.
    """
    ep_dir       = Path(ep_dir)
    dataset_root = Path(dataset_root)

    # ── 1. Episode provenance ─────────────────────────────────────────────────
    ep_meta = read_episode_provenance(ep_dir)
    if ep_meta:
        img_src  = ep_meta.get("image_source", IMAGE_SOURCE_UNKNOWN)
        inst_src = ep_meta.get("instruction_source", INSTRUCTION_SOURCE_UNKNOWN)
        if img_src != IMAGE_SOURCE_UNKNOWN:
            # Cross-check heuristic to detect contradictions
            sample = ep_dir / "rgb" / "000000.jpg"
            if sample.exists():
                h_img, h_conf, h_warn = infer_image_source_heuristic(sample)
                if h_conf != "low" and h_img != img_src:
                    warning = (
                        f"Provenance contradiction: metadata says image_source={img_src!r}, "
                        f"heuristic infers {h_img!r} (dx_std heuristic). "
                        f"Using explicit metadata — it is authoritative."
                    )
                    logger.warning(warning)
                    return ProvenanceResult(
                        image_source=img_src,
                        instruction_source=inst_src,
                        provenance_source=PROVENANCE_SOURCE_EXPLICIT_EPISODE,
                        confidence="high",
                        warning=warning,
                        raw_metadata=ep_meta,
                    )
            return ProvenanceResult(
                image_source=img_src,
                instruction_source=inst_src,
                provenance_source=PROVENANCE_SOURCE_EXPLICIT_EPISODE,
                confidence="high",
                raw_metadata=ep_meta,
            )

    # ── 2. Dataset manifest ───────────────────────────────────────────────────
    ds_meta = read_dataset_provenance(dataset_root)
    if ds_meta:
        img_src  = ds_meta.get("image_source", IMAGE_SOURCE_UNKNOWN)
        inst_src = ds_meta.get("instruction_source", INSTRUCTION_SOURCE_UNKNOWN)
        if img_src != IMAGE_SOURCE_UNKNOWN:
            return ProvenanceResult(
                image_source=img_src,
                instruction_source=inst_src,
                provenance_source=PROVENANCE_SOURCE_EXPLICIT_DATASET,
                confidence="high",
                raw_metadata=ds_meta,
            )

    # ── 3. CLI override ───────────────────────────────────────────────────────
    if cli_image_source is not None:
        return ProvenanceResult(
            image_source=cli_image_source,
            instruction_source=cli_instruction_source or INSTRUCTION_SOURCE_UNKNOWN,
            provenance_source=PROVENANCE_SOURCE_CLI,
            confidence="high",
        )

    # ── 4. Pixel heuristic (fallback) ─────────────────────────────────────────
    sample = ep_dir / "rgb" / "000000.jpg"
    h_img, h_conf, h_warn = infer_image_source_heuristic(sample)
    if h_conf != "low":
        logger.warning(
            "No explicit provenance for %s — using heuristic: %s", ep_dir.name, h_warn
        )
        return ProvenanceResult(
            image_source=h_img,
            instruction_source=INSTRUCTION_SOURCE_UNKNOWN,
            provenance_source=PROVENANCE_SOURCE_HEURISTIC,
            confidence=h_conf,
            warning=h_warn,
        )

    # ── 5. Unknown ────────────────────────────────────────────────────────────
    logger.warning("Provenance unknown for %s: %s", ep_dir.name, h_warn)
    return ProvenanceResult(
        image_source=IMAGE_SOURCE_UNKNOWN,
        instruction_source=INSTRUCTION_SOURCE_UNKNOWN,
        provenance_source=PROVENANCE_SOURCE_UNKNOWN,
        confidence="low",
        warning=h_warn or "No provenance source available",
    )
