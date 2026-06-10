# VisualNav-Transformer Baseline Contract

**Status:** Enforced — machine-verified by `tests/test_baseline_contract.py`  
**Audit script:** `python scripts/visualnav/audit_preprocessing.py`

---

## 1. Upstream Source and Commit

| Field | Value |
|---|---|
| Repository | `github.com/robodhruv/visualnav-transformer` |
| Local path | `third_party/visualnav-transformer/` |
| **Pinned commit** | **`dca79815b704e5aa9c6bdc3082351f9e3b2848c2`** |
| Cloned by | `bash scripts/visualnav/setup_visualnav.sh` |

The upstream repo is **not modified**.  All FleetSafe-specific code lives in
`fleet_safe_vla/integrations/visualnav_transformer/` and wraps the upstream
models without changing their weights, architecture, or inference logic.

---

## 2. Models and Checkpoints

| Model | Backbone | Published by | Checkpoint |
|---|---|---|---|
| **GNM** | ResNet18 CNN | Shah et al., 2023 | `data/model_weights/gnm/gnm.pth` |
| **ViNT** | Vision Transformer | Shah et al., 2023 | `data/model_weights/vint/vint.pth` |
| **NoMaD** | Diffusion (DDPM) | Sridhar et al., 2024 | `data/model_weights/nomad/nomad.pth` |

Checkpoint verification:

```bash
python scripts/visualnav/check_visualnav_checkpoints.py
```

All three models are trained on diverse outdoor and indoor visual navigation
datasets (Go Stanford, RECON, SACSoN, etc.) and are deployed as-is — no
fine-tuning on the FleetSafe hospital environment.

---

## 3. Input Contract

Each adapter preprocesses raw camera frames into the exact tensor format the
upstream model expects.  Deviations here are integration bugs.

### Image sizes (from upstream config files)

| Model | Width × Height | Source |
|---|---|---|
| GNM | 85 × 64 | `train/gnm_train/config/gnm.yaml` |
| ViNT | 85 × 64 | `train/vint_train/config/vint.yaml` |
| NoMaD | 96 × 96 | `train/vint_train/config/nomad.yaml` |

### Normalisation

All three models apply **ImageNet normalisation**:

```
pixel_norm = (pixel_float - mean) / std

mean = [0.485, 0.456, 0.406]
std  = [0.229, 0.224, 0.225]
```

### Context (observation history)

| Property | Value |
|---|---|
| `context_size` | 5 frames for all three models |
| Frame order | **Oldest first** (required by upstream temporal encoder) |
| Padding | If fewer than 5 frames available: oldest frame is repeated |

### Tensor format

```
obs_tensor  : (1, 3 × context_size, H, W)   =  (1, 15, H, W)
goal_tensor : (1, 3, H, W)
```

Both are `torch.float32`.

---

## 4. Output Contract

The model outputs **waypoints in robot frame**:

```
waypoints : (action_horizon, 2)
  column 0 = forward displacement  (x, metres)  — positive = forward
  column 1 = lateral displacement  (y, metres)  — positive = left (CCW)
```

| Model | `action_horizon` |
|---|---|
| GNM | 5 |
| ViNT | 5 |
| NoMaD | 8 (diffusion action sequence) |

The first waypoint `waypoints[0]` is passed to the proportional waypoint
controller (`waypoints_to_cmd_vel`) to produce a `CmdVel`.

### Velocity conversion

```
vx  = clip(|wp[0]| × control_hz, 0, v_max)   # forward speed
wz  = clip(atan2(wp[1], wp[0]), -w_max, w_max) # heading error → angular rate
```

Default limits: `v_max = 0.3 m/s`, `w_max = 0.7 rad/s`, `control_hz = 4 Hz`.

---

## 5. Camera Contract

The navigation backbone must receive **only** egocentric robot-mounted camera
observations.  This is the single most important correctness requirement.

```
ALLOWED:
  robot-mounted forward-facing camera (egocentric, 62° HFOV)

FORBIDDEN:
  bird's-eye view
  spectator / free camera
  any top-down render
  global map or occupancy grid
  oracle obstacle positions
  simulator world state
```

### Bug that was found and fixed (2026-05-22)

The MuJoCo MJCF defined `<site name="camera">` but no `<camera>` element.
MuJoCo silently fell back to the free spectator camera when `cam_name="camera"`
was requested, because sites are not renderable.

**Fix:** Added `<camera name="camera" pos="0.10 0 0.082" xyaxes="0 -1 0 0 0 1" fovy="62"/>`
inside `base_link` to all MJCF files.  The renderer now fails explicitly if
the named camera is absent:

```python
cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "camera")
if cam_id < 0:
    raise RuntimeError("MuJoCo model has no camera named 'camera'. ...")
```

This guard is verified by `TestMuJoCoCameraContract.test_benchmark_runner_raises_without_camera`.

### Per-backend camera validation

| Backend | Camera source | Verification |
|---|---|---|
| MuJoCo | `<camera name="camera">` inside `base_link` | `RuntimeError` if absent |
| Isaac Sim | Camera render product at `{prim}/Camera` | `setup_camera()` asserts prim valid |
| Real robot | ROS2 `/usb_cam/image_raw` or `/camera/image_raw` | `ros2_bridge.get_camera_b64()` |

---

## 6. What the Policy Is Allowed to See

```
✓  obs_tensor   — stacked egocentric camera frames  (3 × context_size channels)
✓  goal_tensor  — goal image from camera snapshot or reference image
```

Nothing else.

---

## 7. What Only FleetSafe Is Allowed to See

```
✓  obs_vec (47-dim)        — IMU, odometry, wheel velocities
✓  obstacle_positions      — world-frame obstacle centres (from LiDAR / sim geometry)
✓  obstacle_radii          — estimated obstacle radii
✓  robot_xy                — robot world-frame position (for CBF computation)
```

These inputs are passed **exclusively** to `YahboomCBFFilter`.  They never
enter `predict_action()` or `preprocess_observation()`.

This separation is enforced in `FleetSafeWrapper.step()` and verified by
`TestPerceptionContract.test_fleetsafe_wrapper_does_not_pass_obstacles_to_policy`.

---

## 8. Wiring Diagram

```
camera frames (egocentric, 62° HFOV)
        │
        ▼
IsaacCameraObsAdapter.push_frame()
        │  context_size=5 frames, resized to model image_size
        ▼
adapter.preprocess_observation(obs_imgs, goal_img)
        │  → {obs_tensor: (1,15,H,W), goal_tensor: (1,3,H,W)}
        ▼
adapter.predict_action(preprocessed)
        │  → ActionOutput(waypoints=(N,2), goal_distance, ...)
        ▼
adapter.action_to_cmd_vel(action)
        │  → CmdVel(vx, vy, wz)  [nominal command]
        │
        │          robot state + obstacle geometry
        │                      │
        ▼                      ▼
    FleetSafeWrapper.step(preprocessed, obs_vec, obstacle_positions)
        │
        │  1. calls predict_action(preprocessed)          ← camera only
        │  2. converts to nominal CmdVel
        │  3. YahboomCBFFilter.filter(obs_vec, nominal)   ← state + obstacles
        │
        ▼
    safe_cmd_vel  →  robot actuators
```

---

## 9. Audit and Regression Tests

### Baseline contract audit (runs in < 5 s, no checkpoints needed)

```bash
python scripts/visualnav/audit_preprocessing.py
python scripts/visualnav/audit_preprocessing.py --model gnm
python scripts/visualnav/audit_preprocessing.py --model vint
python scripts/visualnav/audit_preprocessing.py --model nomad
```

Checks: image size, context size, normalisation, tensor shapes, waypoint shape,
forward/left sign conventions, physical bounds, perception contract, camera adapter.

### Contract test suite

```bash
pytest tests/test_baseline_contract.py -v
```

Tests: adapter configuration, preprocessing tensors, action output, sign
conventions, perception contract, camera adapter, MuJoCo camera guard, upstream pin.

### Golden-frame regression

```bash
# Save expected outputs (run once after baseline is established)
python scripts/visualnav/audit_preprocessing.py --save-golden

# Check against golden outputs in CI
python scripts/visualnav/audit_preprocessing.py --check-golden
```

---

## 10. Known Limitations

| Limitation | Impact |
|---|---|
| No fine-tuning on hospital environment | Model uses zero-shot generalisation from diverse training data. Expected lower performance indoors than in training distribution. |
| NoMaD diffusion horizon 8 vs GNM/ViNT 5 | NoMaD plans further ahead; waypoint controller uses only `waypoints[0]`. |
| ViNT goal-distance estimate | Used for benchmark logging only. Does not affect navigation command. |
| Holonomic M3Pro vs differential training data | `vy` is computed from lateral waypoint but upstream trained on differential robots. |
| 4 Hz control loop | Upstream designed for ≥10 Hz. Inference latency target: < 50 ms on CPU, < 10 ms on GPU. |

---

## Supervisor-ready statement

> We used the GNM / ViNT / NoMaD model family from the official
> `visualnav-transformer` repository (commit `dca7981`), without modifying
> the upstream model weights or architecture.  During integration, we discovered
> that our MuJoCo environment was silently providing the navigation policy with
> a spectator camera view instead of an egocentric robot-mounted camera.  We
> corrected this by adding a named `<camera>` element to all MJCF files and
> making the renderer fail explicitly if that camera is absent.  The navigation
> backbone now receives only egocentric forward-facing camera observations
> (85×64 px, ImageNet-normalised, 5-frame context), while robot state and
> obstacle geometry are reserved exclusively for the FleetSafe CBF safety
> filter.  This contract is machine-verified by `tests/test_baseline_contract.py`
> and audited by `scripts/visualnav/audit_preprocessing.py`.
