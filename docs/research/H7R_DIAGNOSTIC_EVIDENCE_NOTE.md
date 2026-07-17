# H7r Hospital Pilot — Diagnostic Evidence Note

**Audience:** supervisor / research review. **Status:** diagnostic milestone, *not* a
benchmark and *not* a promoted model. **Scope:** internal Isaac-Sim ImageNav only.

> **One line.** Corrected, scene-gated, raised-camera hospital data produces a
> measurable *stopping-reliability* signal: on the hospital held-out test the incumbent
> reaches the goal region but does not stop (OSR 1.00 / SR 0.00), while the H7r
> candidate reaches **and** stops (OSR 1.00 / SR 1.00). This is diagnostic evidence at
> n_test = 2, single seed, fixed placeholder goal — not a promotion.

Provenance (all local, unpushed): camera review `53720e7`, raised-mount pilot `3eca3fa`,
diagnostic training `ff71908`.

---

## 1. Why H7 was needed
- **H6 was a procedural-stage diagnostic only** — a scene-agnostic route-family stage
  (ground plane + fixed landmark cubes), useful for route-type coverage but **not** a
  real hospital scene. It cannot support any hospital-scene claim.
- **H7/H7r correct this** by recording in the **verified Isaac Sim 5.1 `hospital.usd`**
  (S3 asset, 1909 prims, RTX) behind a **fail-closed scene-identity gate** (asset
  referenced, prim count ≥ threshold, scene mode = hospital, no procedural landmark
  cubes, front RGB camera present). Static hospital renders are visual proof only;
  recorded rosbags are the training-grade data.

## 2. Why H7r was needed (over the first H7 pilot)
- The **first H7 pilot proved the hospital recording pipeline** (8/8 gated episodes, 0
  contacts) **but had a camera defect**: the lower ~third of every recorded frame was
  pure black (robot-body near-field occlusion) — a fixed **38.3 %** black band.
- A camera-view review compared three settings and selected a **physically plausible
  raised mount, +0.12 m**, applied as a local +Z translate on `camera_link/rgb_camera`
  with **rotation unchanged** (level horizon, same optical axis as prior sensors).
- **Result:** the raised mount **removed the occlusion** (bottom-third black
  38.3 % → **0.0 %**) while preserving the level horizon; the near-ground floor,
  corridor, and landmarks are now visible.

## 3. Dataset-quality evidence (H7r raised-mount pilot)
- **8/8 scene-gated hospital episodes** in real `hospital.usd`.
- **0 contacts**, 0 emergency stop, 0 XY-bound stop across all episodes.
- **Leakage-clean 4/2/2 split** (train 4 / val 2 / test 2), episode- and route-disjoint;
  families shared train↔eval **by design** (instance-disjoint a/b — the H6
  route-instance generalization protocol).
- Frames are the **actual recorded `/camera/image_raw` stream**, not re-renders.
- **No lower-frame occlusion** (bottom-third black 0.0 %); train/val/test preserved and
  firewalled (only raised-mount, gate-passing, contact-free episodes admitted).

## 4. Diagnostic training result (hospital held-out test, n = 2)
One small fine-tune: **weights-only init** from the retained H1 incumbent, **fresh
optimizer**, **seed 42**, checkpoint selected on the H7r validation split (best val
action loss 0.0512, early-stopped epoch 12). Both models evaluated on the **same**
hospital held-out test with **forced `--data-root`** (locked cross-corpus methodology).

| model | SR | OSR | SPL | NE (m) | nDTW |
|---|---|---|---|---|---|
| H1 incumbent | 0.00 | 1.00 | 0.00 | 15.43 | 0.08 |
| **H7r candidate** | **1.00** | **1.00** | **0.91** | **2.54** | **0.65** |
| H6 procedural (reference) | 0.50 | 1.00 | 0.50 | 3.62 | 0.55 |

Ranking on the hospital held-out: **candidate > H6 procedural > incumbent**. Per-route
family, the candidate succeeds on **both** held-out instances (turn + waiting) that the
incumbent fails — no per-family regression. Sanity splits fit (val SR 1.00 / NE 2.06 m;
train SR 1.00 / NE 2.17 m).

## 5. Metric interpretation (stopping reliability)
Definitions (from `gnm_vlnverse/evaluation/metrics.py`, Anderson et al. 2018), with the
enforced invariant **OSR ≥ SR**:
- **OSR** — did the robot *ever* pass within 3 m of the goal?
- **SR** — did it *finish and stop* within 3 m?

- Incumbent: **OSR 1.00, SR 0.00** → it **enters the goal region but does not stop
  correctly**.
- Candidate: **OSR 1.00, SR 1.00** → it **enters the goal region and stops**.
- This directly supports the **stopping-reliability hypothesis**: the corrected
  raised-camera hospital data teaches the goal-stopping behaviour the incumbent lacks on
  this scene. (SPL 0.91 < SR 1.00 only because one of the two routes took a
  slightly-longer-than-shortest path — internally consistent.)

## 6. Claim boundary (kept deliberately tight)
- **Diagnostic only** — not a final hospital benchmark, not a promoted model, not a
  SOTA claim.
- **n_test = 2**, **single seed**, **fixed placeholder goal image** (`h2_weave_J` reused
  across all episodes → this measures **imitation fidelity / stopping**, *not*
  goal-image conditioning).
- Out-of-domain (procedural H4) success stays 0 for both models — the candidate is
  **hospital-specialised**; there is **no catastrophic OOD break** (NE actually improves
  14.04 → 4.27 m).
- **Incumbent retained. No promotion. No push. No tag. No 20/5/10 expansion yet.**
- Honesty note: the incumbent was trained on the *earlier occluded-camera* data, so part
  of its held-out failure reflects the raised-camera visual shift; the candidate also
  beating the H6 procedural model on the same raised-mount test is the cleaner evidence
  that it learned route-relevant behaviour, not just a matching input distribution.

## 7. Next experiment (recommended order)
1. **Scene-aligned, non-placeholder goal-image check** — the fixed placeholder goal is
   the largest scientific caveat. Before scaling, verify the model is *not* simply
   exploiting route/motion patterns under weak goal conditioning: re-evaluate (and, if
   needed, re-record) with a goal image aligned to each route's true endpoint, and see
   whether the stopping signal survives.
2. **20/5/10 raised-mount collection with multi-seed training** — only if (1) holds;
   scale the dataset and repeat across seeds to turn the directional n = 2 signal into a
   statistical one before any promotion decision.

---
*Evidence artifacts:* `assets/experiments/hospital_h7_raise_collection/` (pilot +
`training/` reports: evaluation matrix, per-family failure table, metric audit,
candidate/incumbent cards, DriftGuard, VerdictPlane, adjudication, diagnostic summary).
Final verdict on record: **`DIAGNOSTIC_ONLY_NOT_PROMOTED`**.
