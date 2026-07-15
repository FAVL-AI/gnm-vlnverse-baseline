# H8-M Track-B Scene Source Shortlist (SOURCING ONLY)

**Status: sourcing/inventory only — no render, no scan, no drive, no train.** Junction geometry is
**`UNVERIFIED_UNTIL_RENDER_SCAN`** for every candidate; nothing is claimed from a filename or asset
type. Governed by `docs/research/H8_TRACK_B_SCENE_SOURCING_REQUIREMENTS.md` (commit `27c4110`).

> **No real T/Y/cross junction, no angular-branch training. Scene sourcing is now the blocker, not
> the model.**

## Already failed — do NOT re-scan

| asset | verdict | evidence | note |
|---|---|---|---|
| `hospital` | FAILED | `ff93e46` | no junction in safe ±6 m envelope; Track-A distance/stop-axis only |
| `office_isaac` | FAILED | `21444e3` | open bullpen; under-lit; no confirmed junction |
| `warehouse_simple` | FAILED | `21444e3` | open hall; `p32` open-floor false positive |
| `warehouse_full` | FAILED | `4e919ef` | open floor + straight parallel aisles; `p13` straight-aisle false positive downgraded |

## Shortlist (candidates for the next bounded render-scan)

| asset_id | availability | scene type | junction? | divergence | lighting risk | open-floor FP risk | wall-only FP risk | real/synthetic | render-scan? | role |
|---|---|---|---|---|---|---|---|---|---|---|
| `warehouse_multiple_shelves` | HTTP 200, 2.3 MB | warehouse, multiple shelf rows | UNVERIFIED (could form cross-aisles; sibling `warehouse_full` had only straight aisles) | ~90° **if** a cross-aisle exists | LOW–MED | **HIGH** | MED | real-world-like | **YES** | **PRIMARY** |
| `synthetic_diagnostic_fork` | NOT YET BUILT | authored T/Y/cross corridors | GUARANTEED by construction (if built to spec); still verify by render-scan | designable ≥90° (T/cross) / ~60° (Y) | LOW | LOW | LOW | **SYNTHETIC_DIAGNOSTIC_ONLY** | YES (if primary fails) | **BACKUP** |

## Rejected sources (with reason)

- `warehouse_with_forklifts.usd` — HTTP 200 but only **14 KB** (a prop/overlay stage, not a navigable scene).
- `simple_room.usd` — a single furnished room (no corridor/junction).
- `Grid/default_environment.usd`, `Grid/gridroom_black.usd` — bare grids / small grid room (no corridors).
- `Jetracer/jetracer_track_solid.usd` — a driving **loop track** (curves, not a corridor T/Y/cross branch-choice).
- `Office/Office.usd`, `Modular_Warehouse/Modular_Warehouse.usd` — **404** at this Isaac 5.1 root.
- Repo-local `assets/custom_vln_office/scene_layout.usda` (single open room), `kujiale_*/scene.usda` (single rooms) — no fork.

## Decision

- **Primary for the next bounded render-scan:** `warehouse_multiple_shelves.usd` — **the only
  untried junction-plausible real-world-like asset** (reachable HTTP 200) whose multi-shelf layout
  *could* form a cross-aisle. **Honest prior: LOW** (its larger sibling `warehouse_full` had only
  straight parallel aisles). This is a single, targeted test of the multi-shelf hypothesis —
  **not** resumed ad hoc scanning.
- **Backup:** a small **`SYNTHETIC_DIAGNOSTIC_ONLY`** T/Y/cross fork (to be built) — a guaranteed
  junction if the primary fails, clearly labelled synthetic and never presented as real-scene or
  benchmark evidence.
- If the user prefers to **stop stock-asset scanning entirely**, promote the synthetic fork to
  primary.

## Claim boundary

Sourcing only. No render / drive / model / benchmark evidence; no training authorization. Junction
geometry `UNVERIFIED_UNTIL_RENDER_SCAN`. No angular branch-choice training until a scene passes the
render gates **and** drive validation. `CL_BOUND_XY` unchanged; incumbent retained.
