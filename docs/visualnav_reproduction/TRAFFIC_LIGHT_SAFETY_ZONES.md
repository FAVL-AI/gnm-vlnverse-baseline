# Traffic-Light Safety Zones

## Concept

FleetSafe classifies the robot's current navigation context into one of three
safety zones using a traffic-light metaphor:

| Zone | Colour | Meaning | Robot behaviour |
|---|---|---|---|
| `GREEN` | 🟢 | Nominal; no hazards detected | Full speed; standard safety margin |
| `AMBER` | 🟡 | Caution; reduce speed, prepare to yield | Speed capped; margin expanded |
| `RED`   | 🔴 | Danger; stop or reroute | Velocity vetoed; FleetSafe intervention |

## Classification logic

Zone assignment is **deterministic** and takes the highest-priority triggered condition:

**RED** (any condition):
- Human within `stop_distance_red_m` of the robot.
- Agent count in `crowding_radius_m` ≥ `red_crowding_agents`.
- Forward path explicitly blocked by the planner.

**AMBER** (if not RED; any condition):
- Human within `human_amber_dist_m` of the robot.
- Agent count in `crowding_radius_m` ≥ `amber_crowding_agents`.
- `occlusion_risk > 0.50`.
- `crowding_score ≥ 0.50`.

**GREEN**: None of the above.

## Per-environment profiles

Each deployment environment has a separate `EnvironmentProfile` that sets all
thresholds.  Profiles ship in `environment_profiles.py`.

| Environment | Stop dist | Amber dist | Max speed (GREEN) | Max speed (AMBER) |
|---|---|---|---|---|
| `hospital` | 0.60 m | 1.20 m | 0.30 m/s | 0.10 m/s |
| `warehouse` | 0.40 m | 0.90 m | 0.50 m/s | 0.25 m/s |
| `school` | 0.70 m | 1.50 m | 0.25 m/s | 0.10 m/s |
| `office` | 0.45 m | 1.00 m | 0.35 m/s | 0.20 m/s |
| `shopping_mall` | 0.50 m | 1.10 m | 0.30 m/s | 0.15 m/s |
| `default` | 0.35 m | 0.90 m | 0.50 m/s | 0.25 m/s |

## Benchmark metrics

Zone occupancy is recorded per episode:

- `steps_green` — number of control steps in GREEN zone.
- `steps_amber` — number of control steps in AMBER zone.
- `steps_red` — number of control steps in RED zone.

A higher `steps_red` fraction in a socially complex scene indicates the robot
encountered more hazardous situations.  A comparison between baseline and FleetSafe
variants shows whether the safety layer reduces `steps_red` by proactive avoidance.

## Reproducibility

The zone classifier is purely geometric and stateless (no learned components).
Given the same agent positions, crowding score, and occlusion risk, it always
produces the same zone.  Zone traces are therefore exactly reproducible from a
saved episode trajectory.

## Usage example

```python
from fleet_safe_vla.social_awareness import SafetyZoneClassifier, SafetyZone
from fleet_safe_vla.social_awareness import get_profile

clf = SafetyZoneClassifier(profile=get_profile("hospital"))
result = clf.classify(
    agents=tracked_agents,
    robot_xy=(x, y),
    crowding_score=0.6,
    occlusion_risk=0.3,
)

if result.zone == SafetyZone.RED:
    robot.emergency_stop()
elif result.zone == SafetyZone.AMBER:
    robot.set_speed(result.recommended_speed_ms)
```
