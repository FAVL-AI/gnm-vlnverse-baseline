# Session A — Map extension and validation session plan

**This session creates no dataset episodes.** It exists to close the structural split-leakage
dependency and to supply the geodesic reference source that four locked metrics require.

**Authorisation:** not yet granted. This is a plan.

## 1. Why this must come first

The H8-S design gate currently reports `all_active_pass = true` but
`split_integrity_ok = false` → `design_ready_to_record = false`.

The cause is structural, not clerical. The confirmed-free coordinate set is exactly the waypoints of
the zero-collision recorded H7/prototype routes (`FEAS_TOL_M = 0.30`). The proven-free lobby is
`x ∈ [−2.31, 0.91]`, but the only navigable far-goals — `(1.0,−0.2)`, `(1.2,0.0)`, `(1.0,0.6)`,
`(1.0,0.4)`, `(0.9,−0.4)` — sit at or just beyond its `x_max`. Distinct decision frames are therefore
**forced** to reuse the same far-goals: `(1.0,−0.2)` appears in train (df01/df02/df05) *and* test
(df07); `(1.2,0.0)` in train (df08) *and* val (df06).

**A manifest edit cannot fix this.** Either the edit fails the feasibility check (no distinct free
coordinates remain) or it guts the held-out sets. The only resolution is to enlarge the
render-confirmed navigable map so physically distinct val/test goal locations exist.

Dependency chain: **H8-S capture → split-leak fix → map extension → Isaac.** The map extension needs
Isaac, so the first authorised Isaac session must be this one.

## 2. Frame-offset problem to resolve

Recording-frame coordinates are **spawn-relative** and do **not** match the committed navmap frame.
The render-confirmed reachable envelope (`hospital_h8_map_extension/h8_candidate_zones.json`) is
`x ∈ [−9.96, 3.99]`, `y ∈ [−0.76, 1.09]` in the bring-up frame; the *proven* lobby is much smaller.
Session A must either resolve the navmap↔bringup offset explicitly or declare the recording frame
canonical and re-express the map in it. Leaving two frames in play is how the current
`start_pose_declared` errors arose.

## 3. Objectives — all must produce evidence, none may produce a dataset episode

| # | Objective | Evidence artefact |
| --- | --- | --- |
| 1 | Verify `hospital.usd` identity | scene-identity gate record |
| 2 | **Compute and record the scene USD SHA-256** | `scene_usd_sha256` — no digest exists anywhere in the current corpus |
| 3 | Extend the render-confirmed navigable area beyond the proven lobby | `h8_navigable_map_v2.json` + render evidence per candidate cell |
| 4 | Resolve the navmap↔bringup frame offset | `h8_frame_alignment_report.json` |
| 5 | Produce a navmesh or equivalent geodesic source | `h8_navmesh_v1.*` + `navmesh_version` |
| 6 | Define candidate route families over the extended map | `h8_route_candidates_v2.json` |
| 7 | Compute route overlap and split-leakage metrics | `h8_split_leakage_analysis.json` |
| 8 | Confirm physically distinct val/test far-goal locations exist | `design_ready_to_record = true` on re-run |
| 9 | Render-confirm the 3 `REQUIRES_VALIDATION` branches | per-branch render evidence |
| 10 | Verify raised-camera visibility at the new mount | contact sheet, black-band fraction ≤ 0.01 |
| 11 | **1280×720 throughput and synchronisation check** | `h8_resolution_throughput_report.json` |
| 12 | Confirm contact telemetry availability and widen detector scope | `h8_contact_scope_report.json` |
| 13 | Confirm `/tf_static` is published and recordable | topic proof |

## 4. The 1280×720 throughput check (objective 11)

Non-dataset. Run the camera at 1280×720 in the hospital scene and measure:

- sustained publish rate (Hz) over ≥ 5 minutes, with variance and dropped-frame count;
- image↔pose↔command↔contact synchronisation offsets;
- wall-vs-sim ratio at this resolution (historical median was >3× at 640×480 — this will worsen);
- bytes per episode, extrapolated to H8-S (~50–110 GB expected) and H8-M;
- RTX render stability over a full episode duration.

**Decision rule.** If sustained rate ≥ 3 Hz with acceptable synchronisation and the storage budget
fits, 1280×720 is confirmed. If not, the resolution changes **only** by a written protocol amendment
recorded in `H8_HOSPITAL_DATASET_PROTOCOL_V2.md` §2 **before** collection. Never mid-collection.

## 5. Explicit prohibitions

- No dataset episode is created. No `episode_manifest.json` is emitted.
- No goal image is captured (that is Session C).
- No route is recorded for training (that is Session D).
- No training or inference runs.
- No historical bag is modified.
- Nothing is committed, pushed or tagged without separate review.

## 6. Exit criteria

Session A succeeds only if it produces, in order: the scene digest; an extended, render-confirmed
navigable map; a resolved frame; a versioned navmesh; a leakage-clean candidate split with physically
distinct val/test goals; a passing `design_ready_to_record`; and a 1280×720 throughput verdict.

If the map cannot be extended enough to give distinct val/test far-goals, that is a **legitimate
negative result** and must be reported as such — the honest alternatives are then to scope H8-S
train-only with no held-out goal-image claim (previously rejected as too weak), or to source a
different scene region. It must not be resolved by reusing coordinates across splits.

## 7. Preconditions

Disk ≥ 100 GB free (re-check against the 1280×720 estimate); Isaac Sim importable; scene-identity gate
armed and fail-closed; bounded per-episode timeout wrapper with return-code capture — never
process-pattern kills; explicit written authorisation from Frank.
