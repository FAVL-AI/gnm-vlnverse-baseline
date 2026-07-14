# H8 navmap <-> bringup Frame-Fit Report

**Scope: analysis only.** No Isaac, no recording, no training. Recovers the transform between the committed navmap frame and the recording (bringup) frame from committed data, resolving the blocker recorded in `H8_NAVIGABLE_MAP_EXTENSION_PLAN.md` §1.

## Frames
- **Navmap frame** (`navmap_meta.json`): built directly from `hospital.usd` geometry in world coordinates; `x,y in [-7, 7] m`, resolution 0.05 m, 280x280; `occupancy_raw.npy` (1=occupied, 0=free), `navigable.npy` (True=free after robot-radius inflation).
- **Bringup frame**: the robot's odometry is **spawn-relative** (spawn reported as (0,0)); route waypoints are authored in this frame.

## Observed offset
Naively assuming spawn == world origin puts **0.0%** of the recorded 0-collision paths on free cells (all axis/flip conventions tested), while 100% are in-bounds -> a genuine frame **offset**, not an indexing convention.

## Fit method
The recorded paths are free space by construction (0 collisions). Register the driven footprint against the navmap free map by deterministic FFT cross-correlation over rotations `theta in [0,360)` (1 deg step); the placement maximising free-cell overlap is the transform. Verified on the **full** driven set (not the subsample used for search).

## Result
- **Rotation:** `theta = 0 deg` (pure translation; no rotation).
- **Translation:** `world = bringup + (2.9562, -6.24) m`.
- **Inverse:** `bringup = (world_x + (-2.9562), world_y + (6.24))`.
- **Verification:** **100.00%** of all 65440 recorded points land on free cells under this transform (target ~100%). The spawn maps to world `(2.9562, -6.24)`.

## Can the frames be aligned safely?
**Yes** — a single, exact rigid translation (no rotation, no scale) aligns them, validated at 100% on 65k+ independently-recorded points. The navmap is therefore usable as a coordinate oracle for the whole hospital via `bringup = world - t`. **Caveat:** navmap-free is *geometric* freedom in the z-slab [0.08, 0.55] after inflation; it certifies candidate coordinates for enumeration but does **not** prove drivability, render quality, or absence of black lower-frame occlusion -> such coordinates are `NEEDS_DRIVE_VALIDATION`.

## Reachable free space (spawn-connected)
- **Inflated `navigable` reachable envelope (bringup):** x[-9.96, 3.99], y[-0.76, 1.09] (10640 cells).
- **Uninflated `occupancy_raw` reachable envelope (bringup):** x[-9.96, 3.99], y[-0.76, 1.39] (12320 cells).
- **Structure:** a single connected corridor ~14 m long, ~1.85-2.15 m wide. **Even uninflated, no rooms or side-branches are reachable from spawn** in the robot slab -> room/hall families are geometrically unreachable here (see zone report).

## Consequence for the map extension
The fit **quadruples** usable corridor length (proven lobby ~3.2 m -> reachable ~14 m), enough to place train/val/test goals in **disjoint x-bands** (leakage-clean by construction). It does **not** unlock rooms; reception/waiting/elevator/side-room families remain deferred pending a drivable doorway or a different scene.
