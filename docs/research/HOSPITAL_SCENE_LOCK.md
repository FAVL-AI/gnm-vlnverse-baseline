# Hospital Scene Lock — official target-scene standard

**Status: LOCKED (2026-07-13).** This document defines the *only* acceptable
hospital-scene visual/data-collection standard for FleetSafe hospital ImageNav.

## The rule

```
Procedural-stage H6 = diagnostic route-family coverage experiment.
Real hospital USD    = official target scene for future hospital ImageNav data,
                       demos, and professor visuals.
```

The locked asset is the real **Isaac Sim 5.1 `hospital.usd`**:

```
https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd
```

Verified reference: ~1909 prims under `/World/Hospital`, RTX ray-traced, robot-height
(0.35 m) front RGB camera, 1280×720. Photorealistic reception desk, wheelchair,
vending unit, corridor, glass sliding doors, waiting-area tables, vinyl floor.

## What changed and why

The H6 route-family diagnostic was collected in the bring-up **default** procedural
scene (`--scene stage`): a grey ground plane plus a few coloured-block landmarks
(`Pillar_Red/Blue/Green`, `Wall_Yellow`). That is fine for a *scene-agnostic*
route-family coverage study, but it is **not** hospital visual evidence. The
procedural frames were withdrawn from hospital decks and replaced with real
`hospital.usd` target-scene renders.

## Standing rules (do)

1. Do **not** use procedural `--scene stage` frames as hospital evidence.
2. Do **not** use grey-floor / coloured-block visuals in professor decks.
3. Do **not** mix procedural H6 metrics with hospital visuals as if they came from
   the same dataset. Keep (A) metrics and (B) hospital visuals separated and labelled.
4. Every future hospital collection/export/demo must explicitly pass `--scene hospital`.
5. Every hospital run must verify, before recording:
   - hospital USD asset path,
   - hospital prim count (≥ threshold),
   - scene mode = `hospital`,
   - front RGB camera path,
   - resolution,
   - timestamp,
   - **no** procedural landmark cubes,
   - image is visually hospital-like (non-flat, non-grey).

## The scene-identity gate

`scripts/gnm/hospital_scene_identity_gate.py` is the reusable, **fail-closed** gate.
It fails (and the caller must refuse to record) if any of the following hold:

- `hospital.usd` is not the referenced asset under `/World/Hospital`;
- prim count under the hospital root is below `MIN_HOSPITAL_PRIMS` (1000; real ≈ 1909);
- `scene_mode != "hospital"`;
- any procedural landmark/ground prim is present
  (`Pillar_Red/Blue/Green`, `Wall_Yellow`, `Landmark`, `Ground_Cube`, `StageGround`);
- the declared front-camera prim is missing;
- the resolution is not declared as `[W, H]`;
- the front image is near-flat/grey (weak visual safety net).

A **scene-identity manifest is written before recording** — `verify_hospital_scene()`
returns the verdict and `write_scene_identity_manifest()` persists it (asset path,
prim count, scene mode, camera path, resolution, forbidden-landmark check, timestamp,
locked rule). Downstream artifacts are therefore self-describing.

### Usage

```python
# inside any Isaac script, AFTER SimulationApp has booted and the scene is loaded:
from hospital_scene_identity_gate import verify_hospital_scene, write_scene_identity_manifest
gate = verify_hospital_scene(stage, scene_mode="hospital",
                             front_cam_path="/World/FrontCam",
                             resolution=[1280, 720], front_rgb=first_frame)
write_scene_identity_manifest(out / "scene_identity_manifest.json", gate)
if not gate["pass"]:
    raise SystemExit(5)   # refuse to record
```

Standalone self-test (boots Isaac, loads hospital, writes the top-level locked manifest):

```
~/miniforge3/envs/isaac/bin/python scripts/gnm/hospital_scene_identity_gate.py
```

## Live demo

`scripts/gnm/hospital_front_camera_demo.py`:

1. opens Isaac Sim,
2. loads the verified hospital USD,
3. runs the scene-identity gate (fail-closed),
4. places a front RGB camera at robot height (stands in for the robot's front sensor),
5. moves it through one short route,
6. captures start / current / goal frames,
7. writes the scene-identity manifest proving the scene is the hospital.

```
# live viewport on a desktop with a display:
~/miniforge3/envs/isaac/bin/python scripts/gnm/hospital_front_camera_demo.py --gui --route reception_to_corridor
# headless pilot pack (all 4 routes):
~/miniforge3/envs/isaac/bin/python scripts/gnm/hospital_front_camera_demo.py --route all
# then build PNG contact sheets (gnm_train PIL — isaac-env PIL crashes on PNG save):
~/miniforge3/envs/gnm_train/bin/python scripts/gnm/hospital_scene_locked_build.py
```

If the scene ever opens as grey floor plus coloured blocks, the gate fails and the
run records nothing.

## Pilot sample pack

`assets/experiments/hospital_h2_collection_20260709/hospital_scene_locked_exports/`
holds a gated pilot pack of four hospital route types — **reception→corridor**,
**corridor straight**, **left/right turn or T-junction**, **waiting area→doorway/goal** —
each with start / current / goal frames + a contact sheet, plus route label, split/use
label, camera pose, robot pose, asset path, and the scene-identity manifest.

## Files

- `scripts/gnm/hospital_scene_identity_gate.py` — reusable fail-closed gate (+ self-test)
- `scripts/gnm/hospital_front_camera_demo.py` — live demo + gated capture
- `scripts/gnm/hospital_scene_locked_build.py` — PNG/contact-sheet builder (gnm_train PIL)
- `assets/experiments/hospital_h2_collection_20260709/hospital_scene_locked_manifest.json` — top-level locked manifest
- `assets/experiments/hospital_h2_collection_20260709/hospital_scene_locked_exports/` — pilot pack
- Corrected professor visuals (committed): `.../hospital_render_exports/` + `h6_professor_deck_corrected.md`

## Claim boundary (for the professor)

> I found that the previous H6 metric run used the default procedural scene, so I am
> not claiming it as hospital visual navigation. I have now locked the real Isaac
> hospital USD as the target scene, and the next run will collect start/current/goal
> front-camera data directly from that hospital asset with a scene-identity gate.
