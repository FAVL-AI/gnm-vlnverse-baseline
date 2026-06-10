# CustomVLN-Office — Evaluation Summary

**Source:** `evaluate_custom_vln_office.py`  
**VLNVerse assets used:** NONE  
**Scene:** independent Isaac Sim primitives

## Dataset

| Metric | Value |
|--------|-------|
| Total episodes | 8 |
| Train episodes | 6 |
| Val episodes   | 2 |
| Goal radius    | 2.0 m |

## Navigation metrics

| Metric | Value |
|--------|-------|
| Avg path length | 9.78 m |
| Avg final distance | 0.0 m |
| Avg min distance | 0.0 m |
| Episodes with waypoint labels | 8/8 |
| Episodes with actions.jsonl | 8/8 |

## GNM inference status

> gnm_base checkpoint not found — model inference skipped

> **Note:** This is an independent proof-of-method evaluation.
> It is NOT an official VLNVerse benchmark result.
> Official Track A result remains: SR 20.0%, OSR 46.7%, NE 6.51 m.

## Per-episode breakdown

| Episode | Split | Frames | Path (m) | Final dist (m) | Min dist (m) | Labels |
|---------|-------|--------|----------|----------------|--------------|--------|
| cvlo_ep001 | train | 31 | 5.02 | 0.0 | 0.0 | yes |
| cvlo_ep002 | train | 31 | 6.68 | 0.0 | 0.0 | yes |
| cvlo_ep003 | train | 41 | 12.407 | 0.0 | 0.0 | yes |
| cvlo_ep004 | train | 41 | 8.504 | 0.0 | 0.0 | yes |
| cvlo_ep005 | train | 41 | 11.324 | 0.0 | 0.0 | yes |
| cvlo_ep006 | train | 41 | 12.407 | 0.0 | 0.0 | yes |
| cvlo_ep007 | val | 41 | 8.511 | 0.0 | 0.0 | yes |
| cvlo_ep008 | val | 51 | 13.39 | 0.0 | 0.0 | yes |

## Evidence statement

CustomVLN-Office uses Isaac Sim assets to create an independent navigation environment.
It does not use VLNVerse scenes, trajectories, or labels.
The purpose is to demonstrate that the GNM-style pipeline can be built and controlled
by us from scratch in Isaac Sim.