# Track A Isaac Metrics Showcase Demo

> **DEPRECATED (2026-07-08) — pre-baseline material.** This document
> predates the live articulated-robot pipeline and must not be cited as
> current evidence; gates and statuses herein are historical. See
> `docs/experiments/PROJECT_BASELINE_STATUS.md` for the valid baseline.

This demo creates a live Isaac Sim sequence for the Year 1 paper: **Accurate and Safety-Aware Visual Navigation: Diagnosing Stopping Reliability in Camera-Only Image-Goal Navigation**.

It visualises the validated Track A finding: baseline GNM reaches the goal region more often than it successfully terminates there. The Isaac scene shows a moving trajectory, start marker, goal marker, success-radius ring, trajectory breadcrumbs, obstacles, and a live metrics HUD.

## Scope

Validated showcase claims:

- Track A camera-only image-goal navigation is the Year 1 scope.
- Baseline GNM: SR 20.0%, OSR 46.7%, NE 6.51 m.
- Temporal neural stop head: SR 33.3%, NE 4.47 m.
- Geometry-aware oracle is diagnostic only.
- The demo supports the Year 1 evidence story and prepares the Year 2 Yahboom/ROS 2 route.

Blocked claims:

- No completed closed-loop Yahboom safety result yet.
- No completed Track B language-grounding result yet.
- No global superiority claim over GNM, ViNT, NoMaD, or SaferPath.

## Run the validation pack first

```bash
cd ~/robotics/gnm-vlnverse-baseline
git pull origin main
bash scripts/gnm/run_tracka_metric_provenance_pack.sh
```

## Run the Isaac metrics showcase

```bash
cd ~/robotics/gnm-vlnverse-baseline
conda activate isaac
python scripts/gnm/isaac_tracka_metrics_showcase.py --duration 60 --save-stage
```

Expected behaviour:

1. Isaac Sim opens.
2. A Track A trajectory scene is created.
3. Start, goal, goal-radius ring, breadcrumbs, obstacles, robot, and metric bars appear.
4. A Track A Metrics HUD appears inside Isaac.
5. The robot first demonstrates the baseline stopping-failure pattern.
6. The second segment demonstrates the temporal stop-head stop decision near the goal.
7. A summary JSON and optional USDA stage are written to `paper/showcase/recordings/`.

## Record footage

Start the Isaac showcase in one terminal. In a second terminal, run:

```bash
cd ~/robotics/gnm-vlnverse-baseline
bash scripts/gnm/record_isaac_tracka_showcase.sh paper/showcase/recordings 60
```

If the capture area does not match your Isaac window, set the offsets and size:

```bash
VIDEO_SIZE=1556x914 X_OFFSET=0 Y_OFFSET=0 bash scripts/gnm/record_isaac_tracka_showcase.sh paper/showcase/recordings 60
```

## Screenshots for presentation

```bash
mkdir -p paper/showcase/isaac_screenshots
gnome-screenshot -w -f paper/showcase/isaac_screenshots/01_tracka_isaac_metrics_showcase_window.png
gnome-screenshot -f paper/showcase/isaac_screenshots/02_tracka_isaac_metrics_showcase_full_desktop.png
```

Use these images in the presentation instead of generated or placeholder visuals.
