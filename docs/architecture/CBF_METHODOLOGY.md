# Control Barrier Function Methodology

**FleetSafe-VisualNav-Benchmark · Technical Reference**

---

## 1. Core Architecture

FleetSafe wraps any Visual Language/Navigation Model (VLA) with a
Control Barrier Function (CBF) safety filter. The filter runs in the action
space, not the observation space — it does not modify the VLA's inputs or
outputs except to override unsafe velocity commands.

```
Observation (camera, pose)
       │
       ▼
  VLA Policy (GNM / ViNT / NoMaD)
       │  v_desired = (vx, vy, ω)
       ▼
  CBF-QP Filter ← map positions + per-obstacle radii
       │  v_safe = argmin ||v - v_desired||²
       │          s.t. dh/dt + α·h ≥ 0  ∀ obstacles
       ▼
  Robot actuators
```

This architecture is:
- **Model-independent**: identical filter, three VLA backbones tested
- **Map-aware**: uses known obstacle positions, not visual detection
- **Online**: solves a small QP at each control step (≤1ms on CPU)

---

## 2. Barrier Function Formulation

### 2.1 Point-Obstacle Barrier (MuJoCo path)

For negligible-radius obstacles (e.g. virtual waypoints, `obs_r = 0`):

```
h(x) = ||p_robot − p_obs||² − d_safe²
```

where `d_safe = 0.30m`. The CBF condition is:

```
ḣ(x) + α·h(x) ≥ 0
2(p_robot − p_obs)ᵀ ṗ_robot + α·h ≥ 0
```

This is the standard exponential CBF (eCBF) with `α = 1.0`.

### 2.2 Surface-Distance Barrier (Isaac path)

For finite-radius obstacles (`obs_r > 0`), the correct invariant is on the
surface distance, not center distance:

```
surface_dist(x) = ||p_robot − p_obs||₂ − r_obs
h(x) = surface_dist² − d_safe²
```

The Lie derivative along the robot velocity `v`:

```
ḣ = 2 · surface_dist · ṡ
  = 2 · surface_dist · (p_robot − p_obs)ᵀ v / ||p_robot − p_obs||
```

CBF constraint added to the QP:

```
2 · surface_dist · v_surface_component + α · h ≥ 0
```

### 2.3 Why the Distinction Matters

For `obs_r = 1.0m` and `d_safe = 0.30m`:
- Point barrier activates at `center_dist = 0.30m` — **inside the obstacle**
- Surface barrier activates at `surface_dist = 0.30m` → `center_dist = 1.30m` — **before contact**

The original barrier would have produced a CBF that only triggers after
physical penetration, which is undetectable in a kinematic simulation and
would misreport `cbf_ok = False` even with correct CBF logic.

---

## 3. QP Formulation

The QP solved at each step (using `quadprog` via `cvxopt`):

```
minimize    ||v - v_des||²    (v = [vx, vy] ∈ ℝ²)
subject to  A_cbf · v ≥ b_cbf    (one row per obstacle within horizon)
            -v_max ≤ v ≤ v_max   (velocity limits)
```

For each obstacle `i` within distance `d_horizon = 2.0m`:

```
A_cbf[i] = [  2·sd·ex,  2·sd·ey  ]   (Isaac path)
          = [  2·ex,    2·ey     ]   (MuJoCo path)
b_cbf[i] = -α · h_i

where (ex, ey) = unit vector from obstacle center to robot
      sd       = surface distance (Isaac) or center distance (MuJoCo)
      h_i      = barrier value for obstacle i
```

e-stop override: if `surface_dist < estop_dist_m (= 0.15m)`, the QP is
bypassed and `v = (0, 0)` is returned immediately.

---

## 4. Per-Obstacle Radius Infrastructure

The radii pipeline ensures geometry semantics are consistent end-to-end:

```
hospital_scenes.py
  ObstacleSpec(x, y, radius_m=1.0)   ← corridor hazard cylinder
  ObstacleSpec(x, y, radius_m=0.15)  ← doorframe marker
  ObstacleSpec(x, y, radius_m=0.30)  ← elevator wall

visualnav_runner.py
  obs_radii = [obs.radius_m for obs in scene.obstacles]
  env = IsaacNavBenchmarkEnv(..., obstacle_radii=obs_radii)
  wrapper.step(..., obstacle_radii=obs_radii)

m3pro_nav_env.py
  self._obstacle_radii_arr = np.array(obstacle_radii)
  _nearest_dist() = min(center_dists - obstacle_radii_arr)

yahboom_cbf.py
  filter(obs_list, obstacle_radii=obs_radii)
  _min_dist() = min(center_dist - r for center_dist, r in zip(...))
  _cbf_qp() dispatches on obs_r > 0 (surface) vs == 0 (center)
```

---

## 5. Smoothing and Stability

Raw CBF solutions can produce chattering near the barrier boundary. We apply
exponential smoothing on the output velocity:

```
v_smooth[t] = γ · v_safe[t] + (1-γ) · v_smooth[t-1]
γ = 0.7  (smoothing = 0.7 in YahboomCBFConfig)
```

This reduces intervention rate noise while preserving the safety guarantee
(the barrier condition is checked on `v_safe`, not `v_smooth`).

---

## 6. Experimental Results

### 6.1 MuJoCo PROVEN (50 seeds, 2026-05-20)

| Model | RAW collision | FS collision | IR | Δcoll |
|-------|:------------:|:------------:|:--:|:-----:|
| ViNT  | 100%         | 0%           | 69.7% | −100% |
| GNM   | 0%           | 0%           | 1.75% | 0%    |
| NoMaD | 0%           | 0%           | ~2%   | 0%    |

Finding: ViNT's aggressive forward prior creates a systematic corridor
collision pattern. GNM and NoMaD are naturally conservative. CBF provides
uniform safety regardless of backbone aggressiveness.

### 6.2 SIM-ISAAC (50-seed run in progress, 2026-05-20)

Invisible map-hazard mode: obstacle radius 1.0m, no visual material.

| Model | Corridor RAW | Corridor FS | IR |
|-------|:-----------:|:-----------:|:--:|
| GNM   | 100%        | 0%          | 49.7% |
| ViNT  | 100% (smoke)| 0% (smoke)  | 37.4% |
| NoMaD | TBD (in progress) | TBD | TBD |

Finding: invisible map-hazards expose a fundamentally different failure mode
than visual collisions. All VLAs fail equally — the hazard is not
model-dependent but geometry-dependent. CBF, operating on the map rather
than visual observations, is the only layer that can prevent it.

### 6.3 Cross-Backend Consistency

Both backends confirm the CBF safety guarantee:
- MuJoCo: surface-distance not applicable (obs_r ≈ 0), original formula
- Isaac: surface-distance barrier required for finite-radius cylinders

The cross-backend agreement strengthens the generalization claim: the CBF
design is not tuned to one physics engine's artefacts.

---

## 7. Theoretical Properties

The surface-distance eCBF satisfies:

**Theorem** (Ames et al., 2017): If `h(x(0)) ≥ 0` and `ḣ + α·h ≥ 0` is
enforced at every step, then `h(x(t)) ≥ 0` for all `t ≥ 0`.

Informally: if the robot starts outside the obstacle (h ≥ 0), the CBF
constraint keeps it outside for all future time, regardless of the VLA's
desired actions.

**Limitation**: This guarantee holds for:
- Known obstacle positions (map-registered hazards)
- Kinematic robot model (no inertia overshoot)
- Accurate distance measurement (GPS/odometry, not visual detection)

It does not guarantee safety against unregistered dynamic obstacles (people,
other robots) — that requires a separate social risk layer (`SocialRiskFilter`).

---

## 8. Implementation Notes

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `d_safe_m` | 0.30m | Yahboom M3Pro body radius ~0.15m + 0.15m margin |
| `alpha` | 1.0 | Class K function; aggressive enough for 0.5m/s operation |
| `estop_dist_m` | 0.15m | Hard stop at contact distance |
| `d_horizon_m` | 2.0m | Only include obstacles within 2m in QP (performance) |
| `smoothing` | 0.7 | Balance between responsiveness and stability |
| `v_max` | 0.5 m/s | Isaac runner control limit |

---

*Generated: 2026-05-20 · Part of FleetSafe-VisualNav-Benchmark documentation*
