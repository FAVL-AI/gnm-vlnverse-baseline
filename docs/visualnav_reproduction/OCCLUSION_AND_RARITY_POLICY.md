# Occlusion and Rarity Policy

## Occlusion Risk

### What it measures

`OcclusionRisk` computes the **shadow zone** behind each static obstacle in the
robot's sensor range.  For each occluding obstacle it computes:

- The angular half-width (how much of the robot's field of view is blocked).
- The zone centre: a point behind the obstacle along the robot→obstacle ray.
- The zone radius: scales with the obstacle's angular subtension.
- A risk score in `[0, 1]`: closer obstacles that subtend larger angles score higher.

### Risk score formula

```
base_risk = max(zone.risk_score for zone in zones)
speed_penalty = min(robot_speed_ms / 0.5, 1.0) * speed_weight
occlusion_risk = min(base_risk * (1 - speed_weight) + speed_penalty, 1.0)
```

The speed penalty reflects the intuition that approaching an unknown zone at speed
is more dangerous than approaching slowly.

### Policy

- `occlusion_risk > 0.50` → AMBER zone (slow down, widen margin)
- `occlusion_risk > 0.75` → `OCCLUSION_SURPRISE` rare event logged
- Approaching a blind corner within `profile.occlusion_caution_distance_m` → AMBER

### Epistemic framing

Occlusion risk is **not** a belief that something is in the shadow zone.  It is
a measure of what the robot **cannot observe**.  The AMBER response is proportional
to uncertainty, not to a predicted occupancy.

## Rare Event Monitor

### Event types

| Type | Trigger |
|---|---|
| `UNKNOWN_DYNAMIC_AGENT` | Agent ID not in the previous step's known set |
| `SUDDEN_VELOCITY_CHANGE` | Agent speed changed by ≥ 0.30 m/s in one step |
| `PATH_BLOCKED` | `path_blocked=True` from planner |
| `UNEXPECTED_CROWDING` | Crowding score crosses 0.70 from below |
| `NEAR_MISS_HUMAN` | Human closer than `human_red_dist_m` |
| `OCCLUSION_SURPRISE` | `occlusion_risk > 0.75` |
| `CORRIDOR_BLOCKED` | (reserved; requires corridor geometry input) |

### Benchmark metric

`rare_event_count` in `EpisodeMetrics` counts the total number of rare events
logged during one episode.  This is the primary "curse-of-rarity" metric: it
captures how often FleetSafe had to respond to something outside the normal
operating distribution.

A robot with a lower rare event count (relative to baseline) demonstrates better
proactive hazard avoidance.

## Tuning parameters

All thresholds are in `EnvironmentProfile`:

| Parameter | Meaning |
|---|---|
| `stop_distance_red_m` | Human distance that triggers RED zone |
| `human_amber_dist_m` | Human distance that triggers AMBER zone |
| `amber_crowding_agents` | Crowd count that triggers AMBER |
| `red_crowding_agents` | Crowd count that triggers RED |
| `occlusion_caution_distance_m` | Occlusion zone proximity that triggers AMBER |
