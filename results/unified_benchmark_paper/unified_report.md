# FleetSafe Unified Cross-Simulator Benchmark

**Date**: 2026-05-23 06:00 UTC
**Episodes per condition**: 50  |  **Simulators**: isaac, gazebo

## Summary Table

| Simulator | World | Model | Condition | Success | Collision | Time (s) | Dev (m) | SPL |
|-----------|-------|-------|-----------|---------|-----------|----------|---------|-----|
| Gazebo | hospital | GNM | Baseline | 46.0% | 40.0% | 14.5 | 0.292 | 0.394 |
| Gazebo | hospital | GNM | FleetSafe | 84.0% | 0.0% | 13.6 | 0.207 | 0.725 |
| Gazebo | hospital | NOMAD | Baseline | 44.0% | 42.0% | 13.0 | 0.290 | 0.368 |
| Gazebo | hospital | NOMAD | FleetSafe | 78.0% | 0.0% | 12.3 | 0.216 | 0.648 |
| Gazebo | hospital | VINT | Baseline | 26.0% | 60.0% | 15.0 | 0.296 | 0.215 |
| Gazebo | hospital | VINT | FleetSafe | 66.0% | 0.0% | 13.8 | 0.227 | 0.569 |
| Gazebo | warehouse | GNM | Baseline | 38.0% | 42.0% | 12.3 | 0.302 | 0.315 |
| Gazebo | warehouse | GNM | FleetSafe | 82.0% | 0.0% | 13.1 | 0.215 | 0.688 |
| Gazebo | warehouse | NOMAD | Baseline | 42.0% | 40.0% | 13.3 | 0.292 | 0.362 |
| Gazebo | warehouse | NOMAD | FleetSafe | 88.0% | 0.0% | 14.0 | 0.209 | 0.748 |
| Gazebo | warehouse | VINT | Baseline | 30.0% | 54.0% | 13.8 | 0.291 | 0.260 |
| Gazebo | warehouse | VINT | FleetSafe | 66.0% | 0.0% | 13.4 | 0.220 | 0.561 |
| Isaac | hospital | GNM | Baseline | 50.0% | 36.0% | 14.6 | 0.195 | 0.443 |
| Isaac | hospital | GNM | FleetSafe | 88.0% | 0.0% | 12.8 | 0.134 | 0.778 |
| Isaac | hospital | NOMAD | Baseline | 54.0% | 36.0% | 13.0 | 0.198 | 0.461 |
| Isaac | hospital | NOMAD | FleetSafe | 88.0% | 0.0% | 12.0 | 0.137 | 0.749 |
| Isaac | hospital | VINT | Baseline | 34.0% | 56.0% | 14.0 | 0.193 | 0.296 |
| Isaac | hospital | VINT | FleetSafe | 84.0% | 0.0% | 12.8 | 0.148 | 0.735 |
| Isaac | warehouse | GNM | Baseline | 42.0% | 38.0% | 11.6 | 0.194 | 0.358 |
| Isaac | warehouse | GNM | FleetSafe | 90.0% | 0.0% | 12.8 | 0.137 | 0.773 |
| Isaac | warehouse | NOMAD | Baseline | 44.0% | 40.0% | 12.4 | 0.198 | 0.386 |
| Isaac | warehouse | NOMAD | FleetSafe | 96.0% | 0.0% | 13.3 | 0.135 | 0.837 |
| Isaac | warehouse | VINT | Baseline | 36.0% | 48.0% | 12.3 | 0.198 | 0.320 |
| Isaac | warehouse | VINT | FleetSafe | 70.0% | 0.0% | 12.3 | 0.143 | 0.612 |

## Sim-to-Real Gap (Isaac − Gazebo success rate)

| Model | Condition | Isaac | Gazebo | Δ Gap |
|-------|-----------|-------|--------|-------|
| GNM | Baseline | 50.0% | 46.0% | +4.0% |
| GNM | Baseline | 42.0% | 38.0% | +4.0% |
| GNM | FleetSafe | 88.0% | 84.0% | +4.0% |
| GNM | FleetSafe | 90.0% | 82.0% | +8.0% |
| NOMAD | Baseline | 54.0% | 44.0% | +10.0% |
| NOMAD | Baseline | 44.0% | 42.0% | +2.0% |
| NOMAD | FleetSafe | 88.0% | 78.0% | +10.0% |
| NOMAD | FleetSafe | 96.0% | 88.0% | +8.0% |
| VINT | Baseline | 34.0% | 26.0% | +8.0% |
| VINT | Baseline | 36.0% | 30.0% | +6.0% |
| VINT | FleetSafe | 84.0% | 66.0% | +18.0% |
| VINT | FleetSafe | 70.0% | 66.0% | +4.0% |

## Key Findings

- **FleetSafe eliminates collisions** in both Isaac Sim and Gazebo (0% collision rate).
- **Isaac Sim advantage**: RTX photorealistic rendering provides richer visual features,
  yielding higher success rates and lower path deviation vs Gazebo (ODE physics).
- **Sim-to-real gap** is quantified above — use for transfer learning calibration.

## Reproduce

```bash
python scripts/benchmarks/unified_benchmark.py --simulators isaac gazebo --models gnm vint nomad --episodes 50
```