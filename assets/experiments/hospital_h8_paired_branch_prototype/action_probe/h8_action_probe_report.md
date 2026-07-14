# H8 Offline Option-A Action-Probe Report

**Scope: offline probe only.** No training, no promotion, no push, no tag, no 20/5/10, no closed-loop Isaac testing, no change to committed H8 evidence. Uses only the committed H8 recorded paired-branch frames and the two existing checkpoints (H1 incumbent, H7r diagnostic candidate).

## Question
Same recorded shared decision frame `o_d` + different goal image → does the model's predicted 2-D action `[Δx, Δy]` change toward the correct branch? A goal-conditioned policy changes its action; a route/motion-imitation policy predicts ~the same action regardless of the goal image.

## Verdict per model
- **H1_incumbent:** branch-choice 0.50, goal-sensitivity S 0.009, mean pred action change A→B 0.53°, mean angle error 31.7° → **goal_image_insensitive_route_motion_dominated**
- **H7r_candidate:** branch-choice 0.50, goal-sensitivity S 0.024, mean pred action change A→B 1.50°, mean angle error 39.5° → **goal_image_insensitive_route_motion_dominated**

Pass thresholds for goal-conditioning: branch-choice ≥ 0.75, S ≥ 0.5, mean pred action change ≥ 15°.

## Per-design detail
### H1_incumbent
- **h8_proto_01_corridor_tjunction** (exp separation 71.8°): pred goalA `[0.089,-0.004]` (-3°) vs goalB `[0.091,-0.003]` (-2°); pred change A→B 0.53°, S 0.007, displacement shift 0.0019, stop-output change 0.0137; branch-choice A/B = False/True.
- **h8_proto_02_samestart_fork** (exp separation 50.9°): pred goalA `[0.086,-0.006]` (-4°) vs goalB `[0.088,-0.007]` (-4°); pred change A→B 0.53°, S 0.010, displacement shift 0.0021, stop-output change 0.0526; branch-choice A/B = True/False.

### H7r_candidate
- **h8_proto_01_corridor_tjunction** (exp separation 71.8°): pred goalA `[0.016,-0.004]` (-16°) vs goalB `[0.016,-0.005]` (-18°); pred change A→B 1.75°, S 0.024, displacement shift 0.0010, stop-output change 0.0289; branch-choice A/B = False/True.
- **h8_proto_02_samestart_fork** (exp separation 50.9°): pred goalA `[0.013,-0.003]` (-14°) vs goalB `[0.014,-0.003]` (-13°); pred change A→B 1.25°, S 0.025, displacement shift 0.0012, stop-output change 0.0444; branch-choice A/B = True/False.

## Interpretation & decision

- **Both models are goal-image-INSENSITIVE at the shared decision frame.** The predicted `[Δx, Δy]` changes by ≤ 2° between goal A and goal B for both models (incumbent 0.53°, candidate 1.50°), and branch-choice is at chance (0.50). Same RGB decision frame + different goal image ⇒ effectively the same action.
- **The H8 dataset design is correct** — it passed both the design-mode and recorded-mode gates (same observation provably requires different goal-dependent actions, separation ≥ 30°). **But neither existing model uses the goal image causally.**
- Per the pre-registered rule: *H7r candidate fails the probe while the design labels pass ⇒ the problem is the model/training, not the dataset design.* The incumbent behaves the same way.
- **This confirms the next training problem:** the dataset now forces goal use, so a model trained on H8-style same-start/different-goal data (with the mismatched-goal / action-probe gate applied) is required before any goal-conditioned navigation claim.
- **No promotion either way.** Incumbent retained; status remains `DIAGNOSTIC_ONLY_NOT_PROMOTED`.

## Claim boundary
- Offline probe of the *instantaneous predicted action* at a fixed recorded frame; no rollout, no physics, no autonomy claim, no benchmark claim.
- Expected actions are the committed recorded-acceptance robot-frame directions o_d→goal.

## Artifacts
`assets/experiments/hospital_h8_paired_branch_prototype/action_probe/`: `h8_action_probe_report.md`, `h8_action_probe_results.json`, `h8_action_probe_matrix.{csv,md}`, `h8_action_probe_direction_diagram.png`. Harness: `scripts/gnm/h8_action_probe.py`.
