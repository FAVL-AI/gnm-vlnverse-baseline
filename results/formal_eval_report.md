# FleetSafe Formal Safety Evaluation Report
*Generated: 2026-05-25 06:40 UTC*

---

## 1. Learned Policy Contract

**Models evaluated:** `gnm, nomad, vint`

GNM, ViNT, and NoMaD are goal-directed visual navigation policies trained
on human teleoperation or simulation data. They map camera images and goal
descriptors to nominal velocity commands `u_nom = [v_nom, ω_nom]`.

**The learned policy is NOT a safety-critical controller.**
It has no formal collision avoidance guarantee.
Its output is treated as a *proposal* that is filtered before execution.

---

## 2. Safety Filter Contract

FleetSafe wraps every nominal command with a **CBF-QP safety filter**:

```
u_safe = argmin  ½ ‖u − u_nom‖²
         subject to  ḣ_i(x,u) + α h_i(x) ≥ 0   ∀ i
                     u_min ≤ u ≤ u_max
```

Safety barrier: `h_i(x) = d_i(x)² − d_safe²`
with `d_safe = 0.5 m`

By the CBF Forward Invariance Theorem (see `docs/math/CBF_QP_SAFETY_PROOF_SKETCH.md`),
if the robot starts inside the safe set and the QP is feasible, it remains there.

---

## 3. Assumptions

| # | Assumption | Status |
|---|-----------|--------|
| A1 | Sensing latency ≤ 100 ms | verified per-step |
| A2 | Valid obstacle estimates from scan/depth | assumed (hardware-dependent) |
| A3 | QP feasible or emergency stop activated | verified per-step |
| A4 | Robot tracks cmd_vel within tolerance | assumed (actuator-dependent) |
| A5 | Emergency stop hardware functional | assumed (hardware-dependent) |

---

## 4. Certificate Summary

| Metric | Value |
|--------|-------|
| Total timesteps | 30 |
| Safe timesteps | 30 (100.0%) |
| Violations | 0 |
| CBF interventions | 3 (10.0%) |
| Max latency | 39.5 ms |
| Min h (barrier) | 0.2274 |
| Min distance | 0.6909 m |

---

## 5. Violations

**No violations.** All certificates satisfy formal safety conditions.

---

## 6. What Is Empirical

- Navigation success rate (reached goal / total episodes)
- Collision count (simulator ground truth)
- Path length efficiency
- Recovery behaviour
- Generalisation across scenes

These are measured by running experiments and counting outcomes.

---

## 7. What Is Mathematically Checked

At **every timestep**, the following are verified by the certificate:

- `h_min ≥ 0` — robot is outside the unsafe zone
- `min_dist_m ≥ 0.5 m` — clearance maintained
- `qp_status ∈ {optimal, estop_fallback}` — safety QP resolved
- `constraint_margin_min ≥ 0` — CBF constraints not violated
- `latency_ms ≤ 100` — sensor data is fresh
- `u_safe` finite — no numerical failure

The CBF Forward Invariance Theorem guarantees that if these hold,
the robot remains in the safe set C under Assumptions A1–A5.

---

## 8. What Is Not Guaranteed

- **Safety of the learned model in isolation.**
  GNM/ViNT/NoMaD have no formal guarantee; the CBF filter is required.
- **Optimality of navigation.**
  The filter may reduce speed or alter heading near obstacles.
- **Safety under A1–A5 violations.**
  Sensor failure, large tracking error, or QP infeasibility without e-stop
  would break the formal guarantee.
- **Absolute collision-free guarantee.**
  The proof holds under the stated assumptions; real-world sensor noise
  and SLAM drift are bounded but non-zero.

---

*For the formal model see `docs/math/FLEETSAFE_FORMAL_MODEL.md`.*
*For the proof see `docs/math/CBF_QP_SAFETY_PROOF_SKETCH.md`.*
