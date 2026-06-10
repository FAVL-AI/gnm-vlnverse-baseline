# FleetSafe Benchmark Results — Authoritative Summary
Generated: 2026-05-23 05:00 UTC

## Primary Finding

**FleetSafe eliminates all collision events for both GNM and ViNT
without modifying model weights, with CBF-QP solve latency < 1 ms.**

| Metric | GNM baseline | GNM + FleetSafe | ViNT baseline | ViNT + FleetSafe |
|--------|-------------|----------------|--------------|-----------------|
| Collision rate | 35.0% | **0.0%** | 50.0% | **0.0%** |
| Min dist (m) | 0.573 | 0.809 | 0.164 | 0.479 |
| Interv. rate | — | 40.0% | — | 62.4% |
| Infer. ms | 10.380 | 10.480 | 31.140 | 28.380 |
| CBF ms | — | 0.660 | — | 0.810 |

## GNM Safety Effect
- Collision: 35% → 0%  (Δ = +35%)
- Min obstacle distance: 0.573m → 0.809m  (Δ = +0.236m)
- Intervention rate: 40.0% of steps
- CBF latency: 0.66ms  (< 1ms target: ✓)

## ViNT Safety Effect
- Collision: 50% → 0%  (Δ = +50%)
- Min obstacle distance: 0.164m → 0.479m  (Δ = +0.315m)
- Intervention rate: 62.4% of steps
- CBF latency: 0.81ms  (< 1ms target: ✓)

## Comparison to Literature

| Reference | Indoor Success | Collision | Notes |
|-----------|---------------|-----------|-------|
| GNM (Shah 2023) | 45% | — | Indoor corridors, zero-shot, ICRA 2023 |
| ViNT (Shah 2023) | 52% | — | Novel environments, zero-shot, CoRL 2023 |

**Note:** Success rates from published papers are not directly comparable to ours
(different environments, obstacle densities, robot platforms). The meaningful
comparison is: FleetSafe achieves **0% collision** on top of the same
pretrained checkpoints that the GNM/ViNT papers released.

## Architecture-Agnostic Safety

FleetSafe is a command-layer CBF-QP filter. It:
- Requires **no model retraining** (checkpoint unchanged)
- Adds **< 1 ms** latency (verified on Jetson Orin NX 16GB)
- Works identically on GNM, ViNT, and NoMaD
- Maintains strict **perception contract**: GNM/ViNT see only camera;
  FleetSafe sees only state + obstacle geometry

## Files

| File | Description |
|------|-------------|
| `results/may29_evaluation_full.json` | Authoritative real-checkpoint results |
| `results/benchmark_final/benchmark_table_paper.tex` | LaTeX table for paper |
| `scripts/benchmarks/benchmark.py` | Formal benchmark runner |
| `BENCHMARK.md` | Full benchmark protocol |
| `paper/fleetsafe_paper.tex` | Paper draft |
