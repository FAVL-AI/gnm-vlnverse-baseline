# M3Pro Navigation Audit Dashboard
Generated: 2026-05-23 04:37 UTC
Total rows: 16

## Summary Table

| Sim | World | Model | Cond | SR | Coll | SPL | MinDist | Interv% | N |
|-----|-------|-------|------|----|------|-----|---------|---------|---|
| mock | hospital | GNM | baseline | 0% | 10% | 0.000 | 3.808 | — | 10 |
| mock | hospital | GNM | baseline | 0% | 10% | 0.000 | 3.808 | — | 10 |
| mock | hospital | GNM | fleetsafe | 0% | 0% | 0.000 | 4.236 | 17% | 10 |
| mock | hospital | GNM | fleetsafe | 0% | 0% | 0.000 | 4.236 | 17% | 10 |
| mock | multi-scene | GNM | baseline | 22% | 48% | 0.225 | 0.457 | — | 40 |
| mock | multi-scene | GNM | fleetsafe | 0% | 0% | 0.000 | 0.785 | 57% | 40 |
| mock | multi-scene | VINT | baseline | 22% | 48% | 0.225 | 0.457 | — | 40 |
| mock | multi-scene | VINT | fleetsafe | 0% | 0% | 0.000 | 0.785 | 57% | 40 |
| mock | warehouse | GNM | baseline | 10% | 20% | 0.013 | 1.867 | — | 10 |
| mock | warehouse | GNM | baseline | 10% | 20% | 0.013 | 1.867 | — | 10 |
| mock | warehouse | GNM | fleetsafe | 0% | 0% | 0.000 | 2.293 | 20% | 10 |
| mock | warehouse | GNM | fleetsafe | 0% | 0% | 0.000 | 2.293 | 20% | 10 |
| mock+realckpt | hospital+cluttered | GNM | baseline | 0% | 35% | — | 0.573 | — | 20 |
| mock+realckpt | hospital+cluttered | GNM | fleetsafe | 0% | 0% | — | 0.809 | 40% | 20 |
| mock+realckpt | hospital+cluttered | VINT | baseline | 0% | 50% | — | 0.164 | — | 20 |
| mock+realckpt | hospital+cluttered | VINT | fleetsafe | 0% | 0% | — | 0.479 | 62% | 20 |

## FleetSafe Safety Effect

- **GNM** (hospital, mock): collision ↓ -10.0%  min_dist +0.428m  SPL +0.000
- **GNM** (multi-scene, mock): collision ↓ -47.5%  min_dist +0.328m  SPL -0.225
- **VINT** (multi-scene, mock): collision ↓ -47.5%  min_dist +0.328m  SPL -0.225
- **GNM** (warehouse, mock): collision ↓ -20.0%  min_dist +0.426m  SPL -0.013
- **GNM** (hospital+cluttered, mock+realckpt): collision ↓ -35.0%  min_dist +0.236m  
- **VINT** (hospital+cluttered, mock+realckpt): collision ↓ -50.0%  min_dist +0.315m  

## Data Sources

- `results/gazebo_smoke/benchmark_summary.json`
- `results/gazebo_smoke/hospital_gnm_bl_mock_benchmark.json`
- `results/gazebo_smoke/hospital_gnm_fs_mock_benchmark.json`
- `results/gazebo_smoke/warehouse_gnm_bl_mock_benchmark.json`
- `results/gazebo_smoke/warehouse_gnm_fs_mock_benchmark.json`
- `results/may29_evaluation_full.json`
- `results/benchmark_smoke/benchmark_results.json`
