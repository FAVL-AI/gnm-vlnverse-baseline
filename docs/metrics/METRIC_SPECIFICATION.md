# Metric Specification — FleetSafe VisualNav Benchmark v0.1

**METRICSET_VERSION: 0.1.0** — frozen. See `docs/governance/METRIC_IMMUTABILITY.md`.

---

## Metric index

| Metric | Category | Direction | Publication allowed |
|---|---|---|---|
| `success_rate` | Navigation | Higher better | Yes (mujoco, ≥50 seeds) |
| `spl_mean` | Navigation | Higher better | Yes |
| `path_length_m_mean` | Navigation | Lower better | Yes |
| `time_to_goal_s_mean` | Navigation | Lower better | Yes |
| `collision_rate` | Safety | Lower better | Yes |
| `near_violation_count_mean` | Safety | Lower better | Yes |
| `min_obstacle_distance_m_mean` | Safety | Higher better | Yes |
| `intervention_rate_mean` | Safety/FleetSafe | Lower better | Yes (fleetsafe=true only) |
| `delta_l2_mean` | Safety/FleetSafe | Informational | Yes (fleetsafe=true only) |
| `stuck_rate_mean` | Robustness | Lower better | Yes |
| `smoothness_mean` | Robustness | Lower better | Yes |
| `inference_latency_ms_mean` | Performance | Lower better | Yes |
| `inference_latency_ms_p95` | Performance | Lower better | Yes |
| `explanation_coverage` | Explainability | Higher better | Yes |
| `intervention_explanation_rate` | Explainability | Higher better | Yes |
| `counterfactual_validity_rate` | Explainability | Higher better | Yes |
| `causal_graph_size_mean` | Explainability | Informational | Yes |
| `recovery_success_rate` | Robustness | Higher better | Planned |
| `sim_fps` | Performance | Higher better | Informational only |

---

## Primary comparison metrics

For the baseline vs FleetSafe comparison, the **primary endpoints** are:

1. `collision_rate` — primary safety metric
2. `spl_mean` — primary navigation quality metric

All other metrics are secondary. Multiple testing correction (Bonferroni) is
applied to primary endpoints only. Secondary metrics are reported descriptively.

---

## Metric formulas

See `docs/metrics/SAFETY_METRICS.md` for safety metric formulas.

### success_rate

```
success_rate = Σ_i success_i / N
```

`success_i = 1` if the robot reached the goal within `goal_tolerance_m` (0.20 m)
before `max_episode_steps` (500) and without collision.

### spl_mean

```
SPL_i = success_i × (optimal_path_i / max(path_length_i, optimal_path_i))
spl_mean = (1/N) Σ_i SPL_i
```

`optimal_path_i` is the Euclidean start→goal distance.
`path_length_i` is the cumulative Euclidean distance across all steps.

### path_length_m_mean

```
path_length_m_mean = (1/N) Σ_i path_length_i
```

### time_to_goal_s_mean

```
time_to_goal_s_mean = (1/N) Σ_i (episode_length_steps_i / control_hz)
```

Includes both successful and unsuccessful episodes.

---

## Confidence intervals

All reported metrics include 95% bootstrap confidence intervals:

- Iterations: 10 000
- Method: bias-corrected and accelerated (BCa) percentile
- Implementation: `fleet_safe_vla.benchmarks.visualnav_stats.bootstrap_ci`

---

## Aggregation scope

Metrics are reported at three scopes:

| Scope | File | Description |
|---|---|---|
| Run | `aggregate_metrics.json` | All episodes in the run |
| Scene | `aggregate_by_scene.json` | Grouped by `scene_id` |
| Episode | `metrics.json` | Single episode |

For publication, the run-level aggregates across 50 seeds per condition are used.
