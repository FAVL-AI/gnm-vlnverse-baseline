# H7r diagnostic training report

**Status: DIAGNOSTIC_ONLY_NOT_PROMOTED.** One small fine-tune to test whether the raised-mount scene-gated hospital pilot can train at all. Not a promotion run.

## 1. Dataset
- data_root `datasets/isaac_hospital_h7r` — 8 raised-mount hospital episodes (train 4 / val 2 / test 2), real `hospital.usd`, camera +0.12 m level, occlusion removed (bottom-third black 0.0%).
- pre-training gate: PASS (only raised-mount recorded `/camera/image_raw`, scene-gate 8/8, leakage-clean episode+route disjoint, fixed goal `h2_weave_J`).
- samples: 704 train windows / 352 val windows.

## 2. Training config
- init: **weights-only** from `checkpoints/hospital_front_rgb_finetune/best.pt` (H1 incumbent); fresh optimizer/scheduler.
- seed 42; epochs max 50 (early-stopped at 12); batch 128; lr 1e-4; select on H7r val (lowest action loss).
- best val action loss: **0.051233**.
- candidate `checkpoints/h7r_hospital_pilot_finetune/best.pt` sha256 `6edf25bab959b56b…`.
- command: `WANDB_MODE=offline python scripts/gnm/04_train_gnm.py --cfg configs/gnm/gnm_h7r_hospital_pilot.yaml`.

## 3. Held-out evaluation (forced --data-root)
| metric | H1 incumbent | H7r candidate | Δ |
|---|---|---|---|
| SR | 0.000 | 1.000 | +1.000 |
| OSR | 1.000 | 1.000 | +0.000 |
| SPL | 0.000 | 0.908 | +0.908 |
| NE (m) | 15.43 | 2.54 | -12.88 |
| nDTW | 0.078 | 0.646 | +0.568 |

See `h7r_evaluation_matrix.md` (full matrix incl. sanity + OOD) and `h7r_per_family_failure_table.md`.

## 4. Contacts / collision
- collection contacts: 0/8. Offline eval CR structurally 0.0 (single-integrator, no physics) — reported N/A, not a claim.

## 5. DriftGuard
- improvement guard on H7r test: **PASS** (SR & SPL ≥ incumbent, NE ≤ incumbent+0.1 m).
- promotion **BLOCKED**: n_test=2 (below floor), fixed placeholder goal, single seed.

## 6. VerdictPlane
- verdict: **deny** (promotion denied — diagnostic scope).

## 7. Adjudication
- **DIAGNOSTIC_ONLY_NOT_PROMOTED**; incumbent RETAINED; candidate kept as diagnostic evidence (first hospital dataset candidate with a positive signal).

## 8. Caveats
- n_test=2, single seed; fixed placeholder goal image (imitation-fidelity, not goal-conditioning); OOD H4 shows hospital specialisation (SR 0, but NE improved). Directional, not statistical.
- **Visual-distribution caveat:** the H1 incumbent was trained on the EARLIER occluded-camera hospital data, so part of its held-out failure reflects the raised-camera visual shift, not navigation skill alone. The candidate ALSO beating the H6 procedural model (SR 1.0 vs 0.5) on the same raised-mount test is the cleaner evidence it learned route-relevant behaviour, not just a matching input distribution.