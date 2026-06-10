# FleetSafe × VisualNav-Transformer: Reproduction and Benchmark

## Overview

This document describes the reproduction pipeline for
**GNM / ViNT / NoMaD** from the upstream
[visualnav-transformer](https://github.com/robodhruv/visualnav-transformer)
repository, integrated with the **FleetSafe** safety layer running on the
Yahboom RosMaster M3Pro in MuJoCo / Isaac Lab.

The pipeline enables two things:

1. **Reproduction**: reproduce GNM / ViNT / NoMaD navigation on the M3Pro
   in simulation with the same seeds and scenes.
2. **Comparison**: run identical episodes with FleetSafe wrapping the nominal
   policy — same model, same data, same seeds — and measure the safety delta.

## Quick Start

### 1. Clone upstream + install dependencies

```bash
bash scripts/visualnav/setup_visualnav.sh
```

This clones `third_party/visualnav-transformer`, installs the upstream packages
in editable mode, and verifies imports.

### 2. Download checkpoints

```bash
bash scripts/visualnav/setup_visualnav.sh --download-weights
```

Checkpoint sizes: GNM ~250 MB, ViNT ~100 MB, NoMaD ~400 MB.
See `configs/visualnav/models.yaml` for Google Drive IDs and expected paths.

### 3. Validate reproduction gates

```bash
python -m fleet_safe_vla.integrations.visualnav_transformer.validate_gates
```

Gates 0–6 must all pass before the benchmark matrix runs.

### 4. Run the full benchmark matrix

```bash
bash scripts/visualnav/run_matrix.sh
```

Or smoke-test (1 seed, 1 scene, 50 steps):

```bash
bash scripts/visualnav/run_matrix.sh --smoke-test
```

### 5. Export the report

```bash
python scripts/visualnav/export_report.py \
  --input  benchmarks/visualnav/results/ \
  --output-dir benchmarks/visualnav/reports/
# → HTML report + CSV
```

### 6. Launch the dashboard

```bash
python web/robot_web_viewer/app.py
# Open http://localhost:8080/visualnav
```

## Architecture

```
third_party/visualnav-transformer/     ← upstream (unchanged)
  train/gnm_train/models/gnm.py
  train/vint_train/models/vint.py
  train/nomad/nomad/nomad.py

fleet_safe_vla/integrations/visualnav_transformer/
  base_adapter.py          ← abstract interface (CmdVel, ActionOutput)
  gnm_adapter.py           ← wraps upstream GNM
  vint_adapter.py          ← wraps upstream ViNT
  nomad_adapter.py         ← wraps upstream NoMaD (diffusion)
  fleetsafe_wrapper.py     ← CBF-QP safety layer on top of any adapter
  isaac_obs_adapter.py     ← camera obs bridge (MuJoCo renderer / Isaac Sim)
  benchmark_runner.py      ← episode runner + metric collection
  validate_gates.py        ← gates 0–6 checker

configs/visualnav/
  models.yaml              ← checkpoint paths, image sizes, action horizons
  isaac_benchmark.yaml     ← scenes, seeds, start/goal pairs

scripts/visualnav/
  setup_visualnav.sh       ← clone + install + verify
  run_baseline_isaac.sh    ← one model, baseline
  run_fleetsafe_isaac.sh   ← one model, FleetSafe-wrapped
  run_matrix.sh            ← full 3×2×3×5×5 matrix
  export_report.py         ← HTML + CSV report

benchmarks/visualnav/
  results/                 ← JSON per run (gitignored if large)
  reports/                 ← HTML + CSV reports
  results_schema.json      ← JSON Schema for validation
```

## Benchmark Matrix

| Model | Mode | Scenes | Seeds | Pairs | Episodes |
|-------|------|--------|-------|-------|----------|
| GNM   | Baseline  | 3 | 5 | 5 | 75 |
| GNM   | FleetSafe | 3 | 5 | 5 | 75 |
| ViNT  | Baseline  | 3 | 5 | 5 | 75 |
| ViNT  | FleetSafe | 3 | 5 | 5 | 75 |
| NoMaD | Baseline  | 3 | 5 | 5 | 75 |
| NoMaD | FleetSafe | 3 | 5 | 5 | 75 |
| **Total** | | | | | **450** |

Estimated wall-clock time (CPU, ~15 ms/step × 500 steps × 450 episodes): ~56 min.
With GPU and faster inference: proportionally faster.

## Metrics

| Metric | Definition |
|--------|-----------|
| success_rate | Fraction reaching goal within MAX_STEPS |
| collision_rate | Fraction ending in collision |
| near_violation_count | Steps within 0.45 m of obstacle |
| min_obstacle_dist_m | Minimum clearance to obstacle |
| intervention_count | CBF-QP interventions per episode (FleetSafe only) |
| time_to_goal_s | Steps to success / control_hz |
| path_length_m | Total trajectory length |
| smoothness | Mean |Δcmd_vel| per step |
| stuck_count | Consecutive stuck streaks |
| latency_ms | Wall-clock time per inference+safety step |
| cmd_vel_delta | |safe - raw| cmd_vel per step |

## Reproduction Gates

| Gate | Description | Required for |
|------|-------------|--------------|
| 0 | Upstream repo cloned and importable | All runs |
| 1 | Checkpoint files exist | Inference |
| 2 | Static inference on synthetic images | Model correctness |
| 3 | Camera obs adapter produces correct shape | Visual input pipeline |
| 4 | Baseline model outputs cmd_vel in sim | Simulation pipeline |
| 5 | FleetSafe wrapper runs on mock data | Safety layer |
| 6 | Report export produces HTML + CSV | Results publication |

## Simulation Backend

**Default: MuJoCo 3.x** with the M3Pro MJCF
(`fleet_safe_vla/robots/yahboom/m3pro/mjcf/yahboom_m3pro.xml`).

Isaac Lab support is planned for Stage 2+ (see `configs/visualnav/isaac_benchmark.yaml`).
The benchmark runner will switch backends when `simulation_backend: isaaclab` is set
in the config.

## FleetSafe Safety Layer

`FleetSafeWrapper` wraps any adapter and applies `YahboomCBFFilter` (CBF-QP):

- Minimises ‖u − u_nom‖² subject to CBF barrier constraints.
- E-STOP if obstacle closer than `estop_dist_m` (default 0.15 m).
- All interventions are logged (reason, min_dist, delta_cmd_vel).
- Holonomic: vx, vy both filtered; wz from CBF heading correction.

See `fleet_safe_vla/fleet_safety/yahboom_cbf.py` for the QP formulation.
