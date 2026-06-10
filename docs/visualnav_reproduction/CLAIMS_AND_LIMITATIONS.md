# Claims and Limitations

This document explicitly states what is and is not claimed by the
FleetSafe × VisualNav-Transformer reproduction and benchmark pipeline.

---

## What This Pipeline Claims

### Structural claims (verifiable without running the benchmark)

1. The upstream GNM / ViNT / NoMaD model code is not modified.
   All FleetSafe-specific code lives under
   `fleet_safe_vla/integrations/visualnav_transformer/`.

2. The adapter interface (`BaseVisualNavAdapter`) correctly wraps the upstream
   model API as documented in the visualnav-transformer README and source.

3. The FleetSafe wrapper applies a CBF-QP safety filter (`YahboomCBFFilter`)
   that is verified on its own test suite (`tests/test_safety_filter.py`).

4. The benchmark runner uses identical seeds for baseline and FleetSafe runs,
   ensuring any performance difference is caused only by the safety layer.

5. The M3Pro MJCF used for simulation is a structural baseline validated by
   `tests/test_m3pro_mjcf.py` (44/44 tests pass, 0.15 s).

### Empirical claims (only after the benchmark runs)

No empirical claims are made until the benchmark matrix completes successfully.

The following claims require all 450 episodes to complete with
`gate_0` through `gate_4` passing:
- Model X achieves success_rate Y on scene Z (mean ± std over N seeds).
- FleetSafe reduces collision_rate by Δ% vs baseline (same seeds, same model).
- FleetSafe intervention_rate is I per episode on scene S.
- Mean latency overhead of FleetSafe CBF-QP is L ms per step.

**Do not cite results from this pipeline until the above runs complete.**

---

## What This Pipeline Does NOT Claim

1. **Not a real-world evaluation.** All results are in MuJoCo simulation.
   Sim-to-real transfer for navigation models is an open research problem.

2. **Not a faithful visual navigation evaluation.** The default benchmark
   runs with synthetic checkerboard goal images (`use_camera: false`).
   Real VisualNav performance depends on visual similarity between training
   and deployment environments. Setting `use_camera: true` enables real camera
   observations but requires the M3Pro camera element to be added to the MJCF.

3. **Baseline reproduction only.** We reproduce results from the upstream repository.
   We do not claim our simulation scores match the upstream paper's real-world
   results. Different evaluation conditions (robot, scene, camera, dataset)
   make direct comparison invalid.

4. **Not a rigorous CBF proof.** The CBF-QP filter (`YahboomCBFFilter`)
   provides a best-effort safety guarantee under the stated assumptions
   (obstacles are point masses, robot dynamics are first-order, obstacle
   positions are known exactly). Real-world safety requires additional
   mechanisms not present here.

5. **Not a complete FleetSafe validation.** The CBF filter is validated on
   synthetic obstacle scenarios in MuJoCo. Real-robot validation requires
   physical testing on the M3Pro hardware.

6. **Inertials are placeholder values.** The M3Pro MJCF uses box/cylinder
   approximations for inertial parameters. Stage 1 physics accuracy requires
   measured values. See `fleet_safe_vla/robots/yahboom/m3pro/ASSET_IMPORT_PLAN.md`.

---

## Known Limitations of the Benchmark

| Limitation | Impact | Mitigation |
|-----------|--------|------------|
| Synthetic goal images | Visual nav models behave as random when goals don't match training distribution | Set `use_camera: true` with real scene data |
| X3 MuJoCo env used for M3Pro fallback | Differential drive ≠ holonomic; vy commands are dropped | Implement M3Pro-specific nav_env with holonomic actuation |
| CBF assumes known obstacle positions | Not realistic; real robot uses lidar/depth | Replace with perception-based obstacle extraction (Stage 3+) |
| No topological graph for ViNT | ViNT's key feature (topological navigation) is disabled | Add graph construction from episode data |
| NoMaD diffusion is slow on CPU | ~150 ms/step → 6.7 Hz; below real-time | Use GPU; or reduce `num_diffusion_steps` to 5 |
| No domain randomisation | Results may not transfer across scenes | Enable configs/domain_randomization/ for training |

---

## How to Extend This Work

1. **Enable real camera observations**: Add `<camera>` element to M3Pro MJCF
   pointing from the `camera` site, then set `use_camera: true`.

2. **Implement M3Pro holonomic nav_env**: Subclass `YahboomMuJoCoBase` with
   M3Pro MJCF and 3-DoF action space (vx, vy, wz via mecanum IK).

3. **Add topological graph for ViNT**: Record a patrol trajectory, build a
   graph of (image, pose) nodes, and use ViNT's goal-distance head for
   node selection.

4. **Isaac Lab backend**: Set `simulation_backend: isaaclab` in
   `configs/visualnav/isaac_benchmark.yaml` and implement the Isaac Lab task
   in `fleet_safe_vla/envs/isaaclab/yahboom/`.

5. **Real-robot deployment**: Use `fleet_safe_vla/sim2real/deployment/` and
   the ROS2 bridge in `ros2_ws/src/fleet_safe_yahboom_control/` to deploy
   a trained ViNT + FleetSafe policy on the physical M3Pro.
