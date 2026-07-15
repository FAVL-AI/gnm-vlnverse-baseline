# H8-M Track-B Scene Scouting Report (INVENTORY ONLY)

**Status: planning/inventory only.** No render, no collection, no drive-validation, no training,
no recording, no promotion, no push, no tag, no 20/5/10, no closed-loop Isaac testing;
`CL_BOUND_XY` unchanged. This report turns the Track-B scouting plan's generic scene **types**
into an **exact, reachability-checked candidate asset shortlist**. It authorises no rendering.

**References:** re-scope plan commit `1a944cb` (`docs/research/H8_TRACK_B_SCENE_SCOUTING_PLAN.md`);
re-scope decision commit `670219e`; depth-aware junction-scan evidence commit `ff93e46`.

## Method

1. Inventoried repo-local scene `.usd/.usda` assets and the repo's own Isaac asset-mapping
   scripts (`scripts/gnm/probe_isaac_assets.py`, `scripts/isaaclab/load_nvidia_assets.py`).
2. For the junction-capable candidate types (office, warehouse, indoor junction) resolved the
   **exact** NVIDIA Isaac stock-environment asset URLs on the **same S3 delivery path that
   `hospital.usd` itself loaded from** this session (proven reachable).
3. Confirmed each exact URL with an HTTP **HEAD** request (status + size) — **no body download,
   no render, no collection**.

## What was found

- **Repo-local scenes are unsuitable.** The only local non-hospital scene, `custom_vln_office/
  scene_layout.usda`, is a single open 16×10 m office room (desks/chairs/one partition) with **no
  corridor fork or T-junction**. `assets/isaac/tracka_hospital_replay_stage.usda` just references
  `hospital.usd` (the already-junction-incapable hospital domain). Kujiale scenes are single
  rooms. None can host an angular branch-choice.
- **Three exact, reachable junction-capable candidate assets exist** (Isaac stock environments,
  same delivery path as hospital, already enumerated in repo scripts):
  - `office_isaac` — `…/Office/office.usd` — HTTP 200, 256 KB — office corridors/rooms.
  - `warehouse_simple` — `…/Simple_Warehouse/warehouse.usd` — HTTP 200, 1.6 MB — aisle grid.
  - `warehouse_full` — `…/Simple_Warehouse/full_warehouse.usd` — HTTP 200, 6.8 MB — larger aisle grid.
- **Unavailable at this version:** `Office/Office.usd` (404; the lowercase `office.usd` is the
  correct 200), `Modular_Warehouse/Modular_Warehouse.usd` (404).
- **`hospital_alt_wing` is BLOCKED** — no independently-validated alternate hospital area exists;
  do not re-search the hospital envelope without a new validated map/room-access path.
- **`synthetic_fork_fallback` does not exist** — it would require authoring and is **diagnostic-
  only**; it must never be presented as hospital or real-world evidence.

## Honesty boundary on "expected" fields

Reachability (HTTP 200) means the asset **file exists**, not that it contains a render-valid
junction. Every candidate's junction location, goal A / goal B regions, and action-angle
separation are **UNVERIFIED and TBD by a later bounded render-scan**; the values recorded are
design targets or hypotheses, **not measurements**. No coordinates were fabricated. This is the
same discipline that caught the hospital false positives: pixel/asset existence ≠ navigability.

## Decision rule (applied)

The plan's rule: *if 1–3 exact local assets are suitable, recommend them for the next bounded
render scan; if none, recommend asset acquisition/scene creation instead of rendering random
scenes; if only a synthetic fork exists, label it diagnostic-only.*

**Outcome:** **three** exact candidate assets are identified and reachability-checked, so the
condition "exact candidate scene assets already identified and explicitly listed" is met and the
next step is a **bounded render-scan on the top candidates** — no asset acquisition/scene creation
is required, and no synthetic scene is used. Recommend the render-scan proceed on **`office_isaac`
(primary)** and **`warehouse_simple`**, holding **`warehouse_full`** as secondary. `hospital_alt_
wing` stays blocked; `synthetic_fork_fallback` stays a labelled diagnostic-only fallback.

**Important caveat:** these three are cloud-delivered Isaac **stock** environments (reachable via
the proven hospital delivery path), not repo-local files. They are exact and enumerable, but their
junction-validity is unproven until the render-scan runs.

## Recommended next step (separate, gated — NOT authorised here)

A **bounded render-scan** on `office_isaac` and `warehouse_simple`, mirroring the hospital
junction-scan method: scene-identity/parity check → decision + goal A + goal B renders with depth
→ **render-validity gate + depth-openness gate (median central depth ≥ 3.0 m on both branches)
first**, before any embedding-distinctness, drive, or training work. Expected primary risks:
office = interior lighting/render-validity; warehouse = aisle **visual similarity** (embedding-
distinctness may fail even if depth is open).

## Claim boundary

- Planning/inventory only. **No render evidence. No drive evidence. No model evidence. No
  benchmark evidence. No promotion.**
- Reachability ≠ junction; candidate junctions are UNVERIFIED.
- Track B remains diagnostic until multi-seed and closed-loop evidence exist: no SOTA, no
  promotion, no full autonomy claim. `CL_BOUND_XY` unchanged; incumbent retained.

## Artifacts

`assets/experiments/hospital_h8_track_b_scene_scouting/`: `track_b_candidate_assets.json`,
`track_b_scene_scouting_table.md`, `track_b_scene_scouting_report.md`,
`track_b_render_scan_readiness.json`.
