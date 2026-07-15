# H8-S Limited Causal Pilot — Design-Gate Report

**Status: `LIMITED_CAUSAL_PILOT`.** Design gate only — no recording, no training, no promotion, no push, no tag, no 20/5/10, no closed-loop, no H8-M sealed-room validation, `CL_BOUND_XY` unchanged. Held for review.

**Gate: PASS** for the re-scoped 3-frame limited pilot.

## Not claimed (honest boundary)
This pilot is **NOT** a strong held-out visual benchmark, **NOT** multi-room / cross-location generalization, **NOT** full goal-conditioned ImageNav. All goal images are the same vending alcove at different scales; it tests only whether the objective makes behaviour respond to the goal on a small, real, coordinate-clean set.

## Split & decision frames (drive-validated coordinates)
| frame | split | zone | o_d | near→far goals | stop-sep m | in confirmed range |
|---|---|---|---|---|---|---|
| h8sl_train_lobby | train | lobby | [-1.0, -0.2] | [-0.4, -0.2]→[0.6, -0.2] | 1.0 | True |
| h8sl_val_midwestB | val | midwest_B | [-3.4, -0.2] | [-3.0, -0.2]→[-2.4, -0.2] | 0.6 | True |
| h8sl_test_eastA | test | east_A | [1.4, 0.1] | [1.7, 0.1]→[2.1, 0.1] | 0.4 ⚠<min | True |

Coordinate bands (disjoint): {'train': [-1.0, 0.6], 'val': [-3.4, -2.4], 'test': [1.4, 2.1]}.
**Note:** frames below stop_min (0.6 m): ['h8sl_test_eastA'] — the east test frame's confirmed drivable range is short (1.4–2.11 m), so its near/far stop separation is modest; acceptable for a LIMITED pilot, flagged, not a strong benchmark.

## Coordinate cleanliness
- coordinate split clean: **True**.
- no reused goal coordinates across splits: **True** (reused: none).
- x-bands disjoint: **True** (overlaps: none).

## Visual distinctness (for a LIMITED pilot, not a benchmark)
- classification: **LIMITED_PILOT_ONLY** — max cross-split aHash **0.863** (strong-held-out would need ≤ 0.6).
- cross-split pairs: train~val=0.641, train~test=0.863, val~test=0.566.
- All goals are the same alcove at different scales, so the gate certifies visual distinctness **only as adequate for a limited pilot**; a strong held-out visual split requires the embedding gate + sealed-room extension (H8-M).

## Honest-label & scope checks
- labelled LIMITED_CAUSAL_PILOT: **True**.
- no strong-held-out / multi-room / full-ImageNav claim: **True**.
- `CL_BOUND_XY` unchanged: **True**.

## Planned metrics & diagnostics
- metrics: TL, NE, SR, OSR, SPL, nDTW, CR (planned: **True**).
- diagnostics: offline action-probe, goal-sensitivity score S, mismatched-goal ablation, visual distinctness audit (aHash now, embedding at H8-M), route+decision-frame+goal-image leakage audit (planned: **True**).

## Dropped / deferred
- **east_B**: duplicate of east_A (aHash 0.93)
- **lookalike_test**: duplicate of east_B (0.96) + confuser west_B safety-deferred
- **seating_west_facing**: supplemental within-alcove analysis only, not held-out proof
- **far_west(west_A,west_B,hardneg)**: DEFERRED_SAFETY_ENVELOPE_LIMITED (|x|>6)
- **val_A**: REJECTED_COLLISION (25 contacts x2)
- **west_C**: REJECTED_COLLISION (7678)

## Decision
**Design gate PASSES for the limited pilot.** Coordinates are clean and disjoint, no goal-coordinate reuse, visual distinctness is honestly classified as LIMITED-only, and the design is labelled and scoped as a limited causal pilot. Recording is **not** authorised here — a recorded-mode gate + the standard diagnostics come next, on review.
- Strong held-out visual generalization remains an **H8-M** objective (`H8_M_SEALED_ROOM_MAP_EXTENSION_PLAN.md`).

## Artifacts
`assets/experiments/hospital_h8_s_limited_pilot/`: `h8sl_decision_frames.json` (design input), `h8sl_design_manifest.json`, `h8sl_acceptance_results.json`, this report. Harness: `scripts/gnm/h8_s_limited_design_gate.py`.
