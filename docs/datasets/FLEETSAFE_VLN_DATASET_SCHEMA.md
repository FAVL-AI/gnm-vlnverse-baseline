# FleetSafe-VLN Dataset Schema

HDF5 episode format for training and evaluation data collected on the
Yahboom ROSMASTER-M3Pro and in Gazebo/Isaac Sim.  Extends the standard GNM
`data/training_episodes/` HDF5 layout with language and certificate fields.

---

## File layout

```
data/
  training_episodes/           # GNM-compatible visual nav episodes
  training_episodes_with_images/  # same + embedded RGB frames
  real_robot_bags/             # raw ROS2 bag recordings (.mcap or .db3)
  gnm_datasets/                # converted GNM-format datasets
    gostanford2/
    scand/
    yahboom_hospital/
```

### Single episode file

```
episode_YYYYMMDD_HHMMSS_XXXXX.hdf5
├─ metadata/              (attrs on group)
│    episode_id           str   uuid-4
│    robot                str   "yahboom_m3pro" | "gazebo" | "isaac"
│    environment          str   free-text scene description
│    date_collected       str   ISO-8601
│    backbone             str   "gnm" | "vint" | "nomad" | "mock"
│    instruction_source   str   "text" | "voice" | "image" | "multimodal"
│    raw_instruction      str   original natural-language instruction
│    transcript_confidence float  [0,1] — ASR confidence (1.0 if typed)
│    enable_motion        bool  True if real /cmd_vel was published
│    d_safe               float CBF safety radius (m)
│    max_vx               float actuator limit (m/s)
│    max_wz               float actuator limit (rad/s)
│    git_commit           str   repo commit hash at record time
│    fleetsafe_version    str   package version
│
├─ observations/          (shape: [T, ...])
│    rgb                  uint8  [T, H, W, 3]  — camera/color/image_raw
│    depth                float32 [T, H, W]   — camera/depth/image_raw (m)
│    scan0                float32 [T, N]       — /scan0 range array (m)
│    scan1                float32 [T, N]       — /scan1 range array (m, optional)
│    odom_x               float32 [T]          — odometry x (m)
│    odom_y               float32 [T]          — odometry y (m)
│    odom_yaw             float32 [T]          — odometry yaw (rad)
│    odom_vx              float32 [T]          — odometry forward speed (m/s)
│    odom_wz              float32 [T]          — odometry yaw rate (rad/s)
│
├─ actions/               (shape: [T, ...])
│    u_nom                float32 [T, 2]       — [vx, wz] before CBF
│    u_safe               float32 [T, 2]       — [vx, wz] after CBF (published)
│    cbf_active           bool    [T]          — True if CBF modified u_nom
│    qp_status            str     [T]          — "skipped"|"optimal"|"estop_fallback"
│
├─ language/
│    instruction_id        str    uuid[:8]
│    action_type           str    "navigate"|"stop"|"turn_left"|…
│    label                 str    extracted landmark/target
│    confidence            float  grounding confidence [0,1]
│    constraints           str    JSON array of avoid targets
│    grounding_candidates  str    JSON list of candidate parses
│    relative_hint         str    spatial hint ("door", "left", …) or ""
│    clarification_needed  bool
│    stop_reason           str    reason string or ""
│
├─ safety/                (shape: [T, ...])
│    h_min                float32 [T]          — min CBF value across obstacles
│    min_dist_m           float32 [T]          — min LiDAR range (m)
│    certificate_ids       str     [T]          — SafetyCertificate uuid per step
│
└─ timestamps/            (shape: [T])
     ns                   int64   [T]          — nanosecond epoch timestamps
```

---

## Step count T

`T` is the number of control steps in the episode.  At 10 Hz nominal rate,
a 60-second run produces T ≈ 600.  Episodes are padded with NaN if sensors
drop out; consumers should filter `np.isfinite()`.

---

## RGB resolution

| Robot | Resolution | FPS |
|---|---|---|
| Yahboom M3Pro (Orbbec DaBai DCW2) | 640 × 480 | 30 |
| Gazebo camera | 640 × 480 | 30 |
| Isaac Sim | 1280 × 720 | 60 |

Stored in the HDF5 with lossless uint8 encoding.  For large datasets
compress with `compression="gzip", compression_opts=4`.

---

## LiDAR scan shape

| Robot | Scanner | Rays N | Range (m) |
|---|---|---|---|
| M3Pro | Tmini-plus ×2 | 450 per head | 0.05 – 12 |
| Gazebo | simulated 2-D | 360 | 0.1 – 30 |
| Isaac Sim | RTX lidar | 1024 | 0.1 – 100 |

`scan0` is the front-mounted head; `scan1` is the rear head (zeroed for
single-head robots or simulators).

---

## GNM compatibility

The `observations/rgb`, `observations/odom_x`, `observations/odom_y`,
`observations/odom_yaw`, and `actions/u_safe` arrays can be extracted
directly into the GNM HDF5 format:

```python
import h5py, numpy as np

def to_gnm_episode(src_path, dst_path):
    with h5py.File(src_path) as src, h5py.File(dst_path, "w") as dst:
        dst.create_dataset("images",   data=src["observations/rgb"][:])
        dst.create_dataset("position", data=np.stack([
            src["observations/odom_x"][:],
            src["observations/odom_y"][:],
        ], axis=-1))
        dst.create_dataset("yaw",      data=src["observations/odom_yaw"][:])
        dst.create_dataset("actions",  data=src["actions/u_safe"][:])
```

---

## Dataset splits

| Split | Episodes | Source | Purpose |
|---|---|---|---|
| `train` | ≥ 200 | Gazebo + Isaac Sim | Backbone fine-tuning |
| `val` | ≥ 50 | Gazebo hold-out scenes | Hyperparameter selection |
| `test_sim` | ≥ 50 | Isaac Sim procedural | SR / SPL evaluation |
| `test_real` | ≥ 10 | M3Pro hospital corridor | Real-robot evaluation |
| `ablation_nosafety` | ≥ 50 | Any | Safety ablation (no CBF) |
| `ablation_voice` | ≥ 10 | M3Pro | Voice instruction modality |

A split manifest `data/splits.json` records which episode file belongs to
which split:

```json
{
  "train": ["episode_20260415_143200_abc12.hdf5", ...],
  "val":   [...],
  "test_sim": [...],
  "test_real": [...]
}
```

---

## Writing an episode with the FleetSafe recorder

```python
import h5py, numpy as np, time, uuid

def record_episode(frames, scans, odom, u_noms, u_safes,
                   cbf_active, h_mins, min_dists,
                   instruction, goal, cert_ids,
                   out_path, metadata: dict):
    T = len(frames)
    with h5py.File(out_path, "w") as f:
        # metadata
        g = f.create_group("metadata")
        for k, v in metadata.items():
            g.attrs[k] = v

        # observations
        obs = f.create_group("observations")
        obs.create_dataset("rgb",       data=np.array(frames,       dtype=np.uint8))
        obs.create_dataset("scan0",     data=np.array([s[0] for s in scans], dtype=np.float32))
        obs.create_dataset("scan1",     data=np.array([s[1] for s in scans], dtype=np.float32))
        obs.create_dataset("odom_x",    data=np.array([o[0] for o in odom],  dtype=np.float32))
        obs.create_dataset("odom_y",    data=np.array([o[1] for o in odom],  dtype=np.float32))
        obs.create_dataset("odom_yaw",  data=np.array([o[2] for o in odom],  dtype=np.float32))

        # actions
        act = f.create_group("actions")
        act.create_dataset("u_nom",     data=np.array(u_noms,   dtype=np.float32))
        act.create_dataset("u_safe",    data=np.array(u_safes,  dtype=np.float32))
        act.create_dataset("cbf_active",data=np.array(cbf_active, dtype=bool))

        # language
        lang = f.create_group("language")
        lang.attrs["instruction_id"]   = instruction.instruction_id
        lang.attrs["action_type"]      = goal.action_type
        lang.attrs["label"]            = goal.label
        lang.attrs["confidence"]       = goal.confidence
        lang.attrs["constraints"]      = str([c.target for c in goal.safety_constraints])

        # safety
        safe = f.create_group("safety")
        safe.create_dataset("h_min",       data=np.array(h_mins,     dtype=np.float32))
        safe.create_dataset("min_dist_m",  data=np.array(min_dists,  dtype=np.float32))

        # timestamps
        f.create_dataset("timestamps/ns", data=np.array(
            [time.time_ns() + i * 100_000_000 for i in range(T)], dtype=np.int64
        ))
```

---

## Minimum episode requirements for paper claims

| Claim | Episodes required |
|---|---|
| SR / SPL on sim | ≥ 50 per (backbone × scene) |
| Safety (collision, CBF rate) | ≥ 50 per condition |
| Real robot | ≥ 10 with valid certificates |
| Voice modality | ≥ 10 with ASR transcripts |
| Ablation: no-safety baseline | ≥ 50 per scene |

See `docs/evaluation/VLN_EVALUATION_PLAN.md` for full metric definitions.
