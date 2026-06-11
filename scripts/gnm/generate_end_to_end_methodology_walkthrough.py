#!/usr/bin/env python3
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/bo_reviewer_packet/32_end_to_end_methodology_evidence_walkthrough.md"

def rel(p: str) -> Path:
    return ROOT / p

def read_text(path: str, max_lines: int = 80) -> str:
    p = rel(path)
    if not p.exists():
        return f"# Missing file: {path}\n"
    lines = p.read_text(errors="replace").splitlines()
    return "\n".join(lines[:max_lines])

def read_json(path: str) -> dict:
    p = rel(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text())

meta = read_json("results/bo_reviewer_packet/temporal_stop_head/22_temporal_stop_head_meta.json")

doc = f"""# End-to-End Methodology and Evidence Walkthrough — GNM-VLNVerse Track A

## 1. Executive summary

This project investigates a specific failure mode in visual robot navigation: the robot can often reach the goal area, but it does not reliably stop there.

The baseline General Navigation Model, abbreviated as GNM, achieves:

| Method | Success Rate | Oracle Success Rate | Navigation Error |
|---|---:|---:|---:|
| Baseline GNM | 20.0% | 46.7% | 6.51 m |
| Temporal neural stop head | 33.3% | 33.3% | 4.47 m |
| Geometry-aware oracle upper bound | 46.7% | 46.7% | 3.79 m |

The key evidence is the gap between Success Rate and Oracle Success Rate.

Success Rate asks: did the robot finish correctly?

Oracle Success Rate asks: did the robot ever enter the goal region during the path?

The baseline has 20.0% Success Rate but 46.7% Oracle Success Rate. That means the robot often reaches the correct region but fails to stop there.

This document explains the full evidence chain: dataset, environment, Isaac Sim setup, GNM integration, training, evaluation, failure analysis, ablations, mitigation, and reproducibility.

---

## 2. Glossary in plain English

| Term | Meaning |
|---|---|
| GNM | General Navigation Model. The visual navigation model used as the robot navigation brain. |
| VLN | Vision-Language Navigation. Navigation using visual observations and task/goal context. |
| VLNVerse | Benchmark/environment source used for indoor navigation trajectory evaluation. |
| VLNTube | Local dataset layout used to organise VLNVerse-style trajectory and scene data. |
| Trajectory | A recorded path through the environment. |
| Waypoint | A short-term movement target predicted by the navigation model. |
| SR | Success Rate. Final task success. |
| OSR | Oracle Success Rate. Whether the path ever entered the goal region. |
| NE | Navigation Error. Final distance from the goal. |
| Isaac Sim | NVIDIA robotics simulator used to visualise live replay. |
| USD | Universal Scene Description. 3D scene file format used by Isaac Sim. |
| Ablation | A controlled experiment where one component is removed or changed to see what matters. |

---

## 3. Full system architecture

```text
+-----------------------------+
| VLNVerse / VLNTube Dataset  |
| train, val, envs            |
+--------------+--------------+
               |
               v
+-----------------------------+
| Dataset Manifest Generator  |
| generate_dataset_scene...   |
| counts scenes + trajectories|
+--------------+--------------+
               |
               v
+-----------------------------+
| GNM Evaluation Pipeline     |
| loads checkpoint + config   |
| runs visual-goal prediction |
+--------------+--------------+
               |
               v
+-----------------------------+
| Rollout and Metrics         |
| SR, OSR, NE, TL             |
+--------------+--------------+
               |
               v
+-----------------------------+
| Stop-Policy Study           |
| thresholds, waypoint gate,  |
| logistic head, temporal head|
+--------------+--------------+
               |
               v
+-----------------------------+
| Evidence Outputs            |
| CSV, Markdown, JSON         |
+--------------+--------------+
               |
               v
+-----------------------------+
| Reproducibility Pack        |
| one command verifies chain  |
+--------------+--------------+
               |
               v
+-----------------------------+
| Isaac Live Demo             |
| stable trajectory replay    |
+-----------------------------+
