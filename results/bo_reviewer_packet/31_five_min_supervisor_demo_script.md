# Five-Minute Supervisor Demo Script

## 0:00–0:45 — Project framing

This is a reproducible GNM-VLNVerse Track A baseline and stop-policy study.

The key question is whether GNM fails only because of navigation quality, or also because it cannot stop reliably.

Opening line:

> The baseline can often reach the goal region, but it does not reliably stop there. That is the failure mode this project isolates and improves.

## 0:45–1:30 — Dataset evidence

Run:

```bash
sed -n '1,90p' results/bo_reviewer_packet/28_dataset_scene_manifest.md
```

Say:

- The study uses 238 train trajectories.
- It evaluates on 15 held-out validation trajectories.
- The local Track A setup uses four Kujiale/VLNVerse scenes.
- The manifest is generated from local files, not manually typed.

## 1:30–2:30 — Result diagnosis

Run:

```bash
sed -n '1,160p' results/bo_reviewer_packet/23_paper_results_table.md
```

Say:

- Baseline SR is 20.0%.
- Baseline OSR is 46.7%.
- The SR/OSR gap means the robot often reaches or passes through the goal region but fails to stop correctly.
- This makes stopping reliability a measurable failure mode, not just an anecdotal weakness.

## 2:30–3:30 — Improvement

Say:

- Scalar thresholds and simple hand-tuned stopping are not enough.
- Logistic calibration does not improve held-out validation SR.
- The temporal neural stop head improves deployable SR from 20.0% to 33.3%.
- It also improves NE from 6.51 m to 4.47 m.
- The temporal stop head uses runtime GNM-derived signals, not oracle geometry, at inference time.

## 3:30–4:20 — Reproducibility

Run:

```bash
bash scripts/gnm/run_reproducibility_pack.sh
```

Expected result:

```text
[SUCCESS] Reproducibility pack completed
131 passed
```

Say:

- This regenerates the manifest.
- It runs the GNM test suite.
- It verifies the README matrix.
- It verifies the expected dataset counts and scene IDs.
- It confirms the evidence chain is reproducible from the current repo state.

## 4:20–5:00 — Isaac live demo

Optional:

```bash
conda activate isaac
python scripts/gnm/isaac_live_trajectory_demo.py
```

Say:

- This replays real VLNVerse/GNM trajectory data in a stable Isaac stage.
- It avoids the heavy full-scene USD instability while still demonstrating live motion from real trajectory data.
- The photorealistic VLNVerse scene path remains a separate runtime-debugging task.

## Final sentence

This repository now contains a staged research trail: baseline diagnosis, stop-policy improvement, ablation evidence, dataset manifest, stable Isaac demo, public README matrix, and one-command reproducibility.
