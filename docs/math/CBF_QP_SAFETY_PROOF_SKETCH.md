# CBF-QP Safety Proof Sketch

This document gives a self-contained proof sketch that the FleetSafe CBF-QP
filter keeps the robot inside the safe set `C` under the stated assumptions.

For full definitions see `FLEETSAFE_FORMAL_MODEL.md`.

---

## Theorem (Forward Invariance of C)

**Given:**
1. Initial state is safe: `h_i(x(0)) ≥ 0` for all obstacles `i`
2. The CBF condition holds at every time `t`:
   `ḣ_i(x(t), u(t)) + α · h_i(x(t)) ≥ 0`
3. Assumptions A1–A5 from the formal model hold.

**Claim:**  `h_i(x(t)) ≥ 0` for all `i` and all `t ≥ 0`.

---

## Proof Sketch (Continuous Time)

**Step 1 — Rewrite as a differential inequality.**

The CBF condition states:

```
ḣ_i(x, u) ≥ −α · h_i(x)
```

Since `ḣ_i = dh_i/dt`, this is a first-order scalar differential inequality
in `h_i(t)`:

```
dh_i/dt ≥ −α · h_i
```

**Step 2 — Apply the Comparison Lemma.**

The differential inequality `dh/dt ≥ −α h` with `α > 0` has the solution
lower bound given by the Comparison Lemma (see Khalil, *Nonlinear Systems*, Lemma 3.4):

```
h_i(t) ≥ h_i(0) · exp(−α t)      for all t ≥ 0
```

**Step 3 — Nonnegativity is preserved.**

Since `h_i(0) ≥ 0` (by assumption 1) and `exp(−α t) > 0` for all finite `t`:

```
h_i(t) ≥ h_i(0) · exp(−α t) ≥ 0      ∀ t ≥ 0
```

**Step 4 — Robot stays in the safe set.**

Because `h_i(x(t)) ≥ 0` for all `i`, by the definition of `C`:

```
x(t) ∈ C = { x | h_i(x) ≥ 0, ∀ i }      ∀ t ≥ 0
```

Therefore the robot never violates a distance constraint.  □

---

## Corollary: Safety of the QP Solution

The FleetSafe QP is designed so that **every feasible solution satisfies the
CBF condition**:

```
u_safe = argmin ½‖u − u_nom‖²_W
s.t.  ḣ_i(x, u) + α h_i(x) ≥ 0      ∀ i
      u_min ≤ u ≤ u_max
```

Therefore `u_safe` satisfies the premise of Step 1, and the theorem applies.

If `u_nom` already satisfies the CBF constraints, then `u_safe = u_nom` (no
intervention). If not, the QP finds the closest command that does satisfy them.

---

## Discrete-Time Implementation

The physical system runs at discrete time steps `Δt` (typically 10–50 ms).
Three additional mechanisms maintain the guarantee in practice:

### 1. Sampled Certificate Margins

At each step `k`, the certificate checks:

```
h_i(x_k) ≥ 0      (verified in the log)
```

A small tolerance `ε_h = 0.02` is allowed for numerical precision.
If `h_i < −ε_h`, a violation is flagged.

### 2. Latency Budget

Assumption A1 requires obstacle estimates to arrive within `τ_max` ms.
The certificate records `latency_ms` at every step. If `latency_ms > τ_max`,
the step is flagged as potentially unsafe (the safety certificate is
conditional on fresh sensor data).

### 3. Emergency Stop Fallback

If the QP becomes infeasible (no command satisfies all CBF constraints), the
system issues an emergency stop (`u_safe = [0, 0]`).  This is always safe
because a stationary robot satisfies `ḣ_i = 0 ≥ −α h_i` when `h_i ≥ 0`.

The emergency stop flag is recorded in the certificate as
`qp_status = "estop_fallback"`.

---

## What This Proof Does and Does Not Cover

| Covered | Not covered |
|---------|------------|
| Invariance of `C` under the CBF constraints | Safety of `u_nom` (the learned model) |
| Convexity of the QP | Correctness of obstacle detection |
| Emergency stop as fallback | SLAM drift / sensor noise |
| Certificate audit trail | Assumption A4 (command tracking error) |

**The learned model (GNM/ViNT/NoMaD) has no formal safety guarantee.**
The safety guarantee belongs entirely to the CBF-QP filter.

---

## References

- A. D. Ames, S. Coogan, M. Egerstedt, G. Notomista, K. Sreenath, P. Tabuada.
  "Control Barrier Functions: Theory and Applications." *ECC 2019.*
- H. K. Khalil. *Nonlinear Systems*, 3rd ed. Prentice Hall, 2002. Lemma 3.4.
- A. Clark. "Control Barrier Functions for Complete and Incomplete Information
  Systems." *IEEE TAC 2021.*
