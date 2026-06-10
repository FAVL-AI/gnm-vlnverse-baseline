# VLN Evaluation Plan

## Metrics

### Navigation performance

| Metric | Description | Range |
|---|---|---|
| SR | Success Rate: goal reached within tolerance | 0–1 |
| SPL | Success weighted by Path Length | 0–1 |
| nDTW | normalised Dynamic Time Warping (path similarity) | 0–1 |
| OSR | Oracle Success Rate (nearest point on any trajectory) | 0–1 |

### Language grounding accuracy

| Metric | Description |
|---|---|
| Goal grounding accuracy | % instructions where label matches target |
| Wrong-goal rate | % where robot reaches wrong landmark |
| Clarification rate | % instructions that trigger clarification_needed |
| ASR error rate | % voice transcripts with word error rate > 20% |

### Safety

| Metric | Description |
|---|---|
| Collision count | Events with distance < 0.10 m |
| Near-miss count | Events with distance < 0.45 m |
| CBF intervention rate | Fraction of steps where CBF overrides u_nom |
| Certificate violation count | Steps with h_min < -h_tol |
| Min observed distance | Minimum LiDAR range across full episode |
| Emergency stop count | CBF-QP infeasibility events |

### System

| Metric | Description |
|---|---|
| Inference latency (mean, p95) | Backbone forward pass (ms) |
| CBF solve time (mean, p95) | QP solve time (ms) |
| End-to-end latency | Instruction → /cmd_vel (ms) |
| Transcript failure count | ASR result with confidence < threshold |

---

## Ablations

### Backbone ablation (language + safety fixed)

| Condition | Backbone | Safety |
|---|---|---|
| GNM only | GNM | FleetSafe CBF |
| ViNT only | ViNT | FleetSafe CBF |
| NoMaD only | NoMaD | FleetSafe CBF |
| Backbone router | Auto | FleetSafe CBF |

### Safety ablation (backbone + language fixed)

| Condition | Safety filter |
|---|---|
| No safety | None (u_nom → /cmd_vel directly) |
| CBF-QP | FleetSafe (formal barrier) |

### Instruction modality ablation

| Condition | Input |
|---|---|
| Text instruction | Typed natural language |
| Voice-transcribed | Voice → Whisper/ASR → text |
| Image goal | Selected camera frame |
| Multimodal | Voice + image |

### Sensing ablation

| Condition | Sensors |
|---|---|
| RGB only | Camera |
| RGB-D + LiDAR | Camera + depth + scan |

---

## Environments

| Environment | Type | Scenes |
|---|---|---|
| Yahboom M3Pro (real) | Physical | Hospital corridor, office |
| Gazebo | Sim | Hospital, warehouse, cafe |
| Isaac Sim | Sim (photorealistic) | Procedural hospital |

---

## Minimum for paper claims

| Claim | Minimum evidence |
|---|---|
| Navigation performance (SR, SPL) | ≥ 50 episodes per (model × scene × instruction) |
| Safety (collision, CBF rate) | ≥ 50 episodes |
| Real robot | ≥ 10 recorded sessions with certificates |
| Voice input | ≥ 10 voice-guided episodes with transcripts |

---

## What NOT to claim

- Ranked on VLN-CE / R2R / REVERIE leaderboards until evaluated on those exact splits.
- "Zero collision" unless backed by ≥ 50 episodes per condition.
- Real-time ASR accuracy without Whisper or similar benchmarked.
- Photorealistic environment without confirmed USD in Isaac viewport.
