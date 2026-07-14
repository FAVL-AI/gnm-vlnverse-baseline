# H8 — Goal-Conditioned Training Objective (DESIGN ONLY)

**Status:** design only. No training, no promotion, no push, no tag, no 20/5/10, no
closed-loop Isaac testing, no code. This document specifies the *next* training objective so
the model must use the goal image causally instead of learning route/motion imitation. It
does not change any committed evidence.

**Provenance.** Direct consequence of the committed chain
`ff71908 → 689df9e → 47d0d58 → af4f595 → 4012d81 → 6199c79 → d8ac839`. Verdict on both
existing models: `DIAGNOSTIC_ONLY_NOT_PROMOTED`, incumbent retained.

**Professor-safe framing carried forward:**
> The dataset-side causal design now works: the same visual state requires different actions
> for different goals. However, the current models do not respond to the goal image. The next
> step is to change the supervised objective so that goal swaps change the predicted 2-D
> action. Only after that passes the offline action-probe should we scale collection.

---

## 1. Problem statement

The H8 design-mode gate (`4012d81`) and recorded-mode gate (`6199c79`) prove the dataset can
make the goal image **necessary**: at a single shared decision frame `o_d`, two distinct
goals require robot-frame actions separated by ≥ 30° (168.6°/61.9° design, 71.8°/50.9° on
real recorded hospital images), so no goal-blind policy can be correct on both branches. The
offline action-probe (`d8ac839`) then showed both existing models **ignore** the goal image.
The bottleneck is therefore **model/training-side**, not the route/dataset design.

**Architectural note (important):** the GNM already *supports* goal-conditioning
(`gnm_vlnverse/models/gnm.py`): `fused = cat[obs_encoder(obs), goal_encoder(goal)]` feeds
both `dist_predictor` and `action_predictor`. So no architecture change is required to *use*
the goal — the action head simply learned to be goal-invariant because the training data (one
route per start) never penalised ignoring `goal_feat`. The fix is **data + objective**. A
stronger fusion (FiLM / cross-attention conditioning of the action head on `goal_feat`) is a
*fallback* only if a concatenation-fed head cannot be forced to use the goal (see §8).

---

## 2. Current failure signature (from the committed action-probe `d8ac839`)

- **branch-choice = 0.50 (chance)** for **both** models;
- **H1 incumbent goal-sensitivity S = 0.009**;
- **H7r candidate goal-sensitivity S = 0.024**;
- **predicted action change under goal swap ≤ 2°** (incumbent 0.53°, candidate 1.50°) at the
  shared decision frame — same RGB + different goal image ⇒ effectively the same `[Δx, Δy]`;
- **route/motion-imitation dominated**; the action head is a function of `obs_feat` only in
  practice;
- status **`DIAGNOSTIC_ONLY_NOT_PROMOTED`**, incumbent retained.

These exact numbers are the pre-training baseline the new objective must move.

---

## 3. New training objective requirements

The objective must force, at a shared decision frame `o_d` (identical current RGB `I_t`):
- same `I_t` + goal A image `I_gA` → action `a_A`;
- same `I_t` + goal B image `I_gB` → action `a_B`;
- different goals at the same decision frame produce **different** predicted `[Δx, Δy]`
  (spread comparable to the target separation, not a collapsed average);
- **wrong goals reduce performance / move the endpoint** (a mismatched goal must not yield the
  route-imitation action).

The single acceptance criterion: at held-out shared decision frames, swapping the goal image
changes the predicted action *toward the goal-consistent branch*.

---

## 4. Proposed losses

Notation: at a shared decision frame, `f(I_t, I_g)` is the predicted action; `a_*` are target
actions; `sep(u,v)` is the angle between two action vectors; `[·]_+ = max(0, ·)`.

**A. Action imitation loss (existing — necessary, not sufficient).**
`L_action = || a_pred − a_target ||` (MSE on normalised action, as in `04_train_gnm.py`'s
`loss_action`). On *paired* same-start/different-goal data this already requires goal use to
fit both targets — but a high-capacity head can hedge by predicting the **average** of `a_A`
and `a_B` (low but non-zero loss on both). Losses B–C exist to defeat that collapse.

**B. Goal-contrastive action loss (the core new term).** For a paired minibatch sharing
`I_t` with goals `(I_gA, I_gB)` and targets `(a_A, a_B)`:
- *separation term* — predictions must spread as much as the targets require:
  `L_sep = [ sep(a_A, a_B) − sep(f(I_t,I_gA), f(I_t,I_gB)) ]_+`;
- *cross-repulsion (triplet)* — each goal's prediction must be closer to its own target than
  to the other branch's:
  `L_rep = [ ||f(I_t,I_gA) − a_A|| − ||f(I_t,I_gA) − a_B|| + m ]_+  (+ symmetric for B)`.
`L_contrastive = L_sep + L_rep`. This directly punishes the ≤2° collapse observed in §2.

**C. Branch-classification auxiliary loss (cheap, high-signal).** Add a small head
`h_branch(fused) → logits over K branches`, cross-entropy against the branch label. **Key
property:** at a shared `o_d` the `obs_feat` half of `fused` is identical across branches, so
the only way to classify the branch correctly is through `goal_feat` — this forces the goal
encoder to be discriminative and injects goal-dependent gradient into the shared trunk.
`L_branch = CE(h_branch(fused), branch_label)`.

**D. Stop/temporal loss (kept, capped).** Retain the existing distance head loss
`L_dist = || d_pred − d_target ||`, but **down-weight** it (`λ_d` small). Rationale: the H7r
candidate likely satisfied its objective largely via the temporal/stopping signal; if `L_dist`
dominates, the action head has little pressure to attend to the goal. Keep the stop behaviour,
don't let it crowd out action-goal-conditioning.

**E. Optional goal-image dropout / swap loss.** Two augmentations:
- *swap negatives* — feed `(I_t, wrong_goal)` with the wrong goal's own branch target (from
  the paired set), so the model sees the same `I_t` mapped to *both* branch actions depending
  on the goal;
- *goal dropout* — with probability `p`, mask/zero `I_g`; exclude that sample from `L_action`
  (or map it to a defined "goal-unknown" target), so the model cannot treat a constant goal as
  a bias term.

**Composite:** `L = λ_a·L_action + λ_c·L_contrastive + λ_b·L_branch + λ_d·L_dist (+ λ_e·L_swap)`,
with `λ_d` deliberately small. Exact weights are an ablation (§8); start `λ_a=1, λ_c=1,
λ_b=0.5, λ_d=0.1`.

---

## 5. Training data structure

Require **paired samples** keyed by decision frame, not by episode:

| field | meaning |
|---|---|
| `decision_frame_id` | shared `o_d` identity (same `I_t` across its goals) |
| `I_t` | current RGB at the decision frame (recorded `/camera/image_raw`, raised mount) |
| `I_g` | goal RGB (scene-aligned recorded final frame) |
| `a_target` | robot-frame `[Δx, Δy]` for this goal at `o_d` |
| `branch_label` | discrete branch id for `L_branch` |
| `goal_id` | goal identity |
| `action_angle_separation_metadata` | angle between this branch's target and the other branch(es) (must be ≥ 30°) |

Invariant: every `decision_frame_id` carries **≥ 2 goals with different `a_target` separated
≥ 30°** (the H8 acceptance property). The committed 2×2 prototype (`6199c79`) is the seed of
this format; the H8 collection scales the number of *distinct decision frames* (the axis that
matters for generalisation, see §8).

---

## 6. Evaluation gates (blocking, before any promotion or 20/5/10)

Reuse the committed instruments:
1. **Rerun the H8 offline action-probe** (`scripts/gnm/h8_action_probe.py`) on the trained
   model. Require:
   - **branch-choice > chance** (target ≥ 0.75; baseline 0.50);
   - **goal-sensitivity S increases meaningfully** (target ≥ 0.5; baseline 0.009 / 0.024);
   - **predicted action angle changes in the correct direction** under goal swap
     (mean pred action change ≥ 15°; baseline ≤ 2°).
2. **Rerun the mismatched-goal ablation** (`scripts/gnm/h7r_mismatched_goal_ablation.py`,
   generalised to H8): wrong goals must **reduce performance or move the endpoint** (the
   opposite of the H7r route-imitation signature).
3. **Retain the standard navigation metrics** via `scripts/gnm/06_evaluate.py` (force
   `--data-root`): **TL, NE, SR, OSR, SPL, nDTW, CR** — a goal-conditioned gain must not come
   at the cost of collapsing basic navigation. (CR = 0 offline; meaningful only under
   closed-loop, per prior locks.)

Held-out discipline: report the action-probe on **held-out decision frames**, not only trained
ones — otherwise "goal-conditioning" is memorisation (see §8 caveat).

---

## 7. Claim boundary

- This is **supervised learning** (imitation + auxiliary losses), **not reinforcement
  learning**.
- It is **not full autonomous navigation**; the action-probe tests the instantaneous predicted
  action, not closed-loop success.
- **Not promoted**, **no SOTA claim**; incumbent retained until the §6 gates pass and are
  reviewed.
- **Closed-loop Isaac rollout remains a later, promotion-grade gate** (Option B), after the
  offline action-probe passes across seeds.

---

## 8. Next implementation plan (minimal diagnostic — do NOT run yet)

1. **Data:** start with only the committed **2×2 H8 paired-branch prototype** (2 decision
   frames × 2 goals = 4 `(I_t, I_g, a_target)` samples, from `6199c79`). Optionally mix the
   existing H7r corpus as a background action-imitation regulariser so basic navigation is not
   forgotten.
2. **Init:** weights-only `training.init_ckpt` from the H7r candidate
   (`checkpoints/h7r_hospital_pilot_finetune/best.pt`), fresh optimizer (per the locked
   fine-tune convention).
3. **Objective ablation:** train tiny variants toggling the new terms — {A only}, {A+B},
   {A+B+C}, {A+B+C+E} — to isolate which term actually moves the predicted action.
4. **Compare:** run the H8 action-probe on each variant vs the current H7r candidate; report
   branch-choice, S, and pred action change (the §2 baseline table is the reference).
5. **Stop after reports.** No promotion, no scale-up.

**Honest caveat (must be stated in the experiment report):** with only **2 distinct decision
frames**, a model can satisfy the objective by *memorising two frames* — this minimal run
tests only whether the new loss can move the predicted action *at all*, not whether
goal-conditioning **generalises**. A generalisable result requires many distinct decision
frames with **held-out** decision frames in val/test — i.e. the H8 collection. The minimal
experiment is a "can the loss move the needle" sanity check that gates whether the H8
collection is worth recording; it is not itself goal-conditioning evidence.

---

## Sequence (unchanged, now with the objective slotted in)
1. **DONE:** H8 design gate, recorded gate, action-probe (dataset design correct; models
   ignore the goal).
2. **This document:** goal-conditioned training objective design (review pending).
3. Minimal objective ablation on the 2×2 prototype → H8 action-probe (this §8).
4. Only on a "needle moved" result: author/scale the H8 collection (many decision frames,
   held-out split) → train → §6 gates.
5. Only on §6 pass across seeds: closed-loop Isaac (Option B) → then consider 20/5/10.

*No training, promotion, push, tag, 20/5/10, closed-loop testing, or code is authorised by
this document. Design only — stop after writing.*
