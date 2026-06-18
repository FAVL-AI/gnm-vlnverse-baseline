<!-- GNM_VLNVERSE_RELEASE_MATRIX_START -->
## Research release matrix

This repository is a staged GNM-VLNVerse Track A stopping-reliability and metric-provenance study. The release ladder records each piece of evidence added for navigation performance, stopping-policy diagnosis, metric provenance, ablation, Isaac live demonstration, and supervisor/reviewer validation.

| Release | Focus | Main evidence |
|---|---|---|
| v1.0 | Track A stop-policy study | Baseline GNM, stop-policy sweep, temporal stop-head result, geometry-aware oracle |
| v1.1 | Temporal stop-head ablation | Sequence length and stability-window ablation |
| v1.2 | Temporal stop-head feature-set ablation | Shows full temporal runtime history is required for best deployable result |
| v1.3 | Stable Isaac live trajectory demo | Live Isaac replay using real VLNVerse/GNM trajectory data |
| v1.4 | Supervisor evidence pack | Answers how GNM is used, how data is labelled, why baseline SR is 20.0%, and why OSR shows stopping failure |
| v1.5 | Dataset and scene manifest | Records 238 train trajectories, 15 validation trajectories, four Kujiale scenes, and local asset inventory |
| v1.6 | Public README research release matrix | Summarises the staged release ladder, result table, dataset split, Isaac demo, and evidence documents |
| v1.7 | One-command reproducibility pack | Single script verifies full evidence chain without Isaac Sim or GPU |
| v1.8 | 131-test suite and stop-policy ablation | Full stop-policy ablation with temporal feature sensitivity evidence |
| v1.9 | Methodology walkthrough | End-to-end architecture and code evidence walkthrough |
| v2.0 | FleetSafe-GNM Isaac ROS 2 implementation manual and data collection pipeline | Implementation manual, ROS 2 topic checker, Isaac rosbag collection wrapper, rosbag-to-GNM converter, GNM fine-tuning wrapper, GNM-only vs GNM-plus-FleetSafe evaluation wrapper, ROS 2 launch skeleton, dry-run-safe scripts |
| v2.1 | Live Isaac ROS 2 bridge verification layer and Yahboom placeholder | Isaac bridge availability checker, live topic verifier (five required topics), Yahboom M3 Pro control scene placeholder checklist, Isaac Sim startup instructions, CI-safe dry-run mode for all checks |
| v2.2 | Yahboom M3 Pro sim-to-real topic bridge plan (prerequisite) | Sim-to-real plan with full concept glossary, asset inventory (5 URDFs, Xacro, 2 USDs, launch files, configs), canonical topic contract, Nova Carter smoke-test retirement, camera alias documentation |
| v2.3 | Yahboom Isaac import and Track A/B verification gates (prerequisite) | Ordered 11-step Isaac import plan, recording gate topic verifier, Track A/B completion gates, full concept glossary, claim boundary table |
| v2.4 | First valid Yahboom Isaac rosbag2 episode (prerequisite) | Yahboom-specific episode collector with mandatory topic gate, episode validator (message_count > 0 on all five topics), Nova Carter contamination check, episode metadata and validation report |
| v2.4.2 | Yahboom ROS 2 OmniGraph topic publishers | Isaac Sim Python script to create ROS 2 action graph (OnPlaybackTick → ROS2Context → 5 publisher/subscriber nodes), updated USDA with Camera sensor prim and OmniGraph stubs, GUI and script methods |
| v2.4.1 | Visible Yahboom Isaac stage and ROS 2 publisher scaffold | Visible geometry-correct placeholder stage (base, deck, camera, lidar, 4 wheels, ground), programmatic USDA generator, five-node OmniGraph scaffold plan, no-absolute-path USDA |
| v2.5 | Metric provenance claim gates and ICRA stopping paper — validated for Track A paper scope | All-methods per-episode provenance (75 rows, 5 methods × 15 episodes), research claim ledger, validation split lock, bootstrap CIs, stop-head feature audit, paper claim-to-evidence map, one-command pack, ICRA paper source |
| v2.6 | Expanded Track A robustness evidence | Per-scene SR/OSR/NE (20 rows, 5 methods × 4 scenes), paired Wilcoxon + sign test (baseline vs temporal), bootstrap seed stability (seeds 41–44), robustness summary with explicit data-availability audit and honest claim boundaries |
| v2.7 | Expanded 253-episode Track A split (baseline + oracle) | 506-row provenance CSV (253 episodes × 2 methods), CI width narrows from ±20 pp to ±6 pp for SR, stopping-gap confirmed at N=253 (OSR−SR = 13 pp), methodology note documents why 3 methods cannot be expanded, split lock, verifier, 8 new CI-enforced tests |
| upstream | Yahboom ROSMASTER M3 Pro upstream integration | Official Yahboom repo as external hardware reference, clone/setup script, upstream inspector, Yahboom-to-canonical topic mapping, OpenClaw architecture note |

### Key Track A results

| Method | SR | OSR | NE |
|---|---:|---:|---:|
| Baseline GNM | 20.0% | 46.7% | 6.51 m |
| Hand-tuned waypoint gate | 26.7% | 26.7% | 5.34 m |
| Logistic stop head, train to validation | 20.0% | 46.7% | 6.51 m |
| Temporal neural stop head | 33.3% | 33.3% | 4.47 m |
| Geometry-aware oracle upper bound | 46.7% | 46.7% | 3.79 m |

### Dataset and scene evidence

The current Track A study uses:

- 238 training trajectories
- 15 validation trajectories
- 4 local Kujiale/VLNVerse scenes

Scene-level split:

| Scene ID | Train trajectories | Validation trajectories |
|---|---:|---:|
| kujiale_0092 | 66 | 2 |
| kujiale_0118 | 60 | 3 |
| kujiale_0203 | 65 | 7 |
| kujiale_0271 | 47 | 3 |

### Stable Isaac live demo

```bash
conda activate isaac
python scripts/gnm/isaac_live_trajectory_demo.py
```

# GNM-VLNVerse Baseline

Repository: https://github.com/FAVL-AI/gnm-vlnverse-baseline

This repository contains a **complete validation package for the GNM-VLNVerse Track A stopping-reliability paper**. The paper is a metric-provenance benchmark-style audit for termination reliability — not a global superiority claim over GNM, ViNT, NoMaD, or SaferPath. All five stop-policy methods are validated at per-episode level. The full package is reproducible with one command.

The official local verification path does **not** require Isaac Sim GUI. Isaac Sim replay is optional and environment-dependent.

---

## Validation Status

| Work item | Status |
|---|---|
| Track A stopping paper (metric-provenance scope) | **Validated** |
| Yahboom sim-to-real recording | Blocked — requires valid `episode_001` rosbag2 |
| Track B language grounding | Blocked — requires held-out Track B evaluation |
| Global superiority over GNM, ViNT, NoMaD, SaferPath | Blocked — requires matched external benchmark |

---

## Current Study Focus

This repository contains a **complete validation package for the GNM-VLNVerse Track A stopping-reliability paper**.

The validated paper claim: baseline GNM navigation failure on VLNVerse is not purely a path-following failure — the model enters the goal region more often than it successfully terminates there. This is a stopping-reliability problem. The gap between SR (20.0%) and OSR (46.7%) directly measures it.

The full Track A validation package includes:

- all five stop-policy methods with per-episode provenance (75 rows, 5 methods × 15 episodes);
- exact final distance and minimum distance rows for all 15 validation episodes per method;
- baseline verifier and all-methods verifier, both with expected-value checks;
- bootstrap 95% confidence intervals for SR, OSR, NE, and SR–OSR gap;
- validation split lock (same 15 episodes used for all methods);
- temporal stop-head feature audit confirming no oracle-geometry leakage;
- paper claim-to-evidence map linking every table entry to a source file;
- one-command validation pack;
- ICRA/IEEE-style paper source that compiles to a local 5-page PDF.

---

## Current Validated Baseline Result

Track A validation evidence:

```text
Train trajectories : 238
Validation episodes: 15
Scenes             : kujiale_0092, kujiale_0118, kujiale_0203, kujiale_0271
Success radius     : 3.0 m
Final successes    : 3 / 15
Oracle successes   : 7 / 15
SR                 : 20.0%  (3 / 15 episodes, final distance <= 3.0 m)
OSR                : 46.7%  (7 / 15 episodes ever within 3.0 m)
NE                 : 6.51 m mean final distance to goal
```

These are reproduced baseline metrics, not a final SOTA claim.

**What this means:** The model enters the goal region (OSR 46.7%) more than twice as often as it successfully finishes (SR 20.0%). The failure is not only navigation; it is also termination reliability. The agent reaches the vicinity of the goal but does not stop at the right time.

---

## Track A Validation Package

### One-command pack

Run the full validation in one command:

```bash
bash scripts/gnm/run_tracka_metric_provenance_pack.sh
```

This runs 8 steps: generate all-methods CSV → verify baseline provenance → verify all-methods provenance (bootstrap CIs) → per-scene breakdown → paired comparison + seed stability → robustness summary → update claim ledger → compile paper. All steps must pass.

### Per-episode provenance — all five methods

Every entry in the paper result table has a source row. The 75-row CSV covers all five methods × 15 validation episodes:

```
results/research_audit/tracka_all_methods_per_episode_metric_provenance.csv
```

Generate (from existing source CSVs in `results/bo_reviewer_packet/`):

```bash
python3 scripts/gnm/generate_all_methods_provenance.py
```

Verify all five methods with bootstrap 95% CIs:

```bash
python3 scripts/gnm/verify_tracka_all_methods_metric_provenance.py
```

Expected: all five methods report `PASS` with SR, OSR, and NE within tolerance.

Baseline-only verifier (faster sanity check):

```bash
python3 scripts/gnm/verify_tracka_metric_provenance.py
```

### Validation split lock

All five methods use the same 15 episode IDs:

```
results/research_audit/tracka_validation_split_lock.json
```

### Feature audit — no oracle leakage

The temporal stop head uses only runtime GNM-derived signals (distance trend, waypoint norm, stability window). It does not use true goal geometry at inference time:

```
results/research_audit/stop_policy_feature_audit.md
```

### Paper claim-to-evidence map

Every quantitative claim in the paper links to an evidence file and verifier:

```
results/research_audit/paper_claim_to_evidence_map.md
```

### Robustness evidence (v2.6)

Per-scene breakdown, paired statistical test, and bootstrap seed stability:

```bash
python3 scripts/gnm/compute_tracka_per_scene_breakdown.py
python3 scripts/gnm/compute_tracka_paired_comparison.py
python3 scripts/gnm/compute_tracka_robustness_summary.py
```

Key findings:

- kujiale_0118: 0% SR for all deployable methods (genuinely hard scene)
- kujiale_0271: temporal stop head SR 0% → 67% (largest per-scene gain)
- Paired test (baseline vs temporal, n=15): Wilcoxon T+=95, z=1.99, p≈0.047; temporal reduces NE in 11/15 episodes
- Bootstrap CIs stable across seeds 41–44 (SR CI varies by 0 pp, NE CI by < 0.05 m)
- No additional held-out data beyond the 15 val episodes (train split is contaminated for logistic/temporal methods)

```
results/research_audit/tracka_per_scene_breakdown.csv
results/research_audit/tracka_paired_comparison.md
results/research_audit/tracka_bootstrap_seed_stability.md
results/research_audit/tracka_robustness_summary.md
```

---

## Research Claim Gates

The claim ledger separates validated claims from blocked claims:

```bash
python3 scripts/gnm/check_research_claim_gates.py
```

**Validated claims (gates open):**

- Baseline GNM SR = 20.0%, OSR = 46.7%, NE = 6.51 m on 15 validation episodes
- Per-episode metric provenance exists for all 15 episodes (baseline and all five methods)
- Stopping-reliability gap is real: OSR − SR = 26.7 percentage points
- Temporal neural stop head improves deployable SR from 20.0% to 33.3%
- Temporal stop head uses only runtime GNM signals — no oracle geometry at inference
- All five methods evaluated on the same locked 15-episode validation split
- Every paper table entry maps to a source file and verifier script
- Per-scene breakdown exists for all 5 methods × 4 scenes
- Paired Wilcoxon test confirms temporal improvement direction (T+=95, p≈0.047, n=15)
- Bootstrap CIs are stable across seeds 41–44
- Stopping-gap confirmed at N=253: baseline OSR−SR = 13 pp, SR CI narrows from ±20 pp to ±6 pp

**Blocked claims (gates closed — evidence does not yet exist):**

- valid Yahboom `episode_001` rosbag2 recording
- Yahboom rosbag2 to GNM dataset conversion
- GNM fine-tuning on validated Yahboom data
- FleetSafe-GNM closed-loop physical Yahboom deployment
- completed Track B language-grounding results
- global superiority over GNM, ViNT, NoMaD, or SaferPath

See `results/research_audit/research_claim_validation_ledger.md` for the full ledger.

---

## ICRA Paper

Paper source: `paper/icra_metric_provenance_stopping/main.tex`

This is an ICRA/IEEE-format paper on metric-provenance-based stopping analysis for GNM-VLNVerse Track A. The paper scope is a metric-provenance benchmark-style audit for termination reliability. All quantitative claims in the paper are fully validated at per-episode level.

Local compile (requires `pdflatex`):

```bash
cd paper/icra_metric_provenance_stopping
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

Run `pdflatex` twice so cross-references and citations resolve correctly. Generated PDFs, logs, and auxiliary files are listed in `paper/icra_metric_provenance_stopping/.gitignore` and must not be committed.

---

## Official Baseline Verification Path

For metric provenance and paper validation, use the single pack command:

```bash
bash scripts/gnm/run_tracka_metric_provenance_pack.sh
```

For the full GNM dataset proof path, use the steps below.

### Step 1 — Bootstrap

```bash
bash scripts/gnm/bootstrap_demo_env.sh
source .venv/bin/activate
```

### Step 2 — Link VLNVerse/VLNTube data

```bash
bash scripts/gnm/link_vlntube_data.sh /path/to/vlntube
python3 scripts/gnm/check_demo_ready.py
```

For this workstation example:

```bash
bash scripts/gnm/link_vlntube_data.sh ~/robotics/FleetSafe-VisualNav-Benchmark/datasets/vlntube
```

### Step 3 — Run proof commands

```bash
python3 scripts/gnm/replay_gnm_demo.py --prove-dataset
python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
python3 scripts/gnm/manual_testdrive.py --dry-run
```

### Step 4 — Verify metric provenance and claim gates

```bash
python3 scripts/gnm/verify_tracka_metric_provenance.py
python3 scripts/gnm/check_research_claim_gates.py
```

### Step 5 — Run tests

```bash
python3 -m pytest tests/gnm -q
```

Expected result: all tests pass. Torch-dependent model tests skip only if PyTorch is absent.

---

## What This Repository Implements

* VLNVerse/Kujiale dataset validation.
* GNM visual-goal input evidence using current RGB and goal RGB.
* Trajectory pose validation from `traj_data.pkl`.
* Local waypoint/action label derivation.
* Non-GUI live dashboard export.
* Manual test-drive dry-run, replay, and GNM-format conversion.
* Reviewer-facing implementation proof documents.
* Local tests for the GNM/VLNVerse baseline pipeline.
* Per-episode metric provenance for all five Track A stop-policy methods (75 rows).
* Bootstrap 95% confidence intervals for SR, OSR, NE, and SR–OSR gap.
* Validation split lock confirming all methods use the same 15 episodes.
* Stop-policy feature audit confirming temporal stop head has no oracle-geometry leakage.
* Paper claim-to-evidence map linking every table entry to a source file and verifier.
* Research claim ledger separating validated from blocked claims.
* One-command validation pack.
* ICRA paper source validated at per-episode level for all five methods.

---

## What This Repository Does Not Claim

* It does not claim a universal new benchmark. This is a metric-provenance benchmark-style audit for termination reliability.
* It does not claim completed ROS 2 closed-loop robot control.
* It does not claim the full FleetSafe safety stack.
* It does not claim global superiority over GNM, ViNT, NoMaD, or SaferPath.
* It does not claim completed Track B language-grounding results.
* It does not commit large VLNVerse datasets, generated dashboard image sequences, checkpoints, or RGB frame dumps.
* It does not treat Isaac Sim GUI replay as the required proof path.

---

## Isaac Sim Runtime Note

The fresh-clone proof path does not require Isaac Sim.

Isaac Sim visual replay is optional and environment-dependent. It additionally requires:

* a working local Isaac Sim Python environment;
* `datasets/vlntube/envs` linked to the VLNVerse USD scene assets;
* a stable local GPU, driver, and GUI runtime.

For Isaac visual replay:

```bash
conda activate isaac

LIVE_DASHBOARD=1 AUTO_PLAY=1 SHOW_GNM_PANELS=1 MAX_STEPS=100000 \
python scripts/gnm/replay_gnm_demo.py
```

For interactive manual driving:

```bash
conda activate isaac
MODE=custom_office python scripts/gnm/manual_testdrive.py
```

Avoid plain `conda run` for interactive Isaac/manual-drive commands because it may not preserve terminal input.

If Isaac Sim GUI is unstable locally, use the non-GUI dashboard export as the reliable evidence path:

```bash
python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
```

---

## Key Review Documents

**Track A paper validation:**

```text
results/research_audit/tracka_all_methods_per_episode_metric_provenance.csv
results/research_audit/tracka_all_methods_metric_provenance_report.md
results/research_audit/tracka_per_episode_metric_provenance.csv
results/research_audit/tracka_metric_provenance_report.md
results/research_audit/tracka_validation_split_lock.json
results/research_audit/stop_policy_feature_audit.md
results/research_audit/paper_claim_to_evidence_map.md
results/research_audit/research_claim_validation_ledger.md
paper/icra_metric_provenance_stopping/main.tex
```

**GNM baseline implementation evidence:**

```text
results/bo_reviewer_packet/BO_RUI_FULL_IMPLEMENTATION_PROOF.md
results/bo_reviewer_packet/BO_RUI_SOURCE_CODE_INDEX.md
results/bo_reviewer_packet/00_tracka_reviewer_summary.md
results/bo_reviewer_packet/23_paper_results_table.md
results/bo_reviewer_packet/03_success_rate_breakdown.md
```

---

## Track A Stop-Policy Improvement Result

Beyond the reproduced GNM-VLNVerse baseline, this repository includes a staged stop-policy study showing that Track A performance is limited by stopping reliability.

Baseline Track A reaches:

* SR: 20.0%
* OSR: 46.7%
* NE: 6.51 m

This gap shows that the agent often enters the goal region but fails to stop successfully.

The strongest deployable held-out method in this repository is a temporal neural stop head trained on Track A train trajectories and evaluated on held-out Track A validation episodes. It uses only runtime GNM signals and derived temporal features.

| Method                     | Protocol        |        SR |   OSR |   NE (m) |
| -------------------------- | --------------- | --------: | ----: | -------: |
| GNM baseline               | val             |     20.0% | 46.7% |     6.51 |
| Hand-tuned waypoint gate   | val             |     26.7% | 26.7% |     5.34 |
| Logistic stop head         | train → val     |     20.0% | 46.7% |     6.51 |
| Temporal neural stop head  | train → val     | **33.3%** | 33.3% | **4.47** |
| Geometry-aware oracle stop | diagnostic only |     46.7% | 46.7% |     3.79 |

The temporal neural stop head improves deployable held-out SR from 20.0% to 33.3%, outperforming scalar thresholds, hand-tuned waypoint stopping, and logistic calibration while using only runtime GNM signals.

Key files:

* `results/bo_reviewer_packet/00_tracka_reviewer_summary.md`
* `results/bo_reviewer_packet/23_paper_results_table.md`
* `results/bo_reviewer_packet/temporal_stop_head/22_temporal_stop_head.md`
* `scripts/gnm/train_temporal_stop_head.py`

---

## v2.0 — FleetSafe-GNM Isaac ROS 2 Implementation Manual and Data Collection Pipeline

v2.0 turns the research-evidence repository into an implementation-ready FleetSafe-GNM Isaac ROS 2 workspace plan.

### Architecture

```
Isaac camera / robot sensors
          ↓
     ROS 2 topics
          ↓
  GNM reads camera / goal
          ↓
   GNM produces raw command  →  /gnm/cmd_vel_raw
          ↓
   FleetSafe CBF-QP shield
          ↓
   safe command             →  /fleetsafe/cmd_vel_safe  →  /cmd_vel
          ↓
     Isaac robot moves
```

### v2.0 files

| File | Purpose |
|---|---|
| `docs/FLEETSAFE_GNM_IMPLEMENTATION_MANUAL.md` | Full implementation manual with architecture, beginner Q&A, and phased plan |
| `configs/gnm_fleetsafe_isaac.yaml` | Unified config for environment, robot, topics, data, GNM, FleetSafe, evaluation |
| `scripts/gnm/check_ros2_topics.sh` | Checks required ROS 2 topics; exits 0 in CI without ROS 2 |
| `scripts/gnm/collect_isaac_rosbag_episode.sh` | Records a rosbag2 episode from Isaac Sim; supports --dry-run |
| `scripts/gnm/convert_rosbag_to_gnm_dataset.py` | Converts rosbag episode to GNM training format; supports --dry-run |
| `scripts/gnm/train_gnm_from_collected_data.sh` | Fine-tuning wrapper (head tuning or LoRA); supports --dry-run |
| `scripts/gnm/eval_gnm_vs_fleetsafe.sh` | Evaluates GNM-only vs GNM+FleetSafe; writes CSV and Markdown; supports --dry-run |
| `launch/gnm_fleetsafe_isaac.launch.py` | ROS 2 launch skeleton for Isaac bridge, GNM, FleetSafe, and logger nodes |

### Dry-run verification

```bash
bash scripts/gnm/check_ros2_topics.sh
bash scripts/gnm/collect_isaac_rosbag_episode.sh demo_episode --dry-run
python3 scripts/gnm/convert_rosbag_to_gnm_dataset.py \
  --rosbag-root datasets/gnm_fleetsafe_rosbags \
  --output-root datasets/gnm_fleetsafe_converted \
  --episode-name demo_episode --dry-run
bash scripts/gnm/train_gnm_from_collected_data.sh --dry-run
bash scripts/gnm/eval_gnm_vs_fleetsafe.sh --dry-run
```

All dry-run commands complete without ROS 2 or Isaac Sim installed.

---

## v2.1 — Live Isaac ROS 2 Bridge Verification Layer

v2.1 adds the first live Isaac ROS 2 verification layer on top of the v2.0 dry-run pipeline.

**Scope:** bridge availability check, required topic verification, Yahboom M3 Pro placeholder.  
**Not in scope:** live GNM inference, FleetSafe shielding, Yahboom hardware integration.

### Required live topics

| Topic | Source |
|---|---|
| `/camera/image_raw` | Isaac Sim camera sensor |
| `/odom` | Isaac Sim differential drive |
| `/tf` | Isaac Sim TF tree |
| `/scan` | Isaac Sim lidar sensor |
| `/cmd_vel` | Robot drive subscriber |

### v2.1 files

| File | Purpose |
|---|---|
| `docs/v2.1_isaac_ros2_bridge_checklist.md` | Full checklist including Isaac Sim startup instructions |
| `docs/yahboom_control_scene_checklist.md` | Yahboom M3 Pro placeholder control scene checklist |
| `scripts/gnm/check_isaac_bridge.sh` | Checks Isaac ROS 2 bridge availability; exits 0 in CI |
| `scripts/gnm/verify_live_topics.py` | Verifies the five required live topics; exits 0 in CI |
| `tests/gnm/test_isaac_ros2_bridge_v21.py` | Test suite for v2.1 (no Isaac Sim required) |

### Dry-run verification

```bash
bash scripts/gnm/check_isaac_bridge.sh
python3 scripts/gnm/verify_live_topics.py
```

Both commands exit 0 without ROS 2 or Isaac Sim installed.

### Live verification (requires Isaac Sim running with ROS 2 Bridge enabled)

```bash
bash scripts/gnm/check_isaac_bridge.sh --strict
python3 scripts/gnm/verify_live_topics.py --strict
```

See `docs/v2.1_isaac_ros2_bridge_checklist.md` for Isaac Sim startup instructions.

---

## v2.2 — Yahboom M3 Pro Sim-to-Real Topic Bridge Plan (Prerequisite)

v2.2 retires Nova Carter as the pipeline robot (smoke test only) and establishes
the Yahboom ROSMASTER M3 Pro as the single target for all simulation and
real-world work.

**Scope:** asset inventory, canonical topic contract, camera alias documentation,
mecanum wheel kinematics, URDF/USD/Xacro status. No live episode yet.

### Asset status

| Asset | Location | Status |
|---|---|---|
| Canonical URDF | `assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf` | Present |
| Xacro (Gazebo + real) | `ros2_ws/src/fleet_safe_description/urdf/yahboom_m3pro.urdf.xacro` | Present |
| USD reference stage | `assets/robots/yahboom_m3_pro/yahboom_m3pro_reference.usda` | Present |
| Robot config | `configs/robots/yahboom_m3_pro.yaml` | Present |
| STL/DAE meshes | — | None — primitive geometry only |
| Isaac Sim live stage | — | Pending — load URDF → USD in Isaac Sim |

### Camera topic alias

The Yahboom hardware driver publishes `/camera/color/image_raw`.
The GNM pipeline requires `/camera/image_raw`.
A topic remap is required before recording training rosbags on the real robot.

### v2.2 files

| File | Purpose |
|---|---|
| `docs/v2.2_yahboom_m3pro_sim_to_real_plan.md` | Full sim-to-real plan with concept glossary |
| `scripts/gnm/discover_yahboom_assets.py` | Inventories all Yahboom URDF, Xacro, USD, config, launch assets |
| `scripts/gnm/check_yahboom_topic_contract.py` | Defines and checks the canonical sim-to-real topic contract |
| `tests/gnm/test_yahboom_sim_to_real_v22.py` | CI-safe test suite for v2.2 |

### Dry-run verification

```bash
python3 scripts/gnm/discover_yahboom_assets.py
python3 scripts/gnm/check_yahboom_topic_contract.py
```

Both commands exit 0 without Isaac Sim or the physical robot connected.

---

## Optional Stable Isaac Live Trajectory Demo

For a stable live Isaac Sim visual demo, use the lightweight trajectory renderer. This uses real VLNVerse/GNM trajectory data but renders it in a simplified Isaac stage instead of loading the full photorealistic VLNVerse USD scene.

```bash
conda activate isaac
python scripts/gnm/isaac_live_trajectory_demo.py
```

Expected behaviour:

- Isaac Sim opens.
- A simple scene appears with floor, walls, obstacles, start marker, goal marker, and trajectory breadcrumbs.
- A robot cube moves along a real recorded VLNVerse trajectory.
- The window remains open until interrupted with `Ctrl+C`.

The full photorealistic VLNVerse USD scene replay remains optional and environment-dependent.

---

## Run the EDA / Training Notebook in Colab

[![Open FleetSafe-GNM EDA Notebook in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/FAVL-AI/gnm-vlnverse-baseline/blob/main/notebooks/fleetsafe_gnm_yahboom_eda_training_safety_notebook.ipynb)

This notebook can run in Colab for data profiling, EDA, trajectory plots, stop-head training demonstrations, and FleetSafe safety-filter visualisation. Isaac Sim, live ROS 2 topics, and rosbag2 recording still require the local Ubuntu/Isaac/Yahboom environment.

---

## Citation

```bibtex
@misc{vanlaarhoven2026gnmvlnverse,
  title  = {GNM-VLNVerse Baseline: Reproducible Visual Goal Navigation Pipeline},
  author = {Van Laarhoven, F.},
  year   = {2026},
  note   = {Research implementation repository},
  url    = {https://github.com/FAVL-AI/gnm-vlnverse-baseline}
}
```

---

## Author

F. Van Laarhoven
Newcastle University
