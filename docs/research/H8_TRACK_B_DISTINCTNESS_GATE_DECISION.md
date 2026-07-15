# H8 Track-B — Distinctness Gate Decision (REVIEWED METHODOLOGY)

**Status: reviewed methodology decision — no code change, no training.** This note records the
decision to adopt **Outcome A + E** for the Track-B goal-distinctness gate, on the basis of the
committed calibration evidence. It authorises **no** operational change yet: no threshold edit, no
metric switch in code, no drive-validation, no recording, no trajectory collection, no training, no
promotion, no push, no tag, no 20/5/10, no closed-loop Isaac testing. `CL_BOUND_XY` unchanged. The
synthetic fork remains `SYNTHETIC_DIAGNOSTIC_ONLY`.

- Evidence commit: `d5e5e25` — *Add Track-B distinctness calibration evidence*
  (`assets/experiments/hospital_h8_track_b_distinctness_calibration/`).
- Governing plan: `docs/research/H8_TRACK_B_DISTINCTNESS_METRIC_CALIBRATION_PLAN.md`.
- Prior boundary result: `assets/experiments/hospital_h8_track_b_synthetic_fork_validation_r4/synthetic_fork_r1_r4_methodology_note.md`.

> **Professor-safe framing.** The calibration study prevents a silent threshold change. It shows DINO
> is useful for real indoor scenes when calibrated, but the absolute 0.60 cutoff was too strict. For
> the synthetic symmetric fork, DINO is not a reliable hard gate because shared corridor perspective
> dominates the embedding. The honest decision is Outcome A + E: recalibrate DINO for real scenes, and
> use synthetic distinctness as advisory while relying on a task-level action-probe after render and
> drive validation.

## 1. Evidence basis

From the committed calibration study (25 labelled pairs — 9 SAME / 10 DISTINCT / 6 HARD_NEGATIVE —
built only from already-rendered, committed frames; metrics DINO ViT-S/16, CLIP ViT-B/16 (LAION-2B),
aHash, SSIM; policy-encoder deferred):

- **Real indoor DINO — SAME cosine 0.83–0.92** (range 0.8327–0.9175, n=2 hospital near/far pairs).
- **Real indoor DINO — DISTINCT cosine 0.26–0.68** (range 0.2552–0.6841, n=4 cross-zone hospital
  pairs).
- **Clean real-scene separation:** on real hospital pairs the SAME and DISTINCT ranges do **not**
  overlap (DISTINCT max 0.6841 < SAME min 0.8327); the observed clean separating threshold is
  **≈ 0.76** (0.7584).
- **The prior `DINO < 0.60` gate is too strict for real indoor scenes:** a genuinely-distinct real
  pair sits at **0.684 ≥ 0.60**, so the 0.60 cutoff would wrongly call it "not distinct".
- **The synthetic symmetric cross does not separate under DINO:** synthetic SAME 0.59–1.0 vs
  synthetic DISTINCT 0.62–0.80 — the ranges **overlap and even invert** (a genuinely-distinct N-vs-W
  pair scores *higher* / less-distinct than a same-branch near/far pair), because every arm of a
  symmetric 4-way cross shares the same corridor perspective/composition.
- **CLIP did not improve separation:** CLIP (LAION-2B ViT-B/16) SAME vs DISTINCT ranges overlap for
  **both** families (synthetic SAME mean ≈ DISTINCT mean; real SAME overlaps DISTINCT); CLIP separates
  SAME/DISTINCT *less* well than DINO here and does not rescue the gate.
- **The `DINO < 0.60` gate on this labelled set produced 7 false negatives and 1 false positive**
  (7 DISTINCT pairs missed — the six synthetic N/W/E/S cross pairs plus one real hospital pair at
  0.684; 1 SAME pair wrongly flagged distinct — a synthetic same-branch near/far view).

## 2. Outcome A — real-scene DINO recalibration

- For **real indoor render scans**, replace the arbitrary absolute `< 0.60` gate with a **calibrated
  DINO threshold around 0.76**, subject to documented **margin** and to **contact-sheet agreement** on
  the labelled pairs.
- This is a **methodology decision**, not a benchmark result. It fixes an ungrounded constant with a
  threshold derived from a labelled same-vs-distinct separation.
- The **exact operational threshold must be implemented in code only after review** — this note does
  not edit the gate. Until then the incumbent code is retained.

## 3. Outcome E — synthetic-fork advisory distinctness

- **Synthetic symmetric-cross DINO scores are advisory only.** Because the shared corridor
  perspective dominates the embedding on a symmetric cross, DINO cosine on the synthetic fork is not a
  trustworthy discriminator of branch identity.
- **Do not use DINO as a hard pass/fail gate for the synthetic fork.** A synthetic-fork DINO score
  above (or below) any threshold must not, by itself, pass or fail the scene.
- **Synthetic-fork progression must instead require all of:**
  - render-valid geometry (scene-load, render-validity),
  - depth openness,
  - visual / contact-sheet verification,
  - action-angle separation (≥ 30°; the N-vs-W branch pair is 90°),
  - drive validation,
  - recorded-mode validation,
  - leakage audit (a leakage-safe split needs a family of ≥ 6 disjoint junction instances; one cross
    is not enough),
  - task-level **action-probe** (does conditioning on goal A vs goal B change the decision-frame
    action?).

## 4. Why this is not moving the goalpost

- The threshold is changed **only after a labelled calibration study**, not to manufacture a pass.
- **False positives and false negatives were measured** against the incumbent 0.60 gate (7 FN, 1 FP)
  and are documented with contact sheets.
- **CLIP was checked** as an alternative metric and did not separate better; the decision does not
  cherry-pick a convenient metric.
- **Contact-sheet agreement is required** for any calibrated threshold — the human gate confirms the
  metric.
- **No training was started before the gate decision.** The gate is being made defensible first.

## 5. Claim boundary

- **No training authorization yet.**
- **No real-scene benchmark claim.**
- **No full goal-conditioned ImageNav claim.**
- **No SOTA.**
- **No promotion** — the incumbent is retained; `DIAGNOSTIC_ONLY_NOT_PROMOTED`.
- **No autonomy claim.**
- The synthetic fork remains **`SYNTHETIC_DIAGNOSTIC_ONLY`** — it never stands in for hospital or
  real-world performance.
- `CL_BOUND_XY` unchanged. This note authorises no threshold or metric change in code; those are
  implemented only under a later, separately-reviewed step.

## 6. Next gate

1. **Update the validation plan** to use this reviewed distinctness decision: real-scene DINO gated by
   the calibrated ≈0.76 threshold (with margin + contact-sheet agreement); synthetic-fork embedding
   distinctness treated as advisory.
2. **Re-assess the synthetic fork R4** under the advisory rule — i.e. embedding distinctness as
   advisory **plus** contact-sheet verification **plus** action-angle separation — instead of the hard
   `DINO < 0.60` gate that R1–R4 failed.
3. **If approved**, proceed later to **drive validation** of the synthetic fork.
4. **Do not start training** until drive validation, recorded-mode data, split/leakage audit, and
   action-probe readiness **all** pass and are reviewed.

## References

- Calibration report: `assets/experiments/hospital_h8_track_b_distinctness_calibration/distinctness_calibration_report.md`
- Distributions + separation-by-family: `.../distinctness_distribution_summary.json`
- FP/FN table: `.../distinctness_false_positive_negative_table.md`
- Per-pair results + manifest: `.../distinctness_metric_results.{csv,md}`, `.../distinctness_pair_manifest.json`
- Harness: `scripts/gnm/h8_track_b_distinctness_calibration.py`
