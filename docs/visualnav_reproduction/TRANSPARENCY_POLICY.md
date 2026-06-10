# No-Black-Box Transparency Policy

Every benchmark episode in FleetSafe-VisualNav-Benchmark is subject to the
audit contract defined in `fleet_safe_vla/explainability/transparency_contract.py`.

This document describes the rules, enforcement mechanism, and rationale.

---

## The contract

### Rule 1: Every model output must be logged

Every inference step must record:

| Field | Source |
|---|---|
| `raw_vx`, `raw_vy`, `raw_wz` | Nominal cmd_vel from adapter |
| `inference_latency_ms` | `time.perf_counter()` around `predict_action()` |
| `model_name` | `adapter.model_name` |
| `checkpoint_path` | Path passed to `load_checkpoint()` |
| `checkpoint_hash` | SHA256/MD5 of checkpoint file (or `"unknown"` if not computed) |

These appear in `actions.csv`, `audit_trail.json`, and the run-level `metadata.yaml`.

---

### Rule 2: Every FleetSafe correction must be logged

Every step where the CBF-QP modifies the nominal action must record:

| Field | Source |
|---|---|
| `safe_vx`, `safe_vy`, `safe_wz` | Post-CBF cmd_vel |
| `delta_l2` | `‖safe_cmd − raw_cmd‖₂` |
| `active_constraint` | Which CBF constraint is active (`violates_margin`, `estop`) |
| `safety_margin_before` | `min_dist_m` at step entry |
| `intervention_reason` | Human-readable string |
| `intervened` | Boolean |

These appear in `actions.csv` and `explanation_log.jsonl`.

---

### Rule 3: Every episode directory must contain these 9 files

```
episode.json
trajectory.csv
actions.csv
safety_events.jsonl
metrics.json
scene_graphs.jsonl        ← added by explainability layer
explanation_log.jsonl     ← added by explainability layer
counterfactuals.jsonl     ← added by explainability layer
audit_trail.json          ← added by explainability layer
```

`validate_transparency_artifacts(episode_dir)` raises `TransparencyViolation`
if any file is absent.

---

### Rule 4: No silent fallback

| Situation | Required action |
|---|---|
| Mock backend used | `audit_trail.json` `backend_label` must contain `"ENGINEERING_ONLY"` |
| Checkpoint load fails | Record in `audit_trail.json` `missing_data_warnings` |
| Isaac Lab unavailable | Report gate failure; do not silently use mock |
| Sensor field is null | `{sensor}_missing_reason` field must be present |

A missing `lidar` field in `episode.json` without `lidar_missing_reason` is a
transparency violation (Rule 4).

---

### Rule 5: Every benchmark claim must link to

```yaml
config_file:      configs/visualnav/benchmark.yaml
seed_list:        metadata.yaml → seeds
checkpoint_hash:  audit_trail.json → checkpoint_hash
backend:          audit_trail.json → backend
git_commit:       git log --oneline -1
metrics_file:     aggregate_metrics.json → run_id
```

A claim not traceable to all six fields is not accepted.

---

### Rule 6: Every explanation must be traceable to data

The explanation string must reference:

- Obstacle node id (e.g., `obstacle_3`)
- Measured obstacle distance in metres
- The graph edge that triggered the constraint (e.g., `violates_margin`)
- The safety threshold used
- Raw action components
- Safe action components
- Action delta L2

These are verified by the `evidence` dict in `explanation_log.jsonl`.

---

## Enforcement

### At episode level

```python
from fleet_safe_vla.explainability.transparency_contract import (
    validate_transparency_artifacts
)

result = validate_transparency_artifacts(episode_dir)
# {"status": "PASS", "checks_passed": 10, ...}
```

Raises `TransparencyViolation` with a newline-separated list of all violations.

### At mock backend level

```python
from fleet_safe_vla.explainability.transparency_contract import (
    validate_mock_backend_labelled
)
audit = json.loads((episode_dir / "audit_trail.json").read_text())
validate_mock_backend_labelled(audit)
```

### Dashboard panel (planned)

The dashboard Explainability panel will show:
- Model checkpoint (path + hash)
- Backend (with ENGINEERING_ONLY label if mock)
- Current raw action
- Current safe action
- Active CBF constraint
- Intervention reason
- Last missing-data warning
- Audit status: **PASS** / **FAIL**

---

## Rationale

### Why require explanation_log.jsonl?

An audit trail that logs *what happened* (actions, collisions) but not *why*
is insufficient for safety-critical systems.  The explanation log provides
the causal link between observed behaviour and the system's internal state.

### Why require counterfactuals.jsonl?

A counterfactual is the minimum evidence that the safety filter is operating
correctly: "the action was modified because the obstacle was at distance X,
and if it had been at distance X + shift, the action would have been accepted."
Without this, a reviewer cannot distinguish a correctly-functioning CBF from
one that is over-conservative or incorrectly implemented.

### Why require audit_trail.json?

The audit trail is the episode-level accountability record. It links every
episode to its model, backend, seed, checkpoint hash, and transparency status.
Any paper claim that cannot link to an audit_trail.json with `"transparency_status": "PASS"`
is not supported by this benchmark.

### Why require mock backend labelling?

The mock backend uses a 2D holonomic integrator with no real physics. Results
from mock runs are systematically different from MuJoCo results (no contact
forces, no wheel slip, no inertia). Unlabelled mock results could be
accidentally included in paper tables. The mandatory label makes this error
impossible.

---

## Adding a new backend

When adding a new backend (e.g., real hardware, Gazebo, Webots):

1. The backend must write all 9 required files.
2. The `audit_trail.json` must use a non-"mock" backend string.
3. The sensor fields (`depth`, `lidar`) must either be populated or carry
   `{sensor}_missing_reason`.
4. `validate_transparency_artifacts()` must return PASS before any
   publication claim from that backend.
