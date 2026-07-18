# H7 / H7R camera-resolution variance and H8 mitigation

**Status:** documented limitation (erratum). Resolution conformity is **OPEN / not
demonstrated** for H7 and H7R. This note **discloses** the discrepancy; it does **not**
rewrite the historical experimental record.

## 1. The discrepancy

| Quantity | Value | Source |
|---|---|---|
| Declared **expected** resolution | **1280×720** | `expected_resolution` in every H7/H7R scene-gate manifest (from `hospital_scene_identity_gate.EXPECTED_RESOLUTION`, mirroring the Isaac `SimulationApp` window `{"width":1280,"height":720}`) |
| **Observed** recorded resolution | **640×480** | the actual camera render product (`rep.create.render_product(CAM_PRIM, (640,480))`, `m3pro_ros2_bringup.py:263`); this is what `/camera/image_raw` contains |

The two differ. The recorded ImageNav stream in all 16 episodes (8 H7 + 8 H7R) is
640×480, while the manifests declared an expectation of 1280×720.

## 2. Why it passed the gate silently (root cause)

At H7/H7R capture time the scene-gate resolution check was **declarative only**:

```python
# hospital_scene_identity_gate.py (H7/H7R capture-time behaviour)
res_ok = list(resolution) == list(EXPECTED_RESOLUTION) or (len(resolution) == 2)
```

The trailing `or (len(resolution) == 2)` means **any** well-formed `[W, H]` pair passes.
The check confirmed a resolution was *declared*; it never compared the *observed* stream
against the *declared* target. So 640×480 satisfied it despite ≠ 1280×720.

## 3. What this does and does not affect

**Not affected** — the following H7/H7R evidence stands unchanged:

- **Scene identity** — verified Isaac Sim `hospital.usd` (1909 prims, no procedural
  landmark cubes), 8/8 gate PASS.
- **ROS 2 bag existence** — 16 recorded bags on disk.
- **Checksum integrity** — SHA-256 over every `.db3` + `metadata.yaml`.
- **Route identification** — 8 routes, 4 families × 2 variants, lengths + split recorded.
- **Topic presence** — six required topics incl. `/camera/image_raw` (≈2117–2124 msgs/ep).

**Affected** — the following is **not** demonstrated:

- **Camera-resolution conformity.** H7 and H7R make **no** claim that the recorded
  resolution matches an intended/declared target. The captures are valid 640×480 image
  streams; they are simply not evidence of resolution conformity.

## 4. Research treatment (what was and was NOT done)

1. **Historical manifests preserved unchanged.** The per-episode scene-gate manifests in
   `assets/experiments/hospital_h7_scene_gate/h7*_*.json` are **not** edited. Back-editing
   them to read "640×480 declared" would rewrite the original experimental condition after
   observing the data and would weaken provenance. Both values are reported side by side
   here instead.
2. **Erratum added** — this document.
3. **Both values stated** — declared 1280×720; observed 640×480 (§1).
4. **Check characterised** — the capture-time check was declarative and did **not**
   compare observed against declared (§2).
5. **Forward fix implemented** for H8 (§5).
6. **Only the evidence appendix and future manifests regenerated** — never the historical
   source evidence.

## 5. H8 mitigation (fail-closed, implemented)

`scripts/gnm/hospital_scene_identity_gate.py :: verify_hospital_scene` now accepts
`declared_resolution` and `enforce_resolution`:

- **Opt-in.** Default `enforce_resolution=False` keeps the check declarative, so the
  historical **H7/H7R verdicts are byte-identical** (no retroactive re-judgement).
- **Fail-closed for H8.** With `enforce_resolution=True`, the gate adds a
  `resolution_matches_declared` check that **refuses admission** when the observed
  recorded resolution ≠ the declared target, and records **both** values
  (`observed.declared_resolution`, `observed.observed_resolution`).

The H8 admission/capture path MUST call the gate with the actual render-product
resolution as `resolution`, the intended target as `declared_resolution`, and
`enforce_resolution=True`.

**Negative test:** `tests/gnm/test_hospital_resolution_gate.py` proves that
640×480-observed vs 1280×720-declared is rejected under enforcement, that both values are
recorded, and that the default (declarative) path still passes the historical 640×480
capture unchanged. All 4 tests pass.

## 6. Bottom line

H7 and H7R are **provenance-backed Isaac Sim hospital-scene pilots** with a **documented
camera-resolution nonconformity**. Scene identity, bag existence, checksum integrity,
route identity and topic presence are supported. Resolution conformity is not — and is now
enforceable, fail-closed, for H8 going forward.
