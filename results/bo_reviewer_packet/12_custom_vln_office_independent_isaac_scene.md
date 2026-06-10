# CustomVLN-Office — Independent Isaac Sim Navigation Scene

**Date:** 2026-06-09  
**Branch:** `gnm-vlnverse-baseline`

---

## Why this was created

Bo raised a valid challenge: to what extent does the project depend on VLNVerse assets and datasets?

This file documents an independent answer.

**CustomVLN-Office** is an entirely separate Isaac Sim environment built without any VLNVerse scenes, trajectories, or labels. It proves that the GNM-style methodology can be reproduced from scratch using only Isaac Sim assets and our own scene design.

---

## Important distinction

| | VLNVerse Reproduction | CustomVLN-Office |
|---|---|---|
| Purpose | Official Track A benchmark | Independent proof-of-method |
| Scene assets | VLNVerse kujiale USD files | Isaac Sim USD primitives |
| Trajectories | VLNVerse collected data | Scripted + manual episodes |
| Official benchmark? | Yes (SR 20.0%, OSR 46.7%, NE 6.51 m) | No — controlled demonstration |
| VLNVerse dependency | Required | None |

**CustomVLN-Office is not a VLNVerse benchmark result. It is a controlled proof-of-method.**

---

## Evidence statement

> CustomVLN-Office uses Isaac Sim assets to create an independent navigation environment. It does not use VLNVerse scenes, trajectories, or labels. The purpose is to demonstrate that the GNM-style pipeline can be built and controlled by us from scratch in Isaac Sim.

---

## What uses Isaac Sim assets

- Floor: UsdGeom.Mesh (grey)
- Walls: UsdGeom.Cube (white, perimeter)
- Desks (4×): UsdGeom.Cube (brown, scaled to desk dimensions)
- Chairs (3×): UsdGeom.Cube (dark grey)
- Cabinets (2×): UsdGeom.Cube (grey)
- Plants (2×): UsdGeom.Sphere (green)
- Shelf: UsdGeom.Cube (beige)
- Meeting table: UsdGeom.Cube (wood-brown)
- Partition wall: UsdGeom.Cube (partial room divider)
- Lights: UsdLux.RectLight × 2 + SphereLight × 1
- Cameras: UsdGeom.Camera (overview + robot eye-height)

All objects are Isaac Sim USD primitives. When Isaac Sim Nucleus assets are available, the scene generator attempts to use them first, falling back to primitives.

## What does NOT use VLNVerse

- No kujiale scene USD files
- No VLNVerse trajectory pkl files
- No VLNVerse episode metadata
- No VLNVerse evaluation splits
- No VLNVerse instructions dataset

---

## Scene design

**Floor plan:** 16 m × 10 m

```
y=10 ─────────────────────────────────────────────────
      │  MEETING AREA         HALLWAY               │
      │  (x=4..10, y=5..10)   (x=10..16, y=5..10)  │
y=5  ─┤──────────────────────────────────────────── │
      │ ENT.│ OPEN OFFICE A   OPEN OFFICE B         │
      │     │(x=4..10,y=0..5) (x=10..16,y=0..5)    │
y=0  ─────────────────────────────────────────────────
      x=0   x=4               x=10                x=16
```

Key positions:
- Entrance: (2, 5)
- Desk A: (5.5, 1.5)
- Desk B: (8.5, 1.5)
- Desk C: (12, 1.5)
- Meeting table: (7, 8.5)
- Cabinet A: (15.2, 7)
- Shelf: (15, 2.5)
- Hallway end: (14, 8)

---

## Robot and camera setup

- **Robot marker:** blue cube 0.5 m × 0.5 m × 0.5 m
- **Camera height:** 1.2 m (eye level)
- **Camera FOV:** ~70° horizontal (focal length 16 mm, aperture 20 mm)
- **Image resolution:** 480 × 360 pixels (JPEG)
- **Frame rate:** 10 Hz equivalent (1 frame per trajectory step)

---

## RGB data collection

The collection script `collect_custom_vln_office_data.py` executes scripted navigation episodes:

1. Loads episode waypoints from `configs/custom_vln_office/tasks.yaml`
2. Interpolates smooth paths between waypoints (10 steps per segment)
3. Moves the robot camera along each path
4. Captures one RGB frame per step (Isaac Sim rendering or synthetic placeholder)
5. Records x, y, yaw per frame

**Dry-run mode** generates the complete dataset structure with synthetic placeholder frames (colour-coded by frame index) without requiring Isaac Sim.

---

## x/y/yaw logging

Every frame records:
- `x`, `y`: world-frame position (metres)
- `yaw`: robot heading (radians)

These are stored in `traj_data.pkl` as:
```python
{
    "position": numpy array (T, 2),
    "yaw": numpy array (T,),
    ...
}
```

The same format as the VLNVerse reproduction, enabling the same GNM training code.

---

## Local waypoint/action labels

Labels are derived at collection time (not predicted by a model):

```
For frame i with horizon h:
  waypoint_world = position[i + h] - position[i]
  waypoint_robot = rotate(waypoint_world, -yaw[i])   # into robot frame
```

Stored in `traj_data.pkl` as `local_waypoints: list[(lx, ly)]`.

Per-frame actions (consecutive pose deltas) are stored in `actions.jsonl`:
```json
{"frame_index": 0, "action_dx": 0.03, "action_dy": 0.0, "action_dyaw": 0.0,
 "local_waypoint_x": 0.15, "local_waypoint_y": 0.0, ...}
```

**In Isaac Sim:** orange cone markers (`WAYPOINT_00`…`WAYPOINT_04`) show the next 5 waypoint targets from the current frame. These are ground-truth derived labels, **not model predictions**.

---

## GNM input/output mapping

| | Value |
|---|---|
| GNM input 1 | Current RGB frame (camera at current robot pose) |
| GNM input 2 | Goal RGB frame (camera at goal pose, last frame of episode) |
| GNM output | Local waypoint (delta_x, delta_y) in robot frame |
| Label source | Consecutive trajectory poses in traj_data.pkl |

This is identical to the VLNVerse reproduction methodology.

---

## Navigation episodes

Defined in `configs/custom_vln_office/tasks.yaml`:

| Episode | Split | Instruction (abbreviated) |
|---------|-------|--------------------------|
| cvlo_ep001 | train | Navigate from entrance to desk area |
| cvlo_ep002 | train | Move through office to meeting room |
| cvlo_ep003 | train | Walk through entire office to hallway end |
| cvlo_ep004 | train | Leave meeting room, go to back desk |
| cvlo_ep005 | train | Desk to cabinet near hallway |
| cvlo_ep006 | train | Walk back from hallway to entrance |
| cvlo_ep007 | val | Back desk to meeting table |
| cvlo_ep008 | val | Entrance to shelf at far wall |

---

## Replay and evaluation

### Replay

```bash
# Dry-run (no Isaac Sim):
python3 scripts/gnm/replay_custom_vln_office.py --dry-run --episode cvlo_ep001

# Isaac Sim:
EPISODE=cvlo_ep003 conda run -n isaac python scripts/gnm/replay_custom_vln_office.py
```

The replay shows:
- `CUSTOM_SCENE_NAME_PANEL`: scene identity, episode, split, instruction
- `DATASET_PROOF_PANEL`: confirms no VLNVerse assets, RGB/label sources
- `GNM_INPUT_PANEL`: current obs + goal image side-by-side
- Orange cones: ground-truth waypoint targets

### Evaluation

```bash
python3 scripts/gnm/evaluate_custom_vln_office.py --dry-run
```

Computes: path length, final distance to goal, waypoint label availability, RGB frame count.

If `checkpoints/gnm_base/best.pt` loads, reports checkpoint status.  
Does **not** fake model predictions on the custom scene.

---

## Limitations

1. **Not an official benchmark result.** CustomVLN-Office performance cannot be compared with VLNVerse Track A (SR 20.0%, OSR 46.7%, NE 6.51 m).

2. **Synthetic RGB in dry-run.** Dry-run frames are colour-gradient placeholders. Real rendered frames require Isaac Sim.

3. **Model not yet evaluated on custom scene.** GNM was trained on VLNVerse data. Applying it directly to CustomVLN-Office without fine-tuning will give degraded performance (domain gap).

---

## Next steps

1. Collect more custom episodes (20–30 train, 5 val) with real Isaac Sim RGB frames
2. Fine-tune GNM on custom scene data
3. Evaluate on held-out custom val episodes
4. Report custom-scene SR/NE metrics (clearly labelled as custom, not VLNVerse)

---

## One-command demo

```bash
bash scripts/gnm/run_custom_vln_office_demo.sh
```

This runs all dry-run commands and prints Isaac Sim commands.

---

## File index

| File | Purpose |
|------|---------|
| `scripts/gnm/discover_isaac_assets.py` | Find Isaac Sim / Nucleus assets |
| `scripts/gnm/create_custom_vln_office_scene.py` | Build the USD scene |
| `scripts/gnm/collect_custom_vln_office_data.py` | Collect RGB + labels |
| `scripts/gnm/manual_custom_vln_office_drive.py` | Manual keyboard drive |
| `scripts/gnm/replay_custom_vln_office.py` | Isaac Sim replay |
| `scripts/gnm/evaluate_custom_vln_office.py` | Metrics + model probe |
| `scripts/gnm/run_custom_vln_office_demo.sh` | One-command demo |
| `configs/custom_vln_office/tasks.yaml` | 8 navigation episodes |
| `datasets/custom_vln_office/` | Collected episode data |
| `assets/custom_vln_office/` | USD scene file |
| `results/custom_vln_office/` | Manifests, eval results |
