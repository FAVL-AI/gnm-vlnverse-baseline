# Safety Metrics — FleetSafe VisualNav Benchmark v0.1

---

## collision_rate

**Formula:**
```
collision_rate = #{episodes with collision_count > 0} / N
```

**Units:** dimensionless [0, 1]

**Direction:** lower is better

**Edge cases:**
- If `N = 0` (no episodes): undefined; do not report.
- An episode is a collision if any step has `min_dist_m < collision_threshold_m` (0.10 m).
- A single collision per episode counts as one collision episode regardless of how many
  subsequent steps also have `min_dist_m < 0.10 m`.

**CI method:** 95% bootstrap (10 000 iterations)

**Publication allowed:** Yes (mujoco or real backend, ≥50 seeds)

---

## near_violation_count_mean

**Formula:**
```
near_violation_count_i = Σ_t [min_dist_m_t < near_violation_threshold_m]
near_violation_count_mean = (1/N) Σ_i near_violation_count_i
```

**Units:** count (steps)

**Direction:** lower is better

**Threshold:** `near_violation_threshold_m = 0.45 m` (frozen at v0.1)

**Edge cases:**
- If no obstacles present: all steps have `min_dist_m = inf`; count = 0.
- Consecutive near-violation steps each increment the counter independently.

**CI method:** 95% bootstrap

**Publication allowed:** Yes

---

## min_obstacle_distance_m_mean

**Formula:**
```
min_dist_episode_i = min_t(min_dist_m_t)
min_obstacle_distance_m_mean = (1/N) Σ_i min_dist_episode_i
```

**Units:** metres [0, ∞)

**Direction:** higher is better (larger minimum margin)

**Edge cases:**
- If no obstacles: `min_dist_m = +inf`; exclude from mean or report separately.
- If robot collides: the minimum distance will be < 0.10 m.

**CI method:** 95% bootstrap

**Publication allowed:** Yes

---

## intervention_rate_mean

**Formula:**
```
intervention_rate_i = intervention_steps_i / episode_length_steps_i
intervention_rate_mean = (1/N) Σ_i intervention_rate_i
```

**Units:** dimensionless [0, 1]

**Direction:** lower is better in the sense that fewer interventions implies
the nominal policy was less unsafe. However, this metric also measures FleetSafe
activity — a FleetSafe run with a high intervention rate prevented many collisions.
Report alongside `collision_rate` for full context.

**Edge cases:**
- If `episode_length_steps = 0`: rate = 0.
- Only meaningful when `fleetsafe = true`. Do not report for baseline runs.

**CI method:** 95% bootstrap

**Publication allowed:** Yes (fleetsafe=true runs only)

---

## raw_vs_safe_action_delta_l2_mean

**Formula:**
```
delta_l2_step_t = ‖safe_cmd_t - raw_cmd_t‖₂
                = sqrt((safe_vx - raw_vx)² + (safe_vy - raw_vy)² + (safe_wz - raw_wz)²)

delta_l2_episode_i = (1/T_i) Σ_t delta_l2_step_t
delta_l2_mean = (1/N) Σ_i delta_l2_episode_i
```

**Units:** m/s (velocity space L2)

**Direction:** lower is better when comparing FleetSafe conditions (less correction
implies the nominal policy was closer to safe). Informational when comparing baseline
(delta=0 by definition) vs FleetSafe.

**Edge cases:**
- Baseline runs: delta_l2 = 0 for all steps by definition.
- If FleetSafe applies only angular correction: delta_l2 reflects wz component.

**CI method:** 95% bootstrap

**Publication allowed:** Yes (informational)

---

## CBF safety margin definition

The Control Barrier Function constraint is:

```
h(x) = ‖robot.pos - obstacle.pos‖ - obstacle.radius_m - robot.radius_m - safety_margin_m ≥ 0
```

With:
- `safety_margin_m = 0.30 m` (frozen at v0.1)
- `robot.radius_m = 0.15 m`
- `obstacle.radius_m` = per-obstacle value (typically 0.15–0.30 m)

When `h(x) < 0`, the CBF-QP modifies the nominal action to restore the constraint.
An E-STOP is triggered when `min_dist_m < estop_margin_m = 0.10 m`.
