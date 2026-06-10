# FleetSafe VisualNav Benchmark Protocol

This document specifies the exact procedure for producing publication-grade
results from the FleetSafe × VisualNav-Transformer benchmark stack.

---

## 1. Overview

The benchmark evaluates three upstream navigation policies (GNM, ViNT, NoMaD)
with and without the FleetSafe CBF-QP safety layer across four canonical scenes.
Each model × mode pair runs over identical seeds so any performance difference
is caused only by the safety layer.

**Primary research claim this benchmark supports:**
> FleetSafe reduces collision rate and near-violation frequency by X% and Y%
> respectively while preserving Z% of baseline SPL, as measured over N episodes
> per (model, scene, seed) cell.

---

## 2. Prerequisites

### 2.1 Software

```bash
bash scripts/visualnav/setup_visualnav.sh
source scripts/visualnav/activate_visualnav_env.sh
```

Gates 0–6 must all pass:

```bash
python -m fleet_safe_vla.integrations.visualnav_transformer.validate_gates
```

### 2.2 Checkpoints

```bash
bash scripts/visualnav/setup_visualnav.sh --download-weights
```

Expected sizes:
- `gnm.pth`   ≈ 100 MB
- `vint.pth`  ≈ 411 MB
- `nomad.pth` ≈ 73 MB

### 2.3 Simulation backend

- **Mock** (`--backend mock`): pipeline testing, CI, development.
  Results are NOT valid for publication claims.
- **MuJoCo** (`--backend mujoco`): publication backend.
  Requires `fleet_safe_vla/envs/mujoco/yahboom/nav_env.py` and
  `fleet_safe_vla/robots/yahboom/m3pro/mjcf/yahboom_m3pro.xml`.
- **Isaac Lab** (`--backend isaaclab`): not yet implemented (gate-failed).

---

## 3. Benchmark Matrix

| Model | Mode       | Scenes | Seeds (paper) | Pairs/Scene | Episodes |
|-------|------------|--------|---------------|-------------|----------|
| GNM   | baseline   | 4      | 50            | 3–4         | ≥600     |
| GNM   | FleetSafe  | 4      | 50            | 3–4         | ≥600     |
| ViNT  | baseline   | 4      | 50            | 3–4         | ≥600     |
| ViNT  | FleetSafe  | 4      | 50            | 3–4         | ≥600     |
| NoMaD | baseline   | 4      | 50            | 3–4         | ≥600     |
| NoMaD | FleetSafe  | 4      | 50            | 3–4         | ≥600     |

Estimated wall-clock (CPU, MuJoCo backend, ~20 ms/step × 300 steps × 3600 episodes): ~6 h.

---

## 4. Canonical Scenes

### 4.1 `straight_corridor`
Open 8×8 m arena, no obstacles. Tests forward navigation speed and efficiency.
Primary metrics: SPL, success rate, mean path length.

### 4.2 `cluttered_static`
8 cylindrical static obstacles (r=0.15 m) in an 8×8 m arena.
Tests collision avoidance without dynamic uncertainty.
Primary metrics: collision rate, near-violation count, SPL.

### 4.3 `narrow_passage`
Two obstacle walls leaving a 0.65 m gap. Tests precise lateral control.
Gap width is intentionally close to the M3Pro chassis width (≈0.34 m).
Primary metrics: success rate, near-violation count, intervention rate.

### 4.4 `dynamic_obstacle`
One circular-orbit obstacle (v≈0.75 m/s) + 3 static obstacles.
Tests temporal safety under moving obstructions.
Primary metrics: collision rate, near-violation count, SPL degradation vs baseline.

---

## 5. Observation Contract

All models receive identical inputs. Changing any field invalidates comparisons.

| Field        | Type                    | Shape          | Notes                                |
|-------------|-------------------------|----------------|--------------------------------------|
| `obs_imgs`  | `list[np.uint8]`        | `[H, W, 3]`    | context_size+1 frames, oldest first  |
| `goal_img`  | `np.uint8`              | `[H, W, 3]`    | Fixed goal image for episode         |
| `depth`     | `np.float32 | None`     | `[H, W]`       | metres; optional (not used by VNT)   |
| `lidar`     | `np.float32 | None`     | `[N_beams]`    | metres; optional (not used by VNT)   |

Image sizes per model (from upstream YAML configs):
- GNM: W=85, H=64
- ViNT: W=85, H=64
- NoMaD: W=96, H=96

Context sizes:
- GNM: 5
- ViNT: 5
- NoMaD: 3

---

## 6. Action Contract

| Field                | Type      | Notes                                          |
|---------------------|-----------|------------------------------------------------|
| `raw_cmd_vel`       | CmdVel    | Direct output of adapter.action_to_cmd_vel()  |
| `safe_cmd_vel`      | CmdVel    | After FleetSafe CBF-QP filter                 |
| `mecanum_fl/fr/rl/rr` | float  | Wheel speeds from IK (M3Pro only, rpm)        |

`CmdVel(vx, vy, wz)` — forward velocity (m/s), lateral velocity (m/s), yaw rate (rad/s).

---

## 7. Metrics

### 7.1 Navigation quality

| Metric               | Formula                                                  | Notes              |
|---------------------|----------------------------------------------------------|--------------------|
| `success_rate`       | Σ S_i / N                                               |                    |
| `spl_mean`           | (1/N) Σ [S_i × L_i* / max(p_i, L_i*)]                  | Anderson et al. '18 |
| `collision_rate`     | Σ C_i / N                                               | episode-level      |
| `path_length_m_mean` | mean total trajectory length                             |                    |
| `episode_length_steps_mean` | mean steps per episode                          |                    |

### 7.2 Safety

| Metric                        | Definition                                              |
|------------------------------|--------------------------------------------------------|
| `near_violation_count_mean`  | Mean steps per episode with obstacle < 0.45 m          |
| `min_obstacle_distance_m_mean` | Mean episode-minimum obstacle clearance              |
| `intervention_rate_mean`     | Mean CBF interventions / total steps (FleetSafe only)  |
| `raw_vs_safe_delta_l2_mean`  | Mean L2 distance between raw and safe cmd_vel per step |

### 7.3 Performance

| Metric                       | Definition                               |
|-----------------------------|------------------------------------------|
| `inference_latency_ms_mean` | Mean wall-clock time per inference step  |
| `inference_latency_ms_p95`  | 95th percentile inference latency        |
| `sim_fps_mean`              | 1000 / mean_latency_ms                   |
| `stuck_rate_mean`           | Stuck steps / episode length             |
| `smoothness_mean`           | Mean |Δcmd_vel| per step                  |

---

## 8. Seed Protocol

- Seeds 0–49 for paper-grade runs.
- Baseline and FleetSafe runs **must use identical seeds** so differences are
  caused only by the safety layer.
- Do not post-hoc filter seeds (e.g., remove "difficult" seeds).
- Report mean ± std across all seeds.

---

## 9. Running the Benchmark

### Smoke test (no checkpoints, mock backend)

```bash
python scripts/visualnav/run_visualnav_benchmark.py \
    --model gnm --seeds smoke --scenes straight_corridor \
    --backend mock --fleetsafe both
```

### Development (10 seeds, mock)

```bash
bash scripts/visualnav/run_publishable_matrix.sh \
    --seeds dev --backend mock
```

### Publication (50 seeds, MuJoCo)

```bash
source scripts/visualnav/activate_visualnav_env.sh
bash scripts/visualnav/run_publishable_matrix.sh \
    --seeds paper --backend mujoco
```

Output structure:

```
benchmarks/visualnav/results/
  {run_id}/
    metadata.yaml
    episodes/
      episode_0001/
        episode.json
        trajectory.csv
        actions.csv
        safety_events.jsonl
        metrics.json
    aggregate_metrics.json
    aggregate_metrics.csv
    aggregate_by_scene.json
benchmarks/visualnav/reports/
  comparison_{timestamp}.html
  comparison_{timestamp}.json
```

---

## 10. Statistical Reporting

For each (model, scene, mode) cell, report:
- mean ± std over N seeds
- 95% confidence interval (if N ≥ 30)

Comparison table structure (paper table format):

| Model | FS | Scene | SPL ↑ | Succ% ↑ | Coll% ↓ | NearMiss ↓ | IntervRate |
|-------|----|-------|-------|---------|---------|------------|------------|
| GNM   | —  | all   | 0.XXX | XX.X    | XX.X    | X.X        | —          |
| GNM   | ✓  | all   | 0.XXX | XX.X    | XX.X    | X.X        | XX.X%      |
| ...   |    |       |       |         |         |            |            |

---

## 11. What NOT to claim

1. Do not claim real-world performance from simulation results.
2. Do not claim SPL equivalence to the VNT paper's real-robot numbers without
   matching conditions (robot, environment, goal-image source).
3. Do not claim the CBF provides a formal safety guarantee in the presence of
   unknown obstacles (only a best-effort guarantee under known obstacle positions).
4. Do not run partial seeds (e.g., 5/50) and report as if full.
5. Do not exclude failed episodes from success/SPL computation — they count as 0.

See `docs/visualnav_reproduction/CLAIMS_AND_LIMITATIONS.md` for the full list.

---

## 12. Validation checklist before submission

- [ ] Gate 0–6 all pass (`python -m fleet_safe_vla.integrations.visualnav_transformer.validate_gates`)
- [ ] Full test suite passes (`pytest tests/ -v`)
- [ ] Paper-grade run completed: 50 seeds × 4 scenes × 6 conditions = ≥3600 episodes
- [ ] HTML/CSV report generated and reviewed
- [ ] Baseline and FleetSafe runs used identical seeds (verify from metadata.yaml)
- [ ] Mock backend results are excluded from all reported numbers
- [ ] Checkpoint checksums match expected values (see `configs/visualnav/models.yaml`)
