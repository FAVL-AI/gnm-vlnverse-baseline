# H8 — Causal Goal-Conditioning Dataset Redesign (PLAN ONLY)

**Status:** planning only. No collection, no training, no promotion, no push, no tag, no
20/5/10 expansion, no commit until reviewed. This document specifies the *next* hospital
ImageNav dataset so that the goal image becomes **causal** to the predicted action, rather
than decorative. It does not change any committed H7r evidence.

**Provenance of this milestone.** Direct consequence of the committed H7r chain:
`ff71908` (H7r diagnostic training) → `689df9e` (scene-aligned goal-image check) →
`47d0d58` (mismatched-goal ablation). Current verdict on the H7r candidate:
`DIAGNOSTIC_ONLY_NOT_PROMOTED`, incumbent retained.

**Corrected claim carried forward (professor-safe):**
> The raised-mount H7r pilot improved the offline hospital diagnostic result, but the
> mismatched-goal ablation showed that the goal image was not causal. When the wrong goal
> image was supplied, the policy still followed nearly the same route. Therefore the
> current evidence supports supervised route/motion imitation under a clean hospital setup,
> **not** true goal-conditioned ImageNav yet.

---

## 1. Problem statement

H7r delivered a real, controlled result: on the raised-mount hospital pilot the candidate
reproduces the demonstrated route/motion pattern markedly better than the incumbent under
the offline Track-A diagnostic (held-out test SR 0.00 → 1.00, NE 15.43 m → 2.54 m). But the
mismatched-goal ablation (`47d0d58`) showed this improvement is **not** driven by the goal
image:

- Swapping the goal image (placeholder / same-family / hard different-family) moved the
  final stop by only **0.1–1.1 m** and **never diverted** the path toward the wrong goal.
- The single SR flip (turn_02 under a same-family goal) was a 3.0 m success-ring boundary
  crossing (NE 2.61 → 3.43 m), still on-route.
- Endpoint perturbation was **anti-correlated** with goal difficulty — the *hard*
  different-family mismatch perturbed *less* than the same-family one — i.e. the goal image
  enters the action head only as weak, non-semantic noise.

**Root cause.** The H1–H7r data regime is *one demonstrated route per start*. With a single
correct trajectory per start, a policy can minimise imitation loss by memorising the
route/motion from the observation stream alone; the goal image carries no additional
information the policy is forced to use. The dataset, not just the model, makes the goal
image ignorable.

**H8 objective.** Redesign the dataset so that **the goal image is the only signal that
disambiguates the correct action** at a decision point. If two episodes share a start (or a
shared corridor) but differ only in goal image and required action, the policy *cannot*
succeed by route memorisation — it must read the goal.

---

## 2. Dataset design rule (the core invariant)

> **Same (or near-identical) start observation must map to multiple different correct goals,
> and the correct action sequence must depend on the selected goal image.**

Concretely, for a decision point `d` with observation `o_d`:
- there exist ≥2 goals `g_i, g_j` reachable from `o_d` whose optimal next actions differ by
  more than a defined margin (e.g. branch left vs branch right, stop vs continue);
- the training set contains demonstrations `(o_d, g_i) → a_i` and `(o_d, g_j) → a_j` with
  `a_i ≠ a_j`;
- therefore any policy that ignores `g` incurs irreducible loss at `d`.

This is the property H7r lacked and is the single acceptance criterion for the H8 dataset
before any training is even attempted.

**Methodological caveat (must be designed around).** The current Track-A evaluator
(`gnm_vlnverse/evaluation/evaluator.py`) is *offline*: it rolls out predicted actions by
dead reckoning over each episode's **own fixed recorded frames** (`goal_idx = -1`; goal =
final recorded frame). Because the observation stream is fixed to one route, an offline
rollout cannot show a policy *diverting* onto a different branch even if it wanted to — the
frames it sees are always the demonstrated route. H8 therefore requires **one** of:
- **(A) Paired-branch offline design** — record, from the same start, the separate branch
  demonstrations, and at the shared decision frame evaluate whether the *predicted action*
  (not the integrated position) points toward the goal-consistent branch. Score the action
  head directly at the branch point, not just the end-of-route position.
- **(B) Closed-loop rollout in Isaac Sim** — the policy's chosen action determines the next
  observation, so a wrong goal can actually carry it onto the wrong branch and be penalised.
This choice is a required decision in the H8 build spec (see §7); (A) is cheaper and
reuses the existing offline harness with a branch-point action probe, (B) is the stronger
test and the eventual target. Recommended: build (A) first as the fast gate, keep (B) as
the promotion-grade gate.

> **DECISION (approved): Option A first.** The paired-branch offline action-probe is the
> approved **fast H8 design gate**, specified in
> `docs/research/H8_PAIRED_BRANCH_OFFLINE_GATE_SPEC.md`. Option B (closed-loop Isaac
> rollout) remains the later **promotion-grade** gate and is not started yet. The full
> 20/5/10 dataset is **not** collected until the Option A gate passes.

---

## 3. Route families (≥4, causality-forcing)

All families reuse the locked hospital scene (`hospital.usd`, scene gate fail-closed via
`m3pro_ros2_bringup.py --scene-gate`) and the raised camera mount (`--camera-raise 0.12`,
validated 0.0 % bottom-band occlusion). Each family is defined to *break* route
memorisation:

1. **same-start / different-goal** — identical spawn pose and identical first *k* frames;
   the goal image selects one of ≥2 terminal rooms. Correct action diverges only after the
   shared prefix. (Directly instantiates the §2 invariant.)
2. **shared-corridor branch choice** — a common corridor leading to a T-/Y-junction; the
   goal image (a view down the left vs right branch, or of the left vs right terminal) must
   select the turn. This is the canonical "does it read the goal at the junction" family.
3. **same-room / different-object goal** — one room, several distinct goal objects/anchors
   (e.g. reception desk vs vending bay vs doorway) at different bearings; the goal image
   selects which object to approach and stop at. Tests fine goal discrimination within one
   visual context.
4. **visually-similar / spatially-different goal** — two goals whose goal *images* look
   alike (two near-identical doorways/corridor ends) but sit at different locations. This
   is the adversarial family: it punishes policies that use only coarse scene gist and
   rewards genuine goal localisation. Doubles as the hard-negative mining source.

Each family must contribute both **matched** pairs (start + its correct goal) and
**mismatched** negatives (start + a wrong goal from the same and a different family), so the
ablation gate (§7) has in-distribution material to probe.

---

## 4. Train / val / test design

Splitting must prevent both route leakage *and* goal-image leakage, and must preserve the
same-start/different-goal structure inside each split:

- **Goal separation** — where geometry allows, hold out *goals* (terminal
  rooms/objects/anchors), not just episodes, so test goals are unseen at train time. Report
  explicitly which goals are seen vs unseen (some overlap is unavoidable for the
  same-room family; declare it).
- **Same-start/different-goal pairs kept within a split** — the disambiguation signal must
  exist *inside* train (so the model is forced to learn it) and *inside* test (so the gate
  can measure it). Do not scatter a pair across splits.
- **Hard mismatched-goal negatives** — every split carries the 4 ablation conditions'
  material (correct / same-family wrong / different-family wrong / placeholder).
- **No route leakage** — reuse the H7r firewall pattern (`build_h7r_dataset_root.py`):
  assert EPISODE-disjoint and ROUTE-disjoint across train/val/test; families may share a/b
  instances by design but never the same route id.
- **No goal-image leakage** — a goal frame used as a *goal* in test must not also appear as
  an *observation* frame in a train episode of a different goal; add an explicit goal-frame
  hash check to the firewall so no test goal image is memorisable from train observations.
- **Scene / camera integrity per episode** — carry `scene_gate_pass`,
  `camera_mount_raise_m = 0.12`, and occlusion check into every episode's metadata, as in
  the H7r pilot.

Sizing is deferred (this is design, not collection). The pilot-scale H8 build should be
large enough that each family has ≥1 matched pair per split; powering (episode counts,
multi-seed) comes only after the gate passes.

---

## 5. Input–output contract

Unchanged from the GNM/ViNT/NoMaD-family contract already used in this repo, stated
explicitly so H8 collection records exactly what the model consumes:

**Input**
- current front RGB image (raised-mount `/camera/image_raw`, hospital scene);
- goal RGB image (episode-specific goal frame; scene-aligned, from the recorded stream —
  never a re-render or procedural/occluded frame);
- optional short temporal context (the model's `context_size` recent frames).

**Output**
- 2-D local action `[Δx, Δy]` (robot-frame displacement), which the goal image **must**
  causally influence at decision points;
- a stop / temporal-distance signal (the model's distance head; stop when predicted
  temporal distance to goal falls below threshold). H8 must make the stop signal
  goal-dependent too — a wrong goal should change *where/whether* the policy stops.

Contract acceptance test: at a §3-family decision point, `[Δx, Δy]` under `g_i` and under
`g_j` must differ by more than the branch margin. If they do not, the collected pair does
not encode causality and is rejected at build time.

---

## 6. Metrics

**Main benchmark metrics** (`gnm_vlnverse/evaluation/metrics.py`, Anderson 2018 conventions;
success radius 3.0 m; micro-averaged):
- **TL** — trajectory length;
- **NE** — navigation error (final distance to goal, m);
- **SR** — success rate (final position within 3.0 m);
- **OSR** — oracle success rate (ever within 3.0 m; invariant OSR ≥ SR, asserted);
- **SPL** — success weighted by path length;
- **nDTW** — normalised dynamic time warping to the reference;
- **CR** — collision rate. *Honest caveat:* CR = 0 by construction in offline Track-A
  dead-reckoning; CR is only meaningful under closed-loop rollout (design option 4B) and
  must be reported as N/A whenever the offline harness is used.

**Diagnostics (the part that actually decides H8):**
- **mismatched-goal ablation** — the committed harness `scripts/gnm/h7r_mismatched_goal_ablation.py`,
  generalised to H8 families, is the primary causality probe;
- **endpoint shift under wrong goal** — but for H8, *signed toward the wrong goal*: a causal
  policy's endpoint should move **toward** the mismatched goal's location, not merely jitter;
- **goal-sensitivity score** — proposed operational definition:
  `S = (behaviour change induced by swapping to a wrong goal) / (behaviour change induced by
  a semantically farther wrong goal)` should be **≥ 1 and large** for a causal policy
  (farther goal ⇒ bigger change). H7r scored `S < 1` (anti-correlated) — the failure
  signature. Finalise the exact estimator (action-level KL / branch-choice accuracy at the
  decision frame) in the build spec;
- **branch-choice accuracy** (new, family-2/1 specific) — at the shared decision frame,
  fraction of episodes where the predicted `[Δx, Δy]` selects the goal-consistent branch;
- **stop reliability** — but conditioned on goal correctness (does a wrong goal change the
  stop decision?);
- **scene gate / leakage / camera validity** — carried as pass/fail integrity gates, as in
  H7r.

---

## 7. Required ablation gate (blocking, before any scale-up or promotion)

**Primary gate = Option A (approved):** the paired-branch offline action-probe, fully
specified in `docs/research/H8_PAIRED_BRANCH_OFFLINE_GATE_SPEC.md`. It holds the current RGB
observation fixed at a shared decision frame and tests whether the predicted 2-D action
`[Δx, Δy]` changes in the correct direction when only the goal image is swapped. Option B
(closed-loop Isaac rollout) is the later promotion-grade gate and is not started yet.

In addition, re-run the mismatched-goal ablation with **four** goal conditions on every H8
test episode, using the committed harness generalised to H8 families:
1. **correct** goal,
2. **same-family wrong** goal,
3. **different-family wrong** goal (hard),
4. **placeholder** goal.

**Pass criteria (a goal-conditioned policy MUST change behaviour under wrong goals):**
- SR(correct) high **and** SR(different-family wrong) materially **lower** (the policy fails
  or diverts when the goal is wrong) — the opposite of the H7r result;
- **branch-choice accuracy** high under correct goal, at chance under wrong goal, on
  families 1–2;
- **endpoint shift signed toward the wrong goal** (positive goal-attraction), not
  direction-agnostic jitter;
- **goal-sensitivity score S ≥ 1** and increasing with goal semantic distance.

If these do **not** hold, H8 remains route/motion-imitation dominated exactly like H7r →
`DIAGNOSTIC_ONLY_NOT_PROMOTED`, and no scale-up occurs. The gate is the same instrument
that correctly caught H7r; it is now a pre-registered acceptance test, not a post-hoc check.

Evaluation discipline (carried from prior locks): force `--data-root` in every eval run
(never trust checkpoint-embedded cfg); weights-only `init_ckpt` from the retained incumbent
with a fresh optimizer if/when training is later approved; select checkpoints on H8
validation `loss_action`.

---

## 8. Claim boundary

- **H8 is diagnostic** until it is powered by more episodes **and** multiple seeds; a pilot
  that passes the gate at small n is *preliminary goal-conditioning evidence*, not proof.
- **Do not claim full autonomous goal-conditioned navigation** until: (i) the mismatched-goal
  gate passes under the §7 criteria, (ii) the result holds across seeds, and (iii) it is
  demonstrated under closed-loop rollout (Option B), not offline dead reckoning alone.
- Offline Track-A remains a *supervised imitation diagnostic over recorded observation
  streams with action rollout / trajectory scoring* — **not** closed-loop autonomy. The H8
  milestone's whole purpose is to make the goal image causally affect the predicted 2-D
  action `[Δx, Δy]`; until the gate proves that, all language stays at
  "route/motion imitation under a controlled hospital diagnostic."
- Incumbent remains retained; nothing in H8 promotes or supersedes prior committed evidence
  until the gate passes and is reviewed.

---

## Next steps after this plan is reviewed (not started here)
1. **DONE — design option decided: Option A (paired-branch offline) approved as the fast
   gate**, specified in `docs/research/H8_PAIRED_BRANCH_OFFLINE_GATE_SPEC.md`. Option B
   (closed-loop) deferred to promotion-grade.
2. Author the H8 paired-branch route files + collection harness (reusing `--scene-gate`,
   `--camera-raise 0.12`, the converter, and the split firewall with the added goal-image
   leakage check **and** the build-time label action-separation check from the Option A spec).
3. Only then collect a small paired-branch pilot; run the Option A gate **before** any
   training decision; and only after a gate pass consider training, then Option B, then
   20/5/10 scaling.

*No collection, training, promotion, push, tag, or 20/5/10 expansion is authorised by this
document. Plan only — stop after writing.*
