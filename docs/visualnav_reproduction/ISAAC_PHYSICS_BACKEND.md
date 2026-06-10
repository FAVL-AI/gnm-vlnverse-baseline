# Isaac Lab Physics Backend

## Purpose and claim scope

Isaac Lab is the second physics backend for the FleetSafe VisualNav Benchmark,
complementary to MuJoCo.

| Backend | Status | Claim scope |
|---|---|---|
| MuJoCo | Active | `simulation_mujoco` — current publication evidence |
| Isaac Lab | **SIM-TO-SIM GATE PASSED (2026-05-21)** | `simulation_isaaclab` — publication-grade evidence |
| Isaac Sim replay | Active (always) | Visualization only — no metric claims |

**Isaac Lab physics results may not be cited in publication until the
sim-to-sim validation gate passes** (see §Validation gate below).

---

## Architecture

```
AppLauncher (boots Isaac Sim process)
  │
  └── run_visualnav_benchmark_isaac.py
        │
        ├── VisualNavBenchmarkRunner(backend="isaaclab")
        │     │
        │     └── _run_isaaclab_episode()
        │           │
        │           └── IsaacNavBenchmarkEnv
        │                 ├── SimulationContext (Isaac physics, 100 Hz)
        │                 ├── Robot placeholder (kinematic box, 2.1 kg)
        │                 ├── Obstacle cylinders (kinematic, r=0.10 m)
        │                 └── Kinematic cmd_vel integration (same as MuJoCo)
        │
        └── Same output artifacts as MuJoCo:
              episode.json / trajectory.csv / actions.csv
              safety_events.jsonl / metrics.json
              intervention_evidence.jsonl / scene_graphs.jsonl
```

### Physics model

The Isaac backend uses **kinematic integration** for robot motion — identical
to the MuJoCo baseline:

```
x_new   = x + vx * cos(yaw) * dt
y_new   = y + vx * sin(yaw) * dt
yaw_new = yaw + wz * dt
```

This is intentional.  MuJoCo also uses kinematic integration (not actuator
dynamics) to avoid physics instability before measured M3Pro inertial parameters
are available.  Identical kinematics means the two backends produce directly
comparable metrics, which is required by the sim-to-sim validation gate.

**Upgrade path**: replace the kinematic box with the M3Pro articulated URDF/USD
when physical inertial measurements are complete.  All other benchmark
infrastructure remains unchanged.

### Obstacle placement

Obstacles are kinematic rigid cylinders (r=0.10 m, h=0.50 m) spawned at exact
SceneSpec (x, y) coordinates.  Isaac's physics engine handles their rigid-body
presence and collision geometry.  Distance queries use the same Python math as
MuJoCo (no Isaac contact API) to guarantee metric comparability.

### Observation contract

The 47-dim observation vector is identical to the MuJoCo backend
(produced by `M3ProObsAdapter` from kinematic state):

```
[0:10]   IMU:    ax, ay, az, wx, wy, wz, qx, qy, qz, qw
[10:22]  Joints: fl/fr/rl/rr pos, vel, eff (from kinematic wheel speed est.)
[22:32]  Odom:   x, y, z, qx, qy, qz, qw, vx, vy, vyaw
[32:47]  Cmd hist: 5 × [vx, vy, wz]
```

The FleetSafe CBF-QP reads `robot_xy` from `obs[22:24]` — the world-frame
position is identical between backends since both use the same kinematic state.

---

## Prerequisites

| Requirement | Check |
|---|---|
| `conda activate isaac` | `python -c "import isaaclab; print('ok')"` |
| M3Pro checkpoints | `check_visualnav_checkpoints.py --model gnm` |
| Gate checks pass | `python scripts/visualnav/check_isaac_physics_backend.py` |
| Isaac Sim streaming (optional for visual) | `ls ~/isaacsim/isaac-sim.streaming.sh` |

---

## Running the benchmark

```bash
# Activate Isaac conda environment
conda activate isaac

# Verify gate checks (6/7 pass without Isaac Sim; check 7 needs AppLauncher)
python scripts/visualnav/check_isaac_physics_backend.py

# Smoke test (1 seed, cluttered_static, headless)
python scripts/visualnav/run_visualnav_benchmark_isaac.py \
    --model gnm \
    --seeds smoke \
    --scenes cluttered_static \
    --fleetsafe both \
    --headless

# Development matrix (3 seeds, all scenes)
python scripts/visualnav/run_visualnav_benchmark_isaac.py \
    --model all \
    --seeds dev \
    --scenes all \
    --fleetsafe both \
    --headless

# With Isaac streaming (visual inspection)
# Step 1: on Isaac workstation
cd ~/isaacsim && ./isaac-sim.streaming.sh

# Step 2: launch benchmark (streaming server already running)
python scripts/visualnav/run_visualnav_benchmark_isaac.py \
    --model gnm --seeds smoke --scenes cluttered_static \
    --fleetsafe both
# (omit --headless — connects to streaming server)
```

### Output artifacts

Same layout as MuJoCo (`benchmarks/visualnav/results/<run_id>/`):

```
<run_id>/
  metadata.yaml              (backend: isaaclab, claim_scope: simulation_isaaclab)
  aggregate_metrics.json
  aggregate_metrics.csv
  aggregate_by_scene.json
  episodes/
    episode_NNNN/
      episode.json
      trajectory.csv
      actions.csv
      safety_events.jsonl
      metrics.json
      intervention_evidence.jsonl
      scene_graphs.jsonl
      explanation_log.jsonl
      counterfactuals.jsonl
      audit_trail.json
```

The replay viewer (`scripts/isaaclab/replay_intervention.sh`) works
identically with Isaac backend artifacts.

---

## Simulation gate checks

```bash
# CI gate (no Isaac required — checks 1-6)
python scripts/visualnav/check_isaac_physics_backend.py

# Full gate (inside AppLauncher — check 7)
conda activate isaac
python -c "
from isaaclab.app import AppLauncher
app = AppLauncher({'headless': True}).app
import subprocess, sys
ret = subprocess.call(['python', 'scripts/visualnav/check_isaac_physics_backend.py', '--with-isaac'])
app.close()
sys.exit(ret)
"
```

| Check | Description | Requires Isaac |
|---|---|---|
| 1. `env_module_importable` | `IsaacNavBenchmarkEnv` importable without Isaac | No |
| 2. `error_class_importable` | `IsaacNotAvailableError` importable | No |
| 3. `raises_without_applaunch` | Init raises loudly outside AppLauncher | No |
| 4. `scene_obs_positions_match` | Isaac scene cfg matches SceneSpec ±1 mm | No |
| 5. `kinematic_formula_matches` | Kinematic integration matches MuJoCo formula | No |
| 6. `obs_vector_dim_consistent` | Both env and adapter report OBS_DIM=47 | No |
| 7. `isaac_env_reset_step` | Full reset/step/teleport_to inside Isaac | Yes |

---

## Sim-to-sim validation gate

Before Isaac Lab results may carry `claim_scope: simulation_isaaclab` in
published work, they must pass the three-way validation against MuJoCo:

```
Step 1: Run N episodes on MuJoCo backend (frozen scene + seed)
Step 2: Run same N episodes on Isaac Lab backend (same scene + seed)
Step 3: Compare across N episodes:
  a) intervention_count per episode: must agree within ±2
  b) collision_count: must agree (0 ↔ 0, ≥1 ↔ ≥1)
  c) trajectory Fréchet distance: must be < 0.5 m
Step 4: If all three checks pass for ≥ 80% of episodes:
        Isaac backend claim gate PASSES
```

Status: **not yet run**.  MuJoCo remains the authoritative backend until
this gate passes.

See `docs/architecture/PPO_DDS_SIM2SIM_DEPLOYMENT.md` §sim-to-sim validation
for the full validation protocol.

---

## Fail policy

```
If --backend isaaclab requested + Isaac not available:
  → IsaacNotAvailableError raised at episode time (loud, traceable)
  → NEVER falls back to mock
  → exit code non-zero

If --backend isaaclab requested outside AppLauncher process:
  → Same: IsaacNotAvailableError
  → Message includes entry point path

If M3Pro URDF/USD missing:
  → Robot placeholder (kinematic box) is used instead
  → Warning printed: "M3Pro USD not found — using kinematic box placeholder"
  → Benchmark runs normally; results are still valid (same kinematics)
```

---

## Files

| File | Role |
|---|---|
| `fleet_safe_vla/envs/isaaclab/yahboom/m3pro_nav_env.py` | Isaac physics env (gym API) |
| `fleet_safe_vla/benchmarks/visualnav_runner.py` | `_run_isaaclab_episode()` |
| `scripts/visualnav/run_visualnav_benchmark_isaac.py` | AppLauncher-first entry point |
| `scripts/visualnav/check_isaac_physics_backend.py` | 7-check gate script |
| `tests/test_isaac_physics_backend.py` | CI + live tests |
| `fleet_safe_vla/envs/isaaclab/yahboom_m3pro/scene_cfg.py` | Isaac scene geometry |
| `docs/architecture/PPO_DDS_SIM2SIM_DEPLOYMENT.md` | Sim-to-sim validation gate |
| `docs/governance/CLAIMS_AND_LIMITATIONS.md` | Publication claim policy |
