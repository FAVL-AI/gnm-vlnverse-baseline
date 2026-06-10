# Reviewer Response — Bo's Questions (2026-06-05)

---

## Q1: How do you use the General Navigation Model in Vision-Language Navigation Verse?

The General Navigation Model (GNM) is the local visual navigation policy.

Vision-Language Navigation Verse (VLNVerse) and NVIDIA Isaac Sim provide the
indoor apartment scene, the expert trajectory, and Red-Green-Blue (RGB) camera images.
During training, the General Navigation Model receives a stack of recent RGB frames
and a visual goal image, then predicts local waypoints or velocity actions.

This is **Track A — visual-goal navigation**.
The language instructions stored in `instruction.txt` are not used yet.
Language-to-subgoal navigation is planned as Track B.

Evidence:
- Training script: `scripts/gnm/05_train.py`
- Evaluation script: `scripts/gnm/06_evaluate.py`
- Isaac Sim replay demo: `scripts/gnm/replay_gnm_demo.py`
  shows `/World/GNM_Replay` with START, GOAL, path markers, and ROBOT_MARKER.
- Track definitions: `results/track_definitions.md`

---

## Q2: How do you label the 238 trajectories, and what labels do you record?

Labels are generated **automatically** from NVIDIA Isaac Sim.
No manual annotation is performed.

The robot follows a predefined expert trajectory from the VLNVerse episode.
At each step, Isaac Sim records:

| Label | Where stored | Shape |
|-------|-------------|-------|
| Red-Green-Blue camera frame | `N.jpg` in trajectory folder | image |
| Floor-plane position (x, y) | `traj_data.pkl` → `position` | (N, 2) float32 |
| Robot heading yaw | `traj_data.pkl` → `yaw` | (N,) float32 |
| Start position | `traj_data.pkl` `position[0]` | derived |
| Goal position | `episode_info.json` → `goal_pos` | [x, y] metres |
| Scene identifier | `episode_info.json` → `scan` | string |
| Episode identifier | `episode_info.json` → `episode_id` | string |
| Language instruction | `instruction.txt` | text (Track B) |

Action targets and distance-to-goal targets are **derived at training time**
by `GNMDataset` — they are not stored in the trajectory files.

Evidence:
- `results/dataset_manifest.md` — full label description
- `scripts/gnm/inspect_trajectory_labels.py` — run to print any trajectory's labels

---

## Q3: Did you let the robot walk a specific trajectory?

**Yes.**
The robot follows predefined expert trajectories from the VLNVerse episodes.
It does not explore randomly.

During data generation, NVIDIA Isaac Sim replays the expert path.
The recording script (`scripts/gnm/04_generate_data.py`) captures the robot's
camera frames, position, and yaw at each step.

The Isaac Sim replay demo (`scripts/gnm/replay_gnm_demo.py`) shows this visually:
the trajectory overlaid as a chain of cyan USD prims forms a coherent path
through the apartment from the green START prim to the red GOAL prim.

Evidence:
- `results/figures/gnm_replay_caption.md` — caption for Isaac Sim screenshot
- Run `conda run -n isaac python scripts/gnm/replay_gnm_demo.py` to see it live.

---

## Q4: Can you share the dataset?

Yes.
A small sample package (one trajectory per scene) can be created with:

```bash
python3 scripts/gnm/package_dataset_sample.py \
    --data-root datasets/vlntube \
    --output artifacts/gnm_vlnverse_sample_dataset.tar.gz \
    --per-scene 1
```

The tarball contains RGB frames, `traj_data.pkl`, `episode_info.json`,
`instruction.txt`, and a README explaining each field.

The full dataset (~12,659 frames across 238 trajectories) can be shared
separately. Image frames make it too large for a direct tarball.
The full dataset can be regenerated from scratch with:

```bash
conda run -n isaac python scripts/gnm/04_generate_data.py
```

The packaging script is at `scripts/gnm/package_dataset_sample.py`.

---

## Q5: Can you send the link to the four scenes?

| Scene ID | Source |
|----------|--------|
| `kujiale_0092` | VLNVerse / Hugging Face |
| `kujiale_0118` | VLNVerse / Hugging Face |
| `kujiale_0203` | VLNVerse / Hugging Face |
| `kujiale_0271` | VLNVerse / Hugging Face |

- VLNVerse project page: https://sihaoevery.github.io/vlnverse/
- Scene assets (Hugging Face): https://huggingface.co/datasets/Eyz/VLNVerse_scene

Only these four scenes were downloaded. The full VLNVerse scene dataset is large.
Scene USD files are not committed to this repository (gitignored).

Evidence: `results/scene_manifest.md`

---

## Q6: How do you divide the training and evaluation dataset?

**Standard split (current reported result):**

| Split | Trajectories | Frames | Percentage |
|-------|-------------|--------|-----------|
| train | 238 | 12,659 | 94.1% |
| val   | 15  | 832    | 5.9%  |

All four scenes appear in both splits.
No trajectory instance appears in both splits.
The split follows the prebuilt VLNVerse trajectory holdout.

**Scene-level holdout split (stricter, run pending):**

| Role | Scenes | Trajectories |
|------|--------|-------------|
| Train | kujiale_0092, kujiale_0203, kujiale_0118 | 191 |
| Scene holdout test | kujiale_0271 | 47 |

Config: `configs/gnm/splits/scene_holdout_kujiale_0271.yaml`

Verification:
```bash
python3 scripts/gnm/check_scene_holdout_split.py \
    --data-root datasets/vlntube \
    --split-config configs/gnm/splits/scene_holdout_kujiale_0271.yaml
```

---

## Q7: Can training and testing be in different scenes?

**Yes — this is now implemented as the scene-level holdout split.**

The config `configs/gnm/splits/scene_holdout_kujiale_0271.yaml` holds out
`kujiale_0271` entirely from training.
The model must navigate in a new apartment it never saw during training.

The split config and data-count verification (`check_scene_holdout_split.py`) are
complete and committed. The full training run on this split is pending.
Once trained, the result will be reported as the "scene-level generalisation test."

---

## Q8: Why not train a Large Language Model (LLM) or use Low-Rank Adaptation (LoRA) yet?

**Short answer**: the current dataset is visual trajectory data, not a verified
language-instruction dataset.

**Detailed reason**:

1. Track A is visual-goal navigation — no language model is needed.
2. The current `datasets/vlntube/` data contains RGB frames, position, and yaw.
   This is sufficient for the General Navigation Model but NOT for
   Large Language Model fine-tuning.
3. Language-to-subgoal supervision (Track B) must be defined and verified
   before any Large Language Model or Low-Rank Adaptation training.
4. Mixing language grounding errors with visual navigation errors before the
   visual baseline is stable makes debugging very hard.

**Low-Rank Adaptation (LoRA)**:
LoRA is most useful for fine-tuning a large pretrained vision-language model.
No such pretrained foundation model has been selected yet for Track B or C.
LoRA is planned for Track C after Track B supervision is verified.

Evidence: `results/track_definitions.md`

---

## Q9: What is the current official result?

**Track A — General Navigation Model MobileNet baseline:**

| SR | OSR | NE | SPL | TL | nDTW | CLS |
|----|-----|----|----|-----|------|-----|
| 20.0% | 46.7% | 6.51 m | 20.0% | 8.08 m | 0.449 | 0.658 |

Checkpoint: `checkpoints/gnm_base/best.pt`
Full ablation record: `results/ablations.md`

---

## Q10: Where is the code?

GitHub: https://github.com/FAVL-AI/FleetSafe-VisualNav-Benchmark/tree/gnm-vlnverse-baseline

The working tree is clean. Generated checkpoints and datasets are gitignored
(they are regenerable from the configuration files and scripts).
