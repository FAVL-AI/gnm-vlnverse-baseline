# H8 — Larger Causal Goal-Conditioning Collection (DESIGN ONLY)

**Status:** design only. No collection, no training, no promotion, no push, no tag, no
20/5/10, no closed-loop Isaac testing. This document designs the larger H8 causal dataset
needed to test whether the goal-conditioned objective **generalizes** beyond the committed
2×2 prototype. It changes no committed evidence.

**Provenance.** Extends the committed chain
`… → 6199c79 (recorded gate) → d8ac839 (action-probe) → 8971cd7 (objective) → 85ada39
(loss-ablation)`. Verdict carried forward: `DIAGNOSTIC_ONLY_NOT_PROMOTED`, incumbent retained.

**Professor-safe framing:**
> The 2×2 prototype shows the objective can break goal-collapse, but the next scientific
> question is generalization. H8 now needs a larger causal collection with held-out decision
> frames, so the model cannot simply memorize two branch points.

---

## 1. Purpose

The committed 2×2 loss-ablation (`85ada39`) proved **objective viability**: on two shared
decision frames, the paired objective makes the predicted `[Δx, Δy]` respond to the goal image
(baseline change 1.5° → trained 58–75°, branch-choice 1.0). But with only **two** decision
frames a pass is fitting/memorisation, **not** generalizable goal-conditioned navigation. The
next dataset must contain **many distinct shared decision frames**, **multiple goals per
decision point**, and a **held-out decision-frame** split so the model cannot succeed by
memorising a handful of branch points. The scientific question shifts from *"can the objective
express goal use?"* to *"does goal use generalise to unseen decision frames?"*.

---

## 2. Dataset design principle (the invariant)

> **Every shared decision frame `o_d` must support ≥ 2 goal images that require different
> robot-frame `[Δx, Δy]` actions, separated by ≥ 30°.**

This is the property proven necessary/sufficient in the design-mode gate
(`h8_paired_branch_acceptance.py`) and confirmed on real images by the recorded-mode gate
(`h8_recorded_acceptance.py`). It is enforced at **build time** (before training) via the
committed action-separation label check, generalised to N goals per decision frame: any
decision frame whose goals do not induce ≥30°-separated targets is rejected.

---

## 3. Proposed scale (staged, NOT immediate 20/5/10)

| stage | decision frames | goals/frame | approx branch recordings | purpose |
|---|---|---|---|---|
| **H8-S** | 8–12 paired | ≥2 | ~16–24 | first generalization signal; cheap to record |
| **H8-M** | 20 train / 5 val / 10 test (=35) | ≥2 | ~70 | powered held-out generalization test |
| **H8-L** | expansion | ≥2–3 | TBD | only if H8-M passes all §10 gates |

Each branch recording is one route-follow episode (~12 min wall incl. Isaac startup, per the
prototype). H8-S ≈ 3–5 h; H8-M ≈ 14 h — recorded in bounded, resumable campaigns (per the
committed `hospital_h8_paired_branch_record.sh` discipline).

**Feasibility prerequisite (honest constraint).** The prototype confirmed that recording-frame
coordinates are **spawn-relative** and do **not** match the committed navmap frame, so routes
must be authored only from render-confirmed free coordinates. The proven free lobby region is
small (≈ x∈[−2.6, 1.2], y∈[−0.8, 1.0]); harvesting 8–12 *distinct* decision frames — let alone
35 — requires **extending the render-confirmed navigable map** (or resolving the navmap↔bringup
frame offset) before H8-M. This map-extension is a gating sub-task for H8-M/L, not H8-S.

---

## 4. Route families (≥7, causality-forcing)

All in the locked `hospital.usd` (scene-gate fail-closed), raised mount (`--camera-raise 0.12`):
1. **corridor T-junction** — straight vs turn (prototype design 1);
2. **same-start fork** — forward-left vs forward-right (prototype design 2);
3. **shared-corridor branch choice** — common corridor to a Y/T, goal selects the branch;
4. **same-room different object** — one room, distinct goal objects/anchors at different
   bearings;
5. **visually-similar but spatially-different goal** — two near-identical goal *images* at
   different locations (adversarial; punishes coarse scene-gist matching);
6. **near/far goal from the same approach** — same corridor direction, goal selects *how far*
   to travel / where to stop (tests the stop/temporal head's goal-dependence);
7. **stop-versus-go decision point** (if feasible) — one goal implies "stop here", another
   implies "continue"; directly probes goal-conditioned stopping.

Every family contributes both **matched** (o_d + its correct goal) and **mismatched**
(o_d + a wrong goal, same- and different-family) material for the §9 diagnostics.

---

## 5. Split rules

- **Held-out decision frames** — val/test decision frames (their `o_d` and goals) never appear
  in train. This is the primary anti-memorisation control.
- **Held-out goal pairs where feasible** — some test goals are goal images unseen at train time.
- **No route leakage** — reuse the committed firewall pattern (`build_h7r_dataset_root.py`):
  assert EPISODE-disjoint and ROUTE-disjoint across splits; **add decision-frame-id disjoint**.
- **No goal-image leakage** — a goal frame used as a *goal* in val/test must not appear as an
  *observation* frame in any train episode; enforce a **goal-image hash check** (extend the
  committed acceptance harness's recorded visual-distinctness check to a cross-split hash audit).
- **No repeated same-frame train/test reuse** — decision-frame ids and their extracted `o_d`
  hashes are unique to one split.
- **Route-family balance** — each split carries a comparable mix of the §4 families (report the
  per-family counts; no split may be dominated by one family).

---

## 6. Input–output contract (unchanged)

**Input:** current front RGB `I_t` (raised-mount `/camera/image_raw`); goal RGB `I_g`
(scene-aligned recorded frame); optional short temporal context (`context_size` recent frames).
**Output:** 2-D local action `[Δx, Δy]` (robot frame); stop / temporal-distance signal. The
goal image must causally influence **both** the action at decision frames and (family 6/7) the
stop signal. `o_d` is captured at the **pre-divergence approach heading** (the fix locked in
the recorded-mode gate), so it is a genuinely shared observation across a frame's goals.

---

## 7. Training objective (carry forward from `8971cd7` / `85ada39`)

Composite `L = λ_a·L_action + λ_c·L_contrastive + λ_b·L_branch + λ_d·L_dist (+ λ_e·L_swap)`:
- **A — action imitation** `||a_pred − a_target||` (necessary; on paired data already forces
  goal use, but can average-collapse at scale);
- **B — goal-contrastive** (separation + triplet repulsion at each shared o_d);
- **C — branch-classification auxiliary** (at a shared o_d the obs half of `fused` is constant,
  so the branch class must flow through `goal_feat` — strong goal-use signal);
- **D — capped stop/temporal loss** (`λ_d` small, so it does not crowd out action learning);
- **E — optional goal swap/dropout** — **re-tuned**: the prototype showed the naive
  zero-goal→mean-action form is counterproductive on tiny data; on H8 use *exclude
  dropped-goal samples from the action loss* (or a distinct "goal-unknown" target) rather than
  forcing them to the mean.

Training discipline (locked): weights-only `init_ckpt` from the retained incumbent, fresh
optimizer; **deterministic cuDNN/cuBLAS** (the reproducibility fix from `85ada39`); logged
seed; select checkpoints on H8 **validation** `loss_action`; **no checkpoint committed** without
explicit review.

---

## 8. Main benchmark metrics

Standing metrics (`gnm_vlnverse/evaluation/metrics.py`, Anderson 2018; success radius 3.0 m;
micro-averaged), via `scripts/gnm/06_evaluate.py` with **forced `--data-root`**:
**TL, NE, SR, OSR, SPL, nDTW, CR**. Invariants asserted: OSR ≥ SR; CR = 0 offline (meaningful
only under closed-loop). A goal-conditioning gain must **not** collapse basic navigation.

---

## 9. Required diagnostics

Reuse/generalise the committed instruments, reported on **held-out** decision frames:
- **offline action-probe** (`h8_action_probe.py`) — predicted `[Δx, Δy]` vs expected per goal;
- **goal-sensitivity score S** and **branch-choice accuracy** (from the probe);
- **mismatched-goal ablation** (`h7r_mismatched_goal_ablation.py`, generalised) — wrong goals
  must reduce performance;
- **endpoint shift under wrong goals** (signed toward the wrong goal, not jitter);
- **stop reliability** (and its goal-dependence for families 6/7);
- **metric audit** (OSR≥SR invariant + result-driven report builder; the `h7r_metric_audit`
  discipline — no hand-typed numbers);
- **leakage audit** (route + decision-frame + goal-image hash, cross-split);
- **scene gate** (per-episode `hospital.usd` identity, fail-closed);
- **camera validity** (raised mount 0.12, occlusion ≈ 0.0 %).

---

## 10. Acceptance gates (blocking, before any promotion)

1. **Design-mode gate passes** (`h8_paired_branch_acceptance.py`) — every decision frame's
   goals induce ≥30°-separated targets (build-time label check).
2. **Recorded-mode gate passes** (`h8_recorded_acceptance.py`) — the property holds on the
   actual recorded frames (scene gate, mount, distinct goals, ≥30°, 0 collisions).
3. **Action-probe passes on held-out decision frames** — branch-choice > chance (target ≥0.75),
   S increases meaningfully (≥0.5), predicted action changes toward the correct branch (≥15°).
4. **Mismatched-goal ablation shows goal dependence** — wrong goals reduce SR / move the
   endpoint (the opposite of the H7r route-imitation signature).
5. **Standard metrics improve or at least do not collapse** (TL/NE/SR/OSR/SPL/nDTW/CR).
6. **Multi-seed check passes** — the action-probe/ablation conclusion holds across ≥3 seeds
   (deterministic runs), not a single-seed artifact.
7. **Closed-loop Isaac remains the later promotion-grade gate** (Option B) — only after 1–6
   pass offline across seeds.

A held-out action-probe pass is the pivotal new evidence H8-S/H8-M must produce; it is the
generalization test the 2×2 prototype could not give.

---

## 11. Claim boundary

- **Supervised learning only** (imitation + auxiliary losses); **not reinforcement learning**.
- **Not full autonomy**; the offline gates test predicted actions, not closed-loop success.
- **No SOTA claim, no promotion.** Incumbent retained until §10 gates pass and are reviewed.
- **H8-S and H8-M are diagnostic** until closed-loop **and** multi-seed evidence exist; a
  held-out action-probe pass at H8-S is *preliminary* generalization evidence, not proof.

---

## 12. Implementation sequence (proposed; nothing started here)

A. **Design routes** — author the §4 families across (extended) render-confirmed free space;
   author decision-frame ids and goal sets.
B. **Run design acceptance** — `h8_paired_branch_acceptance.py` (generalised to N goals); reject
   frames failing the ≥30° label check. *Gate before recording.*
C. **Record small H8-S** — bounded resumable campaign (scene-gate, `--camera-raise 0.12`,
   collision-report, exact-PID cleanup, disk guards); convert rosbags → frames.
D. **Run recorded acceptance** — `h8_recorded_acceptance.py` on the real frames. *Gate before
   training.*
E. **Train loss ablation** — build the held-out-decision-frame data-root (extended firewall);
   train {A, A+B, A+B+C, A+B+C+E(re-tuned)} deterministically from the incumbent.
F. **Run action-probe + mismatched-goal gate** — on **held-out** decision frames; add the
   standard metrics; multi-seed.
G. **Decide** whether H8-M / 20-5-10 is justified — only on a held-out generalization pass.

Each step stops for review before the next; no promotion at any step; closed-loop Isaac and
any 20/5/10 remain gated behind a multi-seed held-out pass.

---

*No collection, training, promotion, push, tag, 20/5/10, closed-loop testing, or code is
authorised by this document. Design only — stop after writing.*
