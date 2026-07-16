# H8 Synthetic Fork — Drive-Validation Report

**Status: DRIVE-VALIDATION (validation-only) — `SYNTHETIC_DIAGNOSTIC_ONLY`.** Physical drivability check under bounded scripted low-speed probes; **no policy/model inference, no recording, no trajectory collection, no action-probe, no training, no rollout metrics.** `CL_BOUND_XY` unchanged (read-only mirror = 6.0).

- **PASS: False**
- fail reasons: ['north_probe_failed', 'static_collision_precheck_failed', 'west_probe_failed']
- scene load: {'loaded': True, 'prim_count': 91, 'scene_collider_count': 61}
- prim type counts: {'DomeLight': 1, 'DistantLight': 1, 'Scope': 1, 'Material': 12, 'Shader': 12, 'Xform': 3, 'Cube': 44, 'Sphere': 4, 'Cone': 9, 'Cylinder': 4}
- collider provenance: {'eligible_types': ['Mesh', 'Cube', 'Sphere', 'Cone', 'Cylinder', 'Capsule', 'Plane'], 'applied_by_type': {'Cube': 44, 'Sphere': 4, 'Cone': 9, 'Cylinder': 4}, 'total_colliders_applied': 61}
- spawn: {'spawned': True, 'valid_state': True, 'root_xy': [-0.0, -3.0], 'in_bounds': True}
- camera: {'resolved': True, 'height_m': 0.47, 'frame_nonempty': True, 'mean_luma': 159.56}
- static collision pre-check: {'queried': True, 'scene_collider_count': 61, 'contacts': 2, 'clear': False}
- North probe: reached=False advanced=0.003 m contacts=1 in_bounds=True timed_out=False policy_driven=False
- West probe: reached=False advanced=0.003 m contacts=1 in_bounds=True timed_out=False policy_driven=False
- overall in-bounds: True
- safe-halt: {'cmd': 'zero_velocity', 'linear_mps': 0.0, 'angular_rps': 0.0, 'settle': True, 'executed': True}

Claim boundary: SYNTHETIC_DIAGNOSTIC_ONLY; physical drivability check only; no policy/model inference; no recording for training; no trajectory collection; no action-probe; no training; no rollout metrics (TL/NE/SR/OSR/SPL/nDTW/CR); no benchmark evidence; no real-scene evidence; no hospital evidence; no autonomy claim; CL_BOUND_XY unchanged.

## Interpretation (second attempt — DEFER diagnosis)

This is a **validation-only** run. The result is **DEFER / FAIL, not a pass** (`PASS: False`; fail reasons `north_probe_failed`, `static_collision_precheck_failed`, `west_probe_failed`). The failure is a **harness contact-classification issue**, not a scene defect.

- **Collider fix worked.** Unlike the first attempt (zero colliders), collision geometry is now established: **61 colliders** applied across the authored primitives (44 Cube + 4 Sphere + 9 Cone + 4 Cylinder), with `prim_type_counts` and `collider_provenance` populated. Scene loads, robot spawns validly at `(0, −3.0)`, and the camera renders non-empty (mean luma 159.56).
- **Floor support contact was counted as collision.** Once every `UsdGeom.Gprim` — including the scene's `Cube "Floor"` slab — became a collider, the robot footprint overlap box (half-extents (0.16, 0.16, 0.12) centred at `ROBOT_Z = 0.05`, so it dips to z ≈ −0.07 into the floor) hit the ground at **every** pose. The overlap query excluded only the robot's own subtree, **not** the floor, so this expected **support** contact was mis-scored as an **obstacle collision**. That is why the static pre-check reported contacts at spawn and both probes registered a contact at step 0 after advancing only 0.003 m. **A grounded robot resting on the floor is support, not collision.**
- **Process exit code was unreliable.** The process exited **0** even though the manifest verdict was `PASS: False`: Isaac's app shutdown hard-exits the process with 0 and **masked the manifest verdict**. The **manifest `pass` field is the source of truth** (correctly `False`); the exit code from this run must not be trusted.
- **The fail-closed verdict guard held.** `compute_verdict()` returned `PASS: False` on genuine `*_failed` contact results (no `incomplete_*` fields) — it did not certify drivability.

### What this run is and is not

- **This is NOT a drivability pass.**
- **This is NOT proof the scene is undrivable.** The harness could not fairly test drivability because floor-support contact was scored as collision and the probes halted on the ground at step 0.
- **No training. No recording. No trajectory collection. No action-probe. No policy/model inference. No rollout metrics (TL/NE/SR/OSR/SPL/nDTW/CR).** `CL_BOUND_XY` unchanged (read-only mirror = 6.0).

### Next fix (a separate, reviewed harness change)

1. **Support-contact classification** — classify floor/ground overlap hits as **support** (allowed) and everything else (walls, end panels, props, stripes, markers) as **obstacle** (failure); record hit prim paths so any remaining contact is identifiable; keep the zero-collider fail-closed guard.
2. **Reliable exit-code handling** — force `os._exit(verdict_exit_code(passed))` **before** any Isaac shutdown so the process status follows the manifest verdict and cannot be masked.

Only after that fix is committed should `isaac-run` be re-run. No training is authorized regardless.
