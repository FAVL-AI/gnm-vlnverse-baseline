# H8 Synthetic Fork — Drive-Validation Report

**Status: DRIVE-VALIDATION (validation-only) — `SYNTHETIC_DIAGNOSTIC_ONLY`.** Physical drivability check under bounded scripted low-speed probes; **no policy/model inference, no recording, no trajectory collection, no action-probe, no training, no rollout metrics.** `CL_BOUND_XY` unchanged (read-only mirror = 6.0).

- **PASS: True**
- fail reasons: []
- scene load: {'loaded': True, 'prim_count': 91, 'scene_collider_count': 61}
- prim type counts: {'DomeLight': 1, 'DistantLight': 1, 'Scope': 1, 'Material': 12, 'Shader': 12, 'Xform': 3, 'Cube': 44, 'Sphere': 4, 'Cone': 9, 'Cylinder': 4}
- collider provenance: {'eligible_types': ['Mesh', 'Cube', 'Sphere', 'Cone', 'Cylinder', 'Capsule', 'Plane'], 'applied_by_type': {'Cube': 44, 'Sphere': 4, 'Cone': 9, 'Cylinder': 4}, 'total_colliders_applied': 61}
- contact classification: robot self-subtree hits excluded; floor/ground leaf-name -> support (allowed); every other collider hit -> obstacle (failure) (support_contact_allowed=True)
- spawn: {'spawned': True, 'valid_state': True, 'root_xy': [-0.0, -3.0], 'in_bounds': True}
- camera: {'resolved': True, 'height_m': 0.47, 'frame_nonempty': True, 'mean_luma': 159.55}
- static collision pre-check: {'queried': True, 'scene_collider_count': 61, 'contacts': 0, 'obstacle_contacts_count': 0, 'support_contacts_count': 2, 'support_contact_allowed': True, 'obstacle_contact_failure': False, 'contact_classification_rule': 'robot self-subtree hits excluded; floor/ground leaf-name -> support (allowed); every other collider hit -> obstacle (failure)', 'clear': True, 'hit_prims': [], 'support_prims': ['/World/Scene/Structure/Floor', '/World/Scene/Structure/S_floor_strip']}
- North probe: reached=True advanced=0.6 m contacts=0 in_bounds=True timed_out=False policy_driven=False
- West probe: reached=True advanced=0.6 m contacts=0 in_bounds=True timed_out=False policy_driven=False
- overall in-bounds: True
- safe-halt: {'cmd': 'zero_velocity', 'linear_mps': 0.0, 'angular_rps': 0.0, 'settle': True, 'executed': True}

Claim boundary: SYNTHETIC_DIAGNOSTIC_ONLY; physical drivability check only; no policy/model inference; no recording for training; no trajectory collection; no action-probe; no training; no rollout metrics (TL/NE/SR/OSR/SPL/nDTW/CR); no benchmark evidence; no real-scene evidence; no hospital evidence; no autonomy claim; CL_BOUND_XY unchanged.

## Interpretation (third attempt — PASS)

This is a **validation-only drive run** on the `SYNTHETIC_DIAGNOSTIC_ONLY` fork, the first meaningful drive-validation after the support-contact and exit-code fixes (harness commit `ddc3f75`). It is a **PASS** (`pass=True`, `fail_reasons=[]`).

- **Process exit code agrees with the manifest verdict.** The run exited `0`, which equals `verdict_exit_code(True)`; the manifest `pass` field is the source of truth and the process status now follows it (the earlier exit-0-despite-`False` masking is fixed — `os._exit(...)` runs before any Isaac shutdown).
- **Collider count is populated and nonzero:** 61 colliders applied. **Primitive/collider provenance is populated:** prim type counts `{Cube 44, Sphere 4, Cone 9, Cylinder 4, ...}`; `collider_provenance.applied_by_type = {Cube 44, Sphere 4, Cone 9, Cylinder 4}`, total 61.
- **Support contacts are classified separately from obstacle contacts.** Static pre-check: `obstacle_contacts_count = 0`, `support_contacts_count = 2`, `obstacle_contact_failure = False`, `clear = True`. The two support prims were `/World/Scene/Structure/Floor` and `/World/Scene/Structure/S_floor_strip`.
- **`S_floor_strip` is treated as a SUPPORT contact, not an obstacle**, because it is a **~4 cm-tall flat floor cue**, not a wall or upright prop: authored as `Cube "S_floor_strip"` with `scale = (0.4, 1.25, 0.02)` centred at `z = 0.02` (top ≈ `z = 0.04`), lying flat on the floor. A grounded robot drives over it exactly as it drives over the floor, so scoring it as support (drivable) rather than obstacle (blocking) is the correct and transparent judgment. Only floor/ground leaf-named prims are excluded; walls, end panels, markers, and upright props remain obstacles (e.g. `N_stripe_*` are not floor-named and would count as obstacles if hit — they were not hit here).
- **Obstacle contacts are zero** at spawn and across both probes (obstacle `hit_prims` = `[]`).
- **North probe completed** (reached=True, advanced 0.6 m, 240 steps, 0 contacts, in-bounds). **West probe completed** (reached=True, advanced 0.6 m, 240 steps, 0 contacts, in-bounds).
- **No timeouts.** `timeouts = []`.
- **480 pose-trace samples, 240 per probe** (bounded low-rate root-pose samples across the two scripted probes).
- **All poses in bounds** — spawn, both probes, and safe-halt stayed well inside `CL_BOUND_XY = 6.0`.
- **`compute_verdict()` has no incomplete fields** — every required physics field (scene identity, scene load, spawn, camera, static pre-check, both probes, in-bounds, safe-halt) is populated and passing; there are no `incomplete_*` reasons.
- **No policy/model inference** (both probes `policy_driven = False`; scripted motion only). **No training data.** **No recording-mode data.** **No rollout metrics** (no TL/NE/SR/OSR/SPL/nDTW/CR emitted). **No action-probe.** `CL_BOUND_XY` **unchanged at 6.0** (read-only mirror).

### What this PASS is and is not

- **This is NOT hospital evidence.**
- **This is NOT real-scene / real-world evidence.**
- **This is NOT benchmark evidence.**
- **This is NOT autonomy evidence.**
- **This is NOT training authorization.**

It certifies only that, on the authored idealised junction, colliders are established and both the North and West branches are physically drivable by a body with real extent under bounded scripted low-speed probes, with support contacts correctly distinguished from obstacle collisions. The next gate is **recorded-mode planning** (planning only) — not recording and not training.
