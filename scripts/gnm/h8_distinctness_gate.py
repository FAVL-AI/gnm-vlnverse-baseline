"""H8 Track-B — reviewed distinctness-gate rule (Outcome A + E). Single source of truth.

Encodes the reviewed methodology decision in
`docs/research/H8_TRACK_B_DISTINCTNESS_GATE_DECISION.md` (commit 53106f3), grounded in the labelled
calibration evidence under `assets/experiments/hospital_h8_track_b_distinctness_calibration/`
(commit d5e5e25) and the plan `docs/research/H8_TRACK_B_DISTINCTNESS_METRIC_CALIBRATION_PLAN.md`.

- **Real indoor scenes (Outcome A):** DINO cosine is the calibrated PRIMARY distinctness metric
  (unless later replaced by review). The arbitrary absolute `< 0.60` gate is replaced by a reviewed
  calibrated threshold ~0.76, requiring a MARGIN band and contact-sheet agreement. Not a benchmark
  claim.
- **`SYNTHETIC_DIAGNOSTIC_ONLY` scenes (Outcome E):** DINO cosine is ADVISORY ONLY — logged, never a
  hard pass/fail gate (a symmetric 4-way cross shares the same corridor perspective, so DINO does not
  separate same-from-distinct on it). Required synthetic gates: scene-load, render-validity,
  depth-openness, open-floor guard, visual/contact-sheet verification, action-angle separation.

This module executes NO metric and NO rendering — it only encodes the pass/advisory RULE and its
provenance. It has no heavy dependencies (no torch/timm/isaac), so it is importable and
unit-testable standalone. It authorises no training, no drive-validation, and no benchmark claim.
"""

# ── provenance ────────────────────────────────────────────────────────────────
DECISION_DOC = "docs/research/H8_TRACK_B_DISTINCTNESS_GATE_DECISION.md"
CALIBRATION_PLAN_DOC = "docs/research/H8_TRACK_B_DISTINCTNESS_METRIC_CALIBRATION_PLAN.md"
CALIBRATION_EVIDENCE_DIR = "assets/experiments/hospital_h8_track_b_distinctness_calibration/"
PROVENANCE = (
    f"Reviewed rule from {DECISION_DOC} (Outcome A + E), calibrated on the labelled evidence in "
    f"{CALIBRATION_EVIDENCE_DIR}; plan {CALIBRATION_PLAN_DOC}. Not benchmark evidence.")

# ── thresholds ────────────────────────────────────────────────────────────────
LEGACY_HARD_THRESHOLD_SUPERSEDED = 0.60   # old arbitrary absolute gate (real-scene) — SUPERSEDED
REAL_SCENE_DINO_THRESHOLD = 0.76          # Outcome A calibrated threshold (real indoor scenes)
REAL_SCENE_MARGIN = 0.04                  # required review band half-width around the threshold

SCENE_REAL = "real_indoor"
SCENE_SYNTHETIC = "SYNTHETIC_DIAGNOSTIC_ONLY"

CLAIM_BOUNDARY = (
    "methodology-consistent code only; not benchmark / real-scene / SOTA evidence; no promotion; "
    "no autonomy claim; no training authorization; no drive-validation authorized")


def classify_real_scene(dino, contact_sheet_ok=None,
                        threshold=REAL_SCENE_DINO_THRESHOLD, margin=REAL_SCENE_MARGIN):
    """Real-indoor distinctness verdict under Outcome A (calibrated hard gate + margin + contact sheet).

    Rule (lower DINO cosine = more distinct):
      * DISTINCT  (pass)  iff cosine <= threshold - margin AND contact-sheet agreement is confirmed.
      * NOT_DISTINCT (fail) iff cosine >= threshold + margin.
      * WARN_REVIEW (hold) otherwise — inside the [threshold-margin, threshold+margin] band, or below
        the band but without confirmed contact-sheet agreement. Never an automatic pass; deferred to
        the mandatory human contact-sheet check.

    Performs no rendering/embedding — `dino` is a precomputed cosine (or None). Returns a dict.
    """
    d = {"scene_type": SCENE_REAL, "gate_mode": "hard_gated_calibrated", "dino_cos": dino,
         "threshold": threshold, "margin": margin, "legacy_threshold_superseded": LEGACY_HARD_THRESHOLD_SUPERSEDED,
         "contact_sheet_ok": contact_sheet_ok, "provenance": PROVENANCE, "claim_boundary": CLAIM_BOUNDARY}
    if dino is None:
        d.update(verdict="INDETERMINATE", passed=None, reason="no DINO cosine available")
        return d
    lo, hi = round(threshold - margin, 6), round(threshold + margin, 6)
    if dino >= hi:
        d.update(verdict="NOT_DISTINCT", passed=False,
                 reason=f"DINO {dino} >= {hi} (threshold {threshold} + margin {margin})")
    elif dino <= lo and contact_sheet_ok:
        d.update(verdict="DISTINCT", passed=True,
                 reason=f"DINO {dino} <= {lo} (threshold {threshold} - margin {margin}) and contact-sheet agrees")
    else:
        why = "within review margin band" if dino > lo else "contact-sheet agreement not confirmed"
        d.update(verdict="WARN_REVIEW", passed=None,
                 reason=f"DINO {dino}: {why}; requires contact-sheet agreement before it passes (not auto-distinct)")
    return d


def advisory_synthetic(dino, threshold=REAL_SCENE_DINO_THRESHOLD):
    """SYNTHETIC_DIAGNOSTIC_ONLY advisory verdict under Outcome E: DINO is logged, NEVER gates.

    `passed` is always None — this is not a pass/fail gate. The reference threshold is reported for
    context only and does not fail the scene. Returns advisory info only; performs no metric.
    """
    note = (
        "ADVISORY ONLY for a symmetric cross — not a pass/fail gate. A symmetric 4-way cross shares "
        "the same corridor perspective, so DINO does not separate same-from-distinct on it. Required "
        "synthetic gates: scene-load, render-validity, depth-openness, open-floor guard, "
        "visual/contact-sheet verification, action-angle separation.")
    return {"scene_type": SCENE_SYNTHETIC, "gate_mode": "advisory_only", "dino_cos": dino,
            "reference_threshold": threshold, "passed": None, "advisory": True,
            "verdict": "ADVISORY", "note": note, "provenance": PROVENANCE, "claim_boundary": CLAIM_BOUNDARY}


def distinctness_report_block(verdict):
    """Uniform report lines for a validation report, from a classify_real_scene / advisory dict."""
    advisory = verdict.get("gate_mode") == "advisory_only"
    lines = [
        f"- scene type: {verdict.get('scene_type')}",
        f"- embedding distinctness: {'ADVISORY (not gated)' if advisory else 'HARD-GATED (calibrated)'}",
        f"- DINO cosine: {verdict.get('dino_cos')}",
    ]
    if advisory:
        lines.append(f"- reference threshold (not gated): {verdict.get('reference_threshold')}")
    else:
        lines.append(f"- threshold used: {verdict.get('threshold')} "
                     f"(margin {verdict.get('margin')}; supersedes legacy {LEGACY_HARD_THRESHOLD_SUPERSEDED})")
        lines.append(f"- contact-sheet verification: {verdict.get('contact_sheet_ok')}")
    lines.append(f"- distinctness verdict: {verdict.get('verdict')}")
    lines.append(f"- provenance: {verdict.get('provenance')}")
    lines.append(f"- claim boundary: {verdict.get('claim_boundary')}")
    return "\n".join(lines)
