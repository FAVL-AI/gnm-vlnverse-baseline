# H8 Imagery-Gap (Visual Distinctness) Report

**Scope: validation/analysis only.** No H8-S collection, no training, no promotion, no push, no tag, no 20/5/10, no closed-loop, **no `CL_BOUND_XY` change**, **H8-S design gate NOT re-run**. Held for review.

## The problem being closed
The recovery step gave a coordinate-clean, per-split-proven zone set, but the visual audit showed the three east test views (east_A/east_B/lookalike_test) are near-duplicates (0.89–0.96) — they collapse to one vending-machine view. Coordinate-clean ≠ image-clean; for ImageNav the goal images must be perceptually distinct or the goal signal is meaningless.

## What the drivable envelope actually contains (decisive finding)
The whole drivable in-envelope corridor is **one alcove** with **2 visually-distinct ends**, not many scenes:
- **vending end (east-facing, yaw 0):** vending machine + wheelchair + bench — shared by lobby (train), midwest_A/B (train/val), east_A/B + lookalike (test). The apparent 'distinctness' of midwest_B is **camera distance/scale**, not a different scene.
- **seating end (west-facing, yaw≈180):** wooden waiting-chairs + water cooler (searchW1/searchW2) — a genuinely different scene, found by the yaw-180 search.
So the envelope offers **two view-types of one alcove**, not the multiple distinct locations a strong held-out visual split needs (reception / waiting rooms remain sealed → `DEFERRED`).

## Visual-distinctness gate (defined)
- **method:** aHash 16x16 (crude); recommend a learned embedding (CLIP/DINO cosine) or SSIM for the recording-time final gate.
- **cross-split threshold:** a test goal vs any train/val goal must be **< 0.8** aHash similarity.
- **within-split threshold:** two decision frames in one split must be **< 0.85** (else they are duplicates → keep one).
- **failure action:** reject the frame as visual leakage; if two same-split frames exceed within-split, keep only one; if no split-distinct set survives, re-scope H8-S.
- **caveat:** aHash is crude for corridors (coarse luminance layout is similar even when content differs), so it FLAGS the semantically-distinct seating view too. A learned embedding is required to adjudicate content-level distinctness at recording time.

## Candidate distinct-test views (west-facing search)
| candidate | vs lobby(train) | vs east(test) | vs midwest_B(val) | passes aHash cross-split | note |
|---|---|---|---|---|---|
| searchW1 | 0.812 | 0.738 | 0.586 | False | seating end, same alcove |
| searchW2 | 0.777 | 0.727 | 0.551 | True | seating end, same alcove |

The seating view is **semantically distinct** (a human sees different furniture), but aHash vs lobby ≈0.78–0.81 **exceeds** the crude cross-split gate, and it is the **same physical alcove** (shared floor/ceiling, wheelchair visible in both). So it does **not** cleanly establish a strong held-out visual split.

## Decision (honest re-scope)
**LIMITED_CAUSAL_PILOT_DEFER_HELDOUT_TO_H8M.**
- No genuinely-different-location second test scene exists in the drivable ±6 m envelope; the only extra view is the seating end of the same alcove, which the automated gate cannot certify as cross-split-distinct.
- Therefore **do NOT force a strong held-out visual claim**. Re-scope H8-S as a **limited causal pilot**: keep **one** east/vending test frame (drop east_B + lookalike_test as duplicates), keep **midwest_B** as the val anchor, keep **lobby** for train; optionally use the **seating (west-facing)** view as a second, clearly-labelled *within-alcove* distinct frame — not as proof of held-out generalization.
- **lookalike_test is dropped/deferred**: its adversarial confuser (west_B) is safety-deferred and it duplicates east_B.
- **Defer the strong held-out visual split to H8-M**, which requires (a) extending the render-confirmed navigable map into the currently-sealed reception/waiting rooms (genuine distinct locations), and (b) an embedding-based distinctness gate.
- **H8-S design gate NOT re-run** here: coordinates qualify, but a strong held-out visual split does not, so re-running the coordinate-only gate would overstate readiness.

## Revised recommendation for H8-S
1. Re-author H8-S as a **limited causal pilot** (coordinate-clean per-split; train=lobby, val=midwest_B, test=one east frame [+ optional west-facing seating frame], labelled 'within-alcove, limited held-out').
2. Add the embedding-based distinctness gate to the recorded-mode acceptance before any recording.
3. Treat genuine multi-room held-out visual generalization as an **H8-M** objective, gated behind the sealed-room map extension.

## Claim boundary
Analysis over rendered `/camera/image_raw` views; aHash is a crude screen, not a final leakage verdict. No dataset recorded, no model trained, no promotion; `CL_BOUND_XY` unchanged; incumbent retained; status `DIAGNOSTIC_ONLY_NOT_PROMOTED`.

## Artifacts
`visual_gap/`: `h8_visual_gap_report.md`, `h8_visual_similarity_matrix.{csv,md}`, `h8_visual_gap_candidates.json`, `contact_sheets/{searchW1,searchW2}.png`, `routes/*.json`, `search_ledger.csv`, `_full_matrix.json`. Harness: `scripts/gnm/h8_visual_search.sh`, `scripts/gnm/h8_visual_gap_report.py`. Rosbags/trajectories NOT for commit.
