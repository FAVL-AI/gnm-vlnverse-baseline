# H8 Map-Extension — Drive-Validation Report

**Scope: validation only.** No H8-S collection, no training, no promotion, no push, no tag, no 20/5/10, no closed-loop beyond these bounded per-zone drives. 6 in-envelope zones, **1 pass each**; the safety watchdog `CL_BOUND_XY` was **not** changed. Held for review.

**Verdict: map extension NOT YET SUFFICIENT for a leakage-clean H8-S redesign.**
4 of 8 candidate zones are `PROVEN_FOR_ROUTE_DESIGN`; proven-by-split = {'train': ['lobby'], 'val': [], 'test': ['east_A', 'east_B', 'lookalike_test']}.

## Frame correction (documented)
- Navmap read-offset **`(2.956, -6.240)`** (measured; 100% of 65,440 recorded points) is for **reading the navmap only**. *(Note: this differs from a `(1.762, -6.240)` value quoted in the task instruction; the committed frame-fit and the live spawn log both give 2.956, so the measured value is used here.)*
- The robot runtime frame ≈ isaac-world / default-spawn; **candidate bringup coords are already isaac-world** and are used directly as `--spawn-pose`.
- Applying the offset at spawn was the first-trial error (spawned at world (2.96,−6.24), |y|>6 → estop). Corrected direct spawn at east_A (1.4,0.1) passed.

## Safety boundary (documented, unchanged)
- `CL_BOUND_XY = 6.0` is a hardcoded safety watchdog on absolute isaac-world position; poses with `|x| > 6` estop immediately.
- **west_A, west_B, hard-neg far-west** are `DEFERRED_SAFETY_ENVELOPE_LIMITED` — deferred because they exceed the watchdog, **not** because the route design or drivability failed. The watchdog was **not** modified.

## Per-zone results (1 pass each)
| zone | split | family | env | collisions | cam_valid | lower-black | drive m | status |
|---|---|---|---|---|---|---|---|---|
| east_A | test | near_far_same_approach | in | 0 | True | 0.0% | 0.705 | **PROVEN_FOR_ROUTE_DESIGN** |
| east_B | test | stop_vs_go | in | 0 | True | 0.0% | 0.503 | **PROVEN_FOR_ROUTE_DESIGN** |
| lookalike_test | test | visually_similar_diff_location | in | 0 | True | 0.0% | 0.203 | **PROVEN_FOR_ROUTE_DESIGN** |
| lobby | train | corridor_t_junction | in | 0 | True | 0.0% | 1.702 | **PROVEN_FOR_ROUTE_DESIGN** |
| west_C | train | shared_corridor_branch | in | 7678 | False | 26.3% | 0.411 | **REJECTED_COLLISION** |
| val_A | val | near_far_same_approach | in | 25 | True | 0.0% | 0.495 | **NEEDS_RETRY** |
| west_A | train | near_far_same_approach | OUT | — | — | — | — | **DEFERRED_SAFETY_ENVELOPE_LIMITED** |
| west_B | train | stop_vs_go | OUT | — | — | — | — | **DEFERRED_SAFETY_ENVELOPE_LIMITED** |
| hardneg_farwest | hard-negative | any | OUT | — | — | — | — | **DEFERRED_SAFETY_ENVELOPE_LIMITED** |

**Key finding — geometric candidacy ≠ drivability.** `west_C` (far-west edge, x=−5.3) is navmap-free yet **7678 PhysX contacts + 26.3% black lower frame** (camera clipping into geometry): the robot is jammed. This is exactly the risk the claim boundary flagged — navmap freedom does not prove drivability. `val_A` (25 contacts) is borderline → `NEEDS_RETRY`.

## Zone-status state machine
```
PROVEN_FOR_ROUTE_DESIGN := PoseValid ∧ RenderValid ∧ CollisionFree(=0) ∧ SceneGate ∧ SplitSafe
NEEDS_RETRY             := 0 < collisions ≤ 50 (borderline; one retry advised)
REJECTED_COLLISION      := collisions > 50 (navmap-free but not drivable)
REJECTED_RENDER         := scene-gate fail OR camera invalid (black/exposure)
DEFERRED_SAFETY_ENVELOPE_LIMITED := |x| > CL_BOUND_XY (not run; not a failure)
```

## Split status (proven zones per split)
- **train:** ['lobby']  (west_C REJECTED_COLLISION → only lobby proven).
- **val:** NONE  (val_A NEEDS_RETRY → **no proven val zone yet**).
- **test:** ['east_A', 'east_B', 'lookalike_test']  (3 proven).

## Success-gate evaluation
- ≥6 of 8 zones pass: **False** (4 proven).
- val retains ≥1 proven zone: **False**.
- test retains ≥1 proven zone: **True**.
- train retains ≥1 proven zone: **True**.
- splits coordinate-disjoint: **True**.
- **→ map extension sufficient for H8-S: False**.

## Revised H8-S recommendation
**Do NOT re-author or record H8-S yet.** The proven set skews to TEST (east corridor: east_A, east_B, lookalike_test), with only **lobby** proven for train and **no proven val zone** (val_A borderline; west_C rejected). A leakage-clean H8-S needs ≥1 independently proven zone per split. Options for review, in order:
1. **Retry val_A** (borderline 25 contacts) — a clean retry recovers the val split.
2. **Add train + val candidates inside the ±6 m envelope** (e.g., additional mid-corridor x-bands between −5 and +1 not yet sampled) to replace west_C and thicken train/val.
3. Re-audit **within-test visual distinctness**: east_A/east_B/lookalike_test share the east vending-machine/wheelchair area and may look alike — confirm they are distinct enough to be separate decision frames (and note lookalike_test's intended west confuser is safety-deferred, so its adversarial pairing is currently unverified).
4. Only once each split has ≥1 proven, coordinate-disjoint zone, re-run the H8-S design gate; proceed to recording only if it reports `design_ready_to_record = YES`.

## Claim boundary
- Bounded per-zone spawn + short GNM-control drive; 1 pass each; collision = PhysX base_link contact count (ground truth); camera checks from recorded `/camera/image_raw`.
- Feasibility study, not statistical proof of navigability; no dataset recorded, no model trained, no promotion. Incumbent retained; status `DIAGNOSTIC_ONLY_NOT_PROMOTED`.

## Artifacts
`drive_validation/`: `validation_manifest.json`, `zone_validation_table.csv`, this report, `contact_sheets/*.png` (6), `render_metadata/*.json` (6), `routes/*.json`, `validation_ledger.csv`. Rosbags/trajectories under `assets/experiments/{rosbags,trajectories}/h8mx_val_*` (NOT for commit). Harness: `scripts/gnm/h8_map_extension_validate.sh`, `scripts/gnm/h8_map_extension_validation_report.py`.
