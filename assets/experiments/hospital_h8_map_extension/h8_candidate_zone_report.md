# H8 Candidate-Zone Enumeration Report

**Scope: analysis only.** No Isaac, no recording, no training, no H8-S collection. Candidate zones are derived from the navmap free space via the recovered frame-fit (`h8_navmap_frame_fit_report.md`). Geometric freedom only -> non-proven zones are `NEEDS_DRIVE_VALIDATION` until render + drive validation (the next, review-gated sub-step).

**Reachable envelope (bringup):** x[-9.96, 3.99], y[-0.76, 1.09].  **Leakage-clean split bands:** YES (val/test/new-train goal x-bands disjoint).

## Claim boundary (what this establishes and what it does NOT)
> The navigation-map frame fit demonstrates that a larger corridor-aligned region is geometrically consistent with the recorded trajectory frame. It does **not** demonstrate that candidate poses are collision-free, camera-valid, spawnable, drivable, visually suitable, or reproducible in Isaac Sim.

The frame fit establishes **geometric candidacy, not navigability or visual suitability.** Consequently:
- The **proven lobby** (`x in [-2.31, 0.91]`) remains the **only previously proven region** — proven by recorded 0-collision driving, not by this analysis. Its `PROVEN` label means exactly that: previously driven collision-free; nothing more is claimed for it here.
- The **eight new regions are candidates only** (`NEEDS_DRIVE_VALIDATION`); they must not be called proven, reachable, safe, spawnable, or dataset-ready until they pass the Isaac render-and-drive validation gate.
- **Side-room and branching-route families remain DEFERRED** — the scene provides no verified drivable side branch or room access in the robot slab.
- **Split cleanliness currently applies to COORDINATES only**, not yet to final rendered imagery or route trajectories; goal-image / trajectory leakage is re-audited after rendering.

## Candidate zones
| candidate_id | kind | family | split | x-range (bringup) | width m | risk | status |
|---|---|---|---|---|---|---|---|
| h8mx_west_A | corridor_continuation | near_far_same_approach | train | [-8.5, -7.0] | 1.85 | low | NEEDS_DRIVE_VALIDATION |
| h8mx_west_B | corridor_continuation | stop_vs_go | train | [-6.8, -5.5] | 1.85 | low | NEEDS_DRIVE_VALIDATION |
| h8mx_west_C | corridor_continuation | shared_corridor_branch | train | [-5.3, -4.0] | 1.85 | low | NEEDS_DRIVE_VALIDATION |
| h8mx_val_A | corridor_continuation | near_far_same_approach | val | [-3.8, -3.0] | 1.85 | low | NEEDS_DRIVE_VALIDATION |
| h8mx_lobby_proven | proven_lobby | corridor_t_junction | train | [-2.31, 0.91] | 1.85 | low | PROVEN |
| h8mx_east_A | corridor_continuation | near_far_same_approach | test | [1.4, 2.4] | 1.85 | low | NEEDS_DRIVE_VALIDATION |
| h8mx_east_B | corridor_continuation | stop_vs_go | test | [2.6, 3.5] | 1.85 | low | NEEDS_DRIVE_VALIDATION |
| h8mx_lookalike_test | visually_similar_diff_location | visually_similar_diff_location | test | [3.0, 3.5] | 1.85 | low | NEEDS_DRIVE_VALIDATION |
| h8mx_hardneg_farwest | hard_negative | any | hard-negative | [-9.9, -9.0] | 1.85 | low | NEEDS_DRIVE_VALIDATION |
| h8mx_side_corridor | deferred_room | side_corridor | none | — | — | — | DEFERRED |
| h8mx_reception_room | deferred_room | reception_side_room | none | — | — | — | DEFERRED |
| h8mx_waiting_elevator_bin | deferred_room | waiting_elevator_bin | none | — | — | — | DEFERRED |
| h8mx_same_room_object | deferred_room | same_room_diff_object | none | — | — | — | DEFERRED |

## Split assignment (leakage-clean by construction)
Correct-goal x-bands are disjoint across splits so no goal coordinate is reused (the exact failure that flagged H8-S): **train** = west corridor `x in [-8.5, -4.0]` + proven lobby `x in [-2.31, 0.91]`; **val** = `x in [-3.8, -3.0]`; **test** = east corridor `x in [1.4, 3.5]`. Hard-negative (wrong) goals sit at the far-west end `x in [-9.9, -9.0]`, disjoint from every correct-goal band. The look-alike test goal sits in the east band; its visual confuser is a west train zone -> only appearance is shared, coordinates are disjoint (render-confirm the similarity).

## Feasible families here
- **Along-corridor stop-conditioning** (near/far, stop-vs-go): abundant distinct x-locations -> easy to make leakage-clean. Primary yield of this extension.
- **Short-baseline action-branch** (shared-corridor branch, T/fork like DF01/DF02): feasible within the ~1.85 m corridor width (~0.9 m lateral gives >=30 deg over ~1 m).
- **Visually-similar-different-location**: two similar corridor stretches at distinct x (adversarial); needs render confirmation of look-alike goal images.
- **Hard-negative goals**: far corridor ends as wrong goals for the mismatched-goal gate.

## Deferred (honest limitation — no reachable geometry)
Reception-hall, waiting/elevator/bin, generic side-corridor, and same-room-different-object families are **DEFERRED**: even uninflated, no rooms/side-branches are reachable from spawn in the robot slab. Realising them needs a drivable doorway (none in slab) or a different scene/asset — out of scope for this corridor extension.

## Next sub-step (review-gated; NOT run here)
Render + drive validation of the `NEEDS_DRIVE_VALIDATION` zones: per zone run the scene gate, raised mount 0.12, export a real `/camera/image_raw` contact sheet, verify hospital context + no black lower-frame occlusion, then a 0-collision drive. Only zones passing all checks graduate to `PROVEN` and feed a re-authored H8-S design gate that must report `design_ready_to_record = YES` before any recording.

## Artifacts
`assets/experiments/hospital_h8_map_extension/`: `h8_navmap_frame_fit_report.md`, `h8_candidate_zones.json`, `h8_candidate_zone_table.csv`, this report, `h8_navmap_overlay.png` (navmap with proven lobby + reachable envelope + candidate zones; **a map figure, not a camera contact sheet** — camera contact sheets are deferred to the render-validation sub-step). Harness: `scripts/gnm/h8_map_extension_enumerate.py`.
