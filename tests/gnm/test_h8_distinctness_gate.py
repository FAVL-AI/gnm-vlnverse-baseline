"""tests/gnm/test_h8_distinctness_gate.py

Lightweight unit tests for the reviewed Track-B distinctness-gate rule (Outcome A + E) encoded in
scripts/gnm/h8_distinctness_gate.py. Pure-python (no torch/timm/isaac); runs no rendering, no
training, no drive-validation. Verifies the reviewed methodology:

  * SYNTHETIC_DIAGNOSTIC_ONLY: DINO is advisory only — a high cosine never hard-fails the scene.
  * real indoor: the calibrated ~0.76 threshold (+margin, +contact-sheet agreement) replaces the
    arbitrary <0.60; above-threshold fails, below-threshold with contact-sheet agreement passes,
    and the borderline / unconfirmed cases warn rather than auto-pass.
  * report blocks carry the correct advisory vs hard-gated wording and provenance.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.gnm.h8_distinctness_gate import (  # noqa: E402
    advisory_synthetic,
    classify_real_scene,
    distinctness_report_block,
    REAL_SCENE_DINO_THRESHOLD,
    REAL_SCENE_MARGIN,
    LEGACY_HARD_THRESHOLD_SUPERSEDED,
    DECISION_DOC,
)


def test_calibrated_constants():
    # Outcome A calibrated threshold ~0.76 supersedes the arbitrary 0.60; margin is positive.
    assert abs(REAL_SCENE_DINO_THRESHOLD - 0.76) < 1e-9
    assert LEGACY_HARD_THRESHOLD_SUPERSEDED == 0.60
    assert REAL_SCENE_MARGIN > 0.0
    assert REAL_SCENE_DINO_THRESHOLD > LEGACY_HARD_THRESHOLD_SUPERSEDED  # recalibrated UP, not down


def test_synthetic_dino_above_060_does_not_hard_fail():
    # Outcome E: synthetic DINO above the old 0.60 (even above 0.76) is advisory, never a fail.
    for cos in (0.62, 0.70, 0.703, 0.85):
        v = advisory_synthetic(cos)
        assert v["passed"] is None, f"synthetic cosine {cos} must not hard-fail (advisory only)"
        assert v["gate_mode"] == "advisory_only"
        assert v["advisory"] is True


def test_real_scene_above_calibrated_threshold_fails():
    # Above threshold+margin -> NOT_DISTINCT (fail). A real SAME pair (~0.85-0.92) lands here.
    for cos in (0.81, 0.85, 0.92):
        v = classify_real_scene(cos, contact_sheet_ok=True)
        assert v["verdict"] == "NOT_DISTINCT"
        assert v["passed"] is False


def test_real_scene_below_threshold_with_contact_sheet_passes():
    # Below threshold-margin AND contact-sheet agreement -> DISTINCT (pass). Real distinct pairs
    # (0.26-0.68) land here, including the 0.68 pair the old <0.60 gate wrongly missed.
    for cos in (0.26, 0.46, 0.68, 0.71):
        v = classify_real_scene(cos, contact_sheet_ok=True)
        assert v["verdict"] == "DISTINCT", f"cosine {cos} should pass with contact-sheet agreement"
        assert v["passed"] is True
    # The specific regression the calibration fixed: 0.68 was a false negative under <0.60.
    assert classify_real_scene(0.68, contact_sheet_ok=True)["passed"] is True


def test_real_scene_requires_contact_sheet_agreement():
    # Below threshold but WITHOUT confirmed contact-sheet agreement -> WARN, never an auto-pass.
    v = classify_real_scene(0.30, contact_sheet_ok=None)
    assert v["verdict"] == "WARN_REVIEW"
    assert v["passed"] is None
    assert classify_real_scene(0.30, contact_sheet_ok=False)["passed"] is None


def test_real_scene_margin_band_warns():
    # Inside the [threshold-margin, threshold+margin] band -> WARN (held for review), not a pass.
    v = classify_real_scene(REAL_SCENE_DINO_THRESHOLD, contact_sheet_ok=True)
    assert v["verdict"] == "WARN_REVIEW"
    assert v["passed"] is None


def test_report_block_wording():
    # Synthetic report must say ADVISORY (not gated); real report must say HARD-GATED (calibrated).
    syn = distinctness_report_block(advisory_synthetic(0.70))
    assert "ADVISORY (not gated)" in syn
    assert "SYNTHETIC_DIAGNOSTIC_ONLY" in syn

    real = distinctness_report_block(classify_real_scene(0.30, contact_sheet_ok=True))
    assert "HARD-GATED (calibrated)" in real
    assert "threshold used: 0.76" in real
    # provenance must trace to the reviewed decision doc in both.
    assert DECISION_DOC in syn
    assert DECISION_DOC in real


def test_indeterminate_when_no_cosine():
    v = classify_real_scene(None, contact_sheet_ok=True)
    assert v["verdict"] == "INDETERMINATE"
    assert v["passed"] is None


if __name__ == "__main__":  # allow running without pytest
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok: {fn.__name__}")
    print(f"ALL {len(fns)} distinctness-gate tests passed")
