# Per-Episode Evaluation Breakdown — Track A

Checkpoint : `gnm_base_stop_0.50.pt`
Split      : val  (15 episodes)
Success threshold : 3.0 m

---

## Summary

| Metric | Value | Calculation |
|--------|-------|-------------|
| **Success Rate (SR)** | **20.0%** | 3 / 15 episodes where final distance ≤ 3.0 m |
| **Oracle SR (OSR)** | **20.0%** | 3 / 15 episodes where robot was EVER within 3.0 m of goal |
| **Mean Navigation Error** | **6.01 m** | Average final distance to goal across all episodes |

**SR = 20.0% means 3 out of 15 val episodes succeeded** (robot stopped within 3.0 m of the goal).

---

## Per-episode table

| # | Episode ID | Scene | Init dist | Final dist | Min dist | TL | Steps | Success | Oracle |
|---|-----------|-------|-----------|-----------|---------|---|-------|---------|--------|
| 1 | `kujiale_0092_kujiale_0092_91_1` | kujiale_0092 | 8.08 m | 7.91 m | 7.91 m | 0.20 m | 2 | no | no |
| 2 | `kujiale_0092_kujiale_0092_9_2` | kujiale_0092 | 8.93 m | 8.69 m | 8.69 m | 0.25 m | 2 | no | no |
| 3 | `kujiale_0118_kujiale_0118_25_3` | kujiale_0118 | 3.63 m | 3.58 m | 3.58 m | 0.19 m | 2 | no | no |
| 4 | `kujiale_0118_kujiale_0118_31_0` | kujiale_0118 | 7.92 m | 7.73 m | 7.73 m | 0.20 m | 2 | no | no |
| 5 | `kujiale_0118_kujiale_0118_40_4` | kujiale_0118 | 10.31 m | 10.25 m | 10.25 m | 0.23 m | 2 | no | no |
| 6 | `kujiale_0203_kujiale_0203_15_3` | kujiale_0203 | 5.56 m | 5.50 m | 5.50 m | 0.13 m | 2 | no | no |
| 7 | `kujiale_0203_kujiale_0203_16_3` | kujiale_0203 | 5.17 m | 5.27 m | 5.17 m | 0.11 m | 2 | no | no |
| 8 | `kujiale_0203_kujiale_0203_22_4` | kujiale_0203 | 5.93 m | 5.89 m | 5.89 m | 0.16 m | 2 | no | no |
| 9 | `kujiale_0203_kujiale_0203_25_0` | kujiale_0203 | 2.76 m | 2.63 m | 2.63 m | 0.16 m | 2 | **YES** | YES |
| 10 | `kujiale_0203_kujiale_0203_32_2` | kujiale_0203 | 2.45 m | 2.33 m | 2.33 m | 0.18 m | 2 | **YES** | YES |
| 11 | `kujiale_0203_kujiale_0203_43_1` | kujiale_0203 | 6.39 m | 6.25 m | 6.25 m | 0.14 m | 2 | no | no |
| 12 | `kujiale_0203_kujiale_0203_49_3` | kujiale_0203 | 6.54 m | 6.39 m | 6.39 m | 0.15 m | 2 | no | no |
| 13 | `kujiale_0271_kujiale_0271_15_1` | kujiale_0271 | 6.71 m | 6.49 m | 6.49 m | 0.23 m | 2 | no | no |
| 14 | `kujiale_0271_kujiale_0271_24_4` | kujiale_0271 | 9.12 m | 8.96 m | 8.96 m | 0.22 m | 2 | no | no |
| 15 | `kujiale_0271_kujiale_0271_7_3` | kujiale_0271 | 2.18 m | 2.27 m | 2.18 m | 0.14 m | 2 | **YES** | YES |

---

## Explanation of each metric

**Success (SR)**  
An episode counts as a success if the robot's **final position** is within **3.0 m** of the goal position.  
Column: `Final dist ≤ 3.0 m` → Success = YES.

**Oracle Success (OSR)**  
An episode counts as an oracle success if the robot was **ever within 3.0 m** of the goal at any step.  
This is an upper-bound metric — it counts episodes where the robot passed through the goal zone but kept walking.

**Navigation Error (NE)**  
The Euclidean distance from the robot's **final** position to the goal.  
Lower is better.  SR = 20% means some episodes have large NE even though OSR = 46.7% shows the robot did pass near the goal.

**Why is SR only 20%?**  
The General Navigation Model's stop criterion is `dist_pred < stop_threshold`.  
When `dist_pred` (predicted distance-to-goal) drops below 0.15, the robot stops.  
In episodes where SR ≠ OSR, the robot was near the goal at some point but the distance head predicted it was still far, so it kept walking and overshot.

---

## Reproduction

```bash
python3 scripts/gnm/explain_eval_success_rate.py \
    --checkpoint /tmp/gnm_base_stop_0.50.pt \
    --output results/eval_episode_breakdown_tracka.md
```
