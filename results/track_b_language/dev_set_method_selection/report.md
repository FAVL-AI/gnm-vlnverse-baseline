# Dev-Set Method Selection — Track B Subgoal Retrieval

**Date:** 2026-06-15
**Split:** train (238 episodes)
**Success radius:** 3.0 m

## Configuration

| Parameter | Value |
|-----------|-------|
| CLIP model | `openai/clip-vit-base-patch16` |
| Keyframe stride | 5 |
| Route prior beta | 1.0 |
| Rejection threshold | 0.2 |
| Random seed | 42 |

## Results

| Method | SR@3m | Mean dist (m) | Median dist (m) |
|--------|-------|---------------|-----------------|
| `random` | 0.462 | 3.79 | 3.36 |
| `first` | 0.055 | 6.51 | 5.99 |
| `final` | 1.000 | 0.00 | 0.00 |
| `oracle` | 1.000 | 0.00 | 0.00 |
| `clip` | 0.344 | 4.10 | 3.66 |
| `clip_route` | 1.000 | 0.09 | 0.00 |
| `clip_route_rej` | 1.000 | 0.09 | 0.00 |

## Notes

- `oracle` is an upper bound: it selects the frame closest to goal_pos.
  It requires privileged information (goal_pos) not available at inference time.
- `clip_route_rej` falls back to `final` frame when the maximum route-weighted
  CLIP score is below the rejection threshold (0.2).
- Evaluation uses the **train split only** (238 episodes). The 15 val episodes
  are reserved for final held-out evaluation.
- SR@3m = fraction of episodes where the selected frame position is within
  3.0 m of goal_pos.