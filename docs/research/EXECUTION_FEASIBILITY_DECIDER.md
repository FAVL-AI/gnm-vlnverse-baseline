# Execution-Aware Demonstration Gating for Vision-Based Robot Navigation
*(FleetSafe-NavGen Decider — H2.3 method contribution)*

## Problem (exactly what H2/H2.1/H2.2 exposed)
A vision-navigation dataset pipeline is blocked because: (1) the learned
policy cannot generate expert demonstrations for unseen goals, (2) the
scripted controller cannot track curved routes under weak yaw authority,
(3) the hand-authored map misses real collision geometry, (4) bad routes
can still record cleanly unless a decider blocks them.

## Position vs literature
Components exist: mecanum/omnidirectional trajectory tracking with
dynamics-aware control (MPC-style; kinematic-only models are known-weak),
kinodynamic local planning (TEB/DWA sample achievable commands rather
than assuming geometric paths are executable), occupancy-grid mapping
(Elfes; measured free/occupied space), and CBF-style safety filters that
modify or block nominal commands. **Our contribution is the combined
forensic execution-feasibility gate for navigation dataset generation:
routes, collectors, maps, and measured robot dynamics are checked before
training data is accepted.**

## The gate
```
route + measured map + measured yaw model + controller + collector type
        -> Execution Feasibility Decider ->
PASS_DEMONSTRATION | PASS_EVALUATION_ONLY | REJECT_MAP_DEFECT |
REJECT_YAW_INFEASIBLE | REJECT_CONTROLLER_INFEASIBLE |
REJECT_ARTIFACT_INCOMPLETE | REJECT_POLICY_NOT_EXPERT
```
Five checks: map feasibility (measured occupancy + robot-radius
dilation), yaw/curvature feasibility (measured calibration curve with a
0.8 safety margin), controller feasibility (full-route precheck
telemetry: completion/contacts/streaks), collector validity (scripted
expert vs learned-policy rollout; policies are evaluation evidence),
evidence integrity (process + artifact completeness; rc0 is necessary,
not sufficient).

## Validation protocol (failure-corpus replay)
The decider is validated against the frozen H2/H2.1/H2.2 ledger: it must
retroactively reject old K/M (map defect), H/I v2-v3 (yaw-infeasible
curvature), h2_td_M (artifact incomplete), and policy rollouts on unseen
goals (not expert), while passing the J_v2 scripted demonstrations.
The validation protocol is failure-corpus replay. The decider is
validated only if it reproduces the independently diagnosed
H2/H2.1/H2.2 outcomes from measured inputs and passes the J
demonstrations. Until that replay table exists and agrees, the decider
is BUILT, not validated.

## Contribution framing (exact)
A measured execution-feasibility decider for camera-only ImageNav data
collection that separates policy failure, controller infeasibility, map
defects, collector invalidity, and evidence incompleteness before
demonstrations are admitted into the imitation dataset.

## Paper story
We initially tried to expand the hospital navigation dataset by
collecting more policy and scripted rollouts. The experiments failed for
reasons that were not visible from success metrics alone: weak yaw
authority, incomplete obstacle maps, and invalid collector assumptions.
We therefore introduced an execution-aware demonstration decider that
rejects routes and rollouts before they contaminate training data.
