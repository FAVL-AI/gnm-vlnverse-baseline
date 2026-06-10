# Causal Scene Graph Design

## Motivation

Standard navigation benchmarks report aggregate statistics (SPL, collision rate)
but provide no structural account of *why* a collision occurred or *why* a safety
filter intervened.  The causal scene graph fills this gap by providing a per-step,
machine-readable, human-interpretable record of spatial relationships and the causal
chain that led to each safety decision.

---

## Graph schema

```
SceneGraph
├── nodes: dict[node_id → SceneNode]
│   ├── node_id:   str          ("robot", "goal", "obstacle_0", ...)
│   ├── node_type: SceneNodeType (robot | goal | obstacle | wall |
│   │                              dynamic_agent | waypoint)
│   ├── position:  (x, y)       world-frame metres
│   ├── radius_m:  float        bounding circle radius
│   └── velocity:  (vx, vy)     world-frame m/s
│
└── edges: list[SceneEdge]
    ├── source_id:  str
    ├── target_id:  str
    ├── relation:   SceneRelation
    │   (near | moving_towards | occludes | blocks_path |
    │    violates_margin | intervention_caused_by)
    ├── distance_m: float        edge-specific distance
    └── attributes: dict         optional extra data
```

---

## Relation semantics

### `near(robot, obstacle_i)`

Added when `‖robot.position − obstacle_i.position‖ − obstacle_i.radius_m < near_threshold_m`
(default 0.45 m).

Interpretation: robot is in the "awareness zone" of obstacle_i.

---

### `moving_towards(robot, obstacle_i)`

Added when:
- `near(robot, obstacle_i)` is present, AND
- `dot(robot.velocity, obstacle_i.position − robot.position) > 0`

Interpretation: the robot's current velocity vector has a positive component
directed toward the obstacle.  Combined with `near`, this predicts an imminent
approach and is a precursor to CBF intervention.

---

### `occludes(obstacle_i, goal)`

Added when obstacle_i's centre is within `2 × radius_m` of the line segment
connecting robot to goal (parameterised projection test, `t ∈ (0, 1)`).

Interpretation: obstacle_i is blocking the line-of-sight from the robot to
the goal image, which may cause the visual navigation policy to predict a
suboptimal heading.

---

### `blocks_path(obstacle_i, waypoint_j)`

Added when `‖waypoint_j.position − obstacle_i.position‖ − obstacle_i.radius_m < blocks_path_m`
(default 0.20 m).

Interpretation: the policy's predicted waypoint_j is physically blocked by
obstacle_i and cannot be reached without collision.

---

### `violates_margin(robot, obstacle_i)`

Added when `‖robot.position − obstacle_i.position‖ − obstacle_i.radius_m < margin_m`
(default 0.30 m, the CBF safety margin).

Interpretation: the robot is inside the safety margin and the CBF-QP is
actively constraining any outgoing velocity command.

---

### `intervention_caused_by(fleet_safe, obstacle_i)`

Added when `intervened=True` AND obstacle_i is the nearest obstacle.

Interpretation: the FleetSafe layer modified the nominal action, and the
nearest obstacle was the proximate cause.  This is the primary edge used by
the causal reasoner to generate the human-readable explanation.

---

## Reasoning pipeline

```
SceneGraph (step t)
    │
    ▼
CausalReasoner.reason()
    │   Classifies: ESTOP | CBF_INTERVENTION | NEAR_VIOLATION | GOAL_PURSUIT | NO_EVENT
    │   Identifies: nearest obstacle id, distance, dominant modified component
    ▼
CausalEvent
    │
    ├──▶ CounterfactualGenerator.generate()
    │        shift = max(0, margin + ε − obstacle_distance)
    │        "If obstacle_i were shift m farther, action would be accepted."
    ▼
Counterfactual
    │
    └──▶ ExplanationGenerator.generate(causal, counterfactual, graph)
             natural_language = template(event_type, obstacle_id, distance, delta)
             active_constraints = [violates_margin edges]
    ▼
Explanation
    │
    └──▶ EventRecorder.record(ExplainabilityStepRecord)
             ┌──────────────────────────────────────────────┐
             │  episode_dir/explanation_log.jsonl            │
             │  episode_dir/scene_graphs.jsonl               │
             │  episode_dir/counterfactuals.jsonl            │
             │  episode_dir/audit_trail.json                 │
             └──────────────────────────────────────────────┘
```

---

## Design decisions

### Why distance-first reasoning?

The CBF-QP is itself distance-first: its constraint is `d(robot, obstacle) ≥ d_safe`.
The causal reasoner mirrors this so that every explanation is *consistent with the
mathematical filter* — there is no mismatch between "why the reasoner says FleetSafe
intervened" and "why the CBF actually intervened."

### Why template-based natural language?

Learned captioning models introduce a second opacity layer: the explanation itself
becomes a black box.  Template-based generation ensures every phrase maps to a
specific measured quantity and can be verified by inspection.

### Why per-step graphs rather than episode-level?

Safety events have precise temporal structure.  A near-violation at step 12 may be
caused by a different obstacle than the collision at step 18.  Per-step graphs
preserve this structure and allow reviewers to reconstruct the exact sequence of
events that led to any outcome.

### Why minimal counterfactuals?

The counterfactual shift `max(0, margin + ε − d)` is the *minimum* displacement
that satisfies the CBF constraint.  It is a lower bound — real-world obstacle
placement may require larger clearance.  The minimum bound is the most defensible
for a paper claim because it is conservative.

---

## Extension points

1. **Learned obstacle detection**: replace manually-specified `obstacles` with
   a detector output (bounding boxes from a depth camera) to make the graph
   sensor-driven rather than ground-truth-driven.

2. **Temporal graphs**: add edges that connect the same node across timesteps
   (`was_at(obstacle_i, t)`) to model dynamic agent trajectories.

3. **Uncertainty nodes**: add confidence scores from the policy's uncertainty
   estimate (e.g., NoMaD ensemble variance) as node attributes to represent
   epistemic safety risk.

4. **Graph neural network reasoning**: use the scene graph as input to a GNN
   safety predictor trained to forecast collision probability from graph structure.
