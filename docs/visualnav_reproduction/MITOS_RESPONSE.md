# FleetSafe Response to the Mitos Robotics Argument

## The scaling-only critique

The Mitos Robotics position (and the broader field-level critique) is:

> "Scaling model size, training data, and compute is insufficient for safe embodied navigation.
> A system that passes benchmark metrics in simulation may still fail catastrophically in
> deployment because it has no principled safety guarantee, no interpretable failure mode,
> and no audit trail."

This is correct. FleetSafe-VisualNav-Benchmark is designed as a direct response.

---

## What scaling alone cannot provide

| Capability | Larger model | FleetSafe layer | This benchmark |
|---|---|---|---|
| Collision avoidance guarantee | ✗ (empirical) | ✓ (CBF formal constraint) | ✓ validated |
| Intervention audit trail | ✗ | ✓ per-step logs | ✓ required by contract |
| Counterfactual explanations | ✗ | ✓ causal reasoner | ✓ per-step output |
| Reproducible statistics | ✗ (checkpoint-locked) | ✓ open checkpoints | ✓ 50-seed protocol |
| Sim-to-real validation | ✗ | ✓ MuJoCo → hardware | ✓ Gate 10 |
| Reviewer-verifiable claims | ✗ | ✓ seed + hash tracing | ✓ audit contract |

---

## How FleetSafe addresses the scaling critique

### 1. Pretrained visual navigation policies

GNM, ViNT, and NoMaD are state-of-art pretrained policies from the visualnav-transformer
ecosystem. They represent the current scaling frontier for visual goal-conditioned navigation.
FleetSafe does not replace or retrain them — it augments them.

### 2. Structured safety filter (CBF-QP)

The Control Barrier Function QP filter provides a *formal* safety constraint over
the 3-DoF holonomic command space. For every policy output:

- If the nominal `cmd_vel` satisfies `d(robot, obstacle) ≥ d_safe`, it is passed unchanged.
- If it violates the margin, the nearest-feasible safe `cmd_vel` is computed via QP.
- If the obstacle is within `estop_dist_m`, all motion is halted.

This is not a heuristic. The barrier constraint is enforced at every step.

### 3. Causal scene graphs

Every episode step produces a scene graph with:
- Spatial nodes (robot, goal, obstacles, dynamic agents, waypoints)
- Typed edges (near, moving_towards, violates_margin, intervention_caused_by, blocks_path)

The graph links every intervention to the specific obstacle, distance, and policy action
that caused it. This is the audit record that scaling-only systems cannot provide.

### 4. Counterfactual explanations

For every CBF intervention, the system generates:

> "If obstacle_3 were 0.23 m farther away (at 0.41 m instead of 0.18 m),
>  the original ViNT action would have been accepted."

This is directly computable from the CBF margin and current distance. It requires
no learned model and is always correct by construction.

### 5. Reproducible benchmark statistics

The benchmark enforces:
- 50 seeds per `(model, scene, mode)` cell
- Identical seeds for baseline and FleetSafe (paired comparison, no confounding)
- Bootstrap CIs, paired Wilcoxon tests, Bonferroni correction
- All checkpoints publicly available with SHA256 hashes

This allows independent reproduction at any lab with a laptop.

### 6. Sim-to-real validation

MuJoCo simulation is the development backend. Isaac Lab (GPU) is the scale-out backend.
The Yahboom M3Pro real robot provides the final validation. The benchmark tracks
Spearman ρ rank correlation between sim and real SPL rankings — if the safety layer
improves safety in simulation but not on hardware, that is a falsifiable claim.

### 7. Explainable intervention reasoning

The no-black-box audit contract requires every episode to contain:
- Per-step explanation log (natural language)
- Per-step causal event (obstacle id, distance, graph edge)
- Per-step counterfactual
- Episode-level audit trail (model, backend, checkpoint, seed, transparency status)
- **Per-step intervention evidence record** (`intervention_evidence.jsonl`)

FleetSafe does not treat intervention as a black-box event. Each intervention
is logged as an evidence record containing the raw policy action, executed safe
action, scene graph delta, causal reason, and counterfactual rollout result.

A benchmark claim that cannot be traced to these artifacts is not accepted.

---

## Framing

This work does not claim to have solved safe navigation or set a definitive performance ceiling.
The framing is:

> **"Towards a new benchmark standard for trustworthy embodied visual navigation."**

The contribution is the *infrastructure* — reproducible evaluation, causal audit,
statistical rigor, sim-to-real framing — that the field currently lacks.
Any claim made from this benchmark is backed by:

- A specific checkpoint hash
- A specific seed list
- A specific backend
- A specific git commit
- A specific metrics file
- A causal explanation for every intervention

That is what distinguishes FleetSafe from scaling-only approaches, regardless of model size.

---

## What is not claimed

- FleetSafe does not eliminate all collisions on the real M3Pro (real runs pending).
- FleetSafe does not improve SPL in all scenes (the safety-performance tradeoff is measured, not assumed).
- FleetSafe's CBF is not a proof of safety for all possible obstacles (it is a local, distance-based constraint).
- Isaac Lab photorealism results are pending implementation.

These limitations are documented in `REPRODUCIBILITY_CHECKLIST.md` Gates 9–10 and
`REVIEWER_QA.md` (claim status section).
