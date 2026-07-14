# H8-S Causal Route Design — Acceptance Report

**Scope: design only.** No collection, no training, no recording, no model. Validates the H8-S decision-frame design from labels/geometry before any recording, so no route is recorded that fails to force goal use (the H7r trap).

**Per-frame geometry gate: PASS** for all 8 active (non-deferred) decision frames; 2 deferred.
**Split-integrity audit: FLAGGED.** 
**Design ready to record as-is: NO** — every per-frame geometry gate passes, but the cross-split goal-image audit flags reused goal coordinates (see *Split-integrity finding* below); resolve before recording.

## Split-integrity finding (the pivotal H8-S result)
The design-mode gate proves each frame's **geometry** forces goal use, but the small proven-free lobby forces distinct decision frames to **reuse the same far-goal coordinates across splits**:
- goal coord `(1.0, -0.2)` used as a goal in splits ['test', 'train'] — goal-image leakage per design-doc §5.
- goal coord `(1.2, 0.0)` used as a goal in splits ['train', 'val'] — goal-image leakage per design-doc §5.
This is not a geometry error — it is the **feasibility constraint from `H8_CAUSAL_COLLECTION_DESIGN.md` §3 made concrete**: the proven-free lobby (≈ x∈[−2.6,1.2], y∈[−0.8,1.0]) does not contain enough *distinct* navigable goal locations to build a leakage-clean held-out goal-image split at H8-S scale. Two honest resolutions, both for review:
  1. **Scope H8-S as a train-only objective-generalization probe** (a few distinct decision frames, no held-out goal-image claim) and defer the held-out split to H8-M; or
  2. **Extend the render-confirmed navigable map first** (the H8-M prerequisite sub-task) to supply physically-distinct val/test goal locations, then re-run this gate.
**Recommended: Resolution 2 (map extension first).** Resolution 1 is rejected: a train-only H8-S would add only weak evidence on top of the committed 2×2 objective-viability result and would blur the claim boundary. The stronger, correctly-preserved finding is that the current proven-free lobby cannot support a leakage-clean H8-S held-out goal-image split; the fix is to extend the verified navigable map so val/test goals are physically distinct from train goals, then re-run this design gate.
The held-out action-probe (design-doc §10 gate 3) therefore **cannot be earned inside the current proven space** — it is blocked on the map extension, exactly as §3 predicted.

## Design principle & two gate types
Each shared decision frame `o_d` pairs with two goals. **Branch families** change the action DIRECTION → gated on action-angle separation ≥ 30°. **Stop families** (near/far, stop-vs-go) keep the same direction but change WHERE to stop → gated on goal-distance separation ≥ 0.6 m (a goal-blind policy cannot know the stop point).

## Decision frames

| route_id | family | gate | tier | split | separation | pass |
|---|---|---|---|---|---|---|
| h8s_df01_tjunction | corridor_t_junction | action_branch | PROVEN | train | 90.0° | ✅ |
| h8s_df02_fork | same_start_fork | action_branch | PROVEN | train | 50.9° | ✅ |
| h8s_df03_branch_corridor | shared_corridor_branch | action_branch | REQUIRES_VALIDATION | train | 45.0° | ✅ |
| h8s_df04_branch_wait | shared_corridor_branch | action_branch | REQUIRES_VALIDATION | test | 33.1° | ✅ |
| h8s_df05_nearfar_corridor | near_far_same_approach | stop_conditioning | PROVEN | train | Δstop 0.80 m | ✅ |
| h8s_df06_nearfar_reception | near_far_same_approach | stop_conditioning | PROVEN | val | Δstop 1.99 m | ✅ |
| h8s_df07_nearfar_waiting | near_far_same_approach | stop_conditioning | PROVEN | test | Δstop 1.61 m | ✅ |
| h8s_df08_stop_vs_go | stop_vs_go | stop_conditioning | REQUIRES_VALIDATION | train | Δstop 1.00 m | ✅ |
| h8s_df09_sameroom_object | same_room_diff_object | action_branch | DEFERRED | none | — | deferred |
| h8s_df10_visually_similar | visually_similar_diff_location | action_branch | DEFERRED | none | — | deferred |

## Split & leakage audit
- **Family coverage (7/7):** corridor_t_junction, near_far_same_approach, same_room_diff_object, same_start_fork, shared_corridor_branch, stop_vs_go, visually_similar_diff_location.
- **Leakage-group → split violations (must be empty):** NONE — every leakage group sits in one split.
- **Goal-image coord reuse across splits (design proxy; hash re-check at recording):** {'(1.0, -0.2)': ['test', 'train'], '(1.2, 0.0)': ['train', 'val']}.
- **Family-by-split:** {'train': {'corridor_t_junction': 1, 'same_start_fork': 1, 'shared_corridor_branch': 1, 'near_far_same_approach': 1, 'stop_vs_go': 1}, 'test': {'shared_corridor_branch': 1, 'near_far_same_approach': 1}, 'val': {'near_far_same_approach': 1}, 'none': {'same_room_diff_object': 1, 'visually_similar_diff_location': 1}}.
- **Note:** with only ~8 active frames the split is train-heavy and not family-balanced; H8-M must add decision frames per split to balance families and enlarge the held-out set.

## Feasibility (the H8 design-doc constraint, made concrete)
- **Tier counts:** {'PROVEN': 5, 'REQUIRES_VALIDATION': 3, 'DEFERRED': 2}.
- **PROVEN** — o_d, both goals, and both branch paths lie on coordinates already recorded 0-collision (H7 / H8-prototype). Recordable now without new map work: h8s_df01_tjunction, h8s_df02_fork, h8s_df05_nearfar_corridor, h8s_df06_nearfar_reception, h8s_df07_nearfar_waiting.
- **REQUIRES_VALIDATION** — o_d and goal endpoints are on confirmed coordinates but at least one branch path is not yet recorded; must be render/drive-validated before recording: h8s_df03_branch_corridor, h8s_df04_branch_wait, h8s_df08_stop_vs_go.
- **DEFERRED** — cannot be realised in the proven-free lobby without extending the render-confirmed navigable map (no confirmed multi-object room; look-alike goals need render validation): h8s_df09_sameroom_object, h8s_df10_visually_similar.
- **Consequence:** H8-S can record the PROVEN frames immediately; the REQUIRES_VALIDATION frames need a short render/drive check first; the DEFERRED families and any move toward H8-M require the map-extension sub-task flagged in `H8_CAUSAL_COLLECTION_DESIGN.md` §3.

## Claim boundary
- Design/geometry validation only — no images recorded, no model run. Visual distinctness of goal images and the goal-image hash leakage check are DEFERRED to the recorded-mode gate.
- No collection, training, promotion, push, tag, 20/5/10, or closed-loop authorised.

## Sequence (unchanged): design → design acceptance (this) → render/drive-validate REQUIRES_VALIDATION → record PROVEN(+validated) H8-S → recorded-mode gate → train ablation → held-out action-probe + mismatched-goal gate.

## Artifacts
`assets/experiments/hospital_h8_s_causal_routes/`: `h8_s_decision_frames.json` (design input), `h8_s_route_manifest.json` (enriched), `h8_s_design_acceptance_results.json`, this report. Harness: `scripts/gnm/h8_s_route_design_acceptance.py`.
