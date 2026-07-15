# H8-M Re-scoping After the Depth-Aware Junction Scan

**Status: decision note (validation-only).** No collection, no training, no promotion, no
push, no tag, no 20/5/10, no closed-loop Isaac testing; `CL_BOUND_XY` unchanged. This note
records a scope decision only; it makes no benchmark, autonomy, or SOTA claim.

**Evidence reference:** commit `ff93e46` — *Add H8-M depth-aware junction scan evidence*
(`assets/experiments/hospital_h8_m_junction_scan/`: manifest, report, table, contact sheets,
render metadata; harness `scripts/gnm/h8m_junction_scan_render.py`,
`scripts/gnm/h8m_junction_scan_analyze.py`). Builds on the H8-S limited pilot (`dfae1f6`) and
the H8-M design/embedding evidence (`5cba15d`, `b5cef81`, `623ee8d`, `509bcc0`).

---

## 1. What changed

The depth-aware junction scan showed that the current `hospital.usd` safe envelope does **not**
contain a render-valid T-junction/fork for angular branch-choice. Eight in-envelope candidates
(corridor T-junctions, reception fork, reception cross, corridor-end fans) were each rendered as
decision + goal A + goal B with depth; the hospital scene-identity gate passed (1909 hospital
prims, no forbidden landmarks). Under the depth-aware gate, **all eight candidates classified as
`WALL_ONLY` and zero render-valid junctions were found**. No candidate has two divergent, open
branches: every candidate branch view faces a wall or furniture within ~0.3–2.9 m median central
depth, and the single open branch (`jc_recep_cross` goal B, ~7.7 m) is paired with a blocked
branch. This corroborates the earlier H8 finding that the reachable envelope is a single straight
corridor plus reception/lobby, not a branching layout.

## 2. Why RGB-only was insufficient

RGB / luma / DINO can make textured walls look like valid, distinct branches: two *different*
walls read as "render-valid + visually distinct." A pixel-validity-only gate (decision + both
goal views render-valid, angular separation ≥ 30°) would have **falsely accepted 7 of 8
candidates** as apparent junctions. Navigability is **geometric, not only visual**, so depth
openness is required: using `distance_to_image_plane`, a real open branch must show a median
central depth ≥ 3.0 m, while a wall-like view (< 2.0 m) is `WALL_ONLY`. Adding this criterion
reclassified all 7 false positives to `WALL_ONLY`. This is the same "pixel validity ≠
navigability" lesson as the earlier reception-junction black-void fix, one level deeper.

## 3. Corrected conclusion

`hospital.usd` should remain a **distance/stop-conditioning and hospital-scene visual-validity**
environment. It is **not** the angular branch-choice environment: no angular branch-choice claim
can be made in this hospital scene under the current safe ±6 m envelope.

## 4. H8-M re-scope

Split H8-M into two independent tracks:

### Track A — Hospital distance/stop-axis track
- Scene: `hospital.usd` (the verified, scene-gated hospital).
- Raised camera mount (~0.12 m above the 0.35 m base), level horizon.
- Hospital scene-identity gate (fail-closed) on every render/rollout.
- Objective: **distance / stop conditioning** only.
- **No angular branch-choice claim.**
- Standard navigation metrics reported **only where a rollout actually exists** (no offline
  fabrication).
- Diagnostics remain **limited** and clearly scoped (as in H8-S).

### Track B — Angular branch-choice track
- **A different scene is required** — one that actually contains a real corridor fork / T-junction.
- Must pass **render-validity + depth openness** (both branches open, median central depth
  ≥ 3.0 m) before anything else.
- Must pass **embedding distinctness** (the two branches are genuinely different corridors, not
  the same wall twice).
- **Then** drive validation in that scene.
- **Then** action-probe / training diagnostics.
- No step is skipped and no earlier gate is weakened to "make it fit."

## 5. Claim boundary

- **No** full goal-conditioned ImageNav claim from `hospital.usd` alone.
- **No** strong held-out visual benchmark from the current hospital envelope.
- **No** SOTA claim.
- **No** promotion (`DIAGNOSTIC_ONLY_NOT_PROMOTED`; incumbent retained).
- **No** autonomy claim.

## 6. Next recommended action

Search/select an additional scene that contains a real corridor fork / T-junction for the
angular branch-choice track (Track B), while preserving `hospital.usd` as the hospital
distance/stop-axis track (Track A). Do not resume searching the hospital envelope for a junction
unless a new, validated map/room-access path is established first.

---

## Professor-safe summary

The depth-aware junction scan showed that the current verified hospital envelope does not contain
a usable fork or T-junction. RGB-only checks falsely identified textured walls as possible
branches, but depth openness corrected that. Therefore, hospital.usd remains useful for
hospital-scene stop/distance diagnostics, while angular branch-choice evidence must move to a
scene that actually contains a real junction.
