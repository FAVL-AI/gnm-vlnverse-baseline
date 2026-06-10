# Track Definitions — FleetSafe Visual Navigation Benchmark

## Track A — Visual Goal Navigation (CURRENT)

**Status: Complete baseline result established.**

The robot is given:
- A context stack of recent Red-Green-Blue (RGB) camera frames.
- A visual goal image (the final frame of the reference trajectory).

The robot must navigate to the location shown in the goal image.
No language instruction is used.

**Model**: General Navigation Model (GNM) — a goal-conditioned visual policy.
The model predicts local waypoints or velocity actions from the image pair.

**Official result**:

| Metric | Value |
|--------|-------|
| Success Rate (SR) | 20.0% |
| Oracle Success Rate (OSR) | 46.7% |
| Navigation Error (NE) | 6.51 m |
| SPL | 20.0% |
| Trajectory Length (TL) | 8.08 m |
| nDTW | 0.449 |
| CLS | 0.658 |

Checkpoint: `checkpoints/gnm_base/best.pt`  
Epoch 11/50, val_loss = 0.296.

---

## Track B — Language-Instruction Navigation (PLANNED)

**Status: Not yet started. Awaiting stable Track A baseline.**

The robot is given:
- A natural-language instruction, e.g.  
  *"Walk down the hallway and stop in front of the large windows."*
- Its current camera image.

The planned pipeline:
1. A language-to-visual-subgoal model converts the instruction into a
   sequence of visual subgoal images.
2. The General Navigation Model navigates to each subgoal in order.

**Why Track B has not started yet**:
- Track A needed a stable visual navigation baseline first.
- The current dataset contains camera frames and robot position labels —
  it is NOT yet a verified language-instruction dataset.
- Language grounding errors and visual navigation errors must be separated.
  Mixing them before the visual baseline is stable makes debugging very hard.

---

## Why we are not training a Large Language Model (LLM) yet

The current dataset (`datasets/vlntube/`) contains:
- Red-Green-Blue camera frames
- Robot position arrays
- Robot yaw arrays
- Expert trajectory waypoints

This is sufficient for General Navigation Model training (Track A).
It is NOT sufficient for Large Language Model fine-tuning because:

1. There is no verified alignment between the language instructions
   (`instruction.txt`) and the visual subgoal frames in the trajectory.
2. Large Language Model training requires instruction-following pairs,
   not trajectory labels.
3. Fine-tuning a Large Language Model on unverified data risks learning
   spurious correlations before the navigation task is understood.

---

## Why we are not using Low-Rank Adaptation (LoRA) yet

Low-Rank Adaptation (LoRA) is a parameter-efficient fine-tuning method
for adapting a large pretrained model to a new task.

We have not used Low-Rank Adaptation yet because:

1. No pretrained large language-vision model has been identified as
   the right foundation for Track B.
2. Low-Rank Adaptation is most useful after the supervision target
   (language instruction → visual subgoal) is clearly defined and verified.
3. Applying Low-Rank Adaptation to the General Navigation Model is
   non-standard — GNM is a small convolutional model, not a transformer.
   Fine-tuning it fully (Track C) is more appropriate.

Low-Rank Adaptation is planned for Track C: adapting a pretrained
vision-language model to the specific scene distribution of this benchmark.

---

## Why we are not using Automatic Mixed Precision (AMP) yet

Automatic Mixed Precision (AMP) with BF16 was tested in ablation A1 and A1b.
It increased the training/validation loss gap (130× vs 15× for baseline)
without improving navigation metrics.
The MobileNet baseline does not benefit from AMP at this dataset scale.

If Automatic Mixed Precision is added later, it should be combined with
Exponential Moving Average (EMA) at decay=0.999 (see ablation A1d),
which is the stable EMA setting for 50-epoch training.

---

## Exponential Moving Average (EMA) note

Exponential Moving Average is used to smooth model weights during training.
Key finding from ablation series:

- EMA decay = 0.9999: half-life = 6,931 optimizer steps.
  50 epochs = 4,850 steps < 1 half-life → EMA weights never converge.
  Do not use at 50-epoch scale.

- EMA decay = 0.999: half-life = 693 steps.
  50 epochs = 7 half-lives → fully converged by epoch 7.
  Safe to use. A1d confirmed this matches the baseline exactly.

---

## Summary

| Track | Task | Model | Status |
|-------|------|-------|--------|
| A | Visual-goal navigation | General Navigation Model | **Done — SR=20%** |
| B | Language→subgoal→navigation | LLM + GNM | Planned |
| C | Domain-adapted navigation | LoRA-tuned VLM + GNM | Future |
