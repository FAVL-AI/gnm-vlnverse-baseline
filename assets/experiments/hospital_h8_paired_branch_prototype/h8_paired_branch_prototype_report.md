# H8 Paired-Branch Design Prototype — Build-Time Acceptance Report

**Scope: design validation only.** No model training, no collection of a large dataset, no autonomous claim, no benchmark claim, no promotion, no push, no tag, no 20/5/10, no closed-loop Isaac testing. This report proves — from the design labels alone, before any frames are recorded — that the H8 paired-branch design makes the goal image **necessary**.

**Result: PASS** — 2 designs, action-angle margin ≥ 30°.

## Why this gate exists
H7r was route/motion-imitation dominated: the goal image was not causal. Before collecting or training H8 we must prove the *dataset design itself* forces the policy to read the goal. At a shared decision frame `o_d`, two distinct goals must require two different robot-frame actions `[Δx, Δy]`; a goal-blind policy (a function of `o_d` only) then cannot be correct on both branches.

## Route pair summary

| design | family | decision frame (x,y,yaw°) | goal A | action A [Δx,Δy] | goal B | action B [Δx,Δy] | Δangle (°) | pass |
|---|---|---|---|---|---|---|---|---|
| h8_proto_01_corridor_tjunction | shared_corridor_branch_choice | (4.0,0.0,0) | A:left @(4.5,5.0) | [0.100,0.995] | B:right @(4.5,-5.0) | [0.100,-0.995] | 168.58 | ✅ |
| h8_proto_02_samestart_fork | same_start_different_goal | (3.0,0.0,0) | A:forward_left_doorway @(8.0,3.0) | [0.858,0.514] | B:forward_right_doorway @(8.0,-3.0) | [0.858,-0.514] | 61.93 | ✅ |

### h8_proto_01_corridor_tjunction (shared_corridor_branch_choice)
- **Start:** (0.0, 0.0, 0°); **decision frame o_d:** (4.0, 0.0, 0°) — shared by both goals.
- **Goal A (left):** pos (4.5, 5.0); planned image `goals_planned/design_01_goalA_left.png`; expected action `[0.100, 0.995]` (bearing 84.3°, range 5.03 m).
- **Goal B (right):** pos (4.5, -5.0); planned image `goals_planned/design_01_goalB_right.png`; expected action `[0.100, -0.995]` (bearing -84.3°, range 5.03 m).
- **Action-angle separation:** 168.58° (≥ 30° required); unit-action L2 diff 1.990; goal separation 10.00 m.
- **Goal-image distinctness:** design-time (visual DEFERRED to collection); design-time geometric proxy distinct = True (goal separation 10.00 m ≥ 1.5 m floor).
- **Checks:** 1_shared_decision_frame=PASS; 2_goals_distinct=PASS; 3_actions_differ=PASS; 4_angle_separation_ge_30deg=PASS; 5_not_route_solvable_without_goal=PASS
- **Design verdict:** PASS

### h8_proto_02_samestart_fork (same_start_different_goal)
- **Start:** (0.0, 0.0, 0°); **decision frame o_d:** (3.0, 0.0, 0°) — shared by both goals.
- **Goal A (forward_left_doorway):** pos (8.0, 3.0); planned image `goals_planned/design_02_goalA_left.png`; expected action `[0.858, 0.514]` (bearing 31.0°, range 5.83 m).
- **Goal B (forward_right_doorway):** pos (8.0, -3.0); planned image `goals_planned/design_02_goalB_right.png`; expected action `[0.858, -0.514]` (bearing -31.0°, range 5.83 m).
- **Action-angle separation:** 61.93° (≥ 30° required); unit-action L2 diff 1.029; goal separation 6.00 m.
- **Goal-image distinctness:** design-time (visual DEFERRED to collection); design-time geometric proxy distinct = True (goal separation 6.00 m ≥ 1.5 m floor).
- **Checks:** 1_shared_decision_frame=PASS; 2_goals_distinct=PASS; 3_actions_differ=PASS; 4_angle_separation_ge_30deg=PASS; 5_not_route_solvable_without_goal=PASS
- **Design verdict:** PASS

## Interpretation
Both prototype designs pair one shared decision frame with two distinct goals whose correct robot-frame actions are separated well beyond the 30° margin (one wide T-junction, one moderate fork). Therefore no goal-blind policy can solve both branches: the design makes the goal image causally necessary at the decision point. This is the property H7r lacked.

## Claim boundary
- **This is design validation only** — it proves the *labels/geometry* require the goal image; it does **not** train, evaluate, or run any model.
- **No autonomous claim, no benchmark claim, no promotion.** Incumbent retained.
- **Visual distinctness of the actual goal images is DEFERRED** to collection: the design-time proxy is geometric goal separation; the recorded `goal.png` frames must be re-checked with the same script (recorded mode) once captured.
- Passing this prototype authorises **only** the next step: collect the small 2×2 paired-branch frames (shared `o_d`, two scene-aligned goal images, raised mount, scene gate) and run the first offline Option-A action probe. It does **not** authorise 20/5/10, training, or closed-loop Isaac testing.

## Artifacts
`assets/experiments/hospital_h8_paired_branch_prototype/`: `design_01_corridor_tjunction.json`, `design_02_samestart_fork.json`, `h8_paired_branch_acceptance_results.json`, this report. Harness: `scripts/gnm/h8_paired_branch_acceptance.py`.
