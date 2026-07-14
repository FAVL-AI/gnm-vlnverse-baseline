# H8 — Paired-Branch Offline Action-Probe Gate (SPEC, Option A)

**Status:** specification only. No collection of the full 20/5/10 dataset, no training, no
promotion, no push, no tag, no closed-loop Isaac testing. This spec defines the **fast**
H8 causality gate (Option A). Option B (closed-loop Isaac rollout) remains the later
promotion-grade gate (§7). Companion to `docs/research/H8_CAUSAL_GOAL_CONDITIONING_PLAN.md`.

**Decision recorded:** Option **A** approved as the fast H8 design gate.

---

## 1. Why A is needed (and what it can / cannot prove)

The current Track-A offline evaluator (`gnm_vlnverse/evaluation/evaluator.py`) rolls out
predicted actions by dead reckoning over each episode's **own fixed recorded frames**
(`goal_idx = -1`; goal = final recorded frame). Because the observation stream is fixed to
one demonstrated route, an offline rollout **cannot** show the robot physically diverting
onto a *different* branch — the frames it sees are always the demonstrated route. This is
exactly why the H7r mismatched-goal ablation could only measure a small endpoint jitter,
not a divert.

But the offline setting **can** answer the causal question directly, without any physical
rollout, by probing the model's *instantaneous prediction*:

> Hold the current RGB observation **fixed** at a shared decision frame, change **only** the
> goal image, and measure whether the predicted 2-D action `[Δx, Δy]` changes in the correct
> direction.

If the same observation with goal A yields a left-branch action and with goal B yields a
right-branch action, the goal image is causal to the action — proven at the level of the
network's output, independent of any rollout artefact. If the action does not change, the
policy is route/motion-imitation dominated (the H7r signature). This is a clean, cheap,
deterministic gate that reuses `evaluator.predict(obs, goal) -> (dist_pred, [Δx, Δy])`
unchanged.

**Scope caveat.** Option A proves *the goal image changes the predicted action at the
decision frame*. It does **not** prove closed-loop physical success (no re-simulation, no
collisions, CR not measurable). Full autonomy claims require Option B.

---

## 2. Paired-branch design

The unit of the gate is a **branch point**, not an episode:

- **same start or same approach corridor** — a spawn pose or corridor whose approach frames
  are shared across the paired demonstrations;
- **shared current RGB decision frame `o_d`** — a single fixed observation captured at the
  junction, used identically across goal conditions (only the goal image varies; the
  observation does not);
- **two or more possible goal images `g_A, g_B, …`** — scene-aligned goal frames (from the
  recorded raised-mount `/camera/image_raw` stream; never re-renders / procedural /
  occluded), each corresponding to a distinct reachable terminal (left room vs right room,
  desk vs doorway, etc.);
- **different correct action per goal** — the demonstrated action at `o_d` differs by more
  than a margin between branches (branch-left vs branch-right; or approach-vs-stop).

Collection records, per branch point:
`o_d` (single shared decision frame), `{g_i}` (goal image per branch), `{a_i*}` (demonstrated
ground-truth action at `o_d` for each branch), the branch geometry (bearing to each goal),
and integrity metadata (`scene_gate_pass`, `camera_mount_raise_m = 0.12`, occlusion check).

To obtain a genuinely shared `o_d`: spawn from the same pose and record each branch
demonstration; take `o_d` from the shared prefix (the last frame before divergence). The
same `o_d` frame is then paired with every goal image at probe time, so the observation is
byte-identical across conditions by construction.

---

## 3. Input–output test

For each branch point `d` with shared observation `o_d` and goals `g_A, g_B`:

```
predict(o_d, g_A) -> (dist_A, a_A),   a_A = [Δx_A, Δy_A]
predict(o_d, g_B) -> (dist_B, a_B),   a_B = [Δx_B, Δy_B]
```

**Requirement:** the predicted 2-D action must change in the **correct direction** when the
goal image changes — `a_A` points toward branch A's goal, `a_B` toward branch B's goal.
Same current RGB frame + goal A → action A; same current RGB frame + goal B → action B.

A route/motion-imitation policy will predict `a_A ≈ a_B` (goal ignored). A goal-conditioned
policy will predict `a_A` and `a_B` separated toward their respective goals.

---

## 4. Build-time label acceptance test (before any training)

The dataset must be proven causal **from the labels alone**, before a model is trained, so
we never train on a branch point that is secretly route-solvable:

For each branch point, from the demonstrated ground-truth actions `a_A*, a_B*` at `o_d`:
- **action-separation check:** `angle(a_A*, a_B*) ≥ θ_margin` (proposed θ_margin = 30°),
  i.e. the two goals genuinely require different actions at the shared frame;
- **goal-distinguishability check:** `g_A` and `g_B` are distinct goals (different terminal
  locations; distance between goal positions ≥ a floor), and for the visually-similar
  family they are confirmed to differ in location despite image similarity;
- **shared-observation check:** `o_d` is the same frame (hash-identical) across the paired
  conditions.

A branch point that fails the action-separation check is **rejected at build time** — it
does not encode causality and must not enter train/val/test. This is the H8 analogue of the
H7r firewall, extended from leakage to *causality*.

---

## 5. Metrics

**Primary gate diagnostics (computed at the decision frame, from `predict`):**
- **action-angle difference** — `Δθ = angle(a_A, a_B)` between predicted actions under the
  two goals; a causal policy produces large `Δθ` matching `angle(a_A*, a_B*)`;
- **endpoint shift** — displacement of the short predicted step / integrated stub under the
  swapped goal, **signed toward the intended goal** (not direction-agnostic jitter);
- **branch-choice accuracy** — fraction of branch points where the predicted action selects
  the goal-consistent branch (correct goal → correct branch); at-chance under wrong goal;
- **goal-sensitivity score S** — `S = (action change induced by a semantically farther goal)
  / (action change induced by a nearer goal)`; a causal policy scores `S ≥ 1` and rising
  with goal semantic distance. (H7r scored `S < 1` — the failure signature.) Finalise the
  exact estimator — action-vector cosine distance or branch-choice KL — in the build spec;
- **stop-probability change** (where applicable) — does a wrong goal change the stop /
  temporal-distance head output at `o_d`?

**Standard navigation metrics (reported later, once a policy is trained and rolled out):**
TL, NE, SR, OSR, SPL, nDTW, CR. Honest caveat: under Option A / offline, CR = 0 by
construction and is reported N/A; CR becomes meaningful only under Option B closed-loop.

---

## 6. Pass / fail rule

**PASS (goal-conditioned):** at the decision frame, the predicted action **changes** under
different goals in the correct direction —
- branch-choice accuracy high under the correct goal (and near chance under wrong goal),
- action-angle difference `Δθ` large and aligned with the label separation,
- goal-sensitivity `S ≥ 1` and increasing with goal distance,
- signed endpoint shift toward the intended goal.

**FAIL (route/motion-imitation dominated):** the policy keeps predicting essentially the
**same action** regardless of the goal image (`a_A ≈ a_B`), branch-choice accuracy at chance,
`S < 1`. This is the H7r outcome; if H8 reproduces it, status stays
`DIAGNOSTIC_ONLY_NOT_PROMOTED`, no scale-up, no promotion.

The gate is blocking: it must PASS before any 20/5/10 collection, any promotion, or any move
to Option B.

---

## 7. Relationship to Option B (later, promotion-grade)

Option A proves the goal image changes the *predicted action* at decision points — necessary
but not sufficient for autonomy. **Option B — closed-loop Isaac rollout**, where the policy's
chosen action determines the next observation so a wrong goal can physically carry the robot
onto the wrong branch and be penalised — remains the **promotion-grade** gate. Sequence:
1. Build the paired-branch offline set and run the **A** gate (this spec).
2. Only on an **A** pass: consider a small training run, then re-run A on the trained policy.
3. Only on a trained-policy **A** pass: build the **B** closed-loop harness and run it across
   seeds before any promotion or 20/5/10 scale-up.

CR, physical divert, and full autonomous goal-conditioned navigation claims are reserved for
a **B** pass. Nothing in Option A promotes or supersedes the retained incumbent.

---

*No collection, training, promotion, push, tag, or closed-loop testing is authorised by this
document. Spec only — stop after writing and after updating the H8 plan.*
