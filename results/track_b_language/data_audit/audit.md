# Track B Language Data Audit

**Date:** 2026-06-15  
**Audited data roots:** 4

## Gate B Decision: `READY_FOR_PROJECT_AUTHORED_ANNOTATION`

> Real images present: 13491 images. Datasets with real images + goal_pos: ['vlntube_fleetsafe']. Datasets with authentic instructions: ['custom_vln_office', 'vlntube_prebuilt', 'vlnverse_imported'] (3 instructions). Instructions and real images are NOT colocated within any single episode set. Action required: pair vlntube_fleetsafe episodes (real images + goal_pos) with language instructions via data/track_b_annotations/ before CLIP evaluation.

## Dataset Summary

| Dataset | Type | Source | Episodes | Instructions | Images | Real Images | Indep. Targets |
|---------|------|--------|----------|--------------|--------|-------------|----------------|
| custom_vln_office | synthetic_dry_run | project_authored_synthetic | 8 | 8 | 318 | ✗ | ✗ |
| vlntube_fleetsafe | real_kujiale_trajectories | upstream_repository_provided | 253 | 0 | 13491 | ✓ | ✓ |
| vlntube_prebuilt | vlntube_benchmark_trajectories | upstream_repository_provided | 2 | 2 | 0 | ✓ | ✗ |
| vlnverse_imported | vlnverse_navigator_runs | benchmark_provided | 1 | 1 | 0 | ✗ | ✗ |

## Totals

| Metric | Count |
|--------|-------|
| Total episodes | 264 |
| Total instructions | 11 |
| Authentic instructions (non-synthetic) | 3 |
| Total images | 13809 |
| Real camera images | 13491 |
| Independently anchored episodes | 253 |

## Missing Fields Per Dataset

**custom_vln_office:** independent_target_annotation, real_images
**vlntube_fleetsafe:** language_instructions
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

**Decision: READY_FOR_PROJECT_AUTHORED_ANNOTATION**

Real camera images and pose data are available. To proceed:

1. Create `data/track_b_annotations/schema.json`
2. For each VLNTube episode, freeze a target frame index independently of model retrieval
3. Write `train.jsonl` and `validation.jsonl` with episode_id, instruction, target_frame_idx
4. Hash and freeze annotation manifest before evaluation
5. Only then run CLIP retrieval against these targets