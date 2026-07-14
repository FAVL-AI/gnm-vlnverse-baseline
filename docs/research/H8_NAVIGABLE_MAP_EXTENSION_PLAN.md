# H8 — Navigable Map Extension Plan (PLAN ONLY)

**Status:** plan only. No collection, no training, no promotion, no push, no tag, no 20/5/10,
no closed-loop Isaac testing. This document plans how to extend the *render-confirmed
navigable* hospital map so H8-S / H8-M can be built with **leakage-clean held-out goal
locations**. It changes no committed evidence and authorises no recording.

**Provenance.** Follows the committed chain
`… → 85ada39 (loss-ablation) → 248d175 (causal collection design) → 0d92459 (H8-S route design
feasibility audit)`. Verdict carried forward: `DIAGNOSTIC_ONLY_NOT_PROMOTED`, incumbent retained.
This plan is the **Resolution 2** path selected after the H8-S feasibility audit (map extension
first; *not* a train-only H8-S).

**Professor-safe framing:**
> The H8-S design did not fail because the causal idea was wrong. It failed because the
> currently proven navigable hospital space is too small to create a leakage-clean held-out
> goal-image split. The correct next step is not train-only scaling; it is extending the
> verified navigable map so validation and test goals are physically distinct from training
> goals.

---

## 1. Current blocker

The only region proven collision-free by successfully-recorded routes (8 H7 + 4 H8-prototype
episodes, all 0-collision) is a small lobby patch, approximately:

> **`x ∈ [−2.6, 1.2]`, `y ∈ [−0.8, 1.0]`** (hospital.usd **bringup frame**; robot spawns at
> world origin, coordinates are spawn-relative).

This envelope is too small to support leakage-clean **train / val / test** goal-image splits:
distinct decision frames are forced to reuse the same far-goal coordinates, so a goal image used
in train reappears as a goal in val/test. A root technical cause is the **navmap↔bringup frame
offset**: the committed navmap (`assets/experiments/hospital_h7_collection/navmap/`, 280×280,
x/y∈[−7,7]) is in a *different* frame than the recording bringup, so it cannot be used to certify
new free coordinates — every route must currently be authored only from already-recorded
coordinates, which is what caps the usable space.

---

## 2. Evidence (why this plan exists)

From the committed H8-S design feasibility audit (`0d92459`,
`assets/experiments/hospital_h8_s_causal_routes/`):

- **Per-frame geometry/action gate: PASS** for all 8 active decision frames (branch frames
  ≥30° action-angle separation; stop frames ≥0.6 m stop-distance separation). 7/7 route
  families covered. Leakage-group→split disjointness clean.
- **Split-integrity audit: FLAGGED.** Two goal coordinates are reused as goals across splits:
  `(1.0, −0.2)` in **train and test**; `(1.2, 0.0)` in **train and val** — goal-image leakage
  per `H8_CAUSAL_COLLECTION_DESIGN.md` §5.
- Therefore **`design_ready_to_record = NO`**, and the held-out action-probe
  (`H8_CAUSAL_COLLECTION_DESIGN.md` §10 gate 3) **cannot be earned inside the current proven
  space**. The audit's recommended resolution is exactly this map extension.

The failure is a **space-size / feasibility** problem, not a flaw in the causal decision-frame
design. Geometry is sound; the map must grow.

---

## 3. Required map-extension objective

Find **additional physically valid, render-confirmed, collision-free** hospital locations —
each with a stable shared decision frame `o_d` and ≥2 goals — sufficient to assign goal images
to splits with **no coordinate and no goal-image reuse across train/val/test**. Concretely,
harvest distinct goal locations for:

- **train goals** — the bulk of decision frames and their paired goals;
- **validation goals** — goal images/locations disjoint from train (for checkpoint selection);
- **test goals** — held-out goal images/locations disjoint from train and val;
- **hard-negative goals** — plausible *wrong* goals (same-family and different-family) for the
  mismatched-goal ablation, physically valid but not the correct branch;
- **visually-similar-but-spatially-distinct goals** — look-alike goal *images* at different
  locations (family 5 / DF10), to punish coarse scene-gist matching.

Sizing target (from `H8_CAUSAL_COLLECTION_DESIGN.md` §3): enough distinct decision frames to
first re-enable a leakage-clean **H8-S** (8–12 frames), then scale toward **H8-M** (20/5/10 = 35).
Priority is *coordinate distinctness across splits*, not raw count.

---

## 4. Validation method (per candidate zone — all must PASS)

Each candidate zone is a proposed decision frame `o_d` + its goals. A zone is accepted only if
**every** check passes; otherwise it is rejected or deferred (§5). Reuses the locked pipeline
(`m3pro_ros2_bringup.py --scene hospital --scene-gate --camera-raise 0.12`, exact-PID cleanup,
disk guards, per-episode timeout wrappers — no process-pattern kills):

1. **Scene gate PASS** — per-episode `hospital.usd` identity manifest, fail-closed
   (`assets/experiments/hospital_h7_scene_gate/{EPISODE_ID}.json`, derive pass from `all(checks)`).
2. **Raised mount 0.12** — `--camera-raise 0.12` applied; mount height recorded.
3. **Render-visible hospital context** — the goal/decision frames show real hospital structure
   (not void/skybox), on the real `/camera/image_raw` stream (not the replicator annotator;
   `--capture-goal` is *not* usable — it bypasses the scene gate).
4. **No black lower-frame occlusion** — lower-frame occlusion ≈ 0.0 %; no camera-clipped/void
   band (the near-clip and unlit-stage hazards).
5. **No collision / contact in drive validation** — a route-follow episode reaches the zone with
   `--collision-report` showing 0 collisions and `route_completed=True`.
6. **Stable shared decision frame** — `o_d` extracted at the **pre-divergence approach heading**
   (the recorded-gate fix), genuinely shared across the zone's goals.
7. **Unique goal-image hash** — each goal frame's perceptual hash is unique; no goal-image hash
   collides with any train observation or any other split's goal (cross-split hash audit).
8. **No goal-coordinate reuse across splits** — the zone's assigned split does not reuse any
   `o_d` or goal coordinate already used in another split (the exact check that flagged H8-S).

A zone that passes 1–8 and clears the committed **design-mode gate** (≥30° branch separation /
≥0.6 m stop separation) is added to the extended navigable envelope.

**Optional root-cause sub-task (recommended, not required):** resolve the **navmap↔bringup
frame offset** by fitting the transform from the recorded 0-collision waypoints to the navmap
grid. If recovered, the navmap becomes a *pre-filter* for candidate coordinates before drive
validation, sharply reducing wasted episodes — but drive validation (checks 1–8) remains
authoritative.

---

## 5. Outputs (produced by executing this plan later — none produced here)

To live under `assets/experiments/hospital_h8_map_extension/` (created only when execution is
approved):

- **Candidate zone list** — proposed `o_d` + goals per zone, target split, target family,
  intended role (train / val / test / hard-negative / look-alike).
- **Render contact sheets** — real `/camera/image_raw` thumbnails per candidate (decision frame
  + each goal), for visual confirmation of hospital context and distinctness.
- **Drive-validation table** — per zone: scene-gate pass, mount height, collision count,
  route_completed, occlusion %, approach-heading `o_d` yaw, goal-image hashes.
- **Updated navigable coordinate envelope** — the extended render-confirmed free region
  (superseding the small lobby patch), in the bringup frame, with provenance per coordinate.
- **Rejected / deferred zones** — with the failing check(s) recorded honestly (no silent drops).
- **Recommendation for revised H8-S route design** — a re-authored decision-frame set that the
  H8-S design gate (`h8_s_route_design_acceptance.py`) certifies with
  `design_ready_to_record = YES` (per-frame gate PASS **and** split-integrity PASS).

Each output is evidence-only and committed only after review; no dataset, checkpoint, weight,
rosbag, or trajectory is committed.

---

## 6. Stop condition

**Do not record H8-S** (and do not train, promote, push, tag, start 20/5/10, or start
closed-loop Isaac) **until this map-extension plan has identified enough distinct,
leakage-clean goal locations** — i.e. until a re-run of `h8_s_route_design_acceptance.py` on the
re-authored decision frames reports **`design_ready_to_record = YES`** (per-frame geometry gate
PASS *and* split-integrity PASS, with zero cross-split coordinate/goal-image reuse).

Until then the status remains `DIAGNOSTIC_ONLY_NOT_PROMOTED`, incumbent retained.

---

## 7. Claim boundary

- Planning only — no images rendered, no episodes recorded, no model run, no map yet extended.
- Supervised-learning research context; not RL, not full autonomy, no SOTA claim, no promotion.
- The map extension is a **feasibility enabler** for a leakage-clean held-out generalization
  test; it does not itself constitute a generalization result.
- Every downstream step (candidate render → drive-validate → re-author H8-S → recorded gate →
  train ablation → held-out action-probe + mismatched-goal gate) stops for review before the
  next; closed-loop Isaac and any 20/5/10 remain gated behind a multi-seed held-out pass.

---

*No collection, training, promotion, push, tag, 20/5/10, closed-loop testing, or map recording
is authorised by this document. Plan only — stop after writing.*
