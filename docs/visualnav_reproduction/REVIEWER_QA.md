# Reviewer Q&A — FleetSafe × VisualNav Benchmark

This document pre-empts the most common reviewer objections for a paper based on
this benchmark stack. Every answer is grounded in the current implementation.

---

## Architecture

**Q: Why Isaac Sim / Isaac Lab?**

Isaac Sim provides GPU-accelerated rigid-body simulation with photorealistic
rendering, supporting domain randomisation over lighting, materials, and object
geometry. Isaac Lab wraps it with a reinforcement learning task API.
The primary motivation for this project is evaluating safety-critical navigation
on the Yahboom M3Pro — a real holonomic robot — in conditions closer to real
deployment than pure MuJoCo can provide. Isaac Sim also enables parallel episode
rollouts (16–128 envs per GPU), reducing paper-grade evaluation wall-clock time
from hours to minutes.

*Current status:* Isaac Lab env stub exists at
`fleet_safe_vla/envs/isaaclab/yahboom/`. Isaac Sim GPU training has been
validated on the H1 humanoid. The M3Pro Isaac Lab backend is the next milestone.

---

**Q: Why MuJoCo too?**

MuJoCo is the default development and unit-test backend because it:
1. Runs on CPU without an Nvidia GPU.
2. Has a well-understood physics model that is reproducible across platforms.
3. Is free from licensing constraints (Apache 2 since 2022).
4. Enables fast iteration on the benchmark harness itself.

The benchmark architecture cleanly separates `backend="mujoco"` from
`backend="isaaclab"` so results from both can be compared (sim-to-sim delta)
and the real robot can be added as `backend="real"`.

---

**Q: Why the Yahboom RosMaster M3Pro?**

The M3Pro is a 4-mecanum-wheel holonomic platform with an onboard Jetson
module, USB-C camera, and a 360° LiDAR mount. It is:
1. Commercially available and reproducible by other labs.
2. Holonomic — which makes the safety problem harder than differential drive.
   A differential robot cannot strafe; the M3Pro can, so the CBF must handle
   vy commands and the FleetSafe wrapper must filter a 3-DoF input.
3. Small enough for indoor tabletop/office experiments but large enough to
   carry a Jetson Orin for real-time inference.

The X3 (differential-drive) is retained as a simpler structural baseline
so reviewers can see that the holonomic case is strictly harder.

---

**Q: Why GNM / ViNT / NoMaD?**

These three models form a progression:
- **GNM** — convolutional backbone, established baseline (2022).
- **ViNT** — vision transformer backbone, better long-horizon goal pursuit (2023).
- **NoMaD** — diffusion policy head, state-of-art on the VNT leaderboard (2023).

All three are from the same upstream repository (`robodhruv/visualnav-transformer`),
use the same observation contract (context stack + goal image), and have
publicly available checkpoints. This makes side-by-side comparison fair: the
only variable is the policy architecture.

The FleetSafe wrapper is architecture-agnostic — it wraps any adapter via the
`BaseVisualNavAdapter` interface — so adding future models (e.g., GR1, RT-2,
OpenVLA) requires only a new adapter file.

---

**Q: Why 2D metrics (SPL, success rate) AND 3D safety metrics?**

2D navigation metrics (SPL, success rate, path length) are standard in the VLN
and visual navigation literature, allowing comparison against prior work.

Safety metrics (collision rate, near-violation count, intervention rate,
cmd_vel delta) are novel to this benchmark. They quantify what the FleetSafe
layer actually does: how often it intervenes, by how much it changes the
nominal command, and whether it prevents near-misses.

Without both sets, reviewers cannot assess the safety-performance tradeoff:
a system that never collides by always stopping is trivially safe but useless
for navigation. The combined table shows FleetSafe's Pareto position.

---

## Data collection

**Q: What data is collected per episode?**

Per episode, the following files are written to disk:

| File                  | Content                                                 |
|-----------------------|---------------------------------------------------------|
| `episode.json`        | Full episode record: identity, metrics, truncated steps |
| `trajectory.csv`      | Step-by-step (x, y, heading, latency_ms)                |
| `actions.csv`         | Step-by-step (raw_vx/vy/wz, safe_vx/vy/wz, delta_l2, intervened) |
| `safety_events.jsonl` | One JSON per near-miss or CBF intervention               |
| `metrics.json`        | Episode-summary EpisodeMetrics dataclass                 |
| `metadata.yaml`       | Run identity, backend, seeds, scenes, timestamps         |

All raw command logs include both the nominal policy output and the post-CBF
safe command so the intervention magnitude is fully auditable.

---

**Q: How are seeds used?**

Seed N controls:
1. The physics engine random state (obstacle placement for cluttered/dynamic scenes).
2. The mock backend RNG (image noise, not used in production).

Critically, baseline and FleetSafe runs use **identical seeds**. This means
any difference in success rate, collision rate, or SPL is caused only by the
CBF safety filter, not by randomness. The metadata.yaml for each run records
the seed list so this can be verified independently.

---

**Q: How is the optimal path length computed?**

`optimal_path_m = Euclidean_distance(start, goal)`.

This is a lower bound on path length — achievable in open space but not through
clutter. The SPL formula penalises extra path length relative to this lower
bound, so a model that navigates around obstacles will have SPL < 1.0 even if
it succeeds. The straight-corridor scene allows SPL close to 1.0 for an
efficient model; the narrow-passage scene forces SPL < 1.0 for all models.

---

## Claims

**Q: What claims are made right now (before paper-grade runs)?**

The following are *structural* claims verifiable without running the benchmark:

1. Upstream GNM / ViNT / NoMaD are correctly adapted (no model code modifications).
2. The FleetSafe CBF-QP filter is formally correct (unit-tested in `tests/test_safety_filter.py`).
3. All 7 reproduction gates pass (verified — see gate run log).
4. The benchmark infrastructure correctly computes SPL, intervention rate,
   near-violation count, and exports JSON/CSV/HTML (unit-tested).
5. Baseline and FleetSafe conditions use identical seeds (enforced by runner code).

**Q: What empirical claims are NOT yet made?**

No quantitative navigation or safety performance claims are made until the
paper-grade run (50 seeds × 4 scenes × 6 conditions, MuJoCo backend) completes.

Specifically, the following remain pending:
- Exact SPL values for GNM/ViNT/NoMaD on each scene.
- Collision reduction percentage from FleetSafe.
- Near-violation reduction percentage from FleetSafe.
- Per-scene intervention rate and cmd_vel delta magnitude.
- Latency overhead of the CBF-QP filter.
- Sim-to-real rank correlation.

Do not cite this repository for any of the above until the run is complete
and the HTML/CSV report has been reviewed.

---

## Baselines

**Q: What baselines remain pending?**

| Baseline             | Status          | Note                                            |
|---------------------|-----------------|------------------------------------------------|
| GNM (no FleetSafe)  | ✓ Ready         | Adapter complete, checkpoint downloaded         |
| ViNT (no FleetSafe) | ✓ Ready         | Adapter complete, checkpoint downloaded         |
| NoMaD (no FleetSafe)| ✓ Ready         | Adapter complete, checkpoint downloaded         |
| Rule-based (DWA)    | ✗ Not implemented | Would require dynamic window approach nav stack |
| Rule-based (Bug2)   | ✗ Not implemented | Would require Bug2 planner integration          |
| GNM + FleetSafe     | ✓ Ready         | CBF wrapper operational                         |
| ViNT + FleetSafe    | ✓ Ready         | CBF wrapper operational                         |
| NoMaD + FleetSafe   | ✓ Ready         | CBF wrapper operational                         |

The DWA/Bug2 rule baselines are worth adding to provide a safety ceiling
(rule-based ≈ collision-free by construction) and navigation floor (rule-based
is not visually goal-conditioned). Until those are added, the comparison
is limited to learned-policy × safety-layer variants.

---

**Q: Why not compare to other safety approaches (e.g., safety shields, LCBF)?**

The FleetSafe CBF-QP is the proposed approach. Comparison against alternative
safety methods (Lagrangian relaxation, shielding, safety-conditioned imitation)
is planned as an ablation but is not yet implemented. The benchmark harness is
designed to accept any wrapper that implements the `FleetSafeWrapper` interface,
so adding alternative safety methods requires only a new wrapper file.

---

**Q: Isn't CBF-QP already well-known? What is the contribution?**

The contribution is not the CBF formulation. It is:
1. The first systematic evaluation of CBF-QP on top of diffusion-based visual
   navigation policies (NoMaD) on holonomic hardware.
2. A reproducible benchmark protocol with open-source code, checkpoints, and
   per-episode logs — something missing from existing VNT papers.
3. Quantification of the safety-performance tradeoff across three policy
   architectures on four canonical scenes.

The CBF implementation (`YahboomCBFFilter`) is intentionally a clean,
minimal QP formulation so reviewers can verify it and compare it to their own.

---

## Reproducibility

**Q: How do I reproduce a specific run?**

Each run produces a `metadata.yaml` with:
- `model`, `fleetsafe`, `backend`
- `seeds`, `scenes`
- `control_hz`, `v_max`, `vy_max`, `w_max`
- `timestamp_utc`
- checkpoint path (implied by model name)

Re-running with the same `--seeds`, `--scenes`, `--backend`, and checkpoint
on the same hardware should produce identical per-episode `metrics.json` files
(deterministic physics for MuJoCo backend with fixed seeds).

**Q: Are the checkpoints publicly available?**

Yes. They are the original published checkpoints from
`robodhruv/visualnav-transformer`. Google Drive IDs are in
`configs/visualnav/models.yaml`. Download with:
```bash
bash scripts/visualnav/setup_visualnav.sh --download-weights
```
or:
```bash
gdown --id <drive_id> -O <path>
```

**Q: What Python and library versions were used?**

See `pyproject.toml` for dependency constraints.
The primary evaluation environment:
- Python 3.10
- PyTorch ≥ 2.0 (weights_only=False required for upstream checkpoints)
- MuJoCo ≥ 3.0
- diffusers 0.11.1 (required by NoMaD)
- diffusion_policy (from `github.com/real-stanford/diffusion_policy`)

---

## Claim status

**Q: What claims are fully supported right now?**

The following claims are supported by the current codebase and can be made
without any additional runs:

| Claim | Evidence |
|-------|----------|
| GNM / ViNT / NoMaD upstream checkpoints load and produce valid output | `check_visualnav_checkpoints.py` PASS |
| The FleetSafe CBF-QP filter is formally correct (KKT conditions, barrier constraint) | Unit tests in `tests/test_safety_filter.py` |
| All 7 reproduction gates pass | `validate_gates.py` output |
| SPL, intervention rate, near-violation count are computed correctly | Unit tests in `tests/test_visualnav_benchmark_metrics.py` |
| Baseline and FleetSafe use identical seeds (no confound) | Enforced in `VisualNavBenchmarkRunner.run()` |
| Per-episode logging (6 file types) is complete and correct | Integration tests in `tests/test_visualnav_benchmark_runner.py` |
| M3Pro MJCF model is physically plausible (contacts, slip, PID) | Tests in `tests/test_yahboom_physics_env.py` |

These are **structural claims** — they assert that the benchmark infrastructure
is correct, not that a specific performance number holds.

**Q: What quantitative claims require MuJoCo paper-grade runs?**

All SPL, collision-rate, near-violation-rate, and intervention-rate numbers
require a full paper-grade run:

```
--backend mujoco --seeds paper --scenes all --fleetsafe both
```

This is `50 seeds × 4 scenes × 6 conditions = 1200 episodes minimum`.

Claims that are blocked until this run completes:
- "GNM achieves SPL of X.XX on straight_corridor"
- "FleetSafe reduces collision rate by X% on cluttered_static"
- "CBF-QP adds N ms latency overhead"
- "Near-violation count decreases by X on narrow_passage"
- Any regression to FleetSafe

**Do not report these numbers from `--backend mock` runs.** The mock backend
uses a simple 2D holonomic integrator with a random-walk policy, not a real
physics model or real inference. Mock numbers have no physical meaning.

**Q: What claims require Isaac Lab real runs?**

The following claims cannot be made until the Isaac Lab backend is implemented
and paper-grade runs complete:

- GPU-parallelised rollout throughput (episodes/hour, GPU utilisation)
- Any claim about photorealistic rendering improving transfer to real
- Domain randomisation ablation (lighting, material variation)
- Any sim-to-sim comparison between MuJoCo and Isaac Lab numbers
- Parallel episode scaling (16 / 64 / 128 envs)

Isaac Lab is gate-failed (`exit 2`) until `fleet_safe_vla/envs/isaaclab/yahboom/`
is fully implemented. See `check_isaac_scenes.py --backend isaaclab` for the
implementation checklist.

**Q: What claims require physical M3Pro hardware runs?**

Any claim about real-world performance requires physical M3Pro runs:

- Sim-to-real transfer: "SPL rank ordering is preserved on the real robot
  (Spearman ρ = X)" requires ≥ 10 real episodes per (model, scene) cell
- "FleetSafe prevents collisions on the real M3Pro" requires hardware testing
  with actual obstacle contacts
- "CBF-QP latency is acceptable for real-time operation at N Hz" requires
  profiling on Jetson Orin (not desktop CPU)
- Any claim in the paper using the word "real" or "physical" or "hardware"

Until real runs exist, all performance claims must be explicitly scoped to
simulation: *"In MuJoCo simulation, ..."*

The ROS2 bridge (`fleet_safe_yahboom_control`) is ready for real runs.
Gate 10 in `REPRODUCIBILITY_CHECKLIST.md` specifies the minimum evidence.

**Q: Why is the mock backend engineering-only and never publication evidence?**

The mock backend (`--backend mock`) is a software engineering tool. It is NOT
a simulation of robot physics. Specifically:

1. **No real physics.** The mock state integrates `cmd_vel` with Euler steps in
   flat 2D. There is no mass, inertia, wheel slip, friction, or contact geometry.
   A real robot running GNM would produce completely different trajectories.

2. **No real inference.** On mock backend, if a checkpoint fails to load (e.g.,
   missing `warmup_scheduler`), the runner silently substitutes `_MockAdapter`,
   which outputs Gaussian noise waypoints. Any "GNM result" from a mock run
   that fell back to `_MockAdapter` is pure noise.

3. **No calibrated obstacle distances.** Near-miss and collision thresholds are
   applied to distances in a 2D plane without mesh geometry. The same threshold
   that is physically meaningful in MuJoCo (contact within 0.10 m) is arbitrary
   in the mock integrator.

4. **Correct use of mock:** Verify that all output files are written, that the
   runner exits cleanly, that the HTML/CSV report exports correctly, and that
   the `--seeds smoke` run completes in under 30 seconds. That is all.

The mock backend generates output in `benchmarks/visualnav/results/` which is
excluded from git (`benchmarks/visualnav/results/` is in `.gitignore`) precisely
because these artifacts must never be confused with real results.
