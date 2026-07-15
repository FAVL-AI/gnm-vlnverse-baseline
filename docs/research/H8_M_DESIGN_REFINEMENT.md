# H8-M — Design Refinement (PLANNING ONLY)

**Status: planning only.** No collection, no training, no promotion, no push, no tag, no 20/5/10,
no closed-loop Isaac, **no `CL_BOUND_XY` change**. This document refines the H8-M design so it
fixes the limitations the H8-S limited pilot exposed. It changes no committed result and
authorises no execution.

**Provenance.** Follows the committed H8-S chain
`… → 99ccbb5 (H8-S limited design gate) → abc78ad (recorded-mode gate) → dfae1f6 (training
diagnostic)`. Extends `docs/research/H8_M_SEALED_ROOM_MAP_EXTENSION_PLAN.md` (how to reach the
sealed rooms) and `docs/research/H8_S_LIMITED_CAUSAL_PILOT_SCOPE.md` (why H8-S was re-scoped).
Verdict carried forward: `DIAGNOSTIC_ONLY_NOT_PROMOTED`, incumbent retained.

**Professor-safe framing:**
> H8-S gave a useful negative diagnostic: the objective can create some goal response, but not
> enough for readiness. H8-M must therefore add more distinct decision frames, real
> branch-divergence geometry, and embedding-based visual distinctness before any stronger claim
> or scale-up.

---

## 1. Why H8-M is needed

H8-S (commit `dfae1f6`) ran the goal-conditioned objective on the committed 3-frame limited
pilot and returned verdict **`GOAL_CONDITIONING_OBJECTIVE_NOT_READY`**. The result is
scientifically clean but negative:

- **Branch-choice passes.** On the distance/stop axis the objective (with goal-contrastive B +
  branch-aux C) recovered correct near/far ordering on **both** held-out frames — held-out
  branch-choice rose from **0.00 (baseline, goal-collapsed)** to **1.00**.
- **Goal response exists.** The mismatched-goal ablation showed a real goal-content response
  (best variant A+B+C: magnitude spread 0.604 m across conditions; placeholder ≠ correct goal),
  i.e. the model is not fully collapsed after training.
- **S ≥ 0.5 fails on one training frame.** Goal-sensitivity magnitude stayed far below the gate:
  best held-out mean **S 0.150**, test **S 0.301** — the model captures only ~15–30 % of the
  expected near/far distance separation. Because both branch-choice **and** S must pass, the
  objective is `NOT_READY`.
- **Distance scaling is too weak.** The predicted action magnitude moves in the right direction
  but under-scales the true near/far distance gap; goal-dropout (E) made it worse.
- **Collinear geometry makes angular branch-choice uninformative.** Every H8-S decision frame is
  `near_far_same_approach`: goalA/goalB are collinear (share y, differ only in along-corridor x),
  so the expected **angular** separation is exactly **0°**. The 15° angular branch-choice gate is
  not well-posed on this set — there is one heading and two distances, no junction.
- **No rollout metrics were produced.** TL/NE/SR/OSR/SPL/nDTW/CR are not computable offline on 3
  decision frames (no simulator rollout); they were reported **N/A**, never fabricated.

Conclusion: the objective *can* induce goal response but the H8-S set is too small, too
visually homogeneous, and geometrically unable to test angular branch-choice. **H8-M must fix
the data, not just re-run the objective.**

## 2. H8-S limitations to fix

1. **Too few decision frames** — 3 total (train=lobby, val=midwest_B, test=east_A); training on
   one frame is memorisation, not learning.
2. **One-alcove visual envelope** — the entire reliably-drivable in-envelope corridor is a single
   vending alcove; all goals are that alcove at different scales/positions.
3. **Weak held-out visual distinctness** — `LIMITED_PILOT_ONLY`, max cross-split aHash 0.887; no
   genuinely distinct held-out goal imagery.
4. **Collinear stop-conditioning instead of true branch divergence** — near_stop vs far_continue
   along one heading; 0° angular separation; cannot test steer-toward-branch.
5. **No multi-room split** — train/val/test are the same room; a strong held-out split needs
   different locations.
6. **No embedding-based distinctness gate** — distinctness judged by crude aHash, which
   over-flags structural similarity and under-flags content similarity.
7. **No rollout** — only instantaneous offline action-probe; no executed-trajectory navigation
   evidence.

## 3. H8-M design requirements

H8-M must include, before any collection is approved:

- **More distinct rooms or zones** — reach genuinely different locations (reception / waiting
  rooms / a second corridor branch) via **spawn-relocation** into each room's own local frame,
  keeping every validated pose within `|x|,|y| ≤ 6` of that spawn (the `CL_BOUND_XY = 6.0`
  watchdog is a safety mechanism, **not** raised — see the sealed-room plan §5).
- **More decision frames** — enough distinct frames per split that training is not
  single-frame memorisation (target ranges in §6/§9), spread across route families (§4).
- **Actual branch-divergence geometry** — at least one location where goalA and goalB require
  **different angular actions** from a shared `o_d`.
- **At least one T-junction or fork** where goal A and goal B genuinely diverge (expected angular
  separation ≥ 30°), so the angular branch-choice gate becomes well-posed.
- **Near/far stop-conditioning only as secondary** — keep the H8-S distance/stop family as a
  supporting axis, not the primary causal test.
- **Embedding-based visual distinctness** — CLIP/DINO-style features for the distinctness gate
  (§5), with aHash retained only as a secondary/auditable cross-check.
- **Held-out decision-frame split** — decision frames (not just coordinates) disjoint across
  train/val/test (§6).
- **Matched and mismatched goal pairs** — each decision frame carries its correct goal(s) plus
  hard-negative mismatched goals for the ablation (§4, §8).

## 4. Route families

H8-M route/decision-frame families (each must be render- **and** drive-validated: scene-gate
PASS, mount 0.12, 0 collisions, no black occlusion, within the ±6 m envelope):

1. **Branch-choice T-junction** — shared `o_d` at a junction; goalA (e.g. left branch) vs goalB
   (right branch) require divergent angular actions (expected separation ≥ 30°). *Primary causal
   family — the one H8-S could not provide.*
2. **Same-start different goal** — one start, two goals in different rooms/directions; tests goal
   image driving the whole trajectory, not just the first step.
3. **Shared-corridor fork** — a corridor that splits; goals down each prong.
4. **Same-room different object** — same room, goal images centred on different objects/props;
   tests object-level goal grounding within a location.
5. **Visually similar but spatially different goals** — look-alike goal images at genuinely
   different coordinates (hard visual confuser; must be embedding-separated in §5 or explicitly
   kept as an adversarial pair).
6. **Near/far stop-conditioning** — the H8-S distance/stop family (near_stop vs far_continue),
   carried forward as a **secondary** axis with the calibrated magnitude term (§7).
7. **Hard-negative mismatched goal** — a wrong-family / cross-scene goal paired to each decision
   frame for the mismatched-goal ablation (§8).

Route-family balance and per-family counts are fixed in §6/§9.

## 5. Visual distinctness gate

Replace the crude aHash gate with an embedding-based gate:

- **Embedding, not only aHash.** Compute per-goal-image embeddings with a CLIP or DINO image
  encoder; use cosine similarity as the primary distinctness metric. Retain aHash + an SSIM
  cross-check as **secondary, auditable** signals (publish all matrices).
- **Per-split threshold (duplicate/collapse).** Within a split, two decision-frame goal images
  with cosine ≥ `T_dup` (e.g. ≥ 0.92, to be calibrated) are duplicates → collapse to one.
- **Cross-split threshold (leakage).** A test goal vs any train/val goal must be **below**
  `T_cross` (e.g. ≤ 0.60 CLIP-cosine, calibrated so genuinely-different rooms pass and same-room
  views fail) or it is visual leakage.
- **Duplicate collapse rule.** If two same-split frames exceed `T_dup`, keep the one with better
  drive-validation / clearer goal content; drop the other.
- **Visually-similar hard-negative rule.** A deliberate look-alike pair (family 5/7) is allowed
  **only** as an explicitly-labelled adversarial hard-negative — never counted as a distinct
  held-out example, and never used to satisfy the cross-split distinctness requirement.
- **Failure action.** For any goal image that violates a threshold: **reject** (drop the frame),
  **merge** (collapse duplicates), or **defer** (mark the zone for later validation). If no
  split-distinct set survives, **do not record** — re-scope rather than overclaim.

Thresholds `T_dup`/`T_cross` are **calibrated on H8-M candidate imagery** before the gate is
binding, and the calibration is reported.

## 6. Dataset split

- **Train / val / test decision-frame split** with route-family balance (§4) represented in each
  split where possible; the branch-choice T-junction family (1) must appear in the **held-out
  test** split.
- **No reused decision frame across splits** — decision-frame images disjoint (not just
  coordinates).
- **No reused goal image across splits** — every goal image belongs to exactly one split.
- **No coordinate reuse across splits** — `o_d` and goal coordinates in disjoint bands per split
  (as in H8-S, extended across rooms).
- **Goal-image hash and embedding audit** — publish both the aHash matrix and the CLIP/DINO
  cosine matrix; assert cross-split below `T_cross` and no within-split duplicates above `T_dup`.
- **Route-family balance** — record per-split counts per family; flag any split that is
  single-family or single-room. Minimum distinct decision frames per split fixed in §9.

## 7. Model / training objective

**Carry forward** (already implemented in `scripts/gnm/h8sl_limited_pilot_train_diag.py` /
`scripts/gnm/h8_loss_ablation.py`; weights-only init from the retained candidate, fresh
optimizer, deterministic, seed logged):

- **Action imitation (A)** — `||a_pred − a_tgt||`, target = robot-frame `o_d→goal` action.
- **Goal-contrastive action loss (B)** — separation + triplet repulsion at each shared `o_d`.
- **Branch auxiliary loss (C)** — classify the branch (left/right for junctions; near/far for
  stop-conditioning) from the fused feature.
- **Capped stop/temporal loss (D)** — distance-head supervision, weight-capped.
- **Optional swap/dropout (E)** — zeroed/swapped goal → neutral action (used with care; E
  regressed magnitude sensitivity on the tiny H8-S set — re-tune or exclude on small splits).

**Add** (directly targeting the H8-S failure modes):

- **Stronger distance-scaling term / magnitude calibration.** H8-S under-scaled the near/far
  magnitude (S ≤ 0.30). Add an explicit magnitude-calibration objective (e.g. supervise
  `|a_pred|` toward the true `o_d→goal` distance, or a scale-matching loss on the near/far
  magnitude ratio) and **report predicted-vs-expected magnitude calibration** so S ≥ 0.5 is
  reachable when the model genuinely tracks distance.
- **Explicit angular branch-choice supervision for divergent routes.** For the T-junction / fork
  families, supervise the predicted action **angle** toward the correct branch (and penalise the
  wrong-branch angle), so the angular gate (branch-choice ≥ 0.75, angular change ≥ 15° toward the
  correct branch) is both well-posed **and** directly optimised.

## 8. Evaluation gates

Run after each variant (as in H8-S), on the **held-out** split:

- **Offline action-probe** — swap only the goal image at a fixed `o_d`; read predicted `[Δx,Δy]`.
- **Mismatched-goal ablation** — correct goal vs same-family wrong goal vs placeholder /
  cross-scene; report whether the action changes or stays collapsed. Use the rollout-based
  `h7r_mismatched_goal_ablation.py` where trajectories exist; the offline probe substitute
  otherwise.
- **Branch-choice accuracy** — angular (junction families) and near/far ordering
  (stop-conditioning family).
- **Goal-sensitivity score S** — angular `S = pred_ang_change / expected_ang_sep` for divergent
  families; distance `S = |mag_far − mag_near| / expected_dist_sep_m` for the stop family.
- **Predicted action angle change** — for divergent routes (must be ≥ 15° toward the correct
  branch, now well-posed).
- **Predicted action magnitude calibration** — predicted-vs-expected `o_d→goal` magnitude
  (targets the H8-S under-scaling).
- **Rollout metrics where available** — TL, NE, SR, OSR, SPL, nDTW, CR from a simulator rollout
  (the honest H8-S gap). Where rollout is infeasible, mark N/A explicitly — never fabricate.

## 9. Acceptance criteria

H8-M does **not** proceed to training unless **all** hold:

- **Design-mode gate passes** — coordinate-disjoint splits, route-family balance, no reused
  decision frame / goal image / coordinate.
- **Recorded-mode gate passes** — real `/camera/image_raw` frames, scene-gate PASS per episode,
  mount 0.12, 0 collisions, no lower-frame occlusion, provenance clean per split.
- **Embedding distinctness passes** — cross-split CLIP/DINO cosine below `T_cross`, no within-split
  duplicates above `T_dup` (§5), calibration reported.
- **At least one true angular branch-choice family exists** — a validated T-junction/fork with
  expected angular separation ≥ 30° in the **held-out** split.
- **Each split has enough distinct decision frames** — target (to finalise at design time):
  **train ≥ 12, val ≥ 4, test ≥ 6** distinct decision frames, no split single-room or
  single-family; enough that training is not single-frame memorisation.

If any criterion fails: re-scope or defer — do not record, do not train.

## 10. Claim boundary

- **Still supervised learning** (imitation + auxiliary losses); **not reinforcement learning.**
- **Not full autonomy** — offline probes + bounded rollout only.
- **Not SOTA**; no "beats GNM/ViNT/NoMaD" claim.
- **Not promotion** — incumbent retained; `DIAGNOSTIC_ONLY_NOT_PROMOTED` until the gates below
  are met.
- **H8-M remains diagnostic** until **multi-seed** results **and** closed-loop Isaac evidence
  exist on a genuinely distinct, embedding-gated, junction-bearing set. A design/recorded/probe
  pass justifies further work; it does **not** justify a held-out visual, generalization, or
  navigation-quality claim.

## 11. Implementation sequence

Strictly gated; each step reviewed before the next; nothing here is authorised yet.

- **A. Route / zone design** — enumerate candidate rooms/junctions reachable by spawn-relocation
  within ±6 m; author decision frames per route family (§4); coordinate-disjoint split (§6).
- **B. Embedding distinctness search** — render candidate goal images; compute CLIP/DINO cosine;
  calibrate `T_dup`/`T_cross`; select a split-distinct set; publish matrices (§5).
- **C. Recorded-mode gate** — record the minimum real frames; scene-gate, mount 0.12, 0 collisions,
  occlusion, provenance (§9).
- **D. Small training run** — weights-only init, fresh optimizer, deterministic, seed logged;
  variants A / A+B / A+B+C / A+B+C+E plus the new distance-calibration and angular-supervision
  terms (§7). No checkpoint committed.
- **E. Action-probe and mismatched-goal gate** — branch-choice (angular + near/far), S, angle
  change, magnitude calibration, mismatched-goal ablation (§8).
- **F. Rollout if feasible** — simulator rollout for TL/NE/SR/OSR/SPL/nDTW/CR; N/A honestly where
  not feasible.
- **G. Review before any scale-up** — no 20/5/10, no closed-loop, no promotion, no push/tag until
  reviewed; multi-seed + closed-loop are prerequisites for any readiness claim (§10).

---

*No collection, training, promotion, push, tag, 20/5/10, closed-loop testing, or `CL_BOUND_XY`
change is authorised by this document. Planning only — stop after writing.*
