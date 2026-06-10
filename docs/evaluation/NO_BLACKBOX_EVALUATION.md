# No-Black-Box Evaluation in FleetSafe

## The Problem with "It Worked" Evaluations

Many learned robot navigation systems are evaluated purely empirically:

> "The robot reached the goal 87% of the time across 50 episodes."

This tells us the system is *useful*, but not *why* it is safe, *when* it
will fail, or *how* decisions are made.  For safety-critical applications
(hospitals, warehouses, public spaces), this is insufficient.

FleetSafe is designed so that **every motion decision is explainable and
formally auditable**.

---

## Architecture: Policy + Safety Filter

```
Image I_t + Goal g
        │
        ▼
  ┌──────────────────┐
  │  Learned Policy   │   GNM / ViNT / NoMaD
  │  (NOT certified)  │   proposes u_nom
  └──────────────────┘
        │ u_nom
        ▼
  ┌──────────────────────────────┐
  │   CBF-QP Safety Filter       │   FleetSafe
  │   (FORMALLY CERTIFIED)       │   computes u_safe
  └──────────────────────────────┘
        │ u_safe
        ▼
    Robot / Simulator
```

**GNM, ViNT, and NoMaD are nominal policies.**
They are goal-directed navigation models trained on data.
They are not safety-critical controllers.

**FleetSafe is the safety layer.**
It solves a quadratic programme at every timestep to find the closest
command to `u_nom` that satisfies mathematically defined distance constraints.

---

## The Two Evaluation Layers

### Layer 1: Empirical Navigation Performance

| Metric | Measured how |
|--------|-------------|
| Success rate (reached goal) | Simulator ground truth |
| Collision count | Simulator / sensor detection |
| Path length | Odometry integration |
| Smoothness | Command variance |
| Recovery from dead ends | Topological map traversal |

These are standard robotics metrics.  They tell us the system is *useful*.

### Layer 2: Mathematical Safety Certificates

At **every timestep**, FleetSafe logs:

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
  "safe": true
}
```

These certificates are the **proof** that the safety filter operated correctly.

The `verify_cbf_certificates.py` script checks all certificates and reports:
- How many timesteps passed the formal safety check
- Whether CBF constraints were ever violated
- How often the filter intervened to correct `u_nom`
- Maximum latency

---

## The Formal Guarantee

For the full mathematical model, see `docs/math/FLEETSAFE_FORMAL_MODEL.md`.
For the proof, see `docs/math/CBF_QP_SAFETY_PROOF_SKETCH.md`.

**Summary of the guarantee:**

> If the robot starts in the safe set `C = {x | h_i(x) ≥ 0}`, obstacle
> estimates are available within `τ_max` ms, and the QP is feasible, then
> the CBF-QP filter keeps the robot in `C` for all future time.
>
> This is proven by the CBF Forward Invariance Theorem via the Comparison Lemma.
>
> The learned model has no formal guarantee.  The certificate belongs to the
> safety filter only.

---

## Professor-Ready Explanation

> GNM and ViNT are used as nominal visual navigation policies. They are not
> trusted as safety-critical controllers. Their output is treated as a
> proposal, `u_nom`. FleetSafe wraps this proposal with a CBF-QP safety
> filter. The QP computes the closest command `u_safe` that satisfies
> formally defined distance-barrier constraints, actuator bounds, and runtime
> feasibility checks. Therefore the learned model handles goal-directed
> navigation, while the safety layer provides mathematical guarantees under
> stated assumptions. Every timestep logs the camera input, model output, CBF
> constraints, QP status, intervention flag, and final command, so the system
> is auditable rather than a black box.
>
> The safety guarantee is: if the robot starts inside the safe set and the
> CBF constraint `ḣ_i + α h_i ≥ 0` is enforced at each step, then by the
> Comparison Lemma, `h_i(t) ≥ h_i(0) · exp(−αt) ≥ 0` for all `t ≥ 0`.
> This means the robot never enters the forbidden zone around any obstacle,
> provided the sensing latency and QP feasibility assumptions hold.
>
> Empirical results (success rate, collision count, path length) measure
> navigation utility. The certificate log measures safety compliance. Both
> are reported so that the system can be evaluated as both useful and safe.

---

## Evaluation Scripts

| Script | Purpose |
|--------|---------|
| `scripts/evaluation/verify_cbf_certificates.py` | Check JSONL certificates for violations |
| `scripts/evaluation/audit_no_blackbox_logs.py` | Audit run directory for explainability |
| `scripts/evaluation/generate_formal_eval_report.py` | Generate Markdown report |

### Example

```bash
# Generate a sample certificate file and report
make formal-check
make formal-report

# Audit an existing run
python scripts/evaluation/audit_no_blackbox_logs.py --run-dir results/my_run/
```

---

## What FleetSafe Does NOT Claim

- We do **not** claim the learned model (GNM/ViNT/NoMaD) is formally safe.
- We do **not** claim the system is safe under sensor failure or SLAM drift
  beyond the stated assumptions.
- We do **not** claim formal verification of the neural network weights.

We claim:
- Every command sent to the robot passed a formally defined CBF-QP filter.
- Every such filter step is logged and auditable.
- The filter has a mathematical invariance proof under stated assumptions.
- The system is **not** a black box: the reason for every intervention is logged.
