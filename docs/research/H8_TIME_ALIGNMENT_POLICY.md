# H8 Image-to-Pose Time Alignment Policy

**Version:** `h8-alignment/1.0.0` — implemented in `scripts/gnm/h8_time_alignment.py`,
tested in `tests/gnm/test_h8_time_alignment.py`.

Closes the blocker recorded by the 2026-07-22 forensic audit: rosbag messages carry two different
clocks, and no verified alignment procedure existed, so per-frame supervision could not be asserted
to pair the right image with the right pose. Every downstream metric inherited that doubt.

---

## 1. Time domains

| Clock | Where it appears | Nature |
| --- | --- | --- |
| ROS message **header** stamp | `sensor_msgs/Image`, `CameraInfo`, `nav_msgs/Odometry`, `tf2_msgs/TFMessage` | **Simulation time** when the publisher uses `use_sim_time` |
| rosbag2 **record** timestamp | the `messages.timestamp` column of the `.db3` store | Wall clock, Unix epoch — when the recorder received the message |
| Simulation `/clock` | `rosgraph_msgs/Clock` | The simulation time source itself |
| Command publication time | `/cmd_vel` (no header on `geometry_msgs/Twist`) | Only a record timestamp exists |
| Inference timestamp | per-step trajectory log | Simulation time |
| Wall-clock / monotonic process time | harness logs | Host time |

### Authoritative clock

> **The ROS message header stamp is authoritative for alignment, in every context** — future Isaac
> recordings, historical simulation bags, historical real-robot bags (none exist yet), and offline
> dataset building.

Mixing wall and simulation time is **refused** (`H8_TIME_DOMAIN_MISMATCH`), never silently converted.

`/cmd_vel` carries no header, so command latency cannot be measured against a header stamp; it is
reported `NOT_COMPUTED_MISSING_LATENCY_TIMESTAMPS` until commands are recorded with a stamped
companion message.

## 2. Evidence

Measured across eight historical bags spanning every family (clean raised-camera H7r, H8 D1
prototype, `h8mx_val_lobby`, occluded unraised H7, an all-black H2 bag, a placeholder-goal H24 bag,
a mislabelled-controller H8MX bag, and an H6 recorded bag).
Machine-readable: `/tmp/h8_s1_alignment_builder_20260722T012726Z/historical_timing_characterisation.csv`.

| Quantity | Result (all eight bags) |
| --- | --- |
| Image header `dt` — p50 / p95 / p99 / max | **0.05 s** exactly (20 Hz simulation time) |
| Odometry header `dt` — p50 / p95 / p99 | **0.05 s** exactly (20 Hz) |
| Minimum observed `dt` | 0.016667 s — one 60 Hz physics step |
| Image-to-nearest-pose residual — p50 / p95 / **p99** | **0.016667 s** — exactly one physics step |
| Residual max | 0.016667 – 0.116667 s (episode edges) |
| Frames with no bracketing pose | 0.09 % – 0.27 %, all at episode start/end |
| `/clock` monotonic | true, every bag |
| Image header within `/clock` span | true, every bag |
| Image `frame_id` | `camera_link`, every bag |
| Odometry frame → child | `odom` → `base_footprint`, every bag |
| **Wall-record span ÷ simulation span** | **5.6× – 7.3×** normally, **146.9×** for the starved all-black bag |

Two conclusions follow directly:

1. **The record timestamp is unusable for alignment.** It runs 5.6–147× slower than simulation time,
   and the ratio is not even constant across bags. This is why the audit's initial 3.15 Hz camera
   estimate (computed from wall duration) was misleading: the true rate is 20 Hz in simulation time.
2. **The image and pose streams are locked to the same 20 Hz grid, offset by exactly one 60 Hz
   physics step.** The residual is not noisy — it is a constant, structural one-step offset.

## 3. Alignment procedure

1. Validate the image timestamp is present and finite.
2. Confirm the image clock is the authoritative clock; refuse otherwise.
3. Confirm the transform is resolved; refuse otherwise.
4. Validate the pose series: single clock, finite, monotonic, unit quaternions.
5. Confirm frame and child-frame identity against expectation.
6. Locate the bracketing poses by binary search.
7. Interpolate position **linearly**.
8. Interpolate orientation by **shortest-path slerp** on the unit quaternion.
9. **Refuse extrapolation** beyond the series; never synthesise a pose.
10. Record the residual, both source pose stamps, the method, the frames and the clock domain.

Every aligned frame emits: image timestamp, image frame id, pose stamp before, pose stamp after,
alignment method, positional interpolation, angular interpolation, maximum timestamp gap, actual
residual, pose source, coordinate frame, child frame, clock domain, policy version, status, and
rejection reason.

**Why slerp and not linear yaw.** A pose pair straddling ±π (e.g. 175° → −175°) interpolates the
short way (through 180°) under shortest-path slerp, but sweeps backwards through 0° under naive
linear yaw interpolation — producing a pose the robot never occupied. `test_f05_yaw_wrap_takes_short_arc`
asserts this.

## 4. Tolerance — derived, not chosen

| Parameter | Value |
| --- | --- |
| `alignment_tolerance_ms` | **25.0 ms** |
| `maximum_position_interpolation_error_m` | **0.005 m** (5 mm) |
| `maximum_yaw_interpolation_error_deg` | **0.573°** |
| Diagnostic tolerance | 50 ms — characterisation only, never dataset admission |

**Derivation.** The tolerance is placed strictly between two measured quantities:

```
observed residual p99  =  16.667 ms   <   tolerance 25 ms   <   publish period 50 ms
```

- **Above the p99 residual**, so every interior frame has a usable bracketing pose pair. Measured
  alignment rate at 25 ms is **99.73 % – 99.91 %**, the shortfall being exactly the episode-edge
  frames that have no bracketing pose and are correctly refused.
- **Below the publish period**, so a genuinely stale pose — one whose partner sample was dropped —
  is refused rather than interpolated across a gap.

**Implied worst-case error** at the locked velocity limits (0.2 m/s linear, 0.4 rad/s angular,
unchanged since H2 and mirrored in `cl_limits`):

```
position :  0.025 s x 0.2 m/s   = 0.005 m   = 1.0 % of the tau = 0.50 m success radius
yaw      :  0.025 s x 0.4 rad/s = 0.010 rad = 0.573 deg
```

A 5 mm worst-case position error against a 500 mm success radius is immaterial to SR, OSR or NE.

**Status: `PROPOSED_DATASET_ACCEPTANCE_TOLERANCE`.**

**Unresolved — carried forward to Session B.** This derivation rests on 640×480 / 20 Hz historical
simulation bags. The canonical acquisition resolution is 1280×720, 2.25× the pixel count, which may
change the publish period. **The tolerance must be re-measured at 1280×720 during Session B before
it is treated as final**, and it follows the publish period: if the rate drops, the tolerance and
the implied interpolation error both change. This is a runtime measurement, not a decision — no
supervisor input is required, but the number is provisional until it is taken.

## 5. Rejection conditions

| Condition | Reason code |
| --- | --- |
| Image timestamp missing or non-finite | `H8_ALIGNMENT_IMAGE_STAMP_MISSING` |
| Pose series empty | `H8_ALIGNMENT_POSE_MISSING` |
| Timestamps out of order (small backward step) | `H8_ALIGNMENT_TIMESTAMP_ORDER_INVALID` |
| Simulation time reset (large backward step) | `H8_ALIGNMENT_CLOCK_RESET` |
| Incompatible clock domains | `H8_TIME_DOMAIN_MISMATCH` |
| Frame or child-frame mismatch | `H8_ALIGNMENT_FRAME_MISMATCH` |
| No bracketing pose, within tolerance of an endpoint | `H8_ALIGNMENT_NO_BRACKETING_POSE` |
| Outside the series beyond tolerance | `H8_ALIGNMENT_EXTRAPOLATION_REFUSED` |
| Residual exceeds tolerance | `H8_ALIGNMENT_GAP_EXCEEDED` |
| Duplicate timestamps make the bracket ambiguous | `H8_ALIGNMENT_DUPLICATE_TIMESTAMP_AMBIGUOUS` |
| Non-unit or non-finite quaternion | `H8_ALIGNMENT_QUATERNION_INVALID` |
| Interpolation produced a non-finite value | `H8_ALIGNMENT_NON_FINITE` |
| Frame transform unresolved | `H8_ALIGNMENT_TRANSFORM_UNRESOLVED` |

Each has at least one deterministic test.

## 6. Boundary

Using historical bags to characterise timing **does not make them dataset-eligible**. They remain
classified exactly as `H8_HISTORICAL_DATA_CLASSIFICATION.md` records them: 13 demonstration,
126 diagnostic, 18 permanently rejected, 0 train/validation/test eligible. Nothing in this policy
alters that, and no historical bag or manifest was modified to produce this evidence.
