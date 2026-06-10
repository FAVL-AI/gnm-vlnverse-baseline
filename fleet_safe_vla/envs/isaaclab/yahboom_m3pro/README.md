# Yahboom M3Pro — Isaac Sim / Isaac Lab Integration

## Status

| Component | Status |
|---|---|
| URDF (structural baseline) | ✅ Available — `fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf` |
| USD cache | Generated on first Isaac Sim run → `fleet_safe_vla/robots/yahboom/m3pro/usd/` |
| Isaac Sim viewer | ✅ `scripts/isaaclab/view_m3pro.sh` |
| Asset gate checker | ✅ `scripts/isaaclab/check_m3pro_isaac_asset.py` |
| Scene configs (4 scenes) | ✅ `scene_cfg.py` — matches SCENESET_v0.1.yaml |
| RL environment | Pending — do not implement until inertials are verified |
| FleetSafe Isaac backend | Pending — Gate-failed until viewer validates |
| Inertials (physically measured) | Pending — box approximations only |
| Mesh geometry (STL/DAE) | Pending — primitive geometry only |

---

## Quick start

```bash
# Check asset readiness (no Isaac Sim required)
python scripts/isaaclab/check_m3pro_isaac_asset.py

# Launch Isaac Sim viewer (requires conda activate isaac)
./scripts/isaaclab/view_m3pro.sh

# View a specific scene
./scripts/isaaclab/view_m3pro.sh --scene cluttered_static
```

---

## Module structure

```
fleet_safe_vla/envs/isaaclab/yahboom_m3pro/
├── __init__.py
├── asset_cfg.py     ← ArticulationCfg factory + asset path constants
├── scene_cfg.py     ← IsaacSceneCfg for all 4 canonical scenes
└── README.md        ← this file
```

---

## Asset pipeline

```
URDF (yahboom_m3pro.urdf)
    │
    ▼  Isaac Sim UrdfConverter (automatic on first run)
USD cache (fleet_safe_vla/robots/yahboom/m3pro/usd/)
    │
    ▼  Isaac Lab ArticulationCfg
Robot Articulation in /World/Yahboom_M3Pro
```

The USD cache is generated automatically on the first viewer run. It is listed
in `.gitignore` as part of `data/usd_cache/` and should not be committed unless
intentionally frozen.

---

## Scene geometry

All four canonical scenes are defined in `scene_cfg.py` and match the frozen
scene manifests in `benchmarks/scenes/canonical/SCENESET_v0.1.yaml` exactly:

| Scene | Description |
|---|---|
| `straight_corridor` | 10 m corridor, no obstacles |
| `cluttered_static` | 4 static cylinder obstacles |
| `narrow_passage` | 0.8 m gap between two large obstacles |
| `dynamic_obstacle` | Single dynamic crossing agent |

---

## FleetSafe visualization overlay

The viewer renders the following debug overlays (when FleetSafe is active):

| Overlay | Description |
|---|---|
| Robot pose trail | Last 50 positions as small spheres |
| Goal marker | Green flat cylinder at goal position |
| Obstacle markers | Red cylinders matching scene spec |
| Raw cmd_vel arrow | White arrow showing nominal policy command |
| Safe cmd_vel arrow | Green arrow showing CBF-filtered command |
| Intervention marker | Red sphere above robot when FleetSafe modifies action |
| Nearest obstacle line | Yellow line from robot to nearest obstacle |
| Safety margin ring | Yellow circle at 0.30 m radius around robot |

---

## Inertial baseline warning

The current URDF uses box/cylinder inertial approximations computed from
product-spec masses. These are **placeholder values** that cause approximately
30% velocity tracking error in sim-to-real transfer.

Before any RL training or sim-to-real claim:
1. Weigh each component on a precision scale (±1 g)
2. Measure dimensions with digital calipers (±0.5 mm)
3. Replace inertial values in the URDF
4. Re-verify kinematics with `check_m3pro_isaac_asset.py`

See `fleet_safe_vla/robots/yahboom/m3pro/ASSET_IMPORT_PLAN.md` for the
complete measurement checklist.

---

## Transparency contract

Every viewer session writes to `logs/isaac_m3pro/`:

```
viewer_session.json    — session metadata, asset paths, warnings, version fields
trajectory.csv         — step-by-step robot pose
actions.csv            — raw + safe cmd_vel per step
safety_events.jsonl    — near-miss and intervention events
scene_graphs.jsonl     — per-step causal scene graphs
explanation_log.jsonl  — per-step natural language explanations
```

These files are git-ignored. The transparency contract (`validate_transparency_artifacts`)
will pass on these outputs when the Isaac backend is fully implemented.

---

## Gate status

The Isaac Lab backend is gate-failed until:

- [ ] `check_m3pro_isaac_asset.py` returns PASS on all checks
- [ ] USD cache generates without errors
- [ ] Ground contact test passes (100 steps, no NaNs, robot stays on ground)
- [ ] 4 wheel joints confirmed in articulation
- [ ] Camera frame confirmed
- [ ] FleetSafe wrapper integrates with Isaac observation space

Run `scripts/visualnav/check_isaac_scenes.py --backend isaaclab` for the
full gate checklist.
