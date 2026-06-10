# Live GNM Input Dashboard

**Date:** 2026-06-09  
**Branch:** `gnm-vlnverse-baseline`

---

## What this is

The live GNM input dashboard shows the full robot navigation process frame by frame, not as static snapshots.

Every frame of a trajectory is rendered as a three-column dashboard image:

```
┌──────────────────────┬──────────────────────┬──────────────────────┐
│    START VIEW        │  CURRENT LIVE VIEW   │     GOAL VIEW        │
│  frame 0             │  frame t / T         │  frame T-1           │
│  x=…  y=…            │  x=…  y=…  yaw=…°   │  x=…  y=…            │
├──────────────────────┼──────────────────────┼──────────────────────┤
│  [start RGB image]   │  [current RGB image] │  [goal RGB image]    │
│                      │  (updates each frame)│                      │
└──────────────────────┴──────────────────────┴──────────────────────┘
│ scene: kujiale_0118  ep: …  split: train  path_len: … m            │
│ dist_to_goal: … m    STATUS: RUNNING / GOAL REACHED                │
│ GNM INPUT: current RGB (frame t) + goal RGB (frame T-1)  →         │
│   local waypoint (delta_x, delta_y)  [labels: traj_data.pkl]       │
│ Official Track A: SR=20.0%  OSR=46.7%  NE=6.51 m                  │
└────────────────────────────────────────────────────────────────────┘
```

---

## How to use

### Export PNG sequence (no Isaac Sim required)

```bash
python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
```

Generates `results/bo_reviewer_packet/live_dashboard/dashboard_NNNNNN.png` — one per trajectory frame.

```bash
SCENE=kujiale_0271 python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
```

Use a different scene (kujiale_0092, kujiale_0118, kujiale_0203, kujiale_0271).

### Export video (requires imageio or ffmpeg)

```bash
EXPORT_LIVE_VIDEO=1 python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
```

Saves `results/bo_reviewer_packet/live_dashboard/live_gnm_input_dashboard.mp4`.

```bash
pip install imageio[ffmpeg]   # or: sudo apt install ffmpeg
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SCENE` | `kujiale_0118` | Which VLNVerse scene to use |
| `DASHBOARD_EVERY_N` | `1` | Export every Nth frame (1 = all frames) |
| `SAVE_LIVE_FRAMES` | `1` | Save PNG files to live_dashboard/ |
| `EXPORT_LIVE_VIDEO` | `0` | Also export .mp4 |

### Isaac Sim live replay

```bash
LIVE_DASHBOARD=1 AUTO_PLAY=1 conda run -n isaac python scripts/gnm/replay_gnm_demo.py
```

This:
1. Creates `/World/GNM_Replay/LIVE_GNM_INPUT_DASHBOARD` — a textured plane visible in the scene
2. Auto-advances the robot through all trajectory frames
3. Updates the plane texture to the current dashboard frame each step
4. Updates orange waypoint cones (WAYPOINT_00–04) to the current lookahead positions
5. Logs GOAL REACHED when `dist_to_goal ≤ success_radius`

```bash
LIVE_DASHBOARD=1 AUTO_PLAY=1 EXPORT_LIVE_VIDEO=1 SAVE_LIVE_FRAMES=1 \
  conda run -n isaac python scripts/gnm/replay_gnm_demo.py
```

---

## Output files

```
results/bo_reviewer_packet/live_dashboard/
  dashboard_000000.png    ← frame 0 (start pose)
  dashboard_000001.png    ← frame 1
  …
  dashboard_NNNNNN.png    ← final frame (near goal)
  live_gnm_input_dashboard.mp4    ← if EXPORT_LIVE_VIDEO=1
```

---

## GNM input/output explanation

Each dashboard frame makes explicit what GNM sees and what it is asked to predict:

| | Frame shown |
|---|---|
| START VIEW | Camera at start pose (x₀, y₀, yaw₀) — frame 0 RGB |
| CURRENT LIVE VIEW | Camera at current robot pose (xₜ, yₜ, yawₜ) — frame t RGB |
| GOAL VIEW | Camera at goal pose (xₜ, yₜ₋₁, yawₜ₋₁) — last frame RGB |

**GNM receives:** current RGB image + goal RGB image  
**GNM predicts:** local waypoint (delta_x, delta_y) in robot frame  
**Ground-truth label:** derived from `positions[t + horizon] − positions[t]`, rotated by `yaw[t]`  

The orange cones in Isaac Sim show these ground-truth waypoint targets. They are **not model predictions** — they are labels derived from `traj_data.pkl`.

---

## Stop condition

The dashboard shows `STATUS: GOAL REACHED` when:

```
dist_to_goal = sqrt((xₜ - x_goal)² + (yₜ - y_goal)²) ≤ success_radius
```

`success_radius = 3.0 m` (standard for this trajectory; stored in `episode_info.json`).

In Isaac Sim, the message `*** GOAL REACHED ***` is printed to the terminal and the dashboard panel shows it in green.

---

## Waypoint cones (live update)

In the Isaac Sim replay loop, orange cones `WAYPOINT_00` through `WAYPOINT_04` are repositioned each frame to show the next 5 lookahead positions:

```
WAYPOINT_k  →  positions[t + k + 1]   (clamped to trajectory end)
```

These are ground-truth derived labels:
- `gnm:type = "local_waypoint_target"`
- `gnm:source = "derived_from_traj_data_pkl"`

---

## Official performance (unchanged)

This dashboard is a visualisation tool. It does not change the official benchmark result:

| Metric | Value |
|--------|-------|
| Success Rate (SR) | 3/15 = **20.0%** |
| Oracle Success Rate (OSR) | 7/15 = **46.7%** |
| Navigation Error (NE) | **6.51 m** |

See `results/bo_reviewer_packet/03_success_rate_breakdown.md` for the per-episode breakdown.

---

## Related files

| File | Purpose |
|------|---------|
| `scripts/gnm/replay_gnm_demo.py` | Main script (`--export-live-dashboard` mode) |
| `results/bo_reviewer_packet/live_dashboard/` | Per-frame dashboard PNGs |
| `results/bo_reviewer_packet/10_full_evidence_chain.md` | Full evidence chain |
| `results/bo_reviewer_packet/09_isaac_camera_click_validation.md` | Camera USD attributes |
