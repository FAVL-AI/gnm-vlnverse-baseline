# FleetSafe Formal System Model

## 1. System Overview

```
Image I_t + Goal g
        │
        ▼
  ┌─────────────────┐
  │  Learned Policy  │   GNM / ViNT / NoMaD
  │   π_θ(I_t, g)   │   (nominally optimal, NOT safety-certified)
  └─────────────────┘
        │  u_nom
        ▼
  ┌─────────────────────────────────────┐
  │       CBF-QP Safety Filter          │   FleetSafe layer
  │   u_safe = argmin ½‖u−u_nom‖²_W    │   (mathematically constrained)
  │   s.t.  ḣ_i(x,u) + α h_i(x) ≥ 0   │
  │         u_min ≤ u ≤ u_max           │
  └─────────────────────────────────────┘
        │  u_safe
        ▼
  Robot / Simulator
  (Isaac Sim · Gazebo · M3Pro Jetson)
```

The learned policy is **not** a safety-critical controller.
It proposes a nominal command; the safety filter is the only component
with formal guarantees.

---

## 2. State and Variable Definitions

| Symbol | Domain | Meaning |
|--------|--------|---------|
| `x` | ℝⁿ | Full robot state (pose, velocity, sensor readings) |
| `p` | ℝ² | Robot position (x, y) in world frame |
| `ψ` | ℝ | Robot yaw angle |
| `v` | ℝ | Linear velocity |
| `ω` | ℝ | Angular velocity |
| `u_nom` | ℝ² | Nominal command from learned policy `[v_nom, ω_nom]` |
| `u_safe` | ℝ² | Filtered command from CBF-QP `[v_safe, ω_safe]` |
| `O_i` | ℝ² | Position of obstacle `i` in world frame |
| `d_i(x)` | ℝ≥0 | Euclidean distance from robot centre to obstacle `i` |
| `d_safe` | ℝ>0 | Minimum required clearance distance |
| `α` | ℝ>0 | CBF decay rate (class-K function parameter) |
| `W` | ℝ²ˣ² | Positive-definite QP cost weighting matrix |

---

## 3. Control Barrier Function

For each obstacle `i`, define the **safety barrier function**:

```
h_i(x) = d_i(x)² − d_safe²
```

**Interpretation:**
- `h_i(x) > 0` → robot is **outside** the unsafe zone around obstacle `i`
- `h_i(x) = 0` → robot is **on the boundary** of the safety zone
- `h_i(x) < 0` → robot is **inside** the unsafe zone (violation)

### Safe Set

```
C = { x ∈ ℝⁿ  |  h_i(x) ≥ 0,  ∀ i }
```

The safe set `C` is the region where every obstacle clearance is at least `d_safe`.

---

## 4. CBF Condition (Invariance Constraint)

To guarantee forward invariance of `C`, every command `u` must satisfy:

```
ḣ_i(x, u) + α · h_i(x) ≥ 0      ∀ i
```

where `ḣ_i(x, u) = ∇_x h_i(x) · f(x, u)` is the Lie derivative of `h_i`
along the robot dynamics `ẋ = f(x, u)`.

For a unicycle robot with state `x = [p_x, p_y, ψ]` and command `u = [v, ω]`:

```
d_i(x)² = (p_x − O_i,x)² + (p_y − O_i,y)²

ḣ_i(x, u) = 2 [(p_x − O_i,x) · v · cos ψ
               + (p_y − O_i,y) · v · sin ψ]
```

The CBF constraint is linear in `u = [v, ω]`, so the QP is always convex.

---

## 5. Safety Filter QP

At each timestep `t`, FleetSafe solves:

```
u_safe = argmin   ½ ‖u − u_nom‖²_W
          u

subject to:
  ḣ_i(x_t, u) + α · h_i(x_t) ≥ 0      ∀ i   (CBF constraints)
  v_min ≤ v ≤ v_max                            (actuator bounds)
  ω_min ≤ ω ≤ ω_max
```

**Properties:**
- The objective minimises deviation from the nominal learned command.
- The CBF constraints are linear in `u` → the QP is quadratic with linear constraints.
- Solution is unique (W ≻ 0) and computed in O(n_obstacles) time.
- If the QP is infeasible (no safe command exists), FleetSafe issues an emergency stop.

---

## 6. Assumptions

For the formal safety guarantee to hold, the following must be satisfied:

| # | Assumption | Implication if violated |
|---|-----------|------------------------|
| A1 | **Bounded sensing latency**: obstacle estimates are available within `τ_max` ms | Stale estimates may miss obstacles |
| A2 | **Valid obstacle estimates**: LiDAR/depth data covers the reachable region | Undetected obstacles outside sensor cone are not protected |
| A3 | **Feasible QP**: a safe command exists given current state and obstacles | CBF may be infeasible in very tight corners; emergency stop activates |
| A4 | **Command tracking**: robot actuators track `u_safe` within tolerance `ε_track` | Tracking error can accumulate; bounds the practical safety margin |
| A5 | **Emergency stop exists**: hardware/software e-stop is functional | Last-resort safety in simulation and on the real M3Pro |

---

## 7. Limitations

- **The learned policy (GNM/ViNT/NoMaD) is NOT formally verified.**
  Its output `u_nom` can be arbitrary. The safety certificate applies only to `u_safe`.
- The CBF proof is for continuous time; the discrete implementation uses finite
  time steps and sampled sensor data, introducing bounded error (see proof sketch).
- Obstacle positions are estimated, not exact; sensor noise and SLAM drift can
  reduce the effective safety margin.
- The proof guarantees the robot stays in `C` under Assumptions A1–A5.
  Violation of any assumption breaks the formal guarantee.

---

## 8. Per-Timestep Safety Certificate

Every command issued by FleetSafe is logged with:

```json
{
  "timestamp": 12.35,
  "model_name": "gnm",
  "u_nom": [0.20, 0.15],
  "u_safe": [0.05, -0.10],
  "h_min": 0.084,
  "min_dist_m": 0.58,
  "cbf_active": true,
  "qp_status": "optimal",
  "constraint_margin_min": 0.012,
  "latency_ms": 18.4,
  "safe": true,
  "notes": ""
}
```

These certificates are the audit trail that makes FleetSafe non-black-box.
See `scripts/evaluation/verify_cbf_certificates.py` to check them.
