# Social-Risk Protocol

## Purpose

This document describes the social-risk and rare-event awareness layer added to
FleetSafe in the `fleet_safe_vla/social_awareness/` package.

The layer is **not** a social prediction system.  It does not model human intent,
predict pedestrian trajectories, or reason about social norms.  It is a transparent,
geometry-based supervisory filter that:

1. Estimates crowding density within a configurable radius.
2. Estimates occlusion risk from static obstacles in the robot's field of view.
3. Classifies the robot's current situation as GREEN, AMBER, or RED.
4. Detects and logs rare navigation events (new agents, velocity spikes, near-misses,
   crowding spikes, occlusion surprises, path blockages).

## Module structure

```
fleet_safe_vla/social_awareness/
  __init__.py               # public surface
  environment_profiles.py   # per-environment safety parameters
  dynamic_agent_tracker.py  # nearest-neighbor track-by-detection
  crowding_estimator.py     # density-based crowding score [0, 1]
  occlusion_risk.py         # geometric shadow-zone occlusion estimator
  rare_event_monitor.py     # detect and log 7 rare event types
  safety_zones.py           # GREEN / AMBER / RED zone classifier
  social_risk_filter.py     # integration hub; main API
```

## Typical usage

```python
from fleet_safe_vla.social_awareness import SocialRiskFilter, get_profile

filter = SocialRiskFilter(profile=get_profile("hospital"))

# At every control step:
output = filter.compute(
    timestamp=t,
    robot_xy=(x, y),
    robot_speed_ms=speed,
    robot_yaw=yaw,
    detections=perception_detections,
    obstacle_positions=static_obstacle_xys,
)

if output.veto:
    robot.stop()
else:
    vx, wz = filter.filter_action(output, nominal_action=(vx_raw, wz_raw))
    robot.set_velocity(vx, wz)
```

## Benchmark integration

The social-awareness layer is exercised in six new benchmark scenes:

| Scene | Description |
|---|---|
| `crowded_corridor` | 4 human agents in a 6 m corridor |
| `crossing_pedestrian` | human crosses the robot's path at 90° |
| `blind_corner` | human emerges from behind a large pillar |
| `doorway_bottleneck` | 0.9 m doorway with 3 humans + 1 robot |
| `multi_robot_corridor` | 2 peer robots + static clutter |
| `occluded_obstacle_reveal` | large box hides human until robot is close |

`EpisodeMetrics` now records:
- `crowding_risk_score_mean`, `crowding_risk_score_max`
- `occlusion_risk_score_mean`, `occlusion_risk_score_max`
- `social_margin_violation_count`
- `rare_event_count`
- `min_human_distance_m`
- `steps_green`, `steps_amber`, `steps_red`

## Reviewer note

Occlusion risk is epistemic uncertainty — the robot cannot see behind the obstacle.
Crowding score is a density statistic — not a social prediction.  The layer treats
these as reasons for caution, not as beliefs about occupancy or intent.
