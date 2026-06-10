# FleetSafe Unified Cross-Simulator Benchmark

**Date**: 2026-05-23 06:00 UTC
**Episodes per condition**: 20  |  **Simulators**: isaac, gazebo

## Summary Table

| Simulator | World | Model | Condition | Success | Collision | Time (s) | Dev (m) | SPL |
|-----------|-------|-------|-----------|---------|-----------|----------|---------|-----|
| Gazebo | hospital | GNM | Baseline | 60.0% | 35.0% | 14.9 | 0.282 | 0.492 |
| Gazebo | hospital | GNM | FleetSafe | 80.0% | 0.0% | 14.6 | 0.214 | 0.661 |
| Gazebo | hospital | VINT | Baseline | 10.0% | 40.0% | 12.6 | 0.315 | 0.080 |
| Gazebo | hospital | VINT | FleetSafe | 65.0% | 0.0% | 13.1 | 0.217 | 0.558 |
| Isaac | hospital | GNM | Baseline | 65.0% | 30.0% | 13.5 | 0.187 | 0.546 |
| Isaac | hospital | GNM | FleetSafe | 95.0% | 0.0% | 13.5 | 0.146 | 0.805 |
| Isaac | hospital | VINT | Baseline | 20.0% | 40.0% | 11.3 | 0.200 | 0.163 |
| Isaac | hospital | VINT | FleetSafe | 70.0% | 0.0% | 12.7 | 0.141 | 0.617 |

## Sim-to-Real Gap (Isaac − Gazebo success rate)

| Model | Condition | Isaac | Gazebo | Δ Gap |
|-------|-----------|-------|--------|-------|
| GNM | Baseline | 65.0% | 60.0% | +5.0% |
| GNM | FleetSafe | 95.0% | 80.0% | +15.0% |
| VINT | Baseline | 20.0% | 10.0% | +10.0% |
| VINT | FleetSafe | 70.0% | 65.0% | +5.0% |

## Key Findings

- **FleetSafe eliminates collisions** in both Isaac Sim and Gazebo (0% collision rate).
- **Isaac Sim advantage**: RTX photorealistic rendering provides richer visual features,
  yielding higher success rates and lower path deviation vs Gazebo (ODE physics).
- **Sim-to-real gap** is quantified above — use for transfer learning calibration.

## Reproduce

```bash
python scripts/benchmarks/unified_benchmark.py --simulators isaac gazebo --models gnm vint --episodes 20
```