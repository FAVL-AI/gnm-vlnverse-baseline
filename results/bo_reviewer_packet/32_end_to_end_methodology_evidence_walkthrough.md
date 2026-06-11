# End-to-End Methodology and Evidence Walkthrough — GNM-VLNVerse Track A

## 1. What this study proves

This document explains the complete GNM-VLNVerse Track A work as an audit trail. It is written so that an A-level student can understand the idea, while a supervisor or reviewer can still check the code, commands, evidence files, and limitations.

The core finding is:

> The baseline General Navigation Model can often reach the goal region, but it does not reliably stop there.

That is a very different failure from simply being lost. The robot often gets near the right place, but the final stop decision is weak. This is why the work studies stop reliability.

The evidence is the gap between:

- **Success Rate (SR):** did the robot finish correctly inside the goal region?
- **Oracle Success Rate (OSR):** did the robot enter the goal region at any point, even if it failed to stop?
- **Navigation Error (NE):** how far the robot ended from the goal.

Baseline result:

| Method | SR | OSR | NE |
|---|---:|---:|---:|
| Baseline GNM | 20.0% | 46.7% | 6.51 m |

The OSR is much higher than SR. That is the forensic clue: the robot often reaches the goal area but fails to stop successfully.

The best deployable improvement is the temporal neural stop head:

| Method | SR | OSR | NE |
|---|---:|---:|---:|
| Temporal neural stop head | 33.3% | 33.3% | 4.47 m |

This improves deployable success from 20.0% to 33.3% and reduces Navigation Error from 6.51 m to 4.47 m.

---

## 2. Key terms explained

| Term | Expanded meaning | Plain-English meaning |
|---|---|---|
| GNM | General Navigation Model | The navigation brain used in this project. It predicts how the robot should move. |
| VLN | Vision-Language Navigation | A robot navigation task using visual observations and goal/task context. |
| VLNVerse | Vision-Language Navigation benchmark environment | The benchmark/source environment used for indoor navigation evidence. |
| VLNTube | VLNVerse-style local dataset layout | The local folder structure used to organise trajectories and scene assets. |
| Trajectory | Recorded movement path | A sequence showing where the robot moved over time. |
| Waypoint | Short-term movement target | The next small target point the robot should move toward. |
| SR | Success Rate | Whether the robot stops correctly at the final goal. |
| OSR | Oracle Success Rate | Whether the robot ever entered the goal area during the route. |
| NE | Navigation Error | Final distance from the goal; lower is better. |
| TL | Trajectory Length | How long the route was. |
| Isaac Sim | NVIDIA Isaac Simulator | A 3D robotics simulator used to replay real trajectory data. |
| USD | Universal Scene Description | A 3D scene format used by Isaac Sim. |
| Ablation | Controlled removal/change | A test where one part is removed or changed to prove what matters. |
| Oracle | Privileged diagnostic information | Information allowed for analysis, but not allowed in deployable runtime decisions. |

---

## 3. High-level architecture

```text
+--------------------------------------------------+
| Local VLNVerse / VLNTube dataset                 |
| datasets/vlntube/train                           |
| datasets/vlntube/val                             |
| datasets/vlntube/envs                            |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
| Dataset audit / manifest                         |
| scripts/gnm/generate_dataset_scene_manifest.py   |
| proves train count, validation count, scenes     |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
| GNM evaluation and rollout                       |
| GNM-derived runtime predictions                  |
| predicted distance + waypoint/action evidence    |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
| Metrics                                          |
| Success Rate, Oracle Success Rate,               |
| Navigation Error, Trajectory Length              |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
| Stop-policy investigation                        |
| threshold, waypoint gate, logistic head,         |
| temporal neural stop head, oracle diagnostic     |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
| Evidence packet                                  |
| markdown, csv, json                              |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
| One-command reproducibility                      |
| scripts/gnm/run_reproducibility_pack.sh          |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
| Isaac Sim live trajectory replay                 |
| scripts/gnm/isaac_live_trajectory_demo.py        |
+--------------------------------------------------+
```

The architecture separates the numerical evaluation from the 3D visual demonstration. This matters because the full photorealistic USD scene path in Isaac Sim can be heavy and unstable, while the research evidence must remain reproducible.

---

## 4. Environment setup

The repository root is:

```bash
cd ~/robotics/gnm-vlnverse-baseline
```

The standard evidence, tests, and reproducibility path uses the base environment:

```bash
conda activate base
python3 -m pytest tests/gnm -q
bash scripts/gnm/run_reproducibility_pack.sh
```

The Isaac Sim visual replay uses the Isaac environment:

```bash
conda activate isaac
python scripts/gnm/isaac_live_trajectory_demo.py
```

Why two environments?

- The base environment is lighter and suitable for tests, data audits, metrics, and evidence generation.
- The Isaac environment contains the heavier robotics simulation stack.
- Keeping them separate makes failures easier to isolate.

If the Python tests pass but Isaac has a graphics problem, that does not invalidate the algorithmic evidence. It only affects the visual simulation path.

---

## 5. Dataset collected and audited

The local Track A study uses:

- 238 training trajectories
- 15 held-out validation trajectories
- 4 local Kujiale/VLNVerse scenes

Scene split:

| Scene ID | Training trajectories | Validation trajectories |
|---|---:|---:|
| `kujiale_0092` | 66 | 2 |
| `kujiale_0118` | 60 | 3 |
| `kujiale_0203` | 65 | 7 |
| `kujiale_0271` | 47 | 3 |

Important dataset paths:

```text
datasets/vlntube/train
datasets/vlntube/val
datasets/vlntube/envs
```

Example trajectory:

```text
datasets/vlntube/train/kujiale_0092_kujiale_0092_0_3/traj_data.pkl
```

A trajectory is a recorded route. In the audited files, trajectory records include:

- `position`: the robot location over time
- `yaw`: the robot heading direction over time

Code evidence:

```text
scripts/gnm/generate_dataset_scene_manifest.py
```

Command to regenerate the dataset audit:

```bash
python scripts/gnm/generate_dataset_scene_manifest.py
```

Generated evidence files:

```text
results/bo_reviewer_packet/28_dataset_scene_manifest.md
results/bo_reviewer_packet/28_dataset_scene_manifest.csv
results/bo_reviewer_packet/28_dataset_scene_manifest.json
```

Reviewer check command:

```bash
sed -n '1,120p' results/bo_reviewer_packet/28_dataset_scene_manifest.md
```

---

## 6. How GNM and VLNVerse were integrated

The integration connects three things:

1. local VLNVerse/VLNTube trajectory data;
2. GNM-derived navigation signals;
3. stop-policy and metric evaluation.

The flow is:

```text
VLNVerse/VLNTube trajectory
        |
        v
GNM evaluation / prediction utilities
        |
        v
runtime signals
(predicted distance, waypoint/action)
        |
        v
rollout and stop decision
        |
        v
SR / OSR / NE evaluation
```

Key code evidence:

```text
scripts/gnm/ablate_deployable_stop_policy.py
scripts/gnm/learn_stop_head.py
scripts/gnm/train_temporal_stop_head.py
gnm_vlnverse/evaluation/metrics.py
```

Reviewer check commands:

```bash
sed -n '1,180p' scripts/gnm/ablate_deployable_stop_policy.py
sed -n '1,180p' scripts/gnm/train_temporal_stop_head.py
sed -n '1,160p' gnm_vlnverse/evaluation/metrics.py
```

What this proves:

- the project does not only contain result tables;
- it contains code paths for data loading, metric calculation, stop-policy analysis, and reproducibility checks.

---

## 7. Training methodology for the temporal neural stop head

The temporal neural stop head is the deployable improvement.

The problem with a single-frame stop decision is that one instant can be misleading. The robot might briefly look close to the goal but still be moving past it. A temporal model looks at short-term history.

Plain-English idea:

> Instead of asking only “am I close now?”, the temporal head asks “over the last few steps, does the movement pattern show that I should stop?”

Training data:

- training split: 238 trajectories
- validation split: 15 trajectories
- input: runtime GNM-derived signals
- target: whether stopping is correct

Runtime-derived features:

- predicted distance
- waypoint norm
- rolling distance mean
- rolling waypoint mean
- distance trend
- waypoint trend

These features are important because they do not require oracle geometry at inference time.

Expected training/evaluation evidence:

```text
results/bo_reviewer_packet/temporal_stop_head/
results/bo_reviewer_packet/temporal_stop_feature_ablation/
```

Code evidence:

```text
scripts/gnm/train_temporal_stop_head.py
```

Reviewer check command:

```bash
sed -n '1,220p' scripts/gnm/train_temporal_stop_head.py
```

Why sequence length and stability matter:

- A sequence length gives the model short-term memory.
- A rolling window smooths noisy signals.
- A stable stop requirement avoids stopping because of a single noisy step.
- A threshold sweep tests different stop-confidence levels.

Evidence files to inspect:

```bash
sed -n '1,180p' results/bo_reviewer_packet/temporal_stop_head/22_temporal_stop_head.md
sed -n '1,180p' results/bo_reviewer_packet/temporal_stop_feature_ablation/25_temporal_stop_feature_ablation.md
```

---

## 8. Evaluation metrics and conclusions

The main metrics are:

| Metric | What it asks | Why it matters |
|---|---|---|
| SR | Did the robot finish correctly? | Measures final task success. |
| OSR | Did the robot ever enter the goal region? | Detects whether the path reached the goal area. |
| NE | How far from the goal did it finish? | Measures final distance error. |

The forensic rule is:

```text
If OSR is much higher than SR,
the robot often reaches the goal area but fails to stop correctly.
```

Baseline:

```text
SR  = 20.0%
OSR = 46.7%
NE  = 6.51 m
```

Conclusion:

The baseline is not merely failing to move toward the goal. It often gets near the goal but fails the final stopping behaviour.

Code evidence:

```text
gnm_vlnverse/evaluation/metrics.py
```

Evidence files:

```text
results/bo_reviewer_packet/23_paper_results_table.md
results/bo_reviewer_packet/00_tracka_reviewer_summary.md
```

Reviewer check commands:

```bash
sed -n '1,160p' results/bo_reviewer_packet/23_paper_results_table.md
sed -n '1,160p' results/bo_reviewer_packet/00_tracka_reviewer_summary.md
```

---

## 9. What failed, what was tried, and what worked

| Attempt | Result | Meaning |
|---|---|---|
| Baseline GNM | SR 20.0%, OSR 46.7%, NE 6.51 m | Reaches goal region more often than it stops correctly. |
| Scalar threshold | weaker than needed | One number cannot capture the stop pattern. |
| Hand-tuned waypoint gate | SR 26.7%, NE 5.34 m | Helps, but can stop too early or too bluntly. |
| Logistic stop head | SR 20.0%, OSR 46.7%, NE 6.51 m | Simple calibration does not generalise. |
| Temporal neural stop head | SR 33.3%, NE 4.47 m | Best deployable result. |
| Geometry-aware oracle | SR 46.7%, NE 3.79 m | Diagnostic upper bound, not deployable. |

Why the failures matter:

The weaker approaches show the investigation was not cherry-picked. The project tested simple options first, measured their limits, and used the evidence to justify temporal modelling.

Code evidence:

```text
scripts/gnm/learn_stop_head.py
scripts/gnm/train_temporal_stop_head.py
```

Reviewer check commands:

```bash
sed -n '1,200p' scripts/gnm/learn_stop_head.py
sed -n '1,220p' scripts/gnm/train_temporal_stop_head.py
```

---

## 10. Ablation evidence

Ablation means controlled testing: remove or change one feature set to prove what matters.

Feature-set ablation:

| Feature set | SR | OSR | NE |
|---|---:|---:|---:|
| Full temporal | 33.3% | 33.3% | 4.47 m |
| Distance plus waypoint | 26.7% | 26.7% | 4.81 m |
| Distance only | 20.0% | 46.7% | 6.38 m |
| Waypoint only | 20.0% | 40.0% | 6.04 m |

Conclusion:

The full temporal feature set is strongest. Distance alone and waypoint alone do not explain the improvement.

Evidence file:

```text
results/bo_reviewer_packet/temporal_stop_feature_ablation/25_temporal_stop_feature_ablation.md
```

Reviewer check command:

```bash
sed -n '1,200p' results/bo_reviewer_packet/temporal_stop_feature_ablation/25_temporal_stop_feature_ablation.md
```

---

## 11. Isaac Sim setup, windows, and what to inspect

Isaac Sim is used to provide live visual proof that real trajectory data can be replayed in simulation.

Run:

```bash
conda activate isaac
python scripts/gnm/isaac_live_trajectory_demo.py
```

Expected terminal output:

```text
GNM LIVE ISAAC TRAJECTORY
Trajectory: datasets/vlntube/train/kujiale_0092_kujiale_0092_0_3/traj_data.pkl
Frames: 48
Starting live replay...
Replay complete. Holding Isaac window open.
```

What opens:

- Isaac Sim graphical window
- main Viewport pane

What to look for in the Viewport:

- floor plane
- boundary walls
- simple obstacles
- start marker
- goal marker
- trajectory breadcrumbs
- moving robot marker

Useful Isaac panes:

| Pane | What it does | How it helps |
|---|---|---|
| Viewport | Shows the 3D world | Watch the robot marker replay the path. |
| Stage | Shows scene objects | Confirm floor, obstacles, markers, breadcrumbs. |
| Property panel | Shows selected object details | Inspect position, scale, material, transform. |
| Terminal/Console | Shows runtime logs | Confirm loaded trajectory, frame count, replay completion. |

Where to see the conclusion in Isaac:

- The moving marker shows real trajectory replay.
- The start and goal markers show the route context.
- Breadcrumbs show the path shape.
- The terminal confirms which real `traj_data.pkl` file was loaded.

Code evidence:

```text
scripts/gnm/isaac_live_trajectory_demo.py
```

Reviewer check command:

```bash
sed -n '1,260p' scripts/gnm/isaac_live_trajectory_demo.py
```

Why the stable Isaac demo exists:

The full photorealistic VLNVerse USD scenes are heavier and may trigger native Isaac/Kit instability during long GUI sessions. The stable replay stage keeps the supervisor-facing demonstration reliable while preserving the full photorealistic scene path as a separate runtime debugging task.

---

## 12. Challenge log and mitigations

| Challenge | Evidence | Mitigation |
|---|---|---|
| Baseline stop failure | SR 20.0%, OSR 46.7% | Stop-policy study. |
| Threshold weakness | threshold sweeps | temporal modelling. |
| Waypoint gate limitation | SR 26.7% | compare against neural temporal head. |
| Logistic head limitation | SR stayed 20.0% | use temporal sequence model. |
| Small validation split | 15 validation trajectories | explicit manifest and claim boundary. |
| Full USD instability | Isaac/Kit GUI instability risk | stable live trajectory replay. |
| Reproducibility risk | static evidence could drift | one-command reproducibility pack. |

This is the forensic method: observe, test, compare, mitigate, and document.

---

## 13. Reproducibility command

Run:

```bash
bash scripts/gnm/run_reproducibility_pack.sh
```

It verifies:

- manifest generator compiles
- manifest regenerates
- GNM tests pass
- evidence files exist
- README matrix exists
- expected dataset counts are present
- scene IDs are present
- Isaac demo script exists

Expected result:

```text
[SUCCESS] Reproducibility pack completed
131 passed
```

Code evidence:

```text
scripts/gnm/run_reproducibility_pack.sh
```

Reviewer check command:

```bash
sed -n '1,220p' scripts/gnm/run_reproducibility_pack.sh
```

---

## 14. Evidence map

| Evidence | File |
|---|---|
| Public release matrix | `README.md` |
| Reviewer summary | `results/bo_reviewer_packet/00_tracka_reviewer_summary.md` |
| Paper result table | `results/bo_reviewer_packet/23_paper_results_table.md` |
| Stable Isaac demo note | `results/bo_reviewer_packet/26_stable_isaac_live_trajectory_demo.md` |
| Supervisor evidence pack | `results/bo_reviewer_packet/27_supervisor_evidence_pack.md` |
| Dataset manifest | `results/bo_reviewer_packet/28_dataset_scene_manifest.md` |
| Reproducibility pack | `results/bo_reviewer_packet/29_reproducibility_and_one_command_eval.md` |
| Presentation pack | `results/bo_reviewer_packet/30_paper_supervisor_presentation_pack.md` |
| Five-minute demo script | `results/bo_reviewer_packet/31_five_min_supervisor_demo_script.md` |
| This walkthrough | `results/bo_reviewer_packet/32_end_to_end_methodology_evidence_walkthrough.md` |

---

## 15. Claim boundary

The correct claim is:

> We provide a reproducible GNM-VLNVerse Track A stop-reliability study that diagnoses the SR/OSR stopping gap, evaluates multiple stopping strategies, improves deployable validation success with temporal runtime features, and packages the full evidence chain for audit.

Do not claim this solves every visual navigation problem.

Do claim this sets a transparent, reproducible benchmark-style evidence trail for this Track A setup.

---

## 16. Final paper-ready claim

This work identifies stop reliability as a key failure mode in GNM-VLNVerse Track A. The reproduced baseline achieves 20.0% final Success Rate but 46.7% Oracle Success Rate, showing that the policy often enters the goal region without terminating successfully. We evaluate scalar thresholding, waypoint gating, logistic calibration, temporal neural stopping, and oracle diagnostic stopping. A temporal neural stop head using runtime GNM-derived features improves held-out deployable Success Rate to 33.3% and reduces Navigation Error to 4.47 m. The study is supported by dataset and scene manifests, ablation evidence, stable Isaac live replay, and one-command reproducibility.
