# GNM-VLNVerse Baseline

Repository: https://github.com/FAVL-AI/gnm-vlnverse-baseline

This repository provides a reproducible baseline proof path for evaluating a General Navigation Model (GNM) style visual-goal navigation pipeline on VLNVerse/Kujiale indoor navigation data.

The official local verification path does **not** require Isaac Sim GUI. Isaac Sim replay is optional and environment-dependent.

---

## Official Baseline Verification Path

Use these command groups to verify the baseline locally.

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

### Step 4 — Run tests

```bash
python3 -m pytest tests/gnm -q
```

Expected result: all tests pass. Torch-dependent model tests skip only if PyTorch is absent.

---

## Current Validated Baseline Result

Track A validation evidence:

```text
Train trajectories : 238
Validation episodes: 15
Scenes             : kujiale_0092, kujiale_0118, kujiale_0203, kujiale_0271
SR                 : 20.0%  (3 / 15 episodes, final distance <= 3.0 m)
OSR                : 46.7%  (7 / 15 episodes ever within 3.0 m)
NE                 : 6.51 m mean final distance to goal
```

These are reproduced baseline metrics, not a final SOTA claim.

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

---

## What This Repository Does Not Claim

* It does not claim completed ROS2 closed-loop robot control.
* It does not claim the full FleetSafe safety stack.
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

```text
results/bo_reviewer_packet/BO_RUI_FULL_IMPLEMENTATION_PROOF.md
results/bo_reviewer_packet/BO_RUI_SOURCE_CODE_INDEX.md
results/bo_reviewer_packet/DEMO_SCRIPT_BO_RUI.md
results/bo_reviewer_packet/13_live_gnm_input_dashboard.md
results/bo_reviewer_packet/14_manual_testdrive_walkthrough.md
results/bo_reviewer_packet/03_success_rate_breakdown.md
```

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
