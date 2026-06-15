# Language-Dependence Control Evaluation — Track B

**Date:** 2026-06-15
**Split:** train (238 episodes)
**CLIP model:** `openai/clip-vit-base-patch16`
**Route prior beta:** 1.0

## Control conditions

| Condition | Description |
|-----------|-------------|
| `correct` | Original instruction for each episode |
| `shuffled` | Instructions permuted across episodes (seed 42) |
| `empty` | Empty string passed as instruction |
| `constant` | Same fixed instruction for all episodes |
| `random_text` | Random words, mean-length matched (seed 12345) |
| `route_only` | Semantic similarity fixed to 1.0; only route prior |
| `clip_only` | Pure CLIP, route prior disabled (beta=0) |

## Results

| Condition | SR@3m | 95% CI | Mean dist (m) | MRR | R@1 | R@3 | Final-frame rate |
|-----------|-------|--------|---------------|-----|-----|-----|-----------------|
| `correct` | 0.987 | [0.973, 1.000] | 0.29 | 0.994 | 0.987 | 1.000 | 0.651 |
| `shuffled` | 1.000 | [1.000, 1.000] | 0.22 | 1.000 | 1.000 | 1.000 | 0.685 |
| `empty` | 0.996 | [0.988, 1.000] | 0.10 | 0.998 | 0.996 | 1.000 | 0.874 |
| `constant` | 0.996 | [0.988, 1.000] | 0.23 | 0.998 | 0.996 | 1.000 | 0.744 |
| `random_text` | 0.992 | [0.980, 1.000] | 0.23 | 0.996 | 0.992 | 1.000 | 0.740 |
| `route_only` | 1.000 | [1.000, 1.000] | 0.00 | 1.000 | 1.000 | 1.000 | 1.000 |
| `clip_only` | 0.382 | [0.321, 0.444] | 3.70 | 0.581 | 0.382 | 0.740 | 0.076 |

## Language sensitivity

| Metric | Value |
|--------|-------|
| Correct vs shuffled delta (SR@3m) | -0.0126 |
| Correct vs constant delta (SR@3m) | -0.0084 |
| Language dependence conclusion | **LANGUAGE_DEPENDENCE_NOT_DEMONSTRATED** |

## Interpretation

> **LANGUAGE_DEPENDENCE_NOT_DEMONSTRATED**
>
> SR@3m remains near 1.000 under shuffled, empty, constant, and route-only
> conditions.  The route prior alone (trajectory endpoint bias) is sufficient
> to achieve SR@3m = 1.000 regardless of instruction content.  This result
> should not be reported as language-grounding evidence.
>
> The dataset property that all trajectories end at goal_pos makes SR@3m
> non-discriminative for language sensitivity.  A discriminative dataset
> is needed before language grounding can be evaluated.

## Per-scene results

| Scene | correct SR@3m | shuffled SR@3m | route_only SR@3m | N |
|-------|---------------|----------------|-----------------|---|
| `kujiale_0092` | 1.0 | 1.0 | 1.0 | 66 |
| `kujiale_0118` | 0.9833 | 1.0 | 1.0 | 60 |
| `kujiale_0203` | 1.0 | 1.0 | 1.0 | 65 |
| `kujiale_0271` | 0.9574 | 1.0 | 1.0 | 47 |