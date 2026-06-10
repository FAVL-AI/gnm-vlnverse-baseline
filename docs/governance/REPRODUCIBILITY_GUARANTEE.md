# Reproducibility Guarantee

## What we guarantee

For any frozen artifact in `benchmarks/frozen/v{version}/{run_id}/`:

1. **Exact bit-for-bit reproduction** is possible if:
   - The same checkpoint file (matching `checkpoint_hash`) is used.
   - The same backend, scenes, seeds, and protocol version are used.
   - The Python environment matches `ENVIRONMENT.txt`.
   - The git commit matches `GIT_STATE.txt → HEAD`.

2. **Statistical reproduction** (within bootstrap CI) is expected if:
   - A different hardware platform is used with the same software stack.
   - Minor floating-point differences exist between platforms.

3. **Qualitative reproduction** (same ranking of models) is expected if:
   - A different checkpoint from the same model family is used.
   - A different random seed set is used (same n_seeds, different values).

---

## Reproduction gates

Before any run, the reproduction gates in `validate_gates.py` must pass:

| Gate | Check |
|---|---|
| Gate 0 | Python ≥ 3.10 |
| Gate 1 | `fleet_safe_vla` importable |
| Gate 2 | `pyproject.toml` present with `[project]` section |
| Gate 3 | `benchmarks/protocols/visualnav_v0.1.yaml` parseable |
| Gate 4 | At least one adapter importable |
| Gate 5 | Transparency contract importable |
| Gate 6 | `benchmark_version.py` importable and has BENCHMARK_VERSION |

Gates are checked by `scripts/visualnav/run_visualnav_benchmark.py --check-gates`.

---

## Reproducibility artifacts

Every frozen run contains:

### `MANIFEST.json`

```json
{
  "run_id": "gnm_baseline_mujoco_1747000000",
  "frozen_at": "2026-05-15T14:00:00Z",
  "benchmark_version": "0.1.0",
  "protocol_version": "0.1.0",
  "git_commit": "abc1234",
  "files": [
    {"path": "metadata.yaml", "sha256": "...", "size_bytes": 512},
    ...
  ]
}
```

### `SHA256SUMS`

```
abc123...  metadata.yaml
def456...  aggregate_metrics.json
...
```

### `GIT_STATE.txt`

```
commit abc1234 (HEAD -> main)
Date: Thu May 15 14:00:00 2026

git status:
nothing to commit, working tree clean
```

### `ENVIRONMENT.txt`

```
python 3.11.5
numpy 1.26.0
scipy 1.11.3
mujoco 3.1.0
...
```

### `intervention_evidence.jsonl` (per episode)

One JSON record per step, written by the explainability layer.  Each record
contains the full replayable evidence for one episode step:

```json
{
  "episode_id": "gnm_fleetsafe_mock_narrow_passage_seed0_ep0001",
  "step_idx": 12,
  "raw_action": [0.28, 0.0, 0.12],
  "safe_action": [0.08, 0.0, 0.12],
  "action_delta": [-0.20, 0.0, 0.0],
  "intervention_applied": true,
  "intervention_reason": "FleetSafe reduced vx from 0.280 to 0.082 ...",
  "scene_graph_delta": {"added_edges": [{"relation": "violates_margin", ...}], ...},
  "causal_explanation": "...",
  "counterfactual_explanation": "If obstacle_0 were 0.13 m farther ...",
  "reproducibility_hash": "a3f1b2c4..."
}
```

FleetSafe does not treat intervention as a black-box event. Each intervention
is logged as an evidence record containing the raw policy action, executed safe
action, scene graph delta, causal reason, and counterfactual rollout result.

---

## Reproduction instructions

To reproduce a frozen run:

```bash
# 1. Match the git commit
git checkout <commit_from_GIT_STATE.txt>

# 2. Match the environment
pip install -r requirements.txt  # or conda env from ENVIRONMENT.txt

# 3. Re-run with same protocol + scenes + seeds
python scripts/visualnav/run_visualnav_benchmark.py \
  --backend mujoco \
  --model gnm \
  --seeds 0 1 2 ... 49 \
  --protocol benchmarks/protocols/visualnav_v0.1.yaml

# 4. Verify SHA256 of key files match MANIFEST.json
python scripts/visualnav/validate_benchmark_artifact.py <run_dir>
```

---

## Known non-determinism sources

| Source | Scope | Mitigation |
|---|---|---|
| CUDA kernel non-determinism | GPU inference | CPU fallback for paper runs |
| OS scheduler timing | `latency_ms` fields | Use mean/p95, not single values |
| Dynamic agent collision detection | Step boundaries ±1 | Fixed seed per episode |
| MuJoCo contact solver | Constraint resolution | Fixed `integrator: RK4` |

Non-determinism that changes metric values (success/failure, collision) is
considered a bug. Report at https://github.com/FAVL-AI/FleetSafe-VisualNav-Benchmark/issues.
