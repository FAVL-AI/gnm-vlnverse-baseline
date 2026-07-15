# H8-S Limited Causal Pilot — Claim Boundary

**Status: `LIMITED_CAUSAL_PILOT`. Verdict: `GOAL_CONDITIONING_OBJECTIVE_NOT_READY`.**

## What this pilot tests
- Whether the H8 goal-conditioned objective makes the model's **predicted 2-D action respond to the goal image** on a small, real, coordinate-clean hospital set — measured on the **distance/stop axis** (near_stop vs far_continue), because the committed frames are collinear near/far (0 deg angular separation).
- Whether the near<->far magnitude ordering/sensitivity **transfers** from the single training frame (lobby) to **held-out** coordinates (val=midwest_B, test=east_A) of the same alcove.

## What this pilot does NOT claim
- **Not** a strong held-out visual benchmark (all goals are the same vending alcove; `LIMITED_PILOT_ONLY`, max cross-split aHash 0.887; a strong claim needs an embedding gate).
- **Not** multi-room / cross-location visual generalization.
- **Not** full goal-conditioned ImageNav.
- **Not** an angular branch-choice result (no junction; deferred to H8-M).
- **Not** a rollout/benchmark navigation result (standard metrics N/A offline).
- **No** SOTA, promotion, autonomy, or model-architecture verdict.

## Method boundary
- Weights-only init from the H7r candidate; fresh optimizer; deterministic; seed logged; trained on **one** decision frame (2 samples); offline action-probe of the instantaneous predicted action; no rollout, no physics, no autonomy.
- Expected distances are the committed decision-frame o_d->goal distances (also the training-target magnitudes), so a pass means the action head **can express** goal-distance-dependent magnitude and transfer its ordering within the same alcove — not that it learned a generalizable goal representation.

## Standing constraints
- No promotion, no push, no tag, no 20/5/10, no closed-loop Isaac, no H8-M validation; incumbent retained; `CL_BOUND_XY` unchanged; no checkpoint/weights committed.
- **H8-M remains required** for the stronger benchmark claim (distinct rooms + embedding distinctness gate + a junction for the angular branch-choice test).

