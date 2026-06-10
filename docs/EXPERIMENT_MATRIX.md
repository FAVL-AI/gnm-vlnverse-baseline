# FleetSafe Experimental Matrix

> Every row in this table must map to a reproducible run with a git commit, seed, and artifact hash.
> Claim status tags: **PROVEN** | **PRELIMINARY** | **SYNTHETIC** | **RECORDED_ONLY** | **NOT_VALIDATED**

---

## 1. Backbone Models

| Model       | Source                   | Role      | Dataset          | Mode     | Status          |
|-------------|--------------------------|-----------|------------------|----------|-----------------|
| ViNT        | visualnav-transformer    | primary   | SACSoN / HuRoN   | RGB-only | SYNTHETIC       |
| NoMaD       | visualnav-transformer    | secondary | SACSoN / HuRoN   | RGB-only | SYNTHETIC       |
| GNM         | visualnav-transformer    | optional  | SACSoN / HuRoN   | RGB-only | SYNTHETIC       |
| SaferPath   | internal reproduction    | reference | matched          | RGB-only | NOT_VALIDATED   |

**Backbone input contract (per paper §3.2):**
- Current RGB observation `o_t`
- Historical RGB observations `{o_{t-k}, …, o_t}`
- Goal image `o_g`
- Output: nominal guidance trajectory `τ̂`

---

## 2. Safety Modes

| Mode              | Description                                   | FleetSafe | Status        |
|-------------------|-----------------------------------------------|-----------|---------------|
| `nominal_only`    | Backbone output passed to robot directly       | No        | SYNTHETIC     |
| `naive_cbf`       | Simple CBF, no delay model, no uncertainty     | Partial   | NOT_VALIDATED |
| `delay_only`      | Delay-aware CBF, no uncertainty scaling        | Partial   | NOT_VALIDATED |
| `uncertainty_only`| Uncertainty-aware only, no explicit delay      | Partial   | NOT_VALIDATED |
| `FleetSafe_full`  | HOCBF-QP with delay + uncertainty + zone model | Yes       | SYNTHETIC     |

**FleetSafe input contract (per paper §4.1):**
- Nominal guidance trajectory `τ̂` from backbone
- Predicted execution-time state `x̂(t + Δ)`
- Measured delay `Δ` (cmd_vel_raw → /odom_raw round-trip)
- Obstacle estimate from FleetSafe perception pipeline

---

## 3. Experimental Conditions

| Factor           | Levels                                              | Controlled |
|------------------|-----------------------------------------------------|------------|
| Backbone         | ViNT, NoMaD, GNM                                    | Yes        |
| Safety mode      | nominal_only, FleetSafe_full                        | Yes        |
| Scene            | hospital_corridor, open_space, crowded_lobby, …     | Yes        |
| Seed             | 0–49 (paper grade), 0 (preliminary)                 | Yes        |
| Robot            | Yahboom M3Pro (real), MuJoCo sim, IsaacLab sim      | Yes        |
| Dataset          | SACSoN, HuRoN, hospital_sim (internal)              | Partial    |
| Delay injection  | 0ms, 50ms, 100ms, 200ms                             | No (TODO)  |
| Crowding density | low, medium, high (# dynamic agents)                | No (TODO)  |

---

## 4. Metrics

| Metric                  | Symbol          | Evidence Source             | Claim Status    |
|-------------------------|-----------------|-----------------------------|-----------------|
| Collision rate          | CR              | replay + safety_events.jsonl| SYNTHETIC       |
| Safety violation rate   | VR              | semantic zone logs          | SYNTHETIC       |
| Time-to-collision       | TTC             | telemetry (odom + obstacles)| SYNTHETIC       |
| Intervention count      | IC              | FleetSafe events            | SYNTHETIC       |
| Intervention rate       | IR              | FleetSafe events / steps    | SYNTHETIC       |
| Command latency         | L_cmd (ms)      | cmd_vel_raw timestamps      | SYNTHETIC       |
| Command jitter          | J_cmd (ms)      | cmd_vel trace variance      | SYNTHETIC       |
| SPL (Success-rate × PL) | SPL             | episode summaries           | SYNTHETIC       |
| Path efficiency         | PL_ratio        | trajectory vs optimal path  | SYNTHETIC       |
| Success rate            | SR              | episode summaries           | SYNTHETIC       |
| Social margin violations| SMV             | FleetSafe zone model        | SYNTHETIC       |
| Steps in RED zone       | T_red           | zone trace                  | SYNTHETIC       |
| Min human distance      | d_min (m)       | obstacle tracks             | SYNTHETIC       |
| Crowding risk           | ρ_crowd         | FleetSafe risk estimator    | SYNTHETIC       |

> All metrics currently SYNTHETIC (simulation only). Real-robot evidence moves them to RECORDED_ONLY
> → PRELIMINARY → PROVEN as data accumulates.

---

## 5. Comparison Matrix (paper Table 1 target)

For each backbone × safety_mode:

```
| Backbone | Safety Mode    | SR    | CR    | IR    | SPL   | L_cmd | Status       |
|----------|----------------|-------|-------|-------|-------|-------|--------------|
| ViNT     | nominal_only   | TBD   | TBD   | 0.0   | TBD   | TBD   | PRELIMINARY  |
| ViNT     | FleetSafe_full | TBD   | TBD   | TBD   | TBD   | TBD   | PRELIMINARY  |
| NoMaD    | nominal_only   | TBD   | TBD   | 0.0   | TBD   | TBD   | PRELIMINARY  |
| NoMaD    | FleetSafe_full | TBD   | TBD   | TBD   | TBD   | TBD   | PRELIMINARY  |
| GNM      | nominal_only   | TBD   | TBD   | 0.0   | TBD   | TBD   | PRELIMINARY  |
| GNM      | FleetSafe_full | TBD   | TBD   | TBD   | TBD   | TBD   | PRELIMINARY  |
```

Cells become PROVEN when: ≥ 10 seeds × ≥ 3 scenes × artifact hashes verified.

---

## 6. Run Metadata Schema

Every run must record:

```yaml
run_id:        string          # {backbone}_{safety_mode}_{backend}_{timestamp}
git_commit:    string          # 7-char SHA
seed:          int
dataset:       string          # SACSoN | HuRoN | hospital_sim
backbone:      string          # vint | nomad | gnm | safepath
safety_mode:   string          # nominal_only | FleetSafe_full | naive_cbf | …
scene:         string
robot:         string          # yahboom_m3pro | sim_mujoco | sim_isaaclab
sim_type:      string          # sim | sim_to_real | real
artifacts:
  aggregate_metrics: path + sha256
  by_scene:          path + sha256
  episodes_dir:      path
  video_path:        path | null
  bag_path:          path | null
evidence_status:  string       # PROVEN | PRELIMINARY | SYNTHETIC | RECORDED_ONLY | NOT_VALIDATED
```

---

## 7. Paper Claim Traceability

| Paper Claim                                      | Required Evidence            | Current Status  |
|--------------------------------------------------|------------------------------|-----------------|
| "FleetSafe reduces collision rate by X%"         | ≥10 seeds, CR measured       | PRELIMINARY     |
| "FleetSafe preserves SR within Y%"               | ≥10 seeds, SR measured       | PRELIMINARY     |
| "Intervention rate Z under FleetSafe"            | episode logs + IR computed   | PRELIMINARY     |
| "Delay-robust at 100ms"                          | delay injection experiment   | NOT_VALIDATED   |
| "Works on real Yahboom M3Pro"                    | ROS2 bag session + video     | RECORDED_ONLY   |
| "Backbone-agnostic (ViNT + NoMaD + GNM)"        | all 3 in registry            | PRELIMINARY     |
| "Hospital scene performance"                     | hospital_corridor scene runs | PRELIMINARY     |

---

## 8. Evidence Promotion Path

```
NOT_VALIDATED
    ↓  (run 1 seed)
PRELIMINARY
    ↓  (run ≥10 seeds, ≥3 scenes, hash-verified)
SYNTHETIC    ← sim only, never real
    ↓  (real robot session recorded)
RECORDED_ONLY
    ↓  (real data analyzed, metrics computed)
PROVEN
```

---

## 9. Reproducibility Requirements

To reproduce any PROVEN result:
1. `git checkout {git_commit}`
2. `python benchmarks/visualnav/run_benchmark.py --backbone {backbone} --safety-mode {safety_mode} --seed {seed} --scene {scene}`
3. Verify: `sha256sum results/{run_id}/aggregate_metrics.json` == recorded hash
4. Evidence ledger entry must exist with matching `id` and `sha256`
