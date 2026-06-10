# MuJoCo ↔ Isaac Sim-to-Sim Validation Gate

## Purpose

Isaac physics results are not citable as benchmark evidence until the agreement gate passes.
This document defines the gate protocol, thresholds, and interpretation.

The gate answers one question:

> Do the MuJoCo and Isaac Lab physics backends produce equivalent trajectory dynamics,
> obstacle distance estimates, and collision events when given identical inputs?

Both backends implement the same unicycle kinematic model:

```
x_new   = x   + vx · cos(yaw) · dt
y_new   = y   + vx · sin(yaw) · dt
yaw_new = yaw + wz · dt
```

where `dt = 1 / control_hz`. With identical actions and start positions, trajectories
must agree within the thresholds below. Any divergence indicates a backend regression.

---

## Evidence claim scope

| Condition | Isaac results status |
|---|---|
| Gate not run | NOT citable — do not report Isaac numbers |
| Gate run, ≥ 1 scenario FAIL | NOT citable — fix the backend regression |
| Gate run, all scenarios PASS | **Citable as sim physics evidence** |

MuJoCo remains the primary evidence backend until the gate passes on the target machine.

---

## Scenarios

### 1. `kinematic_smoke`

- **Scene:** no obstacles
- **Actions:** constant forward drive — `vx=0.20 m/s, wz=0.0 rad/s`
- **Steps:** 20 at 4 Hz → 5 s of motion → 1.0 m total travel
- **Checks:** `final_xy_error_m`, `trajectory_rmse_m`, `path_length_delta_pct`

The kinematic model is deterministic given the same dt and start pose. Trajectories
must match to floating-point precision; the 0.25 m threshold is a generous safety
margin to catch regressions rather than require exact equality.

### 2. `cluttered_navigation`

- **Scene:** 8 canonical cluttered_static obstacle positions
- **Actions:** sinusoidal yaw — `vx=0.20, wz = 0.30·sin(k·π/5)`
- **Steps:** 30 at 4 Hz → 7.5 s of motion
- **Checks:** `trajectory_rmse_m`, `path_length_delta_pct`, `near_violation_agreement`

Tests that `min_obstacle_dist_m` values agree in the presence of multiple obstacles.
Both backends use `OBS_RADIUS_M = 0.10` subtracted from Euclidean distance, so
near-violation events (dist < 0.35 m) must agree on every step (≥ 80 % threshold).

### 3. `forced_collision`

- **Scene:** single obstacle at `(0.8, 0.0)`
- **Actions:** constant forward — `vx=0.30 m/s`
- **Expected collision:** step 10 (`x = 0.75, dist = 0.8 − 0.75 − 0.10 = −0.05 m`)
- **Checks:** `collision_agreement`, `near_violation_agreement`

Both backends must report `collision=True` at exactly step 10. This is analytically
guaranteed when using the same kinematic formula; any mismatch indicates a sign error,
wrong obstacle radius, or wrong dt in one backend.

---

## Pass thresholds

| Metric | Threshold | Applies to |
|---|---|---|
| `final_xy_error_m` | ≤ 0.25 m | kinematic_smoke |
| `trajectory_rmse_m` | ≤ 0.20 m | kinematic_smoke, cluttered_navigation |
| `path_length_delta_pct` | ≤ 10 % | kinematic_smoke, cluttered_navigation |
| `near_violation_agreement` | ≥ 0.80 | cluttered_navigation, forced_collision |
| `collision_agreement` | must be True | forced_collision |

`near_violation_agreement` is computed using a script-level threshold of 0.35 m
(between MuJoCo's internal 0.30/0.45 band and Isaac's 0.30 m safety cost threshold)
so that it is backend-agnostic.

---

## Running the gate

### Without Isaac (CI sanity — MuJoCo only)

```bash
python scripts/visualnav/check_sim_to_sim_agreement.py
```

Exits with code 2 (incomplete). Writes MuJoCo trajectories and comparison skeletons.
All CI-safe tests in `tests/test_sim_to_sim_agreement.py` pass.

### Full gate (requires Isaac Sim, inside AppLauncher)

The script must run **in the same process** as AppLauncher — not as a subprocess — because
`pxr` (USD) bindings are only importable in the process where `AppLauncher` was initialised.

```bash
conda activate isaac
cd ~/robotics/FleetSafe-VisualNav-Benchmark

python -c "
from isaaclab.app import AppLauncher
app = AppLauncher({'headless': True}).app

import sys, importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'check_s2s',
    str(Path('scripts/visualnav/check_sim_to_sim_agreement.py').resolve()),
)
mod = importlib.util.module_from_spec(spec)
sys.modules['check_s2s'] = mod   # register before exec so @dataclass resolves __module__
spec.loader.exec_module(mod)
ret = mod.main(['--with-isaac'])
app.close()
sys.exit(ret)
"
```

Exit codes:
- `0` — all scenarios PASS → Isaac results citable
- `1` — ≥ 1 scenario FAIL → fix backend, re-run
- `2` — Isaac not available → run inside AppLauncher

### Specifying output directory

```bash
python scripts/visualnav/check_sim_to_sim_agreement.py \
    --with-isaac \
    --output-dir benchmarks/validation/sim_to_sim/paper_run_v1
```

---

## Output structure

```
benchmarks/validation/sim_to_sim/<timestamp>/
    kinematic_smoke/
        mujoco_trajectory.csv       # step,x,y,yaw,min_obstacle_dist_m,collision,action_vx,action_wz
        isaac_trajectory.csv        # same schema
        comparison.json             # per-scenario metrics, thresholds, pass/fail
    cluttered_navigation/
        mujoco_trajectory.csv
        isaac_trajectory.csv
        comparison.json
    forced_collision/
        mujoco_trajectory.csv
        isaac_trajectory.csv
        comparison.json
    agreement_report.md             # human-readable summary table
    summary.json                    # machine-readable gate result
```

### `comparison.json` schema

```json
{
  "generated_at": "2026-05-16T12:34:56Z",
  "scenario": "kinematic_smoke",
  "metrics": {
    "trajectory_rmse_m": 0.0,
    "final_xy_error_m": 0.0,
    "path_length_delta_pct": 0.0,
    "collision_agreement": true,
    "near_violation_agreement": 1.0,
    "min_obstacle_distance_delta_m": 0.0
  },
  "thresholds": { "final_xy_error_m": 0.25, "..." : "..." },
  "passed": true,
  "fail_reasons": []
}
```

### `summary.json` top-level fields

| Field | Type | Meaning |
|---|---|---|
| `gate_passed` | bool | True iff Isaac available AND all scenarios pass |
| `isaac_available` | bool | Was Isaac backend reachable? |
| `n_pass` / `n_fail` | int | Scenario counts |
| `scenarios` | list | Full `AgreementMetrics` per scenario |

---

## Interpreting failure

### `trajectory_rmse_m` or `final_xy_error_m` fails

Both backends implement the same kinematic formula. If RMSE > 0 (beyond floating-point),
a dt or formula mismatch exists. Check:

- Both invoked with same `control_hz` (default: 4.0)
- Isaac env uses `dt = 1 / control_hz`, not `SIM_DT` directly
- `teleport_to()` was called after `reset()` in both

### `collision_agreement` fails

Both backends use `OBS_RADIUS_M = 0.10` for the distance computation. A mismatch means:

- Different obstacle radius in the cylinder spawn (`CylinderCfg`) vs. the distance formula
- Wrong prim path for an obstacle (Isaac reads back a different position)
- `teleport_to()` jitter not zeroed before the rollout

### `near_violation_agreement` fails below 0.80

Agreement < 1.0 should not happen for these scenarios since both backends use the same
formula. Any miss is a sign of async pose lag in Isaac (prim write not completing before
`_nearest_dist()` reads). Fix: increase `_flush_app(n=...)` in `IsaacNavBenchmarkEnv`.

---

## Recording the gate for paper submission

After the gate passes:

1. Copy `benchmarks/validation/sim_to_sim/<timestamp>/` into the supplementary artifact.
2. Reference the `summary.json` gate result in the experimental methodology section.
3. Update `docs/visualnav_reproduction/ISAAC_PHYSICS_BACKEND.md` "Validation status" field.
4. Record the confirmed status in `project_fleetsafe.md`.

The gate output is immutable evidence — do not overwrite a passing run's directory.
