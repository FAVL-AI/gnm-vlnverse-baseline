#!/usr/bin/env python3
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/bo_reviewer_packet/32_end_to_end_methodology_evidence_walkthrough.md"


def read_file(path: str, max_lines: int = 100) -> str:
    file_path = ROOT / path
    if not file_path.exists():
        return f"# Missing file: {path}\n"
    lines = file_path.read_text(errors="replace").splitlines()
    return "\n".join(lines[:max_lines])


def read_json(path: str) -> dict:
    file_path = ROOT / path
    if not file_path.exists():
        return {}
    try:
        return json.loads(file_path.read_text(errors="replace"))
    except json.JSONDecodeError:
        return {}


def code_evidence(path: str, language: str = "python", max_lines: int = 100) -> str:
    return (
        f"\n### Code evidence: `{path}`\n\n"
        f"```{language}\n"
        f"{read_file(path, max_lines)}\n"
        f"```\n"
    )


def command_block(command: str) -> str:
    return f"\n```bash\n{command.strip()}\n```\n"


temporal_meta = read_json("results/bo_reviewer_packet/temporal_stop_head/22_temporal_stop_head_meta.json")

parts = []

parts.append(
"""# End-to-End Methodology and Evidence Walkthrough — GNM-VLNVerse Track A

## 1. Executive summary

This document explains the full methodology, implementation, training setup, Isaac Sim setup, evaluation flow, evidence chain, and failure investigation for the GNM-VLNVerse Track A study.

The goal is not only to say that the system works. The goal is to show how it works, where the evidence is stored, what code produced the evidence, what failed, how each failure was investigated, and how the final claims can be reproduced.

The central finding is:

> The baseline GNM model can often reach the goal region, but it does not reliably stop there.

This means the project is not only about path following. It is also about stop reliability.

Baseline result:

| Method | Success Rate | Oracle Success Rate | Navigation Error |
|---|---:|---:|---:|
| Baseline GNM | 20.0% | 46.7% | 6.51 m |
| Temporal neural stop head | 33.3% | 33.3% | 4.47 m |
| Geometry-aware oracle upper bound | 46.7% | 46.7% | 3.79 m |

The Success Rate / Oracle Success Rate gap is the main forensic clue.

Success Rate asks:

> Did the robot finish correctly?

Oracle Success Rate asks:

> Did the robot enter the goal region at any point?

The baseline has 20.0% Success Rate but 46.7% Oracle Success Rate. That means the robot often gets into the correct area, but the stopping decision is unreliable.
"""
)

parts.append(
"""## 2. Plain-English explanation of the problem

Imagine a robot is told to go to a kitchen door.

If it drives near the kitchen door but keeps moving past it, it has not completed the task. It understood the rough direction, but it failed to stop at the correct time.

That is the failure mode studied here.

The project separates two questions:

1. Can the robot reach the goal region?
2. Can the robot stop correctly when it reaches the goal region?

A normal navigation score can hide this distinction. This project exposes it using both Success Rate and Oracle Success Rate.
"""
)

parts.append(
"""## 3. Acronyms and unknown words explained

| Term | Expanded meaning | Plain-English meaning |
|---|---|---|
| GNM | General Navigation Model | The robot navigation model used as the visual navigation brain. |
| VLN | Vision-Language Navigation | A task where a robot uses visual observations and goal/task context to navigate. |
| VLNVerse | Vision-Language Navigation benchmark environment | The benchmark/source environment used for indoor navigation trajectories. |
| VLNTube | VLNVerse-style local dataset pipeline | The local folder/data layout used to organise trajectories and scene assets. |
| SR | Success Rate | Did the robot stop successfully at the goal? |
| OSR | Oracle Success Rate | Did the robot enter the goal region at any time, even if it failed to stop? |
| NE | Navigation Error | Final distance from the goal. Lower is better. |
| TL | Trajectory Length | How long the travelled path is. |
| Waypoint | Short-term target point | The next small movement target predicted by the model. |
| Trajectory | Path through time | The robot’s recorded movement path. |
| Isaac Sim | NVIDIA Isaac Simulator | A 3D robotics simulator used here to replay real trajectory data. |
| USD | Universal Scene Description | A 3D scene file format used by Isaac Sim. |
| Ablation | Controlled removal/change | A test where we remove or change one part to see what matters. |
| Oracle | Diagnostic privileged information | Information used for analysis, not allowed in deployable runtime inference. |
"""
)

parts.append(
"""## 4. Full architecture and data flow

```text
+--------------------------------------------------+
|  VLNVerse / VLNTube local data                   |
|  datasets/vlntube/train                          |
|  datasets/vlntube/val                            |
|  datasets/vlntube/envs                           |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
|  Dataset and scene manifest generator            |
|  scripts/gnm/generate_dataset_scene_manifest.py  |
|  Counts train/val trajectories and scenes        |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
|  GNM evaluation and rollout code                 |
|  Loads trajectory data and GNM-derived signals   |
|  Produces rollout traces                         |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
|  Metric calculation                              |
|  Success Rate, Oracle Success Rate,              |
|  Navigation Error, Trajectory Length             |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
|  Stop-policy investigation                       |
|  Thresholds, waypoint gate, logistic head,       |
|  temporal neural stop head, oracle diagnostics   |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
|  Ablation studies                                |
|  sequence length, stable-K, feature sets         |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
|  Evidence packet                                 |
|  Markdown, CSV, JSON                             |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
|  One-command reproducibility                     |
|  scripts/gnm/run_reproducibility_pack.sh         |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
|  Isaac Sim live trajectory replay                |
|  scripts/gnm/isaac_live_trajectory_demo.py       |
+--------------------------------------------------+
