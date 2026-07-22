# H8 Hospital Dataset Protocol v2 — canonical

**Status: PROTOCOL / PLAN ONLY.** No Isaac/Omniverse/ROS 2 launch, no capture, no training, no
inference, no modification of historical bags, no commit, no push, no tag. Prepared 2026-07-22 from
the forensic audit at `/tmp/gnm_hospital_dataset_audit_20260722T000354Z/`.

**Supersedes for future capture:** the acquisition and labelling conventions used by the H1–H8MX
campaigns. **Does not supersede:** `H8_HOSPITAL_DATASET_AND_COLLECTION_SPEC.md` §2–§3 (the dataset
invariant and route families), which remain the scientific design and are carried forward unchanged.

**Preserved invariant:** `CL_BOUND_XY = 6.0` — unchanged (`scripts/gnm/h8_evidence_schema.py:40`).

---

## 1. Why v2 exists

The audit found the H1–H8MX corpus scientifically unusable as a training or evaluation dataset, for
reasons that are all labelling and acquisition failures rather than logging failures:

| Defect | Extent |
| --- | --- |
| Shared placeholder goal `h2_weave_J` | 93 / 154 episodes, incl. **all 33** gate-verified |
| Declared start pose ≠ first observed pose | 118 / 140 (84 %), up to 4.6 m |
| `policy_mode = gnm_closed_loop` with no policy in the loop | 142 labelled, only 34 with a policy driving |
| Front camera occluded (unraised mount) | 39 / 39 unraised bags, median 38 % of frame height |
| No declared success radius | 0 / 157 episodes |
| No oracle reference path or navmesh | 0 / 157 |
| Scene digest recorded | 0 / 157 |
| Contact telemetry in the bag | 0 / 157 (sidecar only) |
| `/tf_static` (camera extrinsics) | 0 / 157 |

The logging arithmetic was exact (derived vs declared path length and goal distance agreed to
0.0000 m; zero timestamp anomalies). **The instrument was sound; the labels around it were not.**

**Why the good recordings cannot be repaired.** Image-goal navigation requires the goal image to have
been captured at that episode's own goal pose. Assigning a different goal to an existing recording
would fabricate ground truth. The 13 technically strong recordings are therefore permanently
demonstration and diagnostic evidence, and a controlled recapture is required.

## 2. Locked acquisition configuration

```text
Acquisition resolution : 1280 x 720          (canonical)
Camera mount raise     : 0.12 m              (provisional; Session B confirms)
Colour encoding        : rgb8
Training resolution    : deterministic derived resize from the 1280x720 master
Historical 640x480     : diagnostic / demonstration evidence only, never train/val/test
```

**Rationale for 1280×720.** The existing bags are already disqualified by missing episode-specific
goal images, so relaxing the resolution standard would rescue nothing. 1280×720 preserves detail for
later experiments and supervisor inspection, and downsampling to the model input (e.g. 96×96) is
deterministic and lossy in one direction only. Collecting at 640×480 would destroy information that
cannot be recovered.

**Conditional-change clause.** Session B must run a **non-dataset** throughput check at 1280×720 for
sustainable publish rate, synchronisation and storage. If 1280×720 cannot operate reliably, the
resolution changes **only** through a written protocol decision recorded here **before** dataset
collection begins — never during or after collection.

**Derived-image record.** Every derived training image must record: resizing method, crop policy,
colour conversion, interpolation, output dimensions, and the derived-image hash.

## 3. Success criterion — pre-registered

```text
PRIMARY hospital success radius:  tau = 0.50 m
```

**Primary success (position-based):**

```text
final distance to goal      <= 0.50 m
AND robot linear speed      <= 0.05 m/s
AND held continuously for   >= 1.0 s
AND an explicit stop action was emitted
```

**Oracle Success (OSR):** the robot entered the 0.50 m goal region **at any point** during the episode.
OSR ≥ SR by construction; a violation indicates a computation error, not a result.

**Sensitivity analysis** is reported at 0.25, 0.50, 0.75 and 1.00 m. **0.50 m is the primary
pre-registered result.** The other radii exist to characterise sensitivity and must never be used to
select the best-looking number.

**Secondary — pose-aligned success** (reported alongside, never silently replacing the primary):

```text
distance <= 0.50 m  AND  |yaw error| <= 30 deg  AND  stationary >= 1.0 s
```

**Legacy boundary.** Track A Kujiale results retain `tau = 3.0 m`. Hospital and Track A success
figures must always display their threshold and must never be presented as equivalent. Any table
containing both must carry the threshold in the column header.

**Governance.** Frank proposes and documents; Professor Bo Wei approves **before** capture; the value
is then locked into the dataset configuration, the route manifest and the evaluation specification
(`success_criterion.preregistered = true`, `approved_by` populated). Selection after inspecting model
results is prohibited.

## 4. Episode schema v2

Defined normatively in `H8_EPISODE_SCHEMA_V2.json` (`h8-episode-manifest/2.0.0`, Draft-07 validated).
Mandatory fields: `episode_id`, `scene_id`, `scene_usd_path`, `scene_usd_sha256`, `map_version`,
`route_instance_id`, `route_family`, `split`, `start_pose_declared`, `start_pose_observed`,
`start_pose_error`, `goal_pose`, `goal_image_path`, `goal_image_sha256`, `success_radius_m`,
`camera_prim`, `camera_frame_id`, `camera_mount_raise_m`, `camera_resolution`, `camera_encoding`,
`controller_mode`, `policy_in_loop`, `reference_path_id`, `navmesh_version`, `stop_event`,
`stop_timestamp`, `contact_telemetry_available`, `capture_authorisation_id`, `config_sha256`,
`commit_sha`.

### Controller mode — closed vocabulary

| Value | `policy_in_loop` | Meaning |
| --- | --- | --- |
| `scripted_waypoint_follower` | `false` | A scripted executor drives. **92 historical episodes belong here and were mislabelled `gnm_closed_loop`.** |
| `gnm_shadow` | `false` | The policy infers but does not actuate. |
| `gnm_closed_loop` | **`true` (enforced)** | A learned policy actuates. Requires `policy_checkpoint_path` + `policy_checkpoint_sha256`. |
| `manual_control` | `false` | Operator teleoperation. |
| `replay_only` | `false` | Replayed trajectory, no live control. |

Unknown values are **rejected**, not coerced. A scripted waypoint follower must never be labelled
`gnm_closed_loop`.

### Start-pose policy

`start_pose_observed` is computed from the first stable pose samples **at capture time**.
Both declared and observed values are recorded, together with `start_pose_error`. The episode
**fails acceptance** if the error exceeds the pre-registered tolerance (0.05 m position,
0.0873 rad ≈ 5° yaw). The declared value is **never** silently overwritten after capture — that would
destroy the evidence that the discrepancy occurred.

### Goal-image policy

Each approved instance has **its own goal image captured at its own locked goal pose**. The goal
record binds: image bytes, SHA-256, camera prim, camera intrinsics, goal pose, yaw, scene digest, map
version, capture timestamp, route instance and split. A placeholder `goal_id` is forbidden — the
schema explicitly rejects `h2_weave_J`. A goal from another episode cannot be substituted post hoc.

## 5. Split and leakage controls

1. **Decision-frame-id disjoint** across train/val/test.
2. **Leakage-group disjoint** across splits.
3. **No goal-image leakage** — a frame used as a *goal* in val/test must not appear as an
   *observation* in any train episode. Enforced by a goal-image SHA-256 cross-split audit.
4. **No goal-coordinate reuse** across splits. This is the constraint that currently blocks H8-S:
   coords `(1.0,-0.2)` and `(1.2,0.0)` are reused between train and val/test because the proven-free
   lobby (`x ∈ [−2.31, 0.91]`) contains too few distinct far-goal locations. **Structural — only the
   map extension resolves it.**
5. **No a/b duplicate leakage.** An a/b repetition is the *same* route instance and shares
   `route_instance_id`. The audit found `h7_reception_01` / `h7_reception_01_smoke` identical to four
   decimals on path length and goal distance, and likewise `h8mx_val_val_A` / `_retry`. These are
   re-runs, not independent samples, and must never be split across train and test.
6. **Route-family balance** — each split carries a comparable mix of the seven families; per-family
   counts are reported.

## 6. Reference path and navmesh

`SPL`, `nDTW`, `SDTW` and `CLS` require an **oracle** reference path. The commanded waypoint list is
**not** an oracle — in 86 of 92 historical episodes it did not even lead to the declared goal.
Session A must produce a navmesh (or an equivalent geodesic source) and a versioned
`reference_path_id` per route instance. If `reference_path.source = UNAVAILABLE`, those four metrics
are **not computed and not reported** — they are not approximated with Euclidean distance.

## 7. Time alignment — the prerequisite blocker

Bag messages are wall-stamped; trajectory logs are sim-stamped; wall exceeded sim by more than 3× in
74 % of historical episodes. **A written, verified image↔pose alignment procedure with a stated
tolerance must exist before any dataset is built.** Until it does, per-frame supervision cannot be
asserted to be correctly paired, and every downstream metric inherits the doubt.
`acceptance.time_alignment_verified` must be `true` for admission. Authoring this procedure needs no
Isaac and is one of the two things that can be cleared immediately.

## 8. Acceptance gates (schema conformance is not admission)

An episode is admitted only if **all** hold:

| # | Gate |
| --- | --- |
| 1 | Schema-valid against `h8-episode-manifest/2.0.0` |
| 2 | `scene_identity_pass = true`, digest matches the locked USD, prim count ≥ 1000, zero procedural landmarks |
| 3 | `return_code = 0` and `route_completed = true` |
| 4 | `total_collision_count = 0` |
| 5 | `start_pose_error.within_tolerance = true` |
| 6 | Goal image present, hash-bound, cross-split disjoint, not a placeholder |
| 7 | `camera_resolution = [1280,720]`, `camera_mount_raise_m = 0.12`, `camera_encoding = rgb8` |
| 8 | `black_band_fraction ≤ 0.01` and `10 < mean_luminance < 200` |
| 9 | `executed_path_length_m ≥ 1.0` and `stationary_fraction ≤ 0.90` |
| 10 | `stop_event.stop_emitted` recorded (true or false — but recorded, with pose and timestamp) |
| 11 | `contact_telemetry_available = true` with declared detector scope, recorded to a bag topic |
| 12 | `time_alignment_verified = true` |
| 13 | `capture_authorisation_id` present |

Rejection is immediate and per-episode: discard the partial bag, clear stale DDS shared memory,
resume. Never process-pattern kill (standing rule).

## 9. Recorded topics

```text
/camera/image_raw   /camera/camera_info   /odom   /tf   /tf_static   /clock   /cmd_vel   <contact topic>
```

`/tf_static` and the contact topic are **new** — absent from all 157 historical bags, which is why
camera extrinsics are unrecoverable and collision evidence lives only in sidecars.

## 10. Per-episode and per-dataset artefacts

**Per episode, written into the bag directory** (historical bags had zero sidecars):
`episode_manifest.json` (schema v2), `scene_identity_manifest.json`, `checksums.sha256`.

**Per dataset:** `h8_recording_ledger.csv`, `h8_split_manifest.json`, `h8_goal_image_manifest.json`,
`h8_leakage_report.json`, `h8_artifact_completeness_report.json`, `h8_action_separation_report.json`,
`h8_scene_gate/`.

## 11. Scale — unchanged from the H8 spec

| Stage | Decision frames | Goals/frame | Branch recordings | Prerequisite |
| --- | --- | --- | --- | --- |
| H8-S | 8–12 (10 designed, 8 active) | ≥ 2 | ~16–24 | design gate PASS + split-leak fix |
| H8-M | 20 train / 5 val / 10 test | ≥ 2 | ~70 | navigable-map extension |
| H8-L | expansion | ≥ 2–3 | TBD | only if H8-M passes all gates |

Storage: ~1.3–2.0 GB per episode at 640×480 historically; **1280×720 is ~2.25× the pixel count**, so
budget ~3–4.5 GB/episode → **~50–110 GB for H8-S**. The ≥100 GB free-disk standing rule must be
re-checked against this, and Session B must measure it rather than assume the scaling.
