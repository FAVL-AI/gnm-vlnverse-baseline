# benchmarks/visualnav/ — Output Directory

This directory is where the FleetSafe VisualNav benchmark writes its output.

## What is NOT committed

Generated run data is gitignored. The following are reproducible on any machine
with checkpoints and are therefore not stored in the repository:

| Path | Contents | Why gitignored |
|------|----------|----------------|
| `results/`  | Per-run JSON/CSV logs, per-episode files | Reproducible; potentially GBs |
| `reports/`  | HTML comparison reports, aggregate CSVs | Derived from results |
| `episodes/` | Step-by-step trajectory + action logs | Reproducible; large |

## What IS committed

| Path | Contents | Why committed |
|------|----------|---------------|
| `results_schema.json` | JSON Schema for result files | Defines the output contract |
| `README.md`           | This file | Navigation |
| `results/.gitkeep`    | Placeholder | Preserves directory structure after clone |
| `reports/.gitkeep`    | Placeholder | Preserves directory structure after clone |

## How to reproduce results

### Smoke run (no checkpoints, ~30 s)

```bash
source scripts/visualnav/activate_visualnav_env.sh
python scripts/visualnav/run_visualnav_benchmark.py \
    --model gnm --seeds smoke --scenes straight_corridor \
    --backend mock --fleetsafe both
```

### Development run (10 seeds, all scenes, mock backend)

```bash
bash scripts/visualnav/run_publishable_matrix.sh --seeds dev --backend mock
```

### Publication run (50 seeds, all scenes, MuJoCo backend)

```bash
# Prerequisites: gates 0–6 pass, checkpoints downloaded
python -m fleet_safe_vla.integrations.visualnav_transformer.validate_gates
bash scripts/visualnav/run_publishable_matrix.sh --seeds paper --backend mujoco
```

### End-to-end smoke (gates + 2 episodes + report)

```bash
bash scripts/visualnav/run_e2e_smoke.sh
```

## Where results go

```
benchmarks/visualnav/results/
  {run_id}/
    metadata.yaml            ← model, backend, seeds, scenes, timestamp
    aggregate_metrics.json   ← success_rate, SPL, collision_rate, etc.
    aggregate_metrics.csv    ← same, flat CSV
    aggregate_by_scene.json  ← per-scene breakdown
    episodes/
      episode_0001/
        episode.json
        trajectory.csv
        actions.csv
        safety_events.jsonl
        metrics.json

benchmarks/visualnav/reports/
  comparison_{timestamp}.html   ← interactive comparison table
  comparison_{timestamp}.json   ← machine-readable comparison
```

## Why results are not committed

1. **Size**: 50 seeds × 4 scenes × 3–4 pairs × 6 conditions = ≥3600 episodes.
   Each episode writes ~5 files. Total: ~18 000 files, potentially hundreds of MB.

2. **Reproducibility**: Results are fully reproducible from code + checkpoints.
   The checkpoints are public (Google Drive, IDs in `configs/visualnav/models.yaml`).

3. **Git hygiene**: Binary-ish CSVs and large JSON blobs degrade `git log`,
   `git diff`, and clone times. They belong in a dedicated artifact store
   (e.g., DVC, Weights & Biases, or a release asset) not in source control.

4. **No cherry-picking**: Committing selected runs risks accidentally excluding
   unfavourable seeds. The full run must be reproduced fresh for publication.

## Statistical validity note

Results from `--backend mock` are **NOT valid for any publication claim**.
The mock backend uses deterministic kinematic simulation with random-walk policies —
it tests the benchmark infrastructure, not navigation quality.

Only `--backend mujoco` (and future `--backend isaaclab`) results support claims.
See `docs/visualnav_reproduction/STATISTICAL_PROTOCOL.md` for minimum episode counts,
confidence interval methodology, and paired-test requirements.
