# Track B Language Data Audit

**Date:** 2026-06-15  
**Audited data roots:** 4

## Gate B Decision: `READY_FOR_GENERATED_LANGUAGE_BENCHMARK_EVALUATION`

> Datasets ['vlntube_fleetsafe'] have 253 upstream-generated instructions (method: gemini-2.5-flash_from_trajectory_frames; from trajectory frames by Gemini API, sourced from Eyz/VLNVerse_data) colocated with real images and independently established goal_pos targets for 253 episodes. goal_pos is derived from scene-graph A* geometry independent of any instruction or retrieval system. Instruction generator (Gemini) saw trajectory frames including final frames (INDIRECT_TARGET_VISUAL_EXPOSURE); goal_pos was NOT in the generator prompt. Instructions were generated before Track B CLIP retrieval was implemented — no circular dependency with retrieval system. Leakage risk: low_standard_vln (endpoint description is standard VLN task formulation). CLAIM BOUNDARY: These are upstream Gemini-generated instructions, not human-authored benchmark language. Do not make human-language-generalisation claims without a human-authored subset.

## Dataset Summary

| Dataset | Type | Source | Episodes | Instructions | Images | Real Images | Indep. Targets |
|---------|------|--------|----------|--------------|--------|-------------|----------------|
| custom_vln_office | synthetic_dry_run | project_authored_synthetic | 8 | 8 | 318 | ✗ | ✗ |
| vlntube_fleetsafe | real_kujiale_trajectories | upstream_repository_provided | 253 | 253 | 13491 | ✓ | ✓ |
| vlntube_prebuilt | vlntube_benchmark_trajectories | upstream_repository_provided | 2 | 2 | 0 | ✓ | ✗ |
| vlnverse_imported | vlnverse_navigator_runs | benchmark_provided | 1 | 1 | 0 | ✗ | ✗ |

## Totals

| Metric | Count |
|--------|-------|
| Total episodes | 264 |
| Total instructions | 264 |
| Authentic instructions (non-synthetic) | 256 |
| Total images | 13809 |
| Real camera images | 13491 |
| Independently anchored episodes | 253 |

## Missing Fields Per Dataset

**custom_vln_office:** independent_target_annotation, real_images
**vlntube_prebuilt:** goal_pos, independent_target_annotation
**vlnverse_imported:** rgb_images, independent_target_annotation

## Classification Guide

| Code | Meaning |
|------|---------|
| `benchmark_provided` | Official VLNVerse or VLNTube benchmark data |
| `upstream_repository_provided` | From the VLNTube repository |
| `project_authored_synthetic` | Created by this project (synthetic, dry-run) |
| `project_authored` | Created by this project (non-synthetic) |
| `synthetic` | Machine-generated instructions (LLM/Gemini) |
| `unknown` | Origin cannot be determined |

## Next Steps

**Decision: READY_FOR_GENERATED_LANGUAGE_BENCHMARK_EVALUATION**
