# Supervisor Evidence Pack — GNM in VLNVerse Track A

This document answers the core supervisor/reviewer questions about how GNM is used in VLNVerse, how the dataset is labelled, how training and validation are split, why the baseline success rate is 20.0%, and how the live Isaac demonstration is validated.

## 1. How GNM is used in VLNVerse

GNM is used as a goal-conditioned visual navigation policy inside the VLNVerse/VLNTube pipeline.

At runtime, GNM receives:

* current robot camera observation
* goal image or goal-conditioned visual target
* recent context frames, depending on the model configuration

GNM outputs local waypoint/action predictions. These predicted actions are then rolled out through the Track A evaluation pipeline to estimate the robot path, final navigation error, success rate, oracle success rate, and path length.

In this repository, GNM is not treated as a language planner. It is used as the local visual navigation backbone. The VLNVerse/VLNTube data provides the scenes, trajectories, visual observations, poses, and goals. GNM predicts the local motion needed to move toward the goal.

The role of the current work is to study a specific failure mode: GNM often enters or passes near the goal region but does not stop reliably. This is why the project separates:

* navigation ability: measured by oracle success rate
* stopping ability: measured by success rate
* final error: measured by navigation error

This separation is important because the baseline result shows that the robot reaches the goal region more often than it stops correctly.

## 2. Dataset used

The current Track A study uses four Kujiale/VLNVerse scenes prepared through the VLNTube-style data layout.

The project uses:

* 238 training trajectories
* 15 validation trajectories
* four Kujiale scenes
* Track A evaluation protocol

The dataset is stored locally under:

```text
datasets/vlntube/train/
datasets/vlntube/val/
datasets/vlntube/envs/
```

The trajectory data is read from files such as:

```text
datasets/vlntube/train/*/traj_data.pkl
```

A stable live Isaac demo also confirms that real trajectory data can be loaded and replayed visually.

## 3. How the 238 trajectories are labelled

The 238 training trajectories are not manually labelled by hand. They are generated/converted from the VLNVerse/VLNTube trajectory format into a GNM-compatible trajectory representation.

Each trajectory contains the information needed for goal-conditioned visual navigation and evaluation.

The recorded information includes:

* RGB observation frames
* robot position sequence
* robot yaw/orientation sequence
* goal index or goal pose
* local action or waypoint targets
* trajectory metadata
* train/validation split membership

For stop-head experiments, additional derived labels are created from trajectory geometry:

* predicted distance signal from GNM
* waypoint/action norm
* rolling distance mean
* rolling waypoint mean
* distance trend
* waypoint trend
* true distance to goal during rollout
* binary stop label, where stop is positive if the rollout position is within the success radius

Ground-truth geometry is used only for generating training labels and final evaluation metrics. It is not used inside the runtime stop decision.

## 4. What labels are recorded

The project records or derives the following labels/signals.

### Navigation/evaluation labels

* final navigation error
* success within the success radius
* oracle success along the path
* path length
* stop fired or not
* stop step
* final distance to goal

### Runtime GNM-derived signals

* `dist_pred`
* `wp_norm`
* `dist_mean`
* `wp_mean`
* `dist_trend`
* `wp_trend`

### Stop-head labels

* `label_stop`
* `true_dist_m`
* positive stop labels for supervised stop-head training

The important methodological point is that the stop head uses only GNM-derived runtime features during inference. Ground-truth geometry is reserved for supervision and reporting.

## 5. Training and validation split

The current study uses a fixed Track A train/validation split:

* training: 238 trajectories
* validation: 15 trajectories

This is not a random train/test split created after evaluation. The validation trajectories are held out from the training procedure and are used to evaluate the baseline and all stop-policy variants.

The held-out validation set is the basis for the reported Track A numbers:

* baseline GNM
* threshold sweep
* geometry-aware oracle diagnostic
* deployable stop-policy ablation
* logistic stop head
* temporal neural stop head
* temporal stop-head sequence/stability ablation
* temporal feature-set ablation

## 6. Why the baseline success rate is 20.0%

The official baseline result is:

* SR: 20.0%
* OSR: 46.7%
* NE: 6.51 m

This means:

* success rate counts episodes where the robot finishes/stops within the success radius
* oracle success counts episodes where the trajectory enters the goal region at any point
* navigation error measures the final distance from the goal

The gap between SR 20.0% and OSR 46.7% is the key diagnostic finding.

It shows that the baseline GNM policy can often navigate near or through the goal region, but it does not reliably decide when to stop. Therefore, the problem is not only path-following. It is also a stopping-policy problem.

This is why the project focuses on deployable stop-policy improvement.

## 7. Stop-policy improvement ladder

The project currently reports the following progression.

| Method                                  |    SR |   OSR |     NE |
| --------------------------------------- | ----: | ----: | -----: |
| Baseline GNM                            | 20.0% | 46.7% | 6.51 m |
| Hand-tuned waypoint gate                | 26.7% | 26.7% | 5.34 m |
| Logistic stop head, train to validation | 20.0% | 46.7% | 6.51 m |
| Temporal neural stop head               | 33.3% | 33.3% | 4.47 m |
| Geometry-aware oracle upper bound       | 46.7% | 46.7% | 3.79 m |

The current best deployable method is the temporal neural stop head.

It improves held-out validation success from 20.0% to 33.3% using only runtime GNM-derived signals.

## 8. Temporal feature-set ablation

The feature-set ablation tests which runtime signal group explains the improvement.

| Feature set            |    SR |   OSR |     NE |
| ---------------------- | ----: | ----: | -----: |
| full temporal          | 33.3% | 33.3% | 4.47 m |
| distance plus waypoint | 26.7% | 26.7% | 4.81 m |
| distance only          | 20.0% | 46.7% | 6.38 m |
| waypoint only          | 20.0% | 40.0% | 6.04 m |

This shows that the improvement is not explained by distance-only, waypoint-only, or raw distance-plus-waypoint signals. The best result requires the full temporal feature vector, including rolling means and trends.

## 9. Scene evidence and Isaac status

The project uses Kujiale/VLNVerse scene assets through the local VLNTube environment layout.

The heavy photorealistic USD scenes can be loaded in Isaac Sim, and one of the validation checks confirmed:

```text
STAGE_LOADED: True
```

However, long GUI sessions with the full photorealistic USD scene may trigger native Isaac/Kit instability on the current workstation, specifically inside Isaac/Omniverse native runtime libraries such as:

```text
libcarb.assets.plugin.so
libcarb.tasking.plugin.so
```

This is treated as a runtime/asset-loader stability issue, not a GNM algorithmic failure.

To ensure a reliable live demonstration, the project includes a stable Isaac live trajectory demo that uses real VLNVerse/GNM trajectory data but renders it in a lightweight Isaac stage.

## 10. Stable Isaac live trajectory demo

The stable live demo command is:

```bash
conda activate isaac
python scripts/gnm/isaac_live_trajectory_demo.py
```

The demo shows:

* floor plane
* boundary walls
* simple obstacles
* green start marker
* red goal marker
* blue trajectory breadcrumbs
* yellow moving robot marker

Observed output:

```text
GNM LIVE ISAAC TRAJECTORY
Trajectory: datasets/vlntube/train/kujiale_0092_kujiale_0092_0_3/traj_data.pkl
Frames: 48
Starting live replay...
Replay complete. Holding Isaac window open.
```

This proves that the project can load real trajectory data and replay live robot motion in Isaac Sim.

## 11. What can be shared

The repository includes the source code, evidence files, evaluation summaries, scripts, and release archives.

The local dataset layout can be shown to a supervisor using:

```bash
find datasets/vlntube -maxdepth 3 -type f | head -80
find datasets/vlntube/train -maxdepth 2 -type f | head -40
find datasets/vlntube/val -maxdepth 2 -type f | head -40
find datasets/vlntube/envs -maxdepth 2 -type f | head -40
```

The scene and trajectory evidence can also be demonstrated through:

```bash
python scripts/gnm/isaac_live_trajectory_demo.py
```

If a full dataset package is required, it should be created separately from the source-code release because image trajectories and scene assets may be large.

## 12. Summary answer to supervisor

GNM is integrated as the local goal-conditioned visual navigation backbone. The 238 trajectories are generated/converted from VLNVerse/VLNTube trajectory data, not manually labelled. The recorded labels include RGB observations, poses, yaws, goal indices, action/waypoint targets, and derived stop labels for stop-head training. Training uses 238 trajectories and evaluation uses 15 held-out validation trajectories. The 20.0% baseline success rate arises because the robot only stops successfully in 20.0% of validation episodes, even though oracle success is 46.7%, meaning the policy often reaches the goal region but fails to stop reliably. The temporal stop head improves deployable success to 33.3%, and the feature-set ablation shows this improvement depends on full temporal runtime history.
