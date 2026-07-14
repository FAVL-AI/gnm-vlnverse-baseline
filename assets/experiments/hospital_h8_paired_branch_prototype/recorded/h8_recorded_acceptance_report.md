# H8 Paired-Branch RECORDED-Mode Acceptance Report

**Scope: recorded design-validation only.** No training, no promotion, no push, no tag, no 20/5/10, no closed-loop Isaac testing. This converts the H8 design proxy into **real recorded hospital.usd evidence**: for each design the shared decision frame `o_d` and both goal images come from actual `/camera/image_raw` recordings with the scene-identity gate PASS and the raised camera mount (+0.12 m).

**Result: PASS** — 2 designs, action-angle margin ≥ 30°, goal pixel-diff floor 12.

## Recorded acceptance matrix

| design | family | o_d match (m) | goalA↔goalB pixdiff | Δangle (°) | scene gate | cam raise | collisions A/B | pass |
|---|---|---|---|---|---|---|---|---|
| h8_proto_01_corridor_tjunction | shared_corridor_branch_choice | 0.295 | 43.6 | 71.83 | PASS | 0.12/0.12 | 0/0 | ✅ |
| h8_proto_02_samestart_fork | same_start_different_goal | 0.115 | 30.5 | 50.94 | PASS | 0.12/0.12 | 0/0 | ✅ |

### h8_proto_01_corridor_tjunction (shared_corridor_branch_choice)
- **Route A** `h8_d1_routeA_turn_up_20260714_154933` (branch turn_up_left), **Route B** `h8_d1_routeB_straight_20260714_183358` (branch straight); route_completed A/B = True/True; collisions A/B = 0/0.
- **Shared decision frame o_d:** design (0.2,-0.2) → recorded (-0.09,-0.21) yaw 0.00 rad, frame idx 46, match error 0.295 m; image `assets/experiments/hospital_h8_paired_branch_prototype/recorded/frames/h8_proto_01_corridor_tjunction_o_d.jpg`.
- **Goal A (turn_up_left):** recorded pos (0.14,0.51), expected action `[0.312,0.950]`, image `assets/experiments/hospital_h8_paired_branch_prototype/recorded/frames/h8_proto_01_corridor_tjunction_goalA_turn_up_left.jpg`.
- **Goal B (straight):** recorded pos (0.70,-0.21), expected action `[1.000,-0.000]`, image `assets/experiments/hospital_h8_paired_branch_prototype/recorded/frames/h8_proto_01_corridor_tjunction_goalB_straight.jpg`.
- **Action-angle separation (from recorded poses):** 71.83° (≥ 30° required); goalA↔goalB mean abs pixel diff 43.6 (≥ 12 required).
- **Checks:** 1_scene_gate_pass=PASS; 2_camera_mount_raise_0p12=PASS; 3_shared_decision_frame_exists=PASS; 4_real_goal_images_exist=PASS; 5_goalA_goalB_visually_distinct=PASS; 6_action_separation_ge_30deg=PASS; 7_not_route_solvable_without_goal=PASS
- **Design verdict:** PASS

### h8_proto_02_samestart_fork (same_start_different_goal)
- **Route A** `h8_d2_routeA_fwdleft_20260714_184624` (branch forward_left), **Route B** `h8_d2_routeB_fwdright_20260714_185908` (branch forward_right); route_completed A/B = True/True; collisions A/B = 0/0.
- **Shared decision frame o_d:** design (0.2,0.0) → recorded (0.16,0.11) yaw 0.47 rad, frame idx 60, match error 0.115 m; image `assets/experiments/hospital_h8_paired_branch_prototype/recorded/frames/h8_proto_02_samestart_fork_o_d.jpg`.
- **Goal A (forward_left):** recorded pos (0.76,0.43), expected action `[1.000,0.018]`, image `assets/experiments/hospital_h8_paired_branch_prototype/recorded/frames/h8_proto_02_samestart_fork_goalA_forward_left.jpg`.
- **Goal B (forward_right):** recorded pos (0.71,-0.13), expected action `[0.644,-0.765]`, image `assets/experiments/hospital_h8_paired_branch_prototype/recorded/frames/h8_proto_02_samestart_fork_goalB_forward_right.jpg`.
- **Action-angle separation (from recorded poses):** 50.94° (≥ 30° required); goalA↔goalB mean abs pixel diff 30.5 (≥ 12 required).
- **Checks:** 1_scene_gate_pass=PASS; 2_camera_mount_raise_0p12=PASS; 3_shared_decision_frame_exists=PASS; 4_real_goal_images_exist=PASS; 5_goalA_goalB_visually_distinct=PASS; 6_action_separation_ge_30deg=PASS; 7_not_route_solvable_without_goal=PASS
- **Design verdict:** PASS

## Decision

- **Recorded-mode acceptance PASSED on real hospital images.** The paired-branch property holds on actual recordings: identical shared `o_d`, two visually distinct recorded goals, action separation ≥ 30°, scene gate PASS, mount +0.12 m, zero collisions. **H8 is ready for the first offline action-probe** (Option A).
- **No training, no promotion, no autonomous or benchmark claim.** Incumbent retained.

## Claim boundary
- This validates that the paired-branch **design property survives on real recorded hospital images**; it does **not** train, evaluate, or run any model.
- Goal images are the final recorded `/camera/image_raw` frames (Track-A convention); o_d is the recorded frame nearest the shared decision pose.
- Passing authorises **only** the first offline Option-A action probe on these recorded frames — not 20/5/10, training, or closed-loop Isaac testing.

## Artifacts
`assets/experiments/hospital_h8_paired_branch_prototype/recorded/`: `h8_recorded_frame_manifest.json`, `h8_recorded_acceptance_results.json`, `h8_recorded_goal_contact_sheet.png`, this report, `frames/` (6 extracted frames). Harness: `scripts/gnm/h8_recorded_acceptance.py`.
