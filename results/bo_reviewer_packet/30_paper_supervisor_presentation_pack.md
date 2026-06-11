# Paper and Supervisor Presentation Pack — GNM-VLNVerse Track A

## One-minute thesis

The GNM-VLNVerse Track A baseline is not only limited by path following. It is strongly limited by stopping reliability.

Baseline GNM reaches the goal region in 46.7% of validation episodes, but only finishes successfully in 20.0%. This SR/OSR gap shows that the model often gets near the goal but does not stop correctly.

A temporal neural stop head trained on Track A train trajectories and evaluated on held-out validation improves deployable SR from 20.0% to 33.3% using only runtime GNM-derived signals.

## Key result table

| Method | SR | OSR | NE |
|---|---:|---:|---:|
| Baseline GNM | 20.0% | 46.7% | 6.51 m |
| Hand-tuned waypoint gate | 26.7% | 26.7% | 5.34 m |
| Logistic stop head | 20.0% | 46.7% | 6.51 m |
| Temporal neural stop head | 33.3% | 33.3% | 4.47 m |
| Geometry-aware oracle upper bound | 46.7% | 46.7% | 3.79 m |

## Main claim

Short-term temporal runtime history improves deployable stopping beyond scalar thresholds, hand-tuned waypoint stopping, and logistic calibration.

The key methodological point is that the temporal stop head uses runtime GNM-derived signals, not oracle geometry, at inference time.

## Dataset evidence

The current Track A study uses:

- 238 training trajectories
- 15 held-out validation trajectories
- 4 local Kujiale/VLNVerse scenes

Scene-level split:

| Scene ID | Train trajectories | Validation trajectories |
|---|---:|---:|
| kujiale_0092 | 66 | 2 |
| kujiale_0118 | 60 | 3 |
| kujiale_0203 | 65 | 7 |
| kujiale_0271 | 47 | 3 |

## Evidence map

| Evidence | File |
|---|---|
| Public release matrix | `README.md` |
| Reviewer summary | `results/bo_reviewer_packet/00_tracka_reviewer_summary.md` |
| Paper table | `results/bo_reviewer_packet/23_paper_results_table.md` |
| Isaac live demo note | `results/bo_reviewer_packet/26_stable_isaac_live_trajectory_demo.md` |
| Supervisor evidence pack | `results/bo_reviewer_packet/27_supervisor_evidence_pack.md` |
| Dataset and scene manifest | `results/bo_reviewer_packet/28_dataset_scene_manifest.md` |
| Reproducibility pack | `results/bo_reviewer_packet/29_reproducibility_and_one_command_eval.md` |

## Five-minute supervisor flow

1. Open the README and show the research release matrix.
2. Open the dataset manifest and show 238 train trajectories, 15 validation trajectories, and four Kujiale scenes.
3. Show the baseline result: SR 20.0%, OSR 46.7%, NE 6.51 m.
4. Explain the stopping failure: OSR is much higher than SR, so the robot often reaches the goal region but does not stop successfully.
5. Show the temporal stop-head result: SR improves to 33.3% and NE improves to 4.47 m.
6. Run the reproducibility command to show the evidence chain passes from the current repo state.
7. Optionally run the Isaac live trajectory demo to show real VLNVerse/GNM trajectory replay.

## Commands to show

Reproducibility pack:

```bash
bash scripts/gnm/run_reproducibility_pack.sh
```

Optional Isaac live demo:

```bash
conda activate isaac
python scripts/gnm/isaac_live_trajectory_demo.py
```

Dataset manifest preview:

```bash
sed -n '1,90p' results/bo_reviewer_packet/28_dataset_scene_manifest.md
```

Paper result table preview:

```bash
sed -n '1,160p' results/bo_reviewer_packet/23_paper_results_table.md
```

## Paper-ready contribution statement

We identify stopping reliability as a key failure mode in GNM-VLNVerse Track A. The baseline achieves 20.0% final SR but 46.7% OSR, indicating that the agent often enters the goal region without stopping successfully. A temporal neural stop head trained on runtime GNM-derived features improves held-out deployable SR to 33.3%, showing that short-term temporal evidence improves stopping beyond scalar thresholding and logistic calibration.

## Supervisor-ready closing line

The main result is not just that we reproduced a baseline. We diagnosed why it fails, quantified the stopping gap, improved the deployable result with temporal runtime features, built a stable Isaac demo, and added a one-command reproducibility pack.
