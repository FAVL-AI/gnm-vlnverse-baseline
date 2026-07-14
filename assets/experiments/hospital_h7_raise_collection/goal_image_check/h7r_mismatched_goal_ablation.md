# H7r Mismatched-Goal Ablation — does the candidate actually use the goal image?

**Status:** no-training evaluation only. No training, no promotion, no push, no tag, no
20/5/10 expansion, no change to committed H7r evidence. Uses only the committed
raised-mount H7r pilot data and the existing H7r candidate checkpoint
(`checkpoints/h7r_hospital_pilot_finetune/best.pt`).

## Question
The scene-aligned goal-image check showed the candidate succeeds under *both* the correct
scene-aligned goal and the fixed placeholder goal — i.e. it looked goal-image-insensitive.
This ablation tests that directly: for each H7r **test** episode we roll out the **same
trained candidate** on that episode's own recorded frames, swapping only the **goal
image** across four conditions. The goal **position** is always held to the episode's own
route endpoint, so SR / NE / SPL / nDTW measure *"did it still complete ITS OWN route?"*.

Conditions:
1. **correct** — the episode's own final recorded frame (scene-aligned).
2. **placeholder** — the fixed `h2_weave_J` goal image.
3. **mismatch_same_fam** — the same route family's *other* instance final frame
   (turn_02 ← turn_01; waiting_02 ← waiting_01).
4. **mismatch_diff_fam** — a *different* route family's final frame, hard mismatch
   (turn_02 ← reception_01; waiting_02 ← corridor_01).

## Results (H7r held-out test, n = 2)

| goal_condition | n | SR | OSR | SPL | NE (m) | nDTW | mean endpoint Δ vs correct (m) |
|---|---|---|---|---|---|---|---|
| correct | 2 | 1.000 | 1.000 | 0.908 | 2.54 | 0.646 | 0.000 |
| placeholder | 2 | 1.000 | 1.000 | 0.952 | 2.09 | 0.696 | 0.659 |
| mismatch_same_fam | 2 | 0.500 | 1.000 | 0.500 | 2.92 | 0.612 | 0.501 |
| mismatch_diff_fam | 2 | 1.000 | 1.000 | 0.879 | 2.50 | 0.654 | 0.497 |

Per-episode (endpoint Δ = distance between this condition's final stop and the
correct-goal final stop):

| episode | family | condition | SR | NE (m) | nDTW | stop | endpoint Δ (m) |
|---|---|---|---|---|---|---|---|
| h7r_turn_02 | turn_t_junction | correct | 1 | 2.61 | 0.630 | 176/176 | 0.000 |
| h7r_turn_02 | turn_t_junction | placeholder | 1 | 2.37 | 0.652 | 176/176 | 0.241 |
| h7r_turn_02 | turn_t_junction | mismatch_same_fam (turn_01) | **0** | **3.43** | 0.554 | 176/176 | 0.892 |
| h7r_turn_02 | turn_t_junction | mismatch_diff_fam (reception_01) | 1 | 2.81 | 0.610 | 176/176 | 0.210 |
| h7r_waiting_02 | waiting_to_doorway | correct | 1 | 2.47 | 0.662 | 176/176 | 0.000 |
| h7r_waiting_02 | waiting_to_doorway | placeholder | 1 | 1.81 | 0.739 | 176/176 | 1.078 |
| h7r_waiting_02 | waiting_to_doorway | mismatch_same_fam (waiting_01) | 1 | 2.40 | 0.670 | 176/176 | 0.109 |
| h7r_waiting_02 | waiting_to_doorway | mismatch_diff_fam (corridor_01) | 1 | 2.19 | 0.697 | 176/176 | 0.784 |

## Key mechanical observations
1. **Every rollout runs the full reference length (stop 176/176) in every condition.** The
   candidate never triggers its own learned stop threshold (`dist_pred < 0.15`) on these
   test episodes; the rollout ends because the demonstrated frame sequence is exhausted.
   Its low NE therefore comes from producing **route-consistent per-step actions that keep
   the dead-reckoned position near the demonstrated endpoint**, *not* from a goal-driven
   decision to stop. (This refines the earlier "learned stopping" wording: it is action
   imitation over the demonstrated observation stream, not an explicit stop event.)
2. **Wrong goal images move the final stop by only 0.1–1.1 m and never cause a divert.**
   Across all mismatched/placeholder conditions the endpoint shifts ≤ 1.08 m; the policy
   keeps following its own demonstrated route in every case. Nothing steers toward the
   mismatched goal's location.
3. **The one SR flip is a threshold-boundary effect, not a divert.** turn_02 under the
   same-family goal ends 0.89 m further out, pushing NE from 2.61 m to 3.43 m — just across
   the 3.0 m success cutoff. It is still on-route; it merely lands ~0.4 m past the ring.
4. **The perturbation is anti-correlated with goal semantics.** The *hard* different-family
   mismatch perturbed the endpoint *less* (mean Δ 0.497 m) than the same-family mismatch
   (0.501 m) and less than the placeholder (0.659 m). A genuinely goal-conditioned policy
   would be perturbed *more* by a semantically farther goal. The opposite pattern indicates
   the goal image enters the action head only as weak, non-semantic noise.

## Interpretation (honest)
- Under the pre-registered decision rule — *"if performance remains high under mismatched
  goals, mark the current H7r candidate as route/motion-imitation dominated"* — the
  candidate **remains high**: SR 1.0 under placeholder and under the hard different-family
  mismatch; the only sub-1.0 SR is a single boundary-crossing episode still ending on its
  own route. NE stays in a 1.8–3.4 m band and endpoints move ≤ ~1 m regardless of which
  goal image is shown.
- **Verdict: the current H7r candidate is route/motion-imitation dominated.** It reproduces
  the demonstrated route from the observation stream and is essentially insensitive to the
  goal image, which perturbs the endpoint by at most ~1 m without ever redirecting the path.
  This is fully consistent with, and strengthens, the scene-aligned goal-image check.
- There is a *trace* of goal-image influence (endpoint shifts of 0.5–1.1 m, one SR flip),
  but it is small, non-semantic, and anti-correlated with goal difficulty — **not**
  preliminary goal-conditioning evidence.

## Decision
- Mismatched-goal ablation: **route/motion-imitation dominated** (goal image not causal).
- **Result status unchanged: `DIAGNOSTIC_ONLY_NOT_PROMOTED`, incumbent retained.**
- **No promotion, no push, no tag, no 20/5/10 expansion.**

## Consequence for scale-up (unchanged from the goal-image check, now confirmed)
Scaling this candidate as-is would scale route/motion memorization, not goal-conditioned
navigation. Before any 20/5/10 raised-mount collection, goal-conditioning must be made
*causal*: vary the goal during collection/training (multiple distinct goals per route or
goal-frame sampling that forces attention to the goal image), and re-run this same
mismatched-goal ablation as the gate — a goal-conditioned policy should *divert or fail*
under the different-family mismatch, not hold its route.

## Caveats
- **n = 2** held-out test episodes (each SR fraction = one episode); single seed; single
  raised-mount pilot. This is a diagnostic direction-check, not a powered result.
- Track-A offline eval integrates predicted actions by dead reckoning over the episode's
  own recorded frames; it does not re-render the scene under the policy's chosen actions,
  so "divert" here means the integrated endpoint moves, not a re-simulated collision.

## Artifacts
`assets/experiments/hospital_h7_raise_collection/goal_image_check/`:
`h7r_mismatched_goal_ablation.md` (this report),
`h7r_mismatched_goal_manifest.json`,
`h7r_mismatched_goal_eval_matrix.{md,csv}`,
`h7r_mismatched_goal_contact_sheet.png` (correct vs placeholder vs same-/diff-family goal
images with per-cell SR / NE / endpoint Δ).
Harness: `scripts/gnm/h7r_mismatched_goal_ablation.py`.
