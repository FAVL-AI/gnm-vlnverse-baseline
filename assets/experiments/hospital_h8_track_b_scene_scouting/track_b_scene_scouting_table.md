# H8-M Track-B Candidate Asset Shortlist (INVENTORY ONLY)

**Planning/inventory only — no render, no drive, no model, no benchmark evidence.** Reachability
was checked by HTTP HEAD (no download, no render). Junction presence is **UNVERIFIED** for every
candidate; `expected_*` values are hypotheses/design targets, not measurements. No coordinates are
fabricated.

## Exact candidate assets

| asset_id | asset path | reachable | scene type | expected junction | goal A / goal B | safe spawn-reloc? | action-angle sep | render/depth risk | real / synthetic | render-scan? |
|---|---|---|---|---|---|---|---|---|---|---|
| `office_isaac` | `…/Environments/Office/office.usd` | HTTP 200, 256 KB | office corridor + rooms | corridor intersection (loc TBD) | two divergent corridors (TBD) | plausible (bounded) | target ≥30° (~90°); actual TBD | MEDIUM (interior lighting; depth plausible) | real-world-like | **YES (P1)** |
| `warehouse_simple` | `…/Simple_Warehouse/warehouse.usd` | HTTP 200, 1.6 MB | warehouse aisle grid | aisle cross-junction (loc TBD) | two divergent aisles (TBD) | plausible (wide aisles) | target ≥30° (~90°); actual TBD | HIGH on **distinctness** (aisles look alike); depth GOOD | real-world-like | **YES (P2)** |
| `warehouse_full` | `…/Simple_Warehouse/full_warehouse.usd` | HTTP 200, 6.8 MB | warehouse aisle grid (larger) | more aisle intersections (loc TBD) | two divergent aisles (TBD) | plausible | target ≥30° (~90°); actual TBD | distinctness MED-HIGH; depth GOOD; larger asset | real-world-like | hold (P3, secondary) |
| `hospital_alt_wing` | N/A (no validated new area) | asset 200 but domain proven junction-incapable | hospital wing | **BLOCKED** | N/A | needs new validated map first | N/A | N/A | real-world-like | **NO (blocked)** |
| `synthetic_fork_fallback` | does not exist (would need authoring) | — | synthetic corridor fork | designable | designable | yes (designed) | designable ≥30° | LOW (authored open) | **SYNTHETIC diagnostic-only** | NO (fallback only) |

## Unavailable at this Isaac 5.1 S3 root/version
- `Office/Office.usd` — HTTP 404 (use lowercase `office.usd`, which is 200).
- `Modular_Warehouse/Modular_Warehouse.usd` — HTTP 404 (would be an indoor-junction candidate; not present here).

## Local repo scenes reviewed and rejected
- `assets/custom_vln_office/scene_layout.usda` — single open 16×10 m office room (desks/chairs/one partition); **no fork/T-junction**.
- `assets/isaac/tracka_hospital_replay_stage.usda` — references `hospital.usd`; hospital domain, already junction-incapable.
- `assets/experiments/kujiale_*/scene.usda` — procedural single-room scenes; rooms, not junctions.
