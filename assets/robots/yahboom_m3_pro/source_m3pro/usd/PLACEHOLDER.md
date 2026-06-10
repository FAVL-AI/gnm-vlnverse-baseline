# USD Cache Placeholder — `yahboom_m3pro.usd`

**This directory is auto-populated by Isaac Sim. No manual action required.**

When Isaac Sim first loads the M3Pro URDF, it converts it to USD format and
writes the cache here:

```
fleet_safe_vla/robots/yahboom/m3pro/usd/
├── yahboom_m3pro.usd           ← auto-generated (takes ~3 min first run)
└── yahboom_m3pro/              ← cache subdirectory
    ├── meshes/
    ├── materials/
    └── ...
```

## When does auto-generation happen?

On the first call to any script that loads the M3Pro articulation:

```bash
# GUI viewer (once M3Pro URDF exists):
./scripts/isaaclab/view_yahboom.sh --robot m3pro

# Headless bridge:
./scripts/isaaclab/run_yahboom_bridge.sh --robot m3pro

# Training Stage 1:
./scripts/isaaclab/train_yahboom.sh --stage 1
```

The USD conversion is triggered by `UrdfFileCfg(usd_dir=...)` in
`yahboom_m3pro_env_cfg.py`. Subsequent runs load from the cache and start
in seconds.

## Git policy

USD files are large binaries — **do not commit them to git**.

Ensure `.gitignore` (project root) contains:
```
fleet_safe_vla/robots/yahboom/m3pro/usd/*.usd
fleet_safe_vla/robots/yahboom/m3pro/usd/yahboom_m3pro/
data/usd_cache/yahboom_m3pro/
```

## Cache invalidation

If the URDF changes (geometry, joint limits, masses), delete the cache and
let Isaac Sim regenerate it:

```bash
rm -rf fleet_safe_vla/robots/yahboom/m3pro/usd/yahboom_m3pro.usd \
       fleet_safe_vla/robots/yahboom/m3pro/usd/yahboom_m3pro/
# Then re-run any Isaac Sim script to regenerate
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Isaac Sim takes 3+ min every time | Cache missing or in wrong path | Check `usd_dir` param in env_cfg |
| Conversion fails with USD error | URDF has missing inertials or bad mesh | Fix URDF, see `urdf/PLACEHOLDER.md` |
| Wrong geometry in simulation | URDF changed but cache not invalidated | Delete cache (see above) |
| Robot spawns at origin with wrong pose | USD origin mismatch | Check `init_state.pos` in env_cfg |
