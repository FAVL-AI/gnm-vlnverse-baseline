# Reproducibility Checklist — FleetSafe VisualNav Benchmark

Work through this checklist top-to-bottom before any submission.
Each gate must be explicitly verified — not assumed.

---

## Gate 0: Environment setup

- [ ] **Conda environment created** with Python 3.10 or 3.11
  ```bash
  conda create -n fleetsafe-vnav python=3.10 -y
  conda activate fleetsafe-vnav
  ```

- [ ] **PyTorch installed** (≥ 2.0, CPU or CUDA)
  ```bash
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
  ```

- [ ] **Upstream visualnav-transformer cloned**
  ```bash
  bash scripts/visualnav/setup_visualnav.sh
  ```

- [ ] **`vint_train` importable**
  ```bash
  python -c "import vint_train; print('ok')"
  ```

- [ ] **diffusers installed** (required by NoMaD)
  ```bash
  pip install 'diffusers==0.11.1' 'huggingface_hub==0.12.0'
  ```

- [ ] **warmup_scheduler installed** (required by ViNT checkpoint)
  ```bash
  pip install warmup_scheduler
  ```

- [ ] **diffusion_policy installed** (required by NoMaD)
  ```bash
  git clone https://github.com/real-stanford/diffusion_policy.git
  pip install -e diffusion_policy/
  ```

- [ ] **PYTHONPATH configured**
  ```bash
  source scripts/visualnav/activate_visualnav_env.sh
  ```

---

## Gate 1: Checkpoints

- [ ] **GNM checkpoint exists and is correct size**
  ```
  third_party/visualnav-transformer/model_weights/gnm/gnm.pth
  Expected: ~100 MB
  ```

- [ ] **ViNT checkpoint exists and is correct size**
  ```
  third_party/visualnav-transformer/model_weights/vint/vint.pth
  Expected: ~411 MB
  ```

- [ ] **NoMaD checkpoint exists and is correct size**
  ```
  third_party/visualnav-transformer/model_weights/nomad/nomad.pth
  Expected: ~73 MB
  ```

- [ ] **Checkpoints validated by validator script**
  ```bash
  python scripts/visualnav/check_visualnav_checkpoints.py
  ```
  All three models must produce one action from synthetic input.

---

## Gate 2: Model inference

- [ ] **GNM inference gate passes** (validate_gates.py gate 2)
- [ ] **ViNT inference passes** (check_visualnav_checkpoints.py)
- [ ] **NoMaD inference passes** (check_visualnav_checkpoints.py)
- [ ] **Inference latencies logged** (baseline for paper table)
- [ ] **Output shapes correct**:
  - GNM: waypoints (5, 2), goal_dist scalar
  - ViNT: waypoints (5, 2), goal_dist scalar
  - NoMaD: waypoints (8, 2)

---

## Gate 3: Camera/observation pipeline

- [ ] **IsaacCameraObsAdapter produces correct shape**
  ```bash
  python -m fleet_safe_vla.integrations.visualnav_transformer.validate_gates
  # Gate 3 must pass
  ```

- [ ] **Context queue fills correctly** (context_size + 1 frames)
- [ ] **Image normalization applied** (ImageNet mean/std)
- [ ] **Image resized to model-specific size** (GNM/ViNT: 85×64, NoMaD: 96×96)

---

## Gate 4: Simulation setup

- [ ] **M3Pro MJCF exists**
  ```
  fleet_safe_vla/robots/yahboom/m3pro/mjcf/yahboom_m3pro.xml
  ```

- [ ] **MuJoCo nav environment importable**
  ```bash
  python -c "from fleet_safe_vla.envs.mujoco.yahboom.nav_env import YahboomNavEnv"
  ```

- [ ] **Isaac scenes check passes** (when Isaac Lab is available)
  ```bash
  python scripts/visualnav/check_isaac_scenes.py
  ```

---

## Gate 5: FleetSafe safety layer

- [ ] **FleetSafeWrapper initialises without error**
- [ ] **CBF-QP filter produces valid cmd_vel** (within velocity limits)
- [ ] **Intervention logging works** (safety_events.jsonl written)
- [ ] **E-STOP fires correctly** at estop_dist_m threshold
  ```bash
  python -m fleet_safe_vla.integrations.visualnav_transformer.validate_gates
  # Gate 5 must pass
  ```

---

## Gate 6: Output pipeline

- [ ] **episode.json** written for each episode
- [ ] **trajectory.csv** written with step-by-step positions
- [ ] **actions.csv** written with raw + safe cmd_vel
- [ ] **safety_events.jsonl** written (may be empty for open-field episodes)
- [ ] **metrics.json** written with all EpisodeMetrics fields
- [ ] **aggregate_metrics.json** written with mean/std over all episodes
- [ ] **HTML comparison report** generated
- [ ] **CSV comparison** generated
- [ ] Validate with end-to-end smoke:
  ```bash
  bash scripts/visualnav/run_e2e_smoke.sh
  ```

---

## Gate 7: Statistical validity

- [ ] **Seeds 0–49 used** (not a subset)
- [ ] **Baseline and FleetSafe use identical seeds** (verify from metadata.yaml)
- [ ] **No seeds excluded post-hoc** (failures included)
- [ ] **Mock backend results NOT included** in any claim
- [ ] **Bootstrap CIs computed** (n_bootstrap ≥ 2000)
- [ ] **Paired Wilcoxon test run** for each primary metric
- [ ] **Effect sizes (Cohen's d) computed**
- [ ] **Bonferroni correction applied** across 4 scenes
- [ ] Run statistical analysis:
  ```bash
  python -m fleet_safe_vla.benchmarks.visualnav_stats  # (analysis entrypoint TBD)
  ```

---

## Gate 8: Reproducibility package

- [ ] **Environment frozen**
  ```bash
  pip freeze > requirements_frozen.txt
  ```

- [ ] **Checkpoint hashes recorded** in `configs/visualnav/models.yaml`
- [ ] **Run logs archived** (DVC / release asset / S3) with SHA256
- [ ] **metadata.yaml from each run committed** or archived alongside logs
- [ ] **Full test suite passes** with no failures
  ```bash
  pytest tests/ -v
  ```

- [ ] **`git log --oneline` is clean** (no debug/WIP commits)
- [ ] **Generated artifacts NOT in git** (verify: `git ls-files benchmarks/visualnav/results/` → empty)

---

## Gate 9: Claim validation

Before writing any quantitative sentence in the paper:

- [ ] The number comes from a `--backend mujoco` run (NOT mock).
- [ ] The number is averaged over ≥ 50 seeds.
- [ ] A 95% bootstrap CI is computed and reported alongside the number.
- [ ] The paired test is significant (p < 0.05, Bonferroni-corrected) if claiming a difference.
- [ ] The claim is scoped to simulation (not real-world) unless M3Pro hardware runs exist.
- [ ] The CLAIMS_AND_LIMITATIONS.md section is updated to reflect the new claim.

---

## Gate 10: Real-robot validation (sim-to-real)

*(Required before any sim-to-real transfer claim.)*

- [ ] **ROS2 bridge operational** on M3Pro
  ```bash
  ros2 run fleet_safe_yahboom_control vnt_controller --model gnm
  ```

- [ ] **At least 10 real episodes per (model, scene)** collected on physical M3Pro
- [ ] **Sim and real metrics compared** (Spearman ρ of SPL ranking)
- [ ] **Video evidence archived** (one episode per condition minimum)
- [ ] **Collision count reported from real runs** (not inferred from sim)
