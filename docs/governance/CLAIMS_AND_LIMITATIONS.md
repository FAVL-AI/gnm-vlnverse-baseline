# Claims and Limitations

## What claims are allowed

A benchmark claim is a statement of the form:
> "Model A achieves metric M under condition C with value V ± CI."

A claim is **valid** if and only if:

1. The result is backed by a frozen artifact (`benchmarks/frozen/`).
2. `validate_benchmark_artifact.py` returns PASS for the artifact.
3. `validate_transparency_artifacts(episode_dir)` returns PASS for all episodes.
4. The backend is NOT mock (`backend != "mock"`).
5. `n_seeds >= 50` for any quantitative comparison.
6. The claim includes `benchmark_version`, `protocol_version`, `git_commit`.
7. All five traceability fields are present (Rule 5 of TRANSPARENCY_POLICY.md).
8. For comparisons: paired Wilcoxon test passed at α=0.05 with Bonferroni correction.

---

## What can be claimed from each backend

### Mock backend (`backend: mock`)

| Allowed | Not allowed |
|---|---|
| Pipeline validation | Any quantitative navigation claim |
| CI testing | Success rate, SPL, collision rate claims |
| Explainability pipeline testing | Safety filter effectiveness claims |
| Development iteration | Sim-to-real extrapolation |

Mock backend results must carry the label `"ENGINEERING_ONLY — not publication evidence"`
in `audit_trail.json → backend_label`. Aggregates from mock runs must not
appear in paper tables.

### MuJoCo backend (`backend: mujoco`)

| Allowed | Not allowed |
|---|---|
| Simulation success rate | Claims about real-world performance |
| Simulation SPL | Claims about specific hardware |
| CBF intervention analysis | Claims that generalise to other robots |
| Safety metric comparisons | Claims without reproducibility artifacts |

All MuJoCo claims must specify:
- `mujoco_version`
- `m3pro_mjcf_version` (from asset file)
- The scene set version

### Isaac Lab backend (`backend: isaaclab`)

Isaac Lab claims are governed by the SIM-ISAAC PROVEN gate
(see `EVIDENCE_GOVERNANCE_AND_CLAIM_VALIDATION.md`).

**Current status (2026-05-21): PROVEN** (`isaac_publication_20260520T191959`).
18/18 combos complete. `verify_proven_gate.py` exits 0.

Key findings:
- GNM: RAW=100%→FS=0% corridor (IR=49.7%); 0% all scenes do-no-harm ✅
- ViNT: RAW=100%→FS=0% corridor (IR=37.9%); 0% all scenes do-no-harm ✅
- NoMaD: RAW=0% corridor (min_dist=1.5m, diffusion exploration avoids naturally);
  IR=0% — do-no-harm PROVEN, CBF idle across all scenes ✅

Navigation-paradigm finding: goal-directed VLAs (GNM, ViNT) fail with invisible
map-registered hazards; diffusion-based NoMaD avoids without any safety layer.

| Allowed (when PROVEN) | Not allowed |
|---|---|
| Invisible map-hazard collision prevention | Claims about VLA visual quality |
| CBF intervention rate on all 3 models | Sim-to-real transfer without real-robot evidence |
| Cross-backend collision rate comparison | Claims involving dynamic obstacles in Isaac |
| Surface-distance CBF effectiveness | Claims about photoreal fidelity (RTX confirmed, hospital USD pending) |

All Isaac claims must specify:
- `isaac_lab_version` (from omni.isaac.version)
- `omni.replicator` availability (photoreal gate)
- The scene spec version and obstacle visibility mode

### Real hardware (`backend: real`)

Not yet supported. When added:
- Video evidence required
- Hardware configuration frozen
- Deployment protocol documented
- Minimum 10 physical runs per condition

---

## Current limitations (v0.1)

### Simulation fidelity

The MuJoCo M3Pro model uses a simplified MJCF. Limitations:
- No tyre deformation model
- Simplified mecanum wheel contact geometry
- No IMU noise model in simulation
- Camera images are synthetic checkerboard/random (no sim-to-real visual domain gap)

**Claim implication:** Results are valid for evaluating the safety filter
and policy adapter logic, not for predicting exact real-world trajectory quality.

### Policy limitations

GNM, ViNT, and NoMaD are used with their original weights (no fine-tuning).
The visual input in simulation (synthetic images) does not match the distribution
the models were trained on. Consequently:

- Navigation success rates reflect "does the safety layer prevent collisions"
  more than "does the model navigate well in this environment."
- This is intentional: the benchmark evaluates CBF safety properties,
  not upstream policy quality.

### No real-world validation (v0.1)

No M3Pro physical runs exist at this version. The sim-to-real framing
(Spearman ρ rank correlation) is planned for a future version when physical
data is available.

**Claim implication:** Do not claim "the M3Pro achieves X% success rate on
cluttered scenes" based on v0.1 results. Claim "in MuJoCo simulation of the
M3Pro, FleetSafe reduces collision rate by X% relative to the baseline."

### Statistical power

With 50 seeds × 4 scenes × 6 conditions = 1200 episodes, the benchmark has
sufficient power for the primary comparisons (baseline vs FleetSafe per model).
Cross-model comparisons at the scene level require caution; effect sizes below
0.2 Cohen's d should not be reported as significant.

### Dynamic agent limitation

Dynamic agents in v0.1 use constant velocity. Real-world pedestrians and
vehicles have non-constant velocity. Results on `dynamic_obstacle` scenes
are valid for constant-crossing-agent scenarios only.

---

## Honest statement of current claim scope

### BOTH BACKENDS PROVEN (2026-05-21) — publication-ready

### MuJoCo PROVEN (2026-05-20)

> "FleetSafe reduces collision rate in MuJoCo simulation of the hospital
> corridor scene for all three tested backbone models (GNM, ViNT, NoMaD),
> with 50 seeds each. ViNT shows 100% → 0% collision (IR=69.7%). GNM and
> NoMaD show near-zero baseline collision with CBF idle, confirming
> do-no-harm. Gates: seeds_ok ✅ collision_ok ✅ coverage_ok ✅ cbf_ok ✅."

### Isaac Lab — ALL PROVEN (2026-05-21) — 18/18 combos

> "In Isaac Sim with invisible map-registered hazard cylinders (r=1.0m):
>
> **Corridor (primary safety scene — navigation-paradigm dependency revealed):**
> - GNM: RAW=100% → FS=0% (IR=49.7%, n=50) — PROVEN
> - ViNT: RAW=100% → FS=0% (IR=37.9%, n=50) — PROVEN
> - NoMaD: RAW=0% (min_dist=1.5m), FS=0%, IR=0% — do-no-harm PROVEN
>   [NoMaD's diffusion exploration avoids naturally; CBF correctly idle]
>
> **ICU Approach + Elevator Lobby (do-no-harm verification):**
> - GNM: 0%/0%/IR=0% all 3 scenes — PROVEN
> - ViNT: 0%/0%/IR=0% all 3 scenes — PROVEN
> - NoMaD: 0%/0%/IR=0% all 3 scenes — PROVEN
>
> **PROVEN gate (verify_proven_gate.py exits 0):**
>   seeds_ok ✅  collision_ok ✅  coverage_ok ✅  cbf_ok ✅  photoreal_ok ✅
>
> **Navigation-paradigm finding:** goal-directed VLAs (GNM, ViNT) navigate
> through invisible hazards toward their goal → 100% collision. Diffusion-
> based NoMaD does not commit to a fixed path → naturally avoids."

### Supportable claims (v0.1, both backends PROVEN)

| Claim | Evidence | Strength |
|---|---|---|
| FleetSafe reduces corridor collision from 100% to 0% for goal-directed GNM/ViNT in Isaac | 50 seeds each, PROVEN gate | PROVEN |
| FleetSafe reduces ViNT MuJoCo corridor collision from 100% to 0% (IR=69.7%) | 50 seeds, PROVEN gate | PROVEN |
| Goal-directed VLAs are vulnerable to camera-invisible map hazards | GNM/ViNT 100% RAW, min_dist<0.09m | PROVEN |
| Diffusion-based NoMaD avoids invisible hazards naturally (CBF idle) | NoMaD 0% RAW, min_dist=1.531m, IR=0%, n=50 | PROVEN |
| FleetSafe is selective (not over-conservative): IR=0% where safe | All 12 do-no-harm conditions, n=50 each | PROVEN |
| CBF is architecture-agnostic command-layer filter | Applied without modification to 3 paradigm-distinct models | PROVEN |

### What is NOT supportable from current data

- Claims about real M3Pro hardware performance (pending bench session)
- Claims about visual navigation quality (policy quality is not the focus)
- Claims that FleetSafe generalises to other robot morphologies
- Claims about performance on scenes not in the canonical v0.1 set
- Claims about Isaac CBF with dynamic/unregistered obstacles
- Claims that NoMaD's avoidance generalises to all invisible-hazard configurations
- Claims about formal safety guarantees outside of tested conditions
