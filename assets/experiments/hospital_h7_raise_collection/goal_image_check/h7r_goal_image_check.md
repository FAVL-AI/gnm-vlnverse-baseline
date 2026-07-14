# H7r Scene-Aligned Goal-Image Check

**Status:** no-training evaluation only. No promotion, no push, no tag, no 20/5/10, no
change to committed H7r evidence. Uses only the raised-mount H7r pilot data + the two
existing checkpoints (H1 incumbent, H7r candidate).

## Purpose
Test whether the H7r diagnostic signal still holds when the goal image is scene-aligned
and episode-specific rather than a fixed placeholder — the largest remaining caveat
before any scale-up.

## Key finding first: the premise needed correcting
Inspecting the evaluator (`gnm_vlnverse/evaluation/evaluator.py:24, 175-179, 192`) shows
that the offline **Track-A evaluation already uses each episode's OWN final recorded
frame as the goal image** (`goal_idx = -1 → frame T-1`), and the goal *position* is that
same final frame's position. **The fixed placeholder `h2_weave_J` was only the
recording-time goal-id (closed-loop route-follower + saved goal metadata); it never
entered the offline eval metrics.** So the committed H7r diagnostic numbers were already
computed with scene-aligned, episode-specific goal images.

**Faithfulness check:** re-running the scene-aligned condition reproduces the committed
`cand_test` exactly (SR 1.000 / SPL 0.908 / NE 2.54 m / nDTW 0.646), confirming the
harness matches the official evaluator.

## What was done
1. **Inspected** all 8 H7r episodes — every one has usable start / mid / goal frames
   (177 recorded frames each). `inspection_all_usable = true`.
2. **Extracted** the scene-aligned goal image per episode = its final recorded
   `/camera/image_raw` frame (`goals/`, contact sheet `h7r_goal_images_contact_sheet.png`).
   No re-renders, no procedural/H6, no occluded original-H7 images.
3. **Manifest** `h7r_goal_image_manifest.json` (episode_id, split, route_family,
   source_frame_path, source_rosbag_path, goal_frame_index, camera_mount_raise_m = 0.12,
   scene_gate_pass, from_recorded_camera_image_raw).
4. **No-training eval** of both models under two goal conditions:
   **A) scene-aligned** (each episode's own final frame — the eval default) and
   **B) fixed placeholder** (`h2_weave_J` for all episodes), goal *position* held to the
   episode's true endpoint in both.

## Results (H7r held-out test, n=2)

| model | goal condition | SR | OSR | SPL | NE (m) | nDTW |
|---|---|---|---|---|---|---|
| H1 incumbent | scene-aligned | 0.00 | 1.00 | 0.00 | 15.43 | 0.078 |
| H1 incumbent | placeholder | 0.00 | 1.00 | 0.00 | 16.90 | 0.060 |
| **H7r candidate** | **scene-aligned** | **1.00** | 1.00 | 0.908 | 2.54 | 0.646 |
| **H7r candidate** | **placeholder** | **1.00** | 1.00 | 0.952 | 2.09 | 0.696 |

Sanity splits (candidate): val SR 1.00 both conditions (NE 2.06 aligned / 1.78
placeholder); train SR 1.00 both (NE 2.17 / 1.67). Per-family (test): candidate succeeds
on **both** turn_02 and waiting_02 under **both** goal conditions; incumbent fails both
under both.

## Interpretation (honest)
- **The result is NOT placeholder-goal-sensitive.** The candidate reaches and stops on
  the held-out routes with SR 1.00 under *both* the correct scene-aligned goal and the
  wrong fixed placeholder goal. Per the pre-registered decision rule, the diagnostic
  stopping-reliability signal survives the scene-aligned check and is *robust* to the
  goal image — it is not an artifact of the specific placeholder.
- **But the same evidence shows the candidate is largely goal-image-INSENSITIVE.**
  Performance is essentially unchanged (indeed marginally better) when the goal image is
  wrong. This means the candidate's success is driven by **imitating the demonstrated
  route/motion and its learned stopping behaviour**, *not* by conditioning on the goal
  image. Under this small, fixed-route, single-goal regime the goal image is not the
  causal driver.
- The stopping-reliability contrast with the incumbent (reaches the region but does not
  stop, SR 0.00) remains **real and robust** — the candidate learned to stop at the
  route endpoint; the incumbent did not. That is a genuine, useful behaviour, but it is
  **learned route-following + stopping**, not goal-image conditioning.

## Decision
- Scene-aligned goal-image check: **PASSED** (signal holds; robust to goal image;
  extraction unambiguous).
- **Result status unchanged: `DIAGNOSTIC_ONLY_NOT_PROMOTED`, incumbent retained.**
- **New, important caveat for scaling:** the candidate does not yet use the goal image.
  Scaling to 20/5/10 as-is would scale route/motion memorization, not goal-conditioned
  navigation. Therefore the goal-conditioning must be made *causal* before scale-up.

## Recommended next step (revised by this finding)
Before 20/5/10, run a **goal-sensitivity / mismatched-goal ablation and strengthen goal
conditioning**:
1. Add a **mismatched-goal test** (feed a *different* episode's endpoint as the goal) —
   a good goal-conditioned policy should fail or divert; route-memorization will not.
2. Vary the goal during collection/training (multiple distinct goals per route, or
   goal-frame sampling that forces the policy to attend to the goal image).
3. Only once the policy demonstrably *uses* the goal image should the 20/5/10 raised-mount
   multi-seed collection proceed — otherwise scale amplifies memorization.

## Artifacts
`assets/experiments/hospital_h7_raise_collection/goal_image_check/`:
`h7r_goal_image_manifest.json`, `h7r_goal_image_eval_matrix.{md,csv}`,
`h7r_goal_image_per_family.csv`, `h7r_goal_images_contact_sheet.png`, `goals/` (8 extracted
scene-aligned goal frames), this report. Harness: `scripts/gnm/h7r_goal_image_check.py`.
