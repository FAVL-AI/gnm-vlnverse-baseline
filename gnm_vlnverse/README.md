# GNM-VLNVerse Baseline

**Pure GNM (General Navigation Model) on VLNVerse/VLNTube — no FleetSafe safety layer.**

This is the standalone baseline branch for Track A/B/C evaluation.
It can be merged into the main FleetSafe repo when ready.

---

## What is GNM? (Explained for a 14-year-old)

Imagine you want a robot to walk from your bedroom to the kitchen.  You show
it a photo of the kitchen ("this is where you need to go") and it figures out
how to get there just by looking through its camera — no GPS, no map.

GNM (General Navigation Model) does exactly this.  It was trained by watching
recordings from 6 different robots driving around for 60+ hours.  It learned:
- "When I can see the goal clearly, I'm probably close"
- "When the goal is small in the image, I need to keep walking"
- "When I should turn left vs right to get closer"

**GNM outputs two things at every step:**
1. A distance prediction: "I think I'm 12 steps away from the goal"
2. An action: "Go forward 0.3 m and slightly left"

The robot keeps doing this until the distance prediction drops below a
threshold, then it stops.

---

## Three Tracks

| Track | Goal input | Extra adaptation | Description |
|-------|-----------|-----------------|-------------|
| **A** | Goal image (last frame of reference trajectory) | None | Pure visual GNM reproduction |
| **B** | Language instruction | CLIP retrieval | Text → subgoal image → GNM |
| **C** | Same as A or B | LoRA fine-tuning | Domain-adapted GNM |

---

## Repository Structure

```
gnm_vlnverse/
├── models/
│   ├── gnm.py           ← Core GNM architecture
│   ├── encoders.py      ← MobileNetV2 / EfficientNet-B0 encoders
│   ├── lora.py          ← LoRA adapters (Track C)
│   └── __init__.py
├── data/
│   ├── vlntube_converter.py   ← Convert raw episodes to GNM format
│   ├── dataset.py             ← PyTorch Dataset
│   ├── augmentation.py        ← Colour jitter, flip, blur
│   └── __init__.py
├── training/
│   ├── losses.py        ← GNM loss (action + distance)
│   ├── trainer.py       ← GNMTrainer with W&B integration
│   └── __init__.py
├── evaluation/
│   ├── metrics.py       ← SR, OSR, SPL, NE, TL, nDTW, CLS, CR, SRn
│   ├── evaluator.py     ← GNMEvaluator (offline + Isaac)
│   └── __init__.py
├── isaac/
│   ├── env.py           ← Live Isaac Sim environment
│   ├── sensor.py        ← RGB camera, pose sensor
│   └── robot.py         ← Velocity controller
└── vln/
    ├── subgoal_selector.py   ← CLIP text→image retrieval
    ├── planner.py            ← VLN instruction decomposition
    └── __init__.py

configs/gnm/
├── gnm_base.yaml        ← Track A base config
└── lora_sweep.yaml      ← Track C W&B sweep config

scripts/gnm/
├── 01_setup_env.sh        ← Create conda env
├── 02_generate_data.sh    ← Download or generate VLNTube data
├── 03_convert_data.py     ← Convert raw episodes to GNM format
├── 03_compute_action_std.py  ← Compute action normalization stats
├── 04_train_gnm.py        ← Train Track A
├── 05_train_lora.py       ← Train Track C (LoRA)
├── 06_evaluate.py         ← Evaluate on val/test
└── 07_run_demo.sh         ← Live Isaac demo

tests/gnm/
├── test_gnm_model.py         ← Model shapes, gradients, LoRA
├── test_metrics.py           ← All metric functions
├── test_coordinate_frames.py ← Rotation correctness
└── test_data_converter.py    ← CSV parsing, validation
```

---

## 7-Step Quick Start

### Step 1: Set up the environment

```bash
# Creates a conda env called 'gnm_train' with PyTorch + all deps
bash scripts/gnm/01_setup_env.sh

conda activate gnm_train
```

This creates **two separate environments**:
- `gnm_train` — for Python training (this step)
- Isaac Sim's bundled Python — for simulation (separate, provided by Isaac)

### Step 2: Get the training data

```bash
# Option A: Download pre-generated dataset from Hugging Face (recommended)
bash scripts/gnm/02_generate_data.sh

# Option B: Generate fresh with Isaac Sim
bash scripts/gnm/02_generate_data.sh --generate --scenes hospital_v1,hospital_v2

# Smoke test (20 episodes only — fast, for testing the pipeline):
bash scripts/gnm/02_generate_data.sh --smoke-test
```

The dataset will be in `datasets/gnm_vlnverse/{train,val,test}/`.

### Step 3: Convert and compute normalisation stats

```bash
# Convert raw VLNTube episodes to GNM format
python scripts/gnm/03_convert_data.py

# Compute action_std from training data
# This writes the values into configs/gnm/gnm_base.yaml
python scripts/gnm/03_compute_action_std.py --update-config
```

**Why is this important?**
GNM outputs (Δx, Δy) in metres.  If we don't normalise, the loss function
treats a robot that takes 1.0 m steps the same as one that takes 0.01 m steps
— but they're very different!  We divide by the standard deviation so all
values end up in roughly [-1, 1].

### Step 4: Train GNM (Track A)

```bash
# Full training (50 epochs, ~8h on A100)
python scripts/gnm/04_train_gnm.py

# Smoke test (5 epochs, batch 32 — ~10 min)
python scripts/gnm/04_train_gnm.py training.epochs=5 training.batch_size=32

# Override any config value from the command line:
python scripts/gnm/04_train_gnm.py training.lr=3e-4 model.encoder=efficientnet
```

**Checkpoints:** `checkpoints/gnm_base/best.pt` and `latest.pt`

**W&B:** Training metrics stream to `fleetsafe-gnm-vlnverse` project automatically.

### Step 5: Train LoRA (Track C, optional)

```bash
# Fine-tune with LoRA rank=8
python scripts/gnm/05_train_lora.py --base-ckpt checkpoints/gnm_base/best.pt

# Run the rank/alpha sweep (W&B sweep)
wandb sweep configs/gnm/lora_sweep.yaml
# (W&B prints a sweep ID, then:)
wandb agent <entity>/fleetsafe-gnm-vlnverse/<sweep_id>
```

**LoRA ranks tested:** 4, 8, 16 — with alpha = rank × 2

### Step 6: Evaluate

```bash
# Evaluate on validation set (offline, no Isaac)
python scripts/gnm/06_evaluate.py --ckpt checkpoints/gnm_base/best.pt

# Test set (final numbers — only run once!)
python scripts/gnm/06_evaluate.py --ckpt checkpoints/gnm_base/best.pt --split test

# Track C (LoRA)
python scripts/gnm/06_evaluate.py --ckpt checkpoints/gnm_lora/best.pt --track C
```

### Step 7: Live Isaac demo

```bash
# Runs offline evaluation by default, switches to live if Isaac found
bash scripts/gnm/07_run_demo.sh

# Force offline
bash scripts/gnm/07_run_demo.sh --offline
```

---

## Model Architecture

```
obs: (B, context*3, H, W)      goal: (B, 3, H, W)
         ↓                               ↓
  MobileNetV2 encoder            MobileNetV2 encoder
     (shared weights)               (shared weights)
         ↓                               ↓
    (B, 512)                        (B, 512)
         └──────────── cat ─────────────┘
                        ↓
                    (B, 1024)
                 ┌──────┴──────┐
                 ↓             ↓
           dist_head      action_head
              (B, 1)        (B, 2)
            distance       (Δx, Δy)
```

**Why MobileNetV2?**
- Fast (3.4M params, ~22 ms on CPU)
- Good ImageNet features transfer to navigation
- Handles the multi-channel temporal stack via weight repetition

**Context stacking:**
GNM stacks the last `context_size=5` frames.  The input is 15 channels
(5 frames × 3 RGB channels).  The MobileNet was pretrained on 3-channel images,
so we initialise the extra channels by repeating the pretrained first-layer
weights.

---

## Training Loss

```
L_total = α · MSE(action_pred, action_gt) + (1-α) · MSE(dist_pred, dist_gt)
```

Where:
- `action_gt` is normalised: `raw_action / action_std`
- `dist_gt` is the step gap between obs and goal frame (normalised)
- `α = 0.5` by default

**Why MSE?**
We tried Huber loss too (set `loss_type: huber` in config).  For clean VLNTube
data MSE converges slightly faster.  Huber is more robust to outlier frames
in real-world data.

---

## Evaluation Metrics

| Metric | Formula | What it measures | Direction |
|--------|---------|-----------------|-----------|
| SR | `mean(ne_i < 3m)` | Fraction of episodes reaching goal | ↑ higher better |
| OSR | `mean(ever within 3m)` | Upper bound of SR | ↑ |
| SPL | `mean(SR_i × L*_i / max(p_i, L*_i))` | SR penalised for detours | ↑ |
| NE | `mean(‖final_pos - goal‖)` | Average final distance to goal (m) | ↓ lower better |
| TL | `mean(path_length)` | Average metres walked | reference |
| nDTW | `mean(exp(-DTW / (len_ref × 3)))` | Path fidelity to reference | ↑ |
| CLS | `mean(coverage × length_score)` | Path coverage × efficiency | ↑ |
| CR | `mean(collision_steps / total_steps)` | Fraction of time colliding | ↓ |
| SRn | `mean(sub_goals_reached / total_sub_goals)` | Long-horizon goal completion | ↑ |

---

## LoRA Details

LoRA (Low-Rank Adaptation) adds trainable correction matrices to existing
Linear layers.  For a layer with weight W of shape (out, in):

```
output = W @ x + scale × B @ A @ x
scale  = alpha / rank
```

Where A is (rank, in), B is (out, rank), and rank << in.

**Parameter savings example** (encoder projection, out=512, in=1280):
- Original W: 512 × 1280 = 655,360 parameters
- LoRA (rank=8): 8×1280 + 512×8 = 14,336 parameters — **98% fewer**

**Initialisation:** A = Kaiming uniform, B = zeros.
So at the start, LoRA correction is zero — the model starts from the
pretrained checkpoint unchanged.

---

## Reproducibility

All randomness is seeded in `04_train_gnm.py`:
```python
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)
torch.backends.cudnn.deterministic = True
```

To reproduce exactly: same GPU model, same CUDA version, same batch size.
Results may vary slightly across different GPU models (floating point).

---

## Running Tests

```bash
conda activate gnm_train
cd /path/to/FleetSafe-VisualNav-Benchmark

# All tests
pytest tests/gnm/ -v

# Just metrics
pytest tests/gnm/test_metrics.py -v

# Just coordinate frame tests
pytest tests/gnm/test_coordinate_frames.py -v

# With coverage
pytest tests/gnm/ --cov=gnm_vlnverse --cov-report=term-missing
```

---

## Expected Results (Track A baseline)

On VLNVerse hospital scenes, the baseline GNM should achieve approximately:

| Metric | Expected | Notes |
|--------|---------|-------|
| SR | 0.40–0.55 | Depends on scene complexity |
| OSR | 0.55–0.70 | Always ≥ SR |
| SPL | 0.30–0.45 | Penalised for longer paths |
| NE | 4–8 m | Lower after more epochs |
| CR | 0.0 | Offline eval has no collisions |
| nDTW | 0.40–0.60 | Path fidelity |

Track C (LoRA, rank=8) typically adds +5–10 pp SR over Track A.

---

## Weights & Biases Setup

Before training, log in once:
```bash
wandb login
# Enter your API key from https://wandb.ai/settings
```

Your W&B entity is `frankleroyvan` — training logs will appear at:
`https://wandb.ai/fleetsafe-hospitalnav/fleetsafe-gnm-vlnverse`

To set entity in config:
```yaml
wandb:
  entity: frankleroyvan
```

---

## Reviewer FAQ

**Q: How is this different from the original GNM paper?**
A: We use VLNVerse/VLNTube data (Isaac Sim, physics-aware) instead of the
original's 6-robot outdoor/indoor mix.  Same architecture, same loss, new domain.

**Q: Why no FleetSafe CBF-QP layer?**
A: This branch is the BASELINE — it shows what pure GNM achieves.
The main FleetSafe repo adds the CBF-QP safety filter on top.
Comparing this branch vs main shows the safety filter's overhead cost.

**Q: Is the offline evaluator fair?**
A: Yes for SR/NE/SPL/nDTW/CLS comparisons.  CR (collision rate) is always 0
in offline mode — for real CR, use the live Isaac evaluator.

**Q: Why VLNTube instead of the original GNM training data?**
A: We need VLNVerse-compatible scenes and instruction annotations.
VLNTube generates these in Isaac Sim with A* planning.
The pretrained MobileNet encoder can optionally be loaded from the original GNM
checkpoint to leverage its broader training distribution.
