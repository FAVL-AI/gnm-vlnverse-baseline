# Fairness — No Oracle Leakage

This document explains what information is and is not available to the
General Navigation Model during training and evaluation.

---

## Allowed during training

| Information | Source | Used for |
|-------------|--------|---------|
| Red-Green-Blue camera frames | Isaac Sim rendering | Observation input |
| Robot floor-plane position (x, y) | Isaac Sim physics state | Action/waypoint label |
| Robot heading yaw angle | Isaac Sim physics state | Action label (robot-frame rotation) |
| Expert trajectory | VLNVerse navigation episode | Defines the training path |
| Goal image (final frame) | Camera at goal position | Goal-conditioned input |

---

## Allowed during Track A evaluation

| Information | Source |
|-------------|--------|
| Current RGB camera observation | Camera frames from trajectory |
| Goal image (final frame) | Known at episode start (visual goal) |
| Model predictions: `dist_pred`, `action_pred` | Forward pass through GNM |

---

## NOT available as hidden oracle during evaluation

| Information | Why excluded |
|-------------|-------------|
| Ground-truth shortest path | Would trivially solve navigation |
| Final goal coordinate (x, y) | Only the goal *image* is given, not the map position |
| Scene graph at test time | Not available in Track A or B at inference |
| Oracle trajectory during rollout | Model only gets its own predictions, not ground-truth steps |
| Collision map | Not used in Track A offline evaluation |
| Ground-truth distance-to-goal | Model must predict this (dist head output) |

---

## How the stopping criterion works

The model stops when its **own predicted distance-to-goal** (`dist_pred`) drops
below 0.15 (the stop threshold).

This is NOT the ground-truth distance. The model can only observe:
1. Its current camera image
2. The goal image
3. Its predicted distance

This means the model must learn to recognise when it is near the goal from
visual similarity alone — the ground-truth goal position is not provided.

This explains why SR (20%) < OSR (46.7%): in 4 episodes the robot passed
within 3 m of the goal but `dist_pred` never dropped below 0.15, so the model
kept moving and overshot.

---

## What the labels mean

Labels are generated **automatically** from the simulator.
No human annotation is performed.

The expert trajectory defines what the robot *should* do.
The model is trained to imitate this expert by predicting waypoints toward
each sampled goal frame.

The evaluation is offline (no live Isaac Sim) and reproducible:
```bash
python3 scripts/gnm/06_evaluate.py --ckpt checkpoints/gnm_base/best.pt
```

---

## Summary

```text
TRAINING uses:  RGB frames + robot pose labels (auto-generated from simulator)
EVALUATION uses: RGB observation + goal image only
ORACLE info:     NOT provided during evaluation
STOPPING:        model's own dist_pred < 0.15 (no ground-truth signal)
```
