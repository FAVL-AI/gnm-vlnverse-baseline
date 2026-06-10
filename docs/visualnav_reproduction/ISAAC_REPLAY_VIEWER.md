# Isaac Intervention Replay Viewer

## Purpose

The Intervention Replay Viewer is an **evidence viewer**, not a demo renderer.
Every visual element corresponds to a field in `intervention_evidence.jsonl`.
No interpolation, extrapolation, or simulated physics is added to the display.

This is the visualization infrastructure that answers the question:

> "Can we see, frame-by-frame, exactly why FleetSafe intervened?"

---

## Architecture

```
intervention_evidence.jsonl   ← primary replay source (one record per step)
scene_graphs.jsonl            ← supplementary graph data
trajectory.csv                ← x,y,heading per step
metadata.yaml                 ← version fields, backend, model
        ↓
ArtifactLoader                ← fleet_safe_vla/envs/isaaclab/replay/replay_scene.py
        ↓
ReplayFrame[]                 ← one per episode step
        ↓
ReplayTimeline                ← frame navigation, intervention jumping
        ↓
┌──────────────────────────────────────────────────────┐
│ SceneGraphRenderer   → GraphEdgeRenderData           │
│ TrajectoryData       → TrailPoint[]                  │
│ build_action_vectors → ActionVectorData              │
│ build_overlay        → OverlayData (text)            │
│ build_counterfactual → CounterfactualRenderData      │
└──────────────────────────────────────────────────────┘
        ↓                              ↓
Isaac Sim viewer          matplotlib video exporter
(replay_intervention.py)  (export_intervention_video.py)
```

---

## Module layout

| File | Purpose |
|---|---|
| `fleet_safe_vla/envs/isaaclab/replay/replay_scene.py` | `ArtifactLoader`, `ReplayFrame`, `ArtifactManifest` |
| `fleet_safe_vla/envs/isaaclab/replay/replay_overlay.py` | `OverlayData`, text overlay builder |
| `fleet_safe_vla/envs/isaaclab/replay/scene_graph_visualizer.py` | `SceneGraphRenderer`, edge/node color coding |
| `fleet_safe_vla/envs/isaaclab/replay/trajectory_visualizer.py` | `TrajectoryData`, `ReplayTimeline`, `ActionVectorData` |
| `fleet_safe_vla/envs/isaaclab/replay/intervention_replay.py` | `InterventionReplayViewer` orchestrator |
| `scripts/isaaclab/replay_intervention.py` | Isaac Sim viewer entry point |
| `scripts/isaaclab/replay_intervention.sh` | Shell launcher (conda guard) |
| `scripts/visualnav/export_intervention_video.py` | Headless matplotlib MP4/GIF exporter |

---

## Required artifacts

Every episode directory must contain:

| File | Required | Description |
|---|---|---|
| `intervention_evidence.jsonl` | **yes** | Primary replay source |
| `metadata.yaml` | **yes** | Version fields, backend, model |
| `scene_graphs.jsonl` | no | Supplementary graph data |
| `trajectory.csv` | no | x,y,heading per step |
| `actions.csv` | no | Raw/safe cmd_vel per step |

If a required file is missing:
- `ArtifactManifest.missing_required` is non-empty
- A red warning overlay is shown in the viewer
- No silent fallback is performed

---

## Visual elements

### Robot
- Blue circle at recorded position
- Red circle if intervention was applied at that frame
- Trajectory trail: green=safe, yellow=near-violation, red=intervened

### Obstacles
- Cylinder/circle at recorded position
- Radius from scene graph node `radius_m`

### Safety zones
- Yellow dashed ring: CBF safety margin (0.30 m default)
- Red dotted ring: collision threshold (0.10 m default)

### Scene graph edges

| Relation | Color | Meaning |
|---|---|---|
| `near` | yellow | Within near_miss threshold (0.45 m) |
| `moving_towards` | orange | Robot approaching obstacle |
| `occludes` | yellow | Obstacle between robot and goal |
| `blocks_path` | orange | Obstacle within 0.20 m of waypoint |
| `violates_margin` | red | Within CBF safety margin (0.30 m) |
| `intervention_caused_by` | red | Causal link from FleetSafe to obstacle |

Edges from `scene_graph_delta.added_edges` are rendered thicker (newly appeared).
Edges from `scene_graph_delta.removed_edges` are rendered as dashed grey (disappeared).

### Action vectors
- Red arrow: raw policy action (what the model wanted)
- Green arrow: safe action (what FleetSafe executed)
- Orange arrow: delta (difference vector)

### Counterfactual rollout
- Red dashed path: raw action trajectory over 2 s horizon
- Green dashed path: safe action trajectory over 2 s horizon
- Only shown at intervention frames

---

## Evidence contract

Every rendered element comes directly from `intervention_evidence.jsonl`.
No rendering is generated from inference or extrapolation.

| Visual element | Source field |
|---|---|
| Robot position | `scene_graph_before.nodes.robot.position` |
| Raw action arrow | `raw_action` |
| Safe action arrow | `safe_action` |
| Action delta arrow | `action_delta` |
| Edge colors | `scene_graph_before.edges[*].relation` |
| Intervention flag | `intervention_applied` |
| Reason text | `intervention_reason` |
| Causal explanation | `causal_explanation` |
| Counterfactual text | `counterfactual_explanation` |
| Scene graph delta | `scene_graph_delta.added_edges` / `removed_edges` |

---

## Counterfactual rollout backends

| Backend | Status | Claim scope |
|---|---|---|
| `mock` | Active | Engineering only — overlay: "MOCK COUNTERFACTUAL ROLLOUT" |
| `isaac` | `NotImplementedError` | Pending Isaac branching rollout |

The mock backend uses a 2-D constant-action kinematic rollout over 2 seconds.
It shows *whether* the raw action would have collided, not *how exactly* it
would have — this is a transparency tool, not a physics simulation.

The mock rollout disclaimer is always shown in the viewer overlay and embedded
in exported video metadata. No publication claim is allowed from mock rollout results.

---

## Usage

### Isaac Sim viewer (interactive)

```bash
conda activate isaac
cd ~/robotics/FleetSafe-VisualNav-Benchmark

# Run a benchmark episode first (to generate artifacts)
python scripts/visualnav/run_visualnav_benchmark.py \
  --backend mock --model gnm --seeds 0 --max-steps 50

# Then replay the episode
./scripts/isaaclab/replay_intervention.sh \
  --episode-dir benchmarks/visualnav/results/<run_id>/episodes/episode_0001

# Jump directly to interventions
./scripts/isaaclab/replay_intervention.sh \
  --episode-dir <path> \
  --jump-to-interventions \
  --speed 0.5
```

### Headless video export (no Isaac required)

```bash
python scripts/visualnav/export_intervention_video.py \
  --episode-dir benchmarks/visualnav/results/<run_id>/episodes/episode_0001 \
  --output replay.mp4 \
  --fps 4

# Intervention frames only
python scripts/visualnav/export_intervention_video.py \
  --episode-dir <path> \
  --output interventions_only.gif \
  --interventions-only
```

### Python API

```python
from fleet_safe_vla.envs.isaaclab.replay.intervention_replay import InterventionReplayViewer

viewer = InterventionReplayViewer(episode_dir="<path>").load()
print(viewer.manifest.summary())
print(viewer.version_warnings())
print(f"Interventions: {viewer.intervention_count} / {viewer.n_frames} frames")

# Step through all frames
for frame in viewer.frames:
    overlay = viewer.overlay_for(frame)
    edges   = viewer.graph_edges_for(frame)
    if frame.intervention_applied:
        cf = viewer.counterfactual_for(frame)
        print(f"Frame {frame.frame_idx}: {frame.causal_explanation}")
        print(f"  raw_collision={cf.raw_collision}  safe_collision={cf.safe_collision}")
```

---

## Limitations

1. **Mock rollout only**: The 2-D kinematic counterfactual does not account for
   robot dynamics, inertia, or sensor noise. Do not make publication claims
   about rollout results until the Isaac branching rollout backend is implemented.

2. **2-D visualization**: The viewer uses 2-D top-down geometry from the
   scene graph. 3-D obstacle heights are not rendered in the matplotlib exporter.
   The Isaac viewer spawns 3-D cylinders from the same 2-D coordinates.

3. **Heading not in evidence**: The `intervention_evidence.jsonl` does not store
   robot heading. Action vectors are rendered in world frame assuming heading=0.
   The trajectory trail uses recorded (x, y) positions correctly.

4. **No sensor frames**: RGB/depth frames are not stored in the current evidence
   format. The `rgb_frame_ref` and `depth_frame_ref` fields are reserved for
   future sensor recording infrastructure.
