# H8 Synthetic Fork — Drive-Validation Report

**Status: DRIVE-VALIDATION (validation-only) — `SYNTHETIC_DIAGNOSTIC_ONLY`.** Physical drivability check under bounded scripted low-speed probes; **no policy/model inference, no recording, no trajectory collection, no action-probe, no training, no rollout metrics.** `CL_BOUND_XY` unchanged (read-only mirror = 6.0).

- **PASS: False**
- fail reasons: ['static_collision_precheck_failed']
- scene load: {'loaded': True, 'prim_count': 91, 'scene_collider_count': 0}
- spawn: {'spawned': True, 'valid_state': True, 'root_xy': [-0.0, -3.0], 'in_bounds': True}
- camera: {'resolved': True, 'height_m': 0.47, 'frame_nonempty': True, 'mean_luma': 152.13}
- static collision pre-check: {'queried': True, 'scene_collider_count': 0, 'contacts': 0, 'clear': True}
- North probe: reached=True advanced=0.6 m contacts=0 in_bounds=True timed_out=False policy_driven=False
- West probe: reached=True advanced=0.6 m contacts=0 in_bounds=True timed_out=False policy_driven=False
- overall in-bounds: True
- safe-halt: {'cmd': 'zero_velocity', 'linear_mps': 0.0, 'angular_rps': 0.0, 'settle': True, 'executed': True}

Claim boundary: SYNTHETIC_DIAGNOSTIC_ONLY; physical drivability check only; no policy/model inference; no recording for training; no trajectory collection; no action-probe; no training; no rollout metrics (TL/NE/SR/OSR/SPL/nDTW/CR); no benchmark evidence; no real-scene evidence; no hospital evidence; no autonomy claim; CL_BOUND_XY unchanged.

## Interpretation (DEFER diagnosis)

This run is a **DEFER / FAIL, not a pass** (`PASS: False`, fail reason `static_collision_precheck_failed`). It is **not** a scene-is-undrivable result and **not** a drivability pass.

- **`scene_collider_count = 0`.** No collision geometry was established on the scene.
- **Cause: the harness collider-application step only matched `UsdGeom.Mesh` prims.** The authored synthetic scene contains **no `Mesh` prims** — its geometry is `UsdGeom` **Gprim primitives such as Cube, Cone, Sphere, and Cylinder** (44 Cube + 9 Cone + 4 Sphere + 4 Cylinder). None matched `UsdGeom.Mesh`, so **zero colliders were applied or counted**.
- **`contacts = 0` is therefore meaningless** for the static pre-check and both probes: with no colliders present there is nothing for the PhysX overlap queries to hit. A `contacts = 0` result under a zero-collider scene does **not** indicate a clear branch.
- **The fail-closed guard (`compute_verdict`) prevented a false drivability pass.** Even though spawn, camera, and both probes reported superficially "successful" values, the guard requires `scene_collider_count > 0` before it will trust the "clear" reading, so it correctly returned `PASS: False` rather than certifying drivability against no collision geometry. This is exactly the intended behaviour: the pipeline **refused to certify drivability because collision geometry was not established.**
- **This run does NOT prove the synthetic scene is drivable.**
- **This run does NOT prove the synthetic scene is undrivable.** It only shows the harness could not test drivability because colliders were missing.

### Next fix (a separate, reviewed harness change — not applied in this evidence commit)

1. **Broaden collider handling** from `UsdGeom.Mesh` only to all relevant `UsdGeom.Gprim` geometry (Cube, Cone, Sphere, Cylinder, Mesh, and other Gprim subclasses), apply collision APIs where valid, count colliders correctly, still fail when the collider count is zero, and report primitive-type counts + collider-count provenance.
2. **Make the process exit code reflect the manifest verdict** (`pass=True` → exit 0; `pass=False`/DEFER/exception → nonzero), so Isaac's app shutdown cannot mask a returned failure. In this run Isaac's shutdown forced process exit 0 while the manifest verdict was `PASS: False`; the **manifest `pass` field is the source of truth**.

Only after that fix is committed should `isaac-run` be re-run. No training is authorized regardless.
