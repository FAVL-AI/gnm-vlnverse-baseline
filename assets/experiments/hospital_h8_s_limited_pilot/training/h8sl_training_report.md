# H8-S Limited Causal Pilot — Training + Diagnostics Report

**Status: `LIMITED_CAUSAL_PILOT`. Verdict: `GOAL_CONDITIONING_OBJECTIVE_NOT_READY`.**

**Scope.** Tests only whether the H8 goal-conditioned objective can make the predicted action respond to the goal image on the committed H8-S limited real-frame set. No promotion, no push, no tag, no 20/5/10, no closed-loop Isaac, no H8-M validation; incumbent retained; `CL_BOUND_XY` unchanged; no checkpoint written to the repo.

## Gate axis (why distance/stop, not 15 deg angular)
Every committed H8-S decision frame is `near_far_same_approach`: `o_d`, goalA(near_stop) and goalB(far_continue) are **collinear** (share y, differ only in along-corridor x), so the expected **angular** separation is **0 deg** in all three frames. The 15 deg angular branch-choice gate is not well-posed here (one heading, two distances, no junction). The well-posed causal axis is **distance/stop**: swapping near<->far goal should change the predicted action **magnitude** |[dx,dy]| (meters). Because the action target is the full `o_d->goal` displacement, target magnitude encodes goal distance, so predicted magnitude is the clean distance signal:

- `S = |mag_far - mag_near| / |expected_dist_sep_m|`  (meters/meters), gate S >= 0.5
- branch-choice (stop/continue) correct iff `mag_far > mag_near`, gate >= 0.75
- direction-toward-branch: **N/A** (collinear, 0 deg)
- deterministic rerun matches: **yes**

## Setup
- Init: weights-only from the H7r candidate (`checkpoints/h7r_hospital_pilot_finetune/best.pt`), fresh Adam, seed 42, 400 steps, lr 0.001; deterministic cuDNN/cuBLAS.
- Split: **train=lobby**, **val=midwest_B**, **test=east_A**. Trained on the **train frame only** (2 samples); val + test are **held-out** probes (test = primary held-out coordinate).
- Loss variants (distance-axis translation): **A** action imitation (`||a_pred-a_tgt||`, target = full o_d->goal displacement so magnitude encodes distance); **B** goal-contrastive (separation + triplet at the shared o_d); **C** branch aux (near_stop vs far_continue classification); **E** goal-dropout (zeroed goal -> neutral mean action). Weights lambda={'a': 1.0, 'c': 1.0, 'b': 0.5, 'd': 0.1, 'e': 0.5}.

## Progression (distance-axis diagnostics recomputed after each variant)

| variant | held-out branch-choice | held-out mean S | test branch-choice (far>near) | test S | gate |
|---|---|---|---|---|---|
| baseline | 0.00 | 0.003 | False | 0.003 | - |
| A | 0.00 | 0.018 | False | 0.035 | - |
| A+B | 1.00 | 0.059 | True | 0.118 | - |
| A+B+C | 1.00 | 0.150 | True | 0.301 | - |
| A+B+C+E | 1.00 | 0.085 | True | 0.100 | - |

Pass target (distance axis): held-out branch-choice >= 0.75, held-out mean S >= 0.5.

## Per-frame detail (predicted magnitude near vs far)

### baseline
- **train / lobby** (exp near 0.60 m, far 1.60 m, sep 1.00 m): pred mag near 0.017 m vs far 0.016 m (change -0.000 m); far>near = False; S 0.000; pred angular change 1.62 deg (expected 0).
- **val / midwest_B** (exp near 0.40 m, far 1.00 m, sep 0.60 m): pred mag near 0.017 m vs far 0.016 m (change -0.001 m); far>near = False; S 0.002; pred angular change 0.28 deg (expected 0).
- **test / east_A** (exp near 0.30 m, far 0.70 m, sep 0.40 m): pred mag near 0.014 m vs far 0.013 m (change -0.001 m); far>near = False; S 0.003; pred angular change 2.08 deg (expected 0).

### A
- **train / lobby** (exp near 0.60 m, far 1.60 m, sep 1.00 m): pred mag near 0.495 m vs far 1.200 m (change +0.705 m); far>near = True; S 0.705; pred angular change 0.01 deg (expected 0).
- **val / midwest_B** (exp near 0.40 m, far 1.00 m, sep 0.60 m): pred mag near 0.483 m vs far 0.482 m (change -0.001 m); far>near = False; S 0.001; pred angular change 0.02 deg (expected 0).
- **test / east_A** (exp near 0.30 m, far 0.70 m, sep 0.40 m): pred mag near 0.519 m vs far 0.505 m (change -0.014 m); far>near = False; S 0.035; pred angular change 0.10 deg (expected 0).

### A+B
- **train / lobby** (exp near 0.60 m, far 1.60 m, sep 1.00 m): pred mag near 0.404 m vs far 1.208 m (change +0.805 m); far>near = True; S 0.805; pred angular change 0.30 deg (expected 0).
- **val / midwest_B** (exp near 0.40 m, far 1.00 m, sep 0.60 m): pred mag near 0.531 m vs far 0.531 m (change +0.000 m); far>near = True; S 0.000; pred angular change 0.01 deg (expected 0).
- **test / east_A** (exp near 0.30 m, far 0.70 m, sep 0.40 m): pred mag near 0.475 m vs far 0.523 m (change +0.047 m); far>near = True; S 0.118; pred angular change 0.15 deg (expected 0).

### A+B+C
- **train / lobby** (exp near 0.60 m, far 1.60 m, sep 1.00 m): pred mag near 0.357 m vs far 1.193 m (change +0.836 m); far>near = True; S 0.836; pred angular change 0.24 deg (expected 0).
- **val / midwest_B** (exp near 0.40 m, far 1.00 m, sep 0.60 m): pred mag near 0.422 m vs far 0.422 m (change +0.000 m); far>near = True; S 0.000; pred angular change 0.00 deg (expected 0).
- **test / east_A** (exp near 0.30 m, far 0.70 m, sep 0.40 m): pred mag near 0.641 m vs far 0.761 m (change +0.120 m); far>near = True; S 0.301; pred angular change 0.10 deg (expected 0).

### A+B+C+E
- **train / lobby** (exp near 0.60 m, far 1.60 m, sep 1.00 m): pred mag near 0.626 m vs far 0.750 m (change +0.123 m); far>near = True; S 0.123; pred angular change 0.00 deg (expected 0).
- **val / midwest_B** (exp near 0.40 m, far 1.00 m, sep 0.60 m): pred mag near 0.631 m vs far 0.673 m (change +0.042 m); far>near = True; S 0.069; pred angular change 0.01 deg (expected 0).
- **test / east_A** (exp near 0.30 m, far 0.70 m, sep 0.40 m): pred mag near 0.806 m vs far 0.846 m (change +0.040 m); far>near = True; S 0.100; pred angular change 0.01 deg (expected 0).

## Observations

- **Baseline (untrained H7r)** held-out mean S = 0.003, test branch-choice far>near = False: the starting model's goal-image sensitivity on the distance axis before any H8 objective training.
- **The objective breaks the goal-collapse *directionally* (branch-choice passes).** Held-out branch-choice (far>near) rises from 0.00 (baseline, goal-collapsed) to 1.00 with the goal-contrastive (B) + branch-aux (C) terms — the model orders near vs far correctly on the held-out frames (>= 0.75 branch-choice gate met).
- **But the distance-scaling is too weak (magnitude gate fails).** The S >= 0.5 gate is not met on **one training frame** (best variant `A+B+C`, held-out mean S 0.150, test S 0.301); the model reacts to goal content but captures only a fraction of the expected near/far distance separation. Because both criteria must pass, the verdict is NOT_READY.
- Predicted **angular** change near->far is ~0 deg across all variants/frames, as expected for a collinear near/far design — confirming the angular gate would be uninformative here.
- Temporal **dist head** barely separates near vs far (all goals < stop range); the **action magnitude** carries the distance signal, as designed.

- **No variant meets the distance-axis gate on the held-out frames.** On a single training frame the objective can fit lobby but does not reliably transfer the near<->far magnitude ordering/sensitivity to the held-out alcove views. This is a limited-pilot **negative/inconclusive** signal, not a model-architecture verdict.

## Decision

- **Verdict: `GOAL_CONDITIONING_OBJECTIVE_NOT_READY`.**
- **No promotion, no push, no tag, no 20/5/10, no closed-loop, no H8-M validation.** Incumbent retained; status `DIAGNOSTIC_ONLY_NOT_PROMOTED`. No checkpoint written.
- **H8-M is still required** for a strong benchmark claim (genuinely distinct rooms, an embedding distinctness gate, and — for a real angular branch-choice test — a junction with divergent corridors).

## Critical caveats (must not be dropped)
- **One training decision frame** (lobby, 2 samples). A pass proves the objective can make the action magnitude goal-sensitive and transfer the near<->far ordering to held-out **same-alcove** frames — **not** generalizable goal-conditioned navigation.
- **Distance axis only**; the angular branch-choice test is deferred to a junction (H8-M). Direction-toward-branch is N/A here.
- **Standard nav metrics are N/A offline** (no rollout on 3 decision frames) — see `h8sl_metric_table.md`.
- All goal images are the same vending alcove at different scales/positions (`LIMITED_PILOT_ONLY`, max cross-split aHash 0.887); no strong held-out visual, multi-room, or full goal-conditioned ImageNav claim.

## Artifacts
`assets/experiments/hospital_h8_s_limited_pilot/training/`: `h8sl_training_report.md`, `h8sl_training_results.json`, `h8sl_action_probe_matrix.{csv,md}`, `h8sl_mismatched_goal_ablation.md`, `h8sl_metric_table.md`, `h8sl_claim_boundary.md`, `h8sl_direction_diagram.png`. Harness: `scripts/gnm/h8sl_limited_pilot_train_diag.py`. No checkpoint/weights written to the repo.
