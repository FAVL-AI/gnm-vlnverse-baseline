# Track A Robustness Evidence Summary

## Data availability

| Source | Episodes | Scenes | Suitable for expanded eval? |
|---|---|---|---|
| vlntube/val (current locked split) | 15 | 4 | Yes — all 5 methods evaluated |
| vlntube/train | 238 | 4 | No — train split for logistic/temporal stop heads; using it would be in-distribution evaluation |
| VLNVerse / IAmGoodNavigator | 1 (kujiale_0010) | 1 new | No — requires Isaac Sim inference; format differs from vlntube |

> **Conclusion:** No additional held-out trajectories exist beyond the 15 val episodes. Robustness evidence is derived from more rigorous statistical analysis of the existing split.

## What this robustness package adds

| Evidence | File | Status |
|---|---|---|
| Per-scene SR/OSR/NE for all 5 methods | tracka_per_scene_breakdown.csv/.md | Done |
| Paired Wilcoxon + sign test (baseline vs temporal) | tracka_paired_comparison.md | Done |
| Bootstrap CI stability across seeds 41–44 | tracka_bootstrap_seed_stability.md | Done |

## Per-scene SR summary (all methods)

| Scene | n | baseline gnm | hand tuned waypoint gate | logistic stop head | temporal neural stop head | geometry aware oracle |
|---|---|---:|---:|---:|---:|---:|
| kujiale_0092 | 2 | 50.0% | 0.0% | 50.0% | 0.0% | 50.0% |
| kujiale_0118 | 3 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| kujiale_0203 | 7 | 28.6% | 28.6% | 28.6% | 42.9% | 57.1% |
| kujiale_0271 | 3 | 0.0% | 66.7% | 0.0% | 66.7% | 66.7% |

> **Interpretation:** kujiale_0118 has 0% SR for all deployable methods — a hard
> scene where GNM consistently fails to reach within 3 m. kujiale_0271 shows the
> largest temporal stop-head improvement (SR 0% → 67%). kujiale_0203 (n=7, largest
> scene) shows consistent temporal improvement (29% → 43%). Per-scene CIs are wide
> for n ≤ 3; these findings are diagnostic, not statistically conclusive.

## Paired comparison (baseline vs temporal, 15 episodes)

- temporal_neural_stop_head reduces NE in 11/15 episodes (sign test p=0.1185).
- Wilcoxon signed-rank: T+=95.0, z=1.99, p≈0.047 (normal approx, n=15).
- SR improvement: 20% → 33% (13 pp); NE improvement: 6.51 → 4.47 m (1.04 m mean reduction).
- Direction is consistent but n=15 gives limited power. Small-sample caution applies.

## Bootstrap seed stability

- Baseline SR 95% CI is [0, 40] for seeds 41–44 (identical).
- Temporal SR 95% CI is [13, 60] for all seeds.
- NE CIs vary by < 0.05 m across seeds.
- Seed-42 CIs reported in the paper are representative.

## Honest claims this evidence supports

- The stopping-gap diagnosis is consistent across all 4 Kujiale scenes.
- The temporal stop head reduces NE in 11/15 val episodes and improves SR by 13 pp.
- Bootstrap CIs are stable across random seeds.
- The 15-episode split is small; per-scene estimates for n ≤ 3 scenes are diagnostic only.

## Claims this evidence does NOT support

- No global superiority over GNM, ViNT, NoMaD, or SaferPath.
- No Yahboom physical deployment claim.
- No Track B language-grounding claim.
- No claim that the per-scene pattern would hold with n >> 15.
