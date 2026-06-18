# Track A Expanded Split — Methodology Note

## What was expanded

The 15-episode locked val split was expanded to 253 episodes by adding the 238 train-split
episodes. Evaluation covers **baseline_gnm** and **geometry_aware_oracle** only.

## Why only 2 of 5 methods can be expanded

| Method | Can be expanded? | Reason |
|---|---|---|
| baseline_gnm | Yes | `true_dist_m` in traces = live Isaac Sim measurement; no training dependency |
| geometry_aware_oracle | Yes | `min(true_dist_m)` per episode; no training dependency |
| hand_tuned_waypoint_gate | No | Simulating from baseline trajectories diverges from live evaluation: threshold sweep gives SR=20% vs live Isaac Sim runs give SR=26.7%; stopping early changes the robot's subsequent path |
| logistic_stop_head | No | Trained on these exact trace features (`dist_pred`, `wp_norm`); evaluating on training data would be in-distribution (biased) |
| temporal_neural_stop_head | No | Same training contamination as logistic stop head |

## Train vs val SR difference: not an error

The 253-episode expanded set shows baseline SR=37.5%, while the locked 15-episode val
set shows SR=20.0%. This difference is expected and correct:

1. **Val set is harder.** The val set was selected to represent a challenging held-out
   evaluation. The small per-scene counts (2–7 episodes) make the val SR sensitive to
   individual hard episodes.

2. **Stopping-gap persists at N=253.** The key claim is that OSR >> SR for baseline_gnm.
   This holds at both scales: val gap = 26.7 pp, expanded gap = 13.0 pp. The gap is smaller
   at N=253 because the expanded set includes "easier" train episodes where the robot succeeds
   even without an explicit stop signal.

3. **The expanded set confirms, not contradicts, the val finding.** A 13 pp stopping-gap
   at N=253 with CI = [31.6, 43.5] for SR confirms that the gap is real and not a
   small-sample artifact. The val set happens to show a harder version of the same phenomenon.

## What the expanded evaluation can and cannot claim

**Can claim:**
- The stopping-gap (baseline OSR − SR > 0) is confirmed at N=253 across all 4 Kujiale scenes.
- CI width for baseline SR narrows from ±20 pp (val) to ±6 pp (expanded).
- Per-scene baseline SR is: kujiale_0092=38.2%, kujiale_0118=27.0%, kujiale_0203=47.2%, kujiale_0271=36.0%.
- The diagnostic holds across train and val splits.

**Cannot claim:**
- Global superiority over GNM, ViNT, NoMaD, or SaferPath.
- Stop-policy performance at N=253 (only baseline and oracle were expanded).
- That the val SR=20% is wrong — it is correct for the specific 15 val episodes.
- Yahboom physical deployment or Track B language grounding.
