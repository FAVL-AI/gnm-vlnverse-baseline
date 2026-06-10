# Intervention Evidence Replay — FleetSafe VisualNav Benchmark

Every FleetSafe intervention is recorded as a structured, replayable evidence
event.  This document describes the logging flow, file layout, and replay contract.

---

## Principle

FleetSafe does not treat intervention as a black-box event.  Each intervention
is logged as an evidence record containing the raw policy action, executed safe
action, scene graph delta, causal reason, and counterfactual rollout result.

---

## Logging flow

```
Episode step N
│
├─ adapter.predict_action()          → raw_action (vx, vy, wz)  [captured BEFORE FleetSafe]
│
├─ FleetSafeWrapper.step()           → safe_action (vx, vy, wz) [captured AFTER CBF-QP]
│   └─ action_delta = safe - raw     → per-component, L2 norm
│
├─ SceneGraphBuilder.build()         → scene_graph_before  (step N snapshot)
│
├─ sim.step(safe_action)             → new robot pose
│
├─ SceneGraphBuilder.build()         → scene_graph_after   (step N+1 snapshot)
│   └─ diff_scene_graphs()           → scene_graph_delta
│
├─ CausalReasoner.reason()           → causal_event (type, obstacle_id, description)
│
├─ CounterfactualGenerator.generate()→ counterfactual (analytical, from CBF margin)
│
├─ CounterfactualRolloutEngine.rollout()
│   ├─ raw_action trajectory    → raw_min_distance, raw_collision_predicted
│   └─ safe_action trajectory   → safe_min_distance, safe_collision_predicted
│
└─ InterventionEvidence.build()      → evidence record
    └─ written to intervention_evidence.jsonl
```

---

## Files written per episode

| File | Writer | Content |
|---|---|---|
| `safety_events.jsonl` | `_write_episode_files()` | Near-miss + intervention flags (summary only) |
| `explanation_log.jsonl` | `EventRecorder.write_explanation_log()` | Per-step natural language explanations |
| `scene_graphs.jsonl` | `EventRecorder.write_scene_graphs()` | Full scene graph per step |
| `counterfactuals.jsonl` | `EventRecorder.write_counterfactuals()` | Analytical CBF counterfactuals |
| `audit_trail.json` | `EventRecorder.write_audit_trail()` | Episode-level summary |
| **`intervention_evidence.jsonl`** | `EventRecorder.write_intervention_evidence()` | **Full evidence record per step** |

`intervention_evidence.jsonl` is the primary replay artifact.  The other files
provide supplementary detail.

---

## Raw action capture

The raw policy action is captured in `visualnav_runner.py` **before** any
FleetSafe modification:

```python
# With FleetSafe:
step_res = self._wrapper.step(preprocessed, obs_vec, obs_positions_robot)
raw_cmd  = step_res.raw_cmd_vel   # ← policy output, unmodified
safe_cmd = step_res.safe_cmd_vel  # ← after CBF-QP

# Without FleetSafe:
raw_cmd  = cmd
safe_cmd = cmd
```

Both are stored in `_StepRecord` and propagated into `CausalEvent.raw_cmd` and
`CausalEvent.safe_cmd`, which are then written into the evidence record.

---

## Evidence record fields

| Field | Type | Description |
|---|---|---|
| `episode_id` | str | Unique episode identifier |
| `step_idx` | int | Step index within episode |
| `timestamp` | float | Time in seconds |
| `scene_id` | str | Scene name |
| `model_name` | str | Navigation model |
| `backend` | str | Simulation backend |
| `benchmark_version` | str | Artifact schema version |
| `protocol_version` | str | Protocol version |
| `raw_action` | [vx, vy, wz] | Policy output before FleetSafe |
| `safe_action` | [vx, vy, wz] | Executed action after FleetSafe |
| `action_delta` | [dvx, dvy, dwz] | Component-wise difference |
| `intervention_applied` | bool | Whether FleetSafe modified the action |
| `intervention_reason` | str | Causal description |
| `safety_margin_before` | float | Nearest obstacle clearance (m) at step N |
| `safety_margin_after` | float | Nearest obstacle clearance (m) at step N+1 |
| `nearest_obstacle_id` | str | ID of the nearest obstacle node |
| `nearest_obstacle_distance_m` | float | Surface-to-surface distance (m) |
| `active_constraints` | list[str] | Scene graph edges that indicate safety violation |
| `scene_graph_before` | dict | Full graph at step N |
| `scene_graph_after` | dict | Full graph at step N+1 |
| `scene_graph_delta` | dict | Structural diff (added/removed nodes, edges, attributes) |
| `causal_explanation` | str | Natural language explanation |
| `counterfactual_explanation` | str | Analytical "what if" string |
| `counterfactual_rollout_id` | str | UUID linking to rollout result |
| `rgb_frame_ref` | str | Reference to RGB frame file (if available) |
| `depth_frame_ref` | str | Reference to depth frame file (if available) |
| `lidar_ref` | str | Reference to LiDAR scan file (if available) |
| `trajectory_ref` | str | Reference to trajectory CSV |
| `reproducibility_hash` | str | SHA256 (16 hex chars) of the record |

---

## Counterfactual rollout backends

| Backend | Status | Claim scope |
|---|---|---|
| `mock` | Available | Engineering / CI only — no publication claim |
| `isaac` | `NotImplementedError` | Pending Isaac branching rollout integration |

The mock backend performs a 2-second constant-action 2-D kinematic rollout.  It
demonstrates whether the raw action would have led to collision and whether the
safe action avoids it, but does not constitute a physics-validated claim.

---

## Validation contract

`validate_benchmark_artifact.py` checks:

1. `intervention_evidence.jsonl` exists in every episode directory.
2. If `metrics.json` reports `intervention_count > 0`, the JSONL must contain
   at least as many records with `intervention_applied == true`.
3. Mock backend runs may have empty JSONL only if `intervention_count == 0`.

---

## Replay example

```python
import json
from pathlib import Path

ev_path = Path("results/run_id/episodes/episode_0001/intervention_evidence.jsonl")
for line in ev_path.read_text().splitlines():
    ev = json.loads(line)
    if ev["intervention_applied"]:
        print(f"step {ev['step_idx']}: {ev['intervention_reason']}")
        print(f"  raw={ev['raw_action']}  safe={ev['safe_action']}")
        print(f"  delta={ev['action_delta']}")
        print(f"  causal: {ev['causal_explanation']}")
        print(f"  counterfactual: {ev['counterfactual_explanation']}")
        delta = ev["scene_graph_delta"]
        if delta["added_edges"]:
            print(f"  new edges: {[e['relation'] for e in delta['added_edges']]}")
```
