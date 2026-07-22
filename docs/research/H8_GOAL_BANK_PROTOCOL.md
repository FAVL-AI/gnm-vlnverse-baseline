# Goal Bank Protocol (Session C)

The goal bank is the single control that fixes the defect which invalidated the entire existing
corpus. It is captured **before** any route data, and route capture then runs **only** against
already-locked goal records.

## 1. The rule

> Every approved instance has its own goal image, captured by the same camera configuration, at that
> instance's own locked goal pose, in the same scene digest and map version. No placeholder. No
> substitution. No post-hoc reassignment.

The audit found `goal_id = h2_weave_J` in 93 of 154 episodes, including **all 33** gate-verified
hospital episodes, and in 86 of 92 routed episodes the commanded route ended more than 0.5 m from
that declared goal — often 2–7 m away in a different direction. The robot was never driving to the
goal it was scored against.

## 2. Why this cannot be repaired retrospectively

Image-goal navigation defines the task by the goal *image*. The correct goal image is the view from
the goal pose. An episode that never visited a given pose contains no frame taken there. Assigning
a different image would be **fabricated ground truth** — a data-integrity failure, not an
approximation. This is why the 13 technically excellent recordings are permanently
demonstration-and-diagnostic evidence.

## 3. Ordering — goals before routes

```text
Session A  map + navmesh + leakage-clean candidate split
Session B  camera and sensor validation at 1280x720
Session C  GOAL BANK      <- goal images captured and locked here
Session D  route capture  <- runs only against locked goal records
```

Capturing goals first makes substitution structurally impossible: at route-capture time the goal
record already exists, is hash-locked, and is referenced by id. A route episode that cannot resolve
its `goal_id` to a locked record is rejected before it starts.

## 4. Goal record binding

Each goal record binds, immutably:

| Field | Purpose |
| --- | --- |
| `goal_id` | Unique; `h2_weave_J` is forbidden by schema |
| `goal_image_path` + `goal_image_sha256` | The bytes, and proof they are those bytes |
| `goal_pose` (x, y, z, yaw) | Where the image was taken — with yaw, required for pose-aligned success |
| `camera_prim`, `camera_frame_id` | Which sensor took it |
| `camera_intrinsics` (fx, fy, cx, cy, 1280×720) | Reproducible geometry |
| `camera_mount_raise_m = 0.12`, `camera_encoding = rgb8` | Configuration parity with route capture |
| `scene_usd_sha256` | Same scene as the routes |
| `map_version`, `navmesh_version` | Same map frame as the routes |
| `route_instance_id` | Which instance this goal belongs to |
| `split` | Fixed at goal-bank time, before any model sees anything |
| `goal_capture_episode_id`, `goal_capture_timestamp` | Provenance of the capture itself |

## 5. Capture procedure

1. Arm the scene-identity gate, fail-closed. Verify the digest matches Session A's.
2. For each approved instance, drive to the locked goal pose using the Session A navmesh.
3. Verify arrival: position within 0.05 m and yaw within 5° of the locked pose. **Reject and retry
   otherwise** — a goal image taken 0.3 m off its declared pose corrupts every metric computed
   against it.
4. Settle the robot (stationary ≥ 1.0 s) so the frame is not motion-blurred.
5. Capture the frame at 1280×720 rgb8.
6. Run image quality acceptance immediately: `black_band_fraction ≤ 0.01`,
   `10 < mean_luminance < 200`, `std_luminance > 10` (rejects flat/blown frames — this is what would
   have caught `h8mx_calib_lobby` at luminance 226.8 and the six all-black bags at 0.0).
7. Compute SHA-256; write the goal record; make it read-only.
8. Record the scene-identity gate result alongside.

## 6. Cross-split hash audit — run before any route capture

1. **Uniqueness** — no two goal records share a SHA-256. A duplicate means two "distinct" goals are
   the same image.
2. **Cross-split disjointness** — no val/test goal image may also appear as an *observation* frame in
   any train episode.
3. **Coordinate distinctness** — no goal coordinate is reused across splits (the constraint that
   currently blocks H8-S).
4. **Visual distinctness within a decision frame** — the ≥2 goals of a shared observation must be
   genuinely different views, not near-duplicates. Report the pairwise distinctness score against the
   calibrated threshold.
5. **Action separation** — the ≥2 goals must induce robot-frame `[Δx, Δy]` targets differing by ≥30°
   of heading, or ≥0.6 m of goal distance for stop-conditioning frames (H8 spec §2 invariant).

**If any check fails, no route capture begins.** The bank is fixed first.

## 7. Explicit prohibitions

- No placeholder goal, under any circumstance.
- No goal image reused across instances.
- No goal record created or edited after route capture has begun.
- No route episode admitted whose `goal_image_sha256` does not match a locked bank record.
- No goal captured before Session A confirms the map and Session B confirms the camera.

## 8. Exit criteria

A complete, hash-locked, split-assigned goal bank covering every approved instance, passing all five
cross-split audits, with a written record of any instance that could not be captured and why.
