# Stop-Policy Feature Audit

This document audits the input features used by each Track A stop-policy method.
It confirms which methods use runtime-available signals only and which use oracle geometry.

## Summary

| Method | Features | Runtime available | Oracle geometry | Future trajectory | Audit result |
|---|---|---|---|---|---|
| baseline_gnm | GNM distance prediction head | Yes | No | No | PASS |
| hand_tuned_waypoint_gate | GNM waypoint norm (predicted waypoint magnitude) | Yes | No | No | PASS |
| logistic_stop_head | GNM distance prediction (scalar) | Yes | No | No | PASS |
| temporal_neural_stop_head | GNM distance trend, waypoint trend, stability window (runtime history) | Yes | No | No | PASS |
| geometry_aware_oracle | True Euclidean distance to goal at each step | No — diagnostic only | **Yes** | No | DIAGNOSTIC |

---

## Method-by-method detail

### baseline_gnm

The baseline GNM policy never explicitly fires a stop command. The episode ends when the
step budget is exhausted (default 51–74 steps). The "final distance" is the Euclidean
distance from the robot's last pose to the goal.

**Features used at inference:** none — no stopping signal.
**Oracle geometry:** No.
**Future trajectory:** No.
**Verdict:** PASS — deployable as-is.

---

### hand_tuned_waypoint_gate

The hand-tuned waypoint gate computes the L2-norm of the GNM's predicted waypoint vector.
When this norm drops below a fixed threshold `wp_thresh = 0.30` for `k = 3` consecutive
steps, the policy fires a stop command.

**Features used at inference:**
- `wp_norm` — the L2-norm of GNM's predicted waypoint (goal-directed displacement vector).
  This is the GNM output itself, available at every step.

**Oracle geometry:** No. The threshold is hand-tuned on the training set; no true goal
distance is used at inference time.
**Future trajectory:** No.
**Verdict:** PASS — deployable.

---

### logistic_stop_head

The logistic stop head is a single logistic regression layer trained on GNM training
trajectories. At inference it consumes the scalar GNM distance prediction `dist_pred`
and outputs a stop probability `p_stop`. The episode ends when `p_stop >= 0.50`.

**Features used at inference:**
- `dist_pred` — scalar GNM distance-to-goal prediction (model output, runtime available).

**Oracle geometry:** No. The logistic head is trained on training episodes only.
**Future trajectory:** No.
**Observation:** On the 15 held-out validation episodes, `p_stop` never exceeded 0.50,
so the head never fired. SR and OSR match baseline identically. This is a calibration
failure on the held-out set, not a data leak.
**Verdict:** PASS for deployment safety; calibration improvement is an open research item.

---

### temporal_neural_stop_head

The temporal neural stop head is a small feed-forward network trained on Track A training
trajectories. It consumes a fixed-length history (sequence length 8) of runtime GNM
signals at each step and outputs a stop probability `p_stop`.

**Features used at inference (all from GNM runtime history):**
- `dist_pred` over the last 8 steps — scalar distance prediction from GNM head.
- `wp_norm` over the last 8 steps — waypoint norm from GNM head.
- `dist_trend` — finite-difference trend in `dist_pred` over the window.
- `stability_k3` — indicator: `dist_pred` decreased for `k = 3` consecutive steps.

**Oracle geometry:** No. None of the features require knowledge of the true goal
position or true Euclidean distance at inference time.
**Future trajectory:** No. Only past and current step signals are used.
**Verdict:** PASS — deployable. This is the strongest deployable held-out method.

---

### geometry_aware_oracle

The geometry-aware oracle is a **diagnostic upper bound only**. It is not deployable.
At each step, the oracle has access to the true Euclidean distance between the robot
and the goal. It fires when this distance drops below the success radius (3.0 m).

**Features used:**
- True Euclidean distance to goal — **oracle signal, not available at inference time**.

**Oracle geometry:** **Yes — this is the oracle.**
**Future trajectory:** No (it stops on first entry, not by lookahead).
**Verdict:** DIAGNOSTIC — provides an upper bound on SR given perfect stopping geometry.
Must not be compared to deployable methods as a fair baseline.

---

## Provenance chain

Each method's per-episode results are traceable to source files:

| Method | Source file |
|---|---|
| baseline_gnm | `results/research_audit/tracka_per_episode_metric_provenance.csv` |
| hand_tuned_waypoint_gate | `results/bo_reviewer_packet/deployable_stop_policy/17_deployable_stop_policy_details.csv` |
| logistic_stop_head | `results/bo_reviewer_packet/stop_head_train_val_protocol/19_learned_stop_head_details.csv` |
| temporal_neural_stop_head | `results/bo_reviewer_packet/temporal_stop_head/22_temporal_stop_head_details.csv` |
| geometry_aware_oracle | derived from baseline minimum_distance_to_goal |

All five methods are assembled into a single 75-row CSV by:

```bash
python3 scripts/gnm/generate_all_methods_provenance.py
```

The assembled CSV is verified (with bootstrap 95% CIs) by:

```bash
python3 scripts/gnm/verify_tracka_all_methods_metric_provenance.py
```
