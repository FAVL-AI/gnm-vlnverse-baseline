# H8 Map-Extension — Recovery Validation Report

**Scope: validation only.** No H8-S collection, no training, no promotion, no push, no tag, no 20/5/10, no closed-loop beyond bounded per-zone drives, **no `CL_BOUND_XY` change**. Held for review.

## What recovery did
- **Retried val_A** (same isaac-world spawn −3.8, no navmap offset): **25 contacts again** — reproducible obstacle at x≈−3.8, not run-variation → `val_A` escalated to `REJECTED_COLLISION` (retry did not clear it).
- **Probed two mid-west points**: `midwest_A` (−2.8) and `midwest_B` (−3.4) both **0 collisions, camera valid** → the drivable/blocked boundary is sharp between −3.4 (clean) and −3.8 (blocked). **`midwest_B` recovers the val split** (coordinate-disjoint, west of the lobby).
- **Navmap could not have predicted this:** free-y span is identical (−0.76…1.09) at every x from −5.3 to 1.4; the blocking geometry lives outside the navmap z-slab. Only drive validation finds it.

## Final candidate-zone table
| zone | split | env | collisions | cam_valid | driven_x | status |
|---|---|---|---|---|---|---|
| east_A | test | in | 0 | True | [1.4, 2.11] | **PROVEN_FOR_ROUTE_DESIGN** |
| east_B | test | in | 0 | True | [2.6, 3.1] | **PROVEN_FOR_ROUTE_DESIGN** |
| lookalike_test | test | in | 0 | True | [3.0, 3.2] | **PROVEN_FOR_ROUTE_DESIGN** |
| lobby | train | in | 0 | True | [-1.0, 0.7] | **PROVEN_FOR_ROUTE_DESIGN** |
| midwest_A | train | in | 0 | True | [-2.8, -2.3] | **PROVEN_FOR_ROUTE_DESIGN** |
| midwest_B | val | in | 0 | True | [-3.4, -2.9] | **PROVEN_FOR_ROUTE_DESIGN** |
| west_C | train | in | 7678 | False | [-5.3, -4.89] | **REJECTED_COLLISION** |
| val_A | val | in | 25 | True | [-3.79, -3.3] | **REJECTED_COLLISION** |
| val_A_retry | val | in | 25 | True | [-3.79, -3.3] | **NEEDS_RETRY** |
| west_A | train | OUT | — | — | — | **DEFERRED_SAFETY_ENVELOPE_LIMITED** |
| west_B | train | OUT | — | — | — | **DEFERRED_SAFETY_ENVELOPE_LIMITED** |
| hardneg_farwest | hard-negative | OUT | — | — | — | **DEFERRED_SAFETY_ENVELOPE_LIMITED** |

## Split status (proven, coordinate-disjoint)
- **train:** ['lobby', 'midwest_A']  (lobby [−2.31,0.91]; midwest_A reserve, overlaps lobby).
- **val:** ['midwest_B']  (midwest_B [−3.4,−2.9], west of lobby — **RECOVERED**).
- **test:** ['east_A', 'east_B', 'lookalike_test']  (east [1.4,3.5]).
- Coordinate bands are disjoint: val [−3.4,−2.9] · train [−2.31,0.91] · test [1.4,3.5] (gaps ≥0.49 m).

## Visual-distinctness audit (task 3 — the new blocker)
aHash similarity on the post-drive view (1 − Hamming/256; >0.80 = suspiciously similar; crude for structurally-alike corridors, but the RELATIVE pattern is informative):
- **Test zones are near-duplicates:** east_A~east_B=0.93, east_A~lookalike_test=0.887, east_B~lookalike_test=0.957 — east_A/east_B/lookalike_test all show the same vending-machine/wheelchair bay, so TEST carries **~1 distinct view, not 3**. lookalike_test's adversarial pairing is **unresolved** (intended confuser west_B is safety-deferred, and it duplicates east_B).
- **Cross-split similarity:** east_A~lobby=0.863, east_B~lobby=0.832 — east(test)~lobby(train) ≈0.83–0.86 (same corridor structure); moderate, to be re-checked with a proper perceptual-hash gate at recording.
- **midwest_B (val) is strongly distinct** (0.53–0.76 to all others) — a clean, well-separated val zone.

## H8-S design-gate preconditions
- each split has a proven zone: **True**.
- coords disjoint across splits: **True**.
- enough DISTINCT zones (test not collapsed): **False**.
- visual distinctness acceptable: **False**.
- **→ OK to re-run H8-S design gate now: False**.

The H8-S design gate was **NOT re-run**: coordinates qualify, but visual distinctness does not yet (test near-duplicates + moderate train/test cross-similarity). The coordinate-only design gate would report 'ready' and mislead — the real gap is imagery.

## Revised H8-S recommendation (held for review)
The map extension now yields a **coordinate-clean, per-split-proven** zone set (train=lobby, val=midwest_B, test=east) — a genuine advance over the flagged H8-S. But before recording, resolve the **imagery** gap:
1. **Give TEST distinct decision frames** — the east bay is one view; either use a single east test frame (not three), or find a second visually-distinct in-envelope test location.
2. **Resolve lookalike_test** — its adversarial confuser (west_B) is safety-deferred; drop the visually-similar family from H8-S, or pair it inside the envelope.
3. **Add a perceptual-hash cross-split gate** at recording (the §5 goal-image hash audit), using midwest_B (val) as the distinct anchor; treat east~lobby ≈0.85 as the threshold to beat.
4. Only then re-run the H8-S design gate (coords) **and** a recorded-image distinctness gate; record only if both pass.

## Claim boundary
Bounded per-zone spawn + short drive; 1 pass (val_A: 2 passes, reproducible). Collisions = PhysX base_link contacts (ground truth). Visual similarity = crude aHash screen, not a final leakage verdict. Feasibility study; no dataset recorded, no model trained, no promotion; `CL_BOUND_XY` unchanged; incumbent retained.

## Artifacts
`drive_validation/`: `recovery_manifest.json`, `recovery_zone_table.csv`, this report, `recovery_ledger.csv`, `contact_sheets/{val_A_retry,midwest_A,midwest_B}.png` + prior 6, `render_metadata/*.json` incl. `_visual_audit.json`, `routes/h8mx_{val_A_retry,midwest_A,midwest_B}.json`. Harness: `scripts/gnm/h8_map_extension_recover.sh`, `scripts/gnm/h8_map_extension_recovery_report.py`. Rosbags/trajectories NOT for commit.
