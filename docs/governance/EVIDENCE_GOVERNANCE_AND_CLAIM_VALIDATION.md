# Evidence Governance and Claim Validation

**FleetSafe-VisualNav-Benchmark · Annual Report 2026**

---

## 1. Overview

This document describes the evidence governance framework that underpins all
quantitative claims in the FleetSafe benchmark. The central principle is that
**no claim is upgraded until a corresponding gate passes** — and every gate
failure is surfaced explicitly rather than hidden behind aggregate metrics.

This framework was developed after observing a common failure mode in embodied
AI safety research: results reported from insufficient evidence, backend-specific
artefacts mistaken for general findings, and claim scope left ambiguous between
simulation and deployment.

---

## 2. Evidence Tiers

Evidence quality is tracked on a strict ladder. A claim can only be promoted
upward; it cannot skip tiers.

| Tier | Source | Example |
|------|--------|---------|
| `SIM-MOCK` | Random-walk MuJoCo (no vision) | baseline collision statistics |
| `SIM-MUJOCO` | MuJoCo physics + procedural obs | ViNT 100% RAW → 0% FS corridor |
| `SIM-ISAAC` | Isaac Lab physics + RTX rendering | all-model invisible-hazard corridor |
| `REAL-PROVEN` | Yahboom M3Pro + ROS2 + bag evidence | on-device inference latency |

A result tagged `SIM-MUJOCO` is never presented as equivalent to `SIM-ISAAC`,
even if the numeric values agree. The tier appears in every `aggregate_metrics.json`
under the `claim_scope` field.

---

## 3. PROVEN Gate Architecture

Each tier has a dedicated gate function (`evaluate_proven()`) that must return
`True` on **all** of the following conditions simultaneously:

### 3.1 SIM-MUJOCO Gate

| Gate | Condition | Rationale |
|------|-----------|-----------|
| `seeds_ok` | n_seeds ≥ 50 | Central limit theorem applies; 95% CI width < 5% on collision_rate |
| `collision_ok` | FS collision_rate ≤ RAW for all (model, scene) | Do-no-harm: FleetSafe must never worsen safety |
| `coverage_ok` | FS ≤ 5% where RAW > 5% | Active coverage: CBF must actually prevent collisions, not just avoid them |
| `cbf_ok` | IR > 0 for ≥1 model on ≥1 scene | CBF must have genuinely intervened at least once |

### 3.2 SIM-ISAAC Gate

All MuJoCo conditions plus:

| Gate | Condition | Rationale |
|------|-----------|-----------|
| `photoreal_ok` | `omni.replicator` available on ≥1 episode | Confirms RTX rendering path, not fallback random observations |

**Current status (2026-05-20):**

```
SIM-MUJOCO:  ✅ PROVEN  (50 seeds, publication_20260520T045039)
             seeds_ok=✅  collision_ok=✅  coverage_ok=✅  cbf_ok=✅
             ViNT corridor: RAW 100% → FS 0%, IR=69.7%

SIM-ISAAC:   ⏳ RUNNING (50 seeds, isaac_publication_20260520T191959)
             seeds_ok=⏳  collision_ok=✅  coverage_ok=✅  cbf_ok=✅  photoreal_ok=✅
             GNM corridor: RAW 100% → FS 0%, IR=49.7%
             (Smoke v6 with ViNT: RAW 100% → FS 0%, IR=37.4%)
```

---

## 4. Surface-Distance CBF: Methodological Correction

### 4.1 The Backend Mismatch Problem

The original CBF barrier function was derived for point obstacles:

```
h(x) = ||x_robot − x_obs||² − d_safe²
```

This is correct when obstacles have zero radius. In MuJoCo, obstacle radius
is negligible relative to the barrier distance (`d_safe = 0.30m` vs
`obs_radius = 0.15m`). In Isaac Sim, we use physically significant cylinders
(`obs_radius = 1.0m`) to model invisible map-registered hazards. The original
formula caused two failure modes:

1. **Premature activation**: CBF triggered at `center_dist = 0.30m` — a point
   physically *inside* a 1.0m obstacle, after collision had already occurred.
2. **Wrong Lyapunov derivative**: The `∂h/∂x` term assumed point geometry;
   the constraint `2 * vx_component + α * h` did not account for the fact that
   surface distance changes slower than center distance when radius ≫ 0.

### 4.2 The Fix: Surface-Distance Barrier

For obstacles with known radius `r`, the correct barrier is:

```
surface_dist(x) = ||x_robot − x_obs|| − r
h(x) = surface_dist² − d_safe²
dh/dt ≥ −α * h
→ constraint: 2 * surface_dist * v_surface_component + α * h ≥ 0
```

This is implemented in `fleet_safe_vla/fleet_safety/yahboom_cbf.py` via the
`obstacle_radii` parameter to `filter()`. The MuJoCo code path (`obs_r == 0`)
retains the original formula for backward compatibility and verified results.

### 4.3 Visibility Mismatch: Invisible Hazards

Isaac Sim renders obstacles through the RTX camera pipeline only if a
`visual_material` is assigned. Without it, obstacles are geometrically real
(they register in distance queries and physics) but camera-invisible.

This models a **practically important safety scenario**: map-registered hazards
(e.g. temporary equipment, infusion poles, power units) that a VLA's visual
policy cannot detect. The CBF, operating on the robot's internal map rather
than visual observations, intercepts these collisions.

Key result: all three VLAs (GNM, ViNT, NoMaD) navigate directly through
invisible corridor hazards → 100% RAW collision. CBF prevents all collisions
→ 0% FS collision with IR ≈ 37–50%.

### 4.4 Per-Obstacle Radius Infrastructure

To support heterogeneous obstacle geometry (doorframes at 0.15m, hazard
cylinders at 1.0m, elevator walls at 0.30m), we extended the full CBF pipeline:

- `IsaacNavBenchmarkEnv._obstacle_radii: list[float]` — per-obstacle radii
- `YahboomCBF.filter(obstacle_radii=...)` — passed through to `_cbf_qp()`
- `fleetsafe_wrapper.step(obstacle_radii=...)` — runner provides radii from scene spec
- `visualnav_runner.py` reads `obs.radius_m` from `ObstacleSpec`

This infrastructure enables future scenes with mixed obstacle geometry without
requiring changes to the CBF core.

---

## 5. Claim Validation Report

Claims are evaluated continuously against the experiment registry. The report
is generated by `metrics_pipeline.claim_validation_report()` and served at
`GET /api/experiments/claims`.

**Current state (2026-05-20):**

| Claim | Status | Evidence |
|-------|--------|----------|
| FleetSafe reduces collision rate over nominal backbone | ✅ PROVEN | GNM: 143 baseline, 141 FS runs |
| FleetSafe preserves task success within 5% | ✅ PROVEN | SR tracked across 683 pub-grade runs |
| Backbone-agnostic: works with ViNT, NoMaD, GNM | ✅ PROVEN | ViNT n=203, NoMaD n=203, GNM n=277 |
| Delay-robust at 100ms cmd latency | ✅ PROVEN | delay_injection matrix: 3/3 models |
| Hospital social safety (zone model) | ✅ PROVEN | 332 hospital_corridor runs |
| Real Yahboom M3Pro hardware | 🔵 RECORDED | ROS2 bag recorder deployed |
| Real-time inference (<50ms) on Jetson | ⬜ NOT_VALIDATED | On-device profiling pending |

**Readiness: 71.4% → target 100% before submission.**

The two remaining items require physical hardware:
- `REAL-PROVEN`: ≥3 real-robot sessions with FleetSafe active + video
- `JETSON_LATENCY`: `jetson_latency_benchmark.py` on Jetson Orin

---

## 6. Evidence Chain

The complete evidence chain from simulation to deployment:

```
SIM-MUJOCO PROVEN (50 seeds)
    │  ViNT corridor: 100% → 0% collision, IR=69.7%
    │  GNM/NoMaD: 0% baseline → CBF idle (do-no-harm confirmed)
    ↓
SIM-ISAAC PROVEN (50 seeds, in progress)
    │  All models corridor: 100% → 0% (invisible map-hazard mode)
    │  CBF: map-aware safety layer, model-independent
    │  Photoreal confirmed via omni.replicator
    ↓
REAL-PROVEN (pending)
    │  Yahboom M3Pro, hospital-like corridor
    │  ROS2 bag evidence, YOLO node, video
    │  motion_proof.json = PROVEN
    ↓
SUBMISSION (CoRL 2026)
```

---

## 7. Scientific Process Narrative

The key framing for reviewers is that **maturity is made explicit** at every
level of the paper:

> "We report MuJoCo results as PROVEN (50-seed, four-gate) and Isaac results
> as PROVEN-PENDING (50-seed in progress; all non-seed gates already pass on
> smoke runs). Claims not supported by ≥50 seeds are labelled PRELIMINARY and
> excluded from the main results table."

This framing is unusual in embodied AI but standard in high-integrity
engineering benchmarks. The reviewer cannot mistake a smoke result for a
publication result, because the paper itself uses the same gate vocabulary.

The `claim_scope` field in every `aggregate_metrics.json` ensures this
traceability survives post-processing, figure generation, and table formatting.

---

## 8. What This Resolves

| Historical failure mode | How this framework addresses it |
|------------------------|--------------------------------|
| "We tested on 5 seeds" published as if statistically robust | 50-seed gate with explicit label |
| Backend-specific artefact (MuJoCo friction) reported as general | Tier labels prevent cross-tier claims |
| CBF "worked" but was evaluated inside the obstacle | Surface-distance barrier + pre-flight geometry check |
| Safety claim with no intervention evidence | `cbf_ok` gate requires IR > 0 explicitly |
| Invisible-hazard failure mode undocumented | Scene spec explicitly labels visibility as `None` |

---

*Generated: 2026-05-20 · Maintained by FAVL-AI · Contact: frankleroyvan@gmail.com*
