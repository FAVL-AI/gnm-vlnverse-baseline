# Track A Metric Provenance Report

This report regenerates SR, OSR, and NE from per-episode rows.

Required columns:

episode_id, final_distance_to_goal, method, minimum_distance_to_goal, scene_id, success_radius

## Formula

- final success: `final_distance_to_goal <= success_radius`
- oracle success: `minimum_distance_to_goal <= success_radius`
- SR: `sum(success_flag) / episodes * 100`
- OSR: `sum(oracle_success_flag) / episodes * 100`
- NE: `mean(final_distance_to_goal)`

## Method results

| Method | Episodes | Success radius | Final successes | Oracle successes | SR | OSR | NE | Expected match |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| baseline_gnm | 15 | 3 | 3 | 7 | 20.0% | 46.7% | 6.51 | PASS |
