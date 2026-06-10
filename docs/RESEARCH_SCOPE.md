# Research Scope

## What this repository is

This repository is a **baseline implementation and reproducibility resource** for the General Navigation Model (GNM) evaluated on VLNVerse/Kujiale indoor navigation data within Isaac Sim.

It provides:

- Trajectory data validation and pose proof from `traj_data.pkl`.
- GNM visual-goal input/output format exposition (current RGB + goal RGB → local waypoint).
- Isaac Sim replay with start/current/goal camera views and live dashboard export.
- Manual test-drive data collection with per-step RGB, pose, and action logging.
- Manual episode replay and GNM-format conversion.
- An independent CustomVLN-Office proof-of-method scene.
- Source-code implementation proof documents for reviewer validation.

## What this repository is not

- It is **not** the full FleetSafe safety stack. Legacy FleetSafe technical content is preserved under `docs/legacy/` for reference only.
- It does **not** implement or claim a completed ROS2 closed-loop control loop. ROS2 integration is planned.
- It does **not** commit large datasets, generated image sequences, checkpoints, or dashboard renders.
- It does **not** claim a formal SOTA result. The current SR 20.0%, OSR 46.7%, NE 6.51 m are reproduced validation metrics.

## Implemented vs Planned

| Item | Status |
|------|--------|
| VLNVerse dataset proof (238 train, 15 val) | Implemented |
| Four Kujiale scenes indexed | Implemented |
| RGB frame validation | Implemented |
| `traj_data.pkl` pose validation | Implemented |
| GNM current/goal image input proof | Implemented |
| Local waypoint/action label derivation | Implemented |
| Live dashboard export | Implemented |
| Manual test-drive dry-run | Implemented |
| Manual episode replay | Implemented |
| Manual-to-GNM conversion | Implemented |
| CustomVLN-Office scene (proof-of-method) | Implemented |
| ROS2 closed-loop Isaac-to-GNM interface | Planned |
| Zero-shot/off-the-shelf GNM formal result | Pending validation |
| `kujiale_0271` full scene-holdout performance | Configured / Pending validation |

## Claims policy

All claims in this repository must be:

1. **Backed by a source file** in `scripts/gnm/` or evidence in `results/bo_reviewer_packet/`.
2. **Qualified** when incomplete: items not yet evaluated are marked Planned or Pending validation.
3. **Not overclaimed**: manual test-drive episodes are proof of data collection, not official benchmark results; CustomVLN-Office is proof-of-method, not an official VLNVerse metric.

## Current validated result

```text
Train trajectories : 238
Validation episodes: 15
Scenes             : kujiale_0092, kujiale_0118, kujiale_0203, kujiale_0271
SR                 : 20.0%   (3 / 15 episodes, final distance <= 3.0 m)
OSR                : 46.7%   (7 / 15 episodes ever within 3.0 m)
NE                 : 6.51 m  (mean final distance to goal)
```

Per-episode breakdown: `results/bo_reviewer_packet/03_success_rate_breakdown.md`
