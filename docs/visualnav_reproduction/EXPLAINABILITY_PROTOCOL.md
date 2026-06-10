# Explainability Protocol — FleetSafe VisualNav Benchmark

This document specifies the per-step explainability pipeline that is run
automatically by the benchmark runner for every episode.

---

## Overview

For every episode step, the explainability layer produces:

1. A **scene graph** — spatial snapshot of all entities and their relationships
2. A **causal event** — why (or why not) FleetSafe intervened
3. A **counterfactual** — what would have had to change for the intervention not to occur
4. An **explanation** — human-readable natural language summary

These are accumulated over the episode and written to four files in the episode
output directory.

---

## Output files

| File | Format | Content |
|---|---|---|
| `scene_graphs.jsonl` | JSONL (1 object/step) | Full graph serialisation |
| `explanation_log.jsonl` | JSONL (1 object/step) | Natural language + evidence |
| `counterfactuals.jsonl` | JSONL (1 object/step) | Counterfactual record |
| `audit_trail.json` | JSON | Episode-level audit summary |
| `intervention_evidence.jsonl` | JSONL (1 object/step) | Full replayable evidence record |

These are required by the transparency contract. An episode directory without
all five files fails `validate_benchmark_artifact.py`.

FleetSafe does not treat intervention as a black-box event. Each intervention
is logged as an evidence record containing the raw policy action, executed safe
action, scene graph delta, causal reason, and counterfactual rollout result.

See `docs/visualnav_reproduction/INTERVENTION_EVIDENCE_REPLAY.md` for the
complete logging flow and field specification.

---

## Scene graph

### Nodes

| Type | ID pattern | Description |
|---|---|---|
| `robot` | `robot` | The M3Pro robot |
| `goal` | `goal` | Navigation goal |
| `obstacle` | `obstacle_0`, `obstacle_1`, ... | Static obstacles |
| `dynamic_agent` | `dynamic_agent_0`, ... | Moving obstacles |
| `waypoint` | `waypoint_0`, `waypoint_1`, ... | Policy waypoint predictions |
| `wall` | `wall_0`, ... | Corridor walls |

### Edges

| Relation | Meaning | Trigger |
|---|---|---|
| `near` | Robot is within near_miss threshold | dist < 0.45 m |
| `moving_towards` | Robot velocity has positive component toward obstacle | dot(v, d_obs) > 0 and near |
| `occludes` | Obstacle lies between robot and goal | geometrically |
| `blocks_path` | Obstacle is within 0.20 m of a waypoint | geometrically |
| `violates_margin` | Robot is within CBF safety margin | dist < 0.30 m |
| `intervention_caused_by` | FleetSafe → nearest threat | when intervened=True |

### Serialisation

```json
{
  "step": 12,
  "timestamp_s": 3.0,
  "nodes": [
    {"node_id": "robot",      "node_type": "robot",    "position": [1.2, 0.4], "radius_m": 0.15, "velocity": [0.2, 0.0]},
    {"node_id": "obstacle_0", "node_type": "obstacle", "position": [1.5, 0.5], "radius_m": 0.15, "velocity": [0.0, 0.0]},
    {"node_id": "goal",       "node_type": "goal",     "position": [3.0, 0.0], "radius_m": 0.20, "velocity": [0.0, 0.0]}
  ],
  "edges": [
    {"source_id": "robot", "target_id": "obstacle_0", "relation": "near",            "distance_m": 0.18},
    {"source_id": "robot", "target_id": "obstacle_0", "relation": "violates_margin", "distance_m": 0.18},
    {"source_id": "robot", "target_id": "obstacle_0", "relation": "moving_towards",  "distance_m": 0.18},
    {"source_id": "fleet_safe", "target_id": "obstacle_0", "relation": "intervention_caused_by", "distance_m": 0.18}
  ]
}
```

---

## Causal event

The causal reasoner produces one of five event types per step:

| Type | Description |
|---|---|
| `estop` | E-STOP triggered (obstacle within collision_m) |
| `cbf_intervention` | CBF-QP modified the nominal action |
| `near_violation` | Robot within near_miss threshold but not intervened |
| `goal_pursuit` | Normal navigation, no safety event |
| `no_event` | No obstacles in scene |

### Example explanation string

```
FleetSafe reduced vx from 0.280 to 0.082 because the predicted path
entered a near-violation zone 0.183 m from obstacle_0.
```

---

## Counterfactual

For every intervention, the minimum obstacle displacement that would have
prevented the intervention is computed analytically:

```
shift = max(0, margin_m + ε - obstacle_distance_m)
```

### Example counterfactual string

```
If obstacle_0 were 0.13 m farther away (at 0.31 m instead of 0.18 m),
the original ViNT action (vx=0.280, vy=0.000, wz=0.120) would have been
accepted by FleetSafe (safety margin 0.30 m satisfied with ε=0.01 m buffer).
```

---

## Explainability benchmark metrics

These metrics are computed from the episode's ExplainabilityStepRecord list
and included in the run aggregate:

| Metric | Formula |
|---|---|
| `explanation_coverage` | steps with non-empty NL explanation / total steps |
| `intervention_explanation_rate` | CBF/E-STOP steps with causal explanation / total CBF/E-STOP steps |
| `counterfactual_validity_rate` | CBF steps with distance_shift_m > 0 / total CBF steps |
| `causal_graph_size_mean` | mean (nodes + edges) per graph |
| `explanation_latency_ms_mean` | mean latency_ms across all step records |

---

## Backend compatibility

| Backend | Scene graph source | Causal event source |
|---|---|---|
| `mock` | Synthesised from obstacle specs + robot pose | Distance from 2D kinematic sim |
| `mujoco` | Extracted from MuJoCo model + env info | Distance from MuJoCo contacts |
| `isaaclab` | Planned: USD stage + sensor pipeline | Planned: Isaac sensor distances |

On the mock backend, obstacle positions come from `SceneSpec.obstacles` directly.
On the MuJoCo backend, they come from `env._obs_positions` if available.
Isaac Lab will extract them from the USD stage.

---

## Usage

```python
from fleet_safe_vla.explainability import (
    SceneGraphBuilder, CausalReasoner, CounterfactualGenerator,
    ExplanationGenerator, EventRecorder, ExplainabilityStepRecord,
)

builder  = SceneGraphBuilder()
reasoner = CausalReasoner()
cf_gen   = CounterfactualGenerator()
exp_gen  = ExplanationGenerator()
recorder = EventRecorder(model_name="gnm", backend="mujoco", scene="narrow_passage")

for step_record in episode_step_records:
    graph   = builder.build(step=step_record.step, ...)
    causal  = reasoner.reason(step=step_record.step, scene_graph=graph, ...)
    cf      = cf_gen.generate(causal)
    expl    = exp_gen.generate(causal, cf, graph)
    recorder.record(ExplainabilityStepRecord(
        step=step_record.step, scene_graph=graph,
        causal_event=causal, counterfactual=cf, explanation=expl, ...
    ))

recorder.write_all(episode_dir)
print(recorder.coverage_metrics())
```
