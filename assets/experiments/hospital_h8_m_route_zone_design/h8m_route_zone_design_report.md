# H8-M Step A — Route/Zone Design Report (DESIGN ONLY)

**Status: DESIGN ONLY.** No recording, no model, no benchmark claim, no autonomy claim, no promotion. No Isaac was run; no `CL_BOUND_XY` change. All coordinates are PROPOSED/hypothesized and every distinct-room zone is UNVALIDATED (render+drive gates are Steps B-C). Purpose: design the H8-M candidate set so H8-M does not become a larger H8-S.

## What H8-M must fix (from the H8-S diagnostic)
H8-S gave a clean negative: the objective produced partial goal response (branch-choice recovered) but failed readiness (S 0.30 < 0.5, weak distance scaling) and its collinear one-alcove geometry could not test angular branch-choice. H8-M therefore needs **distinct rooms, more decision frames, a true angular junction, and embedding-based distinctness** before any collection.

## Candidate zones
| zone | family | split | exp angle A/B (deg) | ang sep (deg) | true angular branch | feasibility | distinctness (est.) |
|---|---|---|---|---|---|---|---|
| h8m_recep_junction | branch_choice_t_junction | test | 49.2 / -49.2 | 98.4 | YES | NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION | high |
| h8m_recep_fork | shared_corridor_fork | test | 42.0 / -42.0 | 84.0 | YES | NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION | moderate |
| h8m_recep_desk_multiobj | same_room_different_object | train | 90.0 / 12.1 | 77.9 | no | NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION | moderate |
| h8m_side_corridor | same_start_different_goal | val | -0.0 / -76.0 | 76.0 | YES | NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION | moderate |
| h8m_waiting_seating | same_room_different_object | train | -0.0 / -31.0 | 31.0 | no | NEEDS_RENDER_VALIDATION | low |
| h8m_lobby_vending_nearfar | near_far_stop_conditioning | train | 0.0 / 0.0 | 0.0 | no | DRIVE_VALIDATED | low |
| h8m_east_vending_nearfar | near_far_stop_conditioning | val | 0.0 / 0.0 | 0.0 | no | DRIVE_VALIDATED | low |
| h8m_lookalike_confuser | visually_similar_distinct_location | hard_negative | 36.9 / -36.9 | 73.7 | no | NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION | low |
| h8m_hardneg_crossscene | hard_negative_mismatch | hard_negative | — | — | — | DESIGN_ONLY | n/a |

A **true angular branch** needs expected angular separation >= 30 deg. Zones flagged YES: h8m_recep_junction, h8m_recep_fork, h8m_side_corridor.

## True angular branch-divergence (the core H8-S fix)
`h8m_recep_junction` (test) is the PRIMARY angular family: goalA (left/north wing) and goalB (right/south wing) from a shared reception `o_d` give expected actions that diverge by 98.4 deg — a real left-vs-right branch, not near/far scaling. `h8m_recep_fork` is a second divergent candidate. **Both are UNVALIDATED**: whether a drivable junction exists within the +/-6 m envelope is the single biggest open risk (risk #1). **If Step-C render+drive validation finds no drivable junction within the +/-6 m envelope, H8-M must be re-scoped rather than presented as a stronger benchmark.** Near/far stop-conditioning (the two H8-S vending zones) is retained only as a SECONDARY axis.

## Visual distinctness planning
Primary gate = **CLIP/DINO embedding cosine** (Step B); aHash + SSIM are secondary/auditable only. Per-zone estimates (pending rendering): the reception/junction/side-corridor zones are estimated **moderate-high** distinctness (genuinely different rooms); the two vending zones and `waiting_seating` are **low** (same alcove as H8-S — flagged, must pass the cross-split embedding gate or be dropped/merged); `lookalike_confuser` is **low by design** (adversarial hard-negative only). Duplicate risks: `recep_fork` vs `recep_junction` (same junction), and the three alcove views among each other.

## Draft split
Target (H8-M acceptance): **train >= 12, val >= 4, test >= 6** distinct decision frames, no reused frame/goal-image/coordinate across splits, route-family balance, and >=1 true angular family in TEST.
- Draft by zone: train ['h8m_recep_desk_multiobj', 'h8m_waiting_seating', 'h8m_lobby_vending_nearfar'], val ['h8m_side_corridor', 'h8m_east_vending_nearfar'], test ['h8m_recep_junction', 'h8m_recep_fork'], hard-negative ['h8m_lookalike_confuser', 'h8m_hardneg_crossscene'].
- Coordinate integrity (no cross-split coordinate reuse): **OK**.
- TEST contains a true angular branch: **True**.

**Feasibility verdict: NOT_YET_FEASIBLE_AT_TARGET_SCALE.** Only the 2 H8-S alcove zones are drive-validated now, and both are collinear (secondary axis). Every distinct-room and angular-branch zone is unvalidated, and one decision frame was drafted per zone, so the current candidates yield far fewer than the target counts. Reaching the target requires (a) Step-C render+drive validation of >=3-4 genuinely distinct rooms incl. a true junction, and (b) authoring multiple decision frames per validated zone. **Per H8-M acceptance, collection must not proceed until the scale and the embedding gate are met.**

## Claim boundary
- **Design only** — no recording, no model, no training, no rollout.
- **No benchmark claim, no autonomy claim, no promotion**; incumbent retained; status `DIAGNOSTIC_ONLY_NOT_PROMOTED`.
- Coordinates are hypothesized design seeds to be corrected against the rendered scene; expected actions/angles are exact functions of those proposed coordinates only.
- `CL_BOUND_XY` unchanged; sealed-room access must use safe spawn-relocation + local validation, never a casual safety-bound change.

## Next (separate gated step, not authorised here)
Step B — embedding distinctness search on rendered candidate goal images (calibrate T_dup/T_cross); then Step C recorded-mode gate. No recording/training/closed-loop until reviewed.

## Artifacts
`assets/experiments/hospital_h8_m_route_zone_design/`: `h8m_zone_candidates.json`, `h8m_route_family_manifest.json`, `h8m_split_plan.json`, `h8m_design_risk_register.md`, `h8m_route_zone_design_report.md`. Harness: `scripts/gnm/h8m_route_zone_design.py`. No Isaac, no images, no checkpoints, no datasets.
