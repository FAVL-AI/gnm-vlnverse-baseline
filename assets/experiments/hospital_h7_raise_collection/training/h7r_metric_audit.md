# H7r metric audit — definitions + OSR>=SR invariant

Definitions verified against `gnm_vlnverse/evaluation/metrics.py` (Anderson et al. 2018):

| metric | definition | type |
|---|---|---|
| SR | final position within 3.0 m of goal | binary mean |
| OSR | EVER within 3.0 m of goal along path | binary mean (**>= SR always**) |
| SPL | success × shortest/max(actual,shortest) | continuous 0..1 |
| NE | final distance to goal (m) | lower better |
| nDTW | exp(-DTW/(len_ref·3)) path match | continuous 0..1 |

**Clarification of the flagged value:** the `0.908` on the H7r candidate held-out test is **SPL, not OSR**. The candidate **OSR = 1.000** (≥ SR 1.000). The earlier compressed table dropped the OSR column, so SPL was misread as OSR.

## OSR ≥ SR invariant — verified on all 8 runs

| run | SR | OSR | OSR≥SR |
|---|---|---|---|
| inc_test | 0.000 | 1.000 | ✅ |
| cand_test | 1.000 | 1.000 | ✅ |
| h6ref_test | 0.500 | 1.000 | ✅ |
| cand_val | 1.000 | 1.000 | ✅ |
| cand_train | 1.000 | 1.000 | ✅ |
| inc_val | 0.000 | 1.000 | ✅ |
| cand_ood_h4 | 0.000 | 0.667 | ✅ |
| inc_ood_h4 | 0.000 | 1.000 | ✅ |

Invariant holds for every run. No metric is mislabelled; the diagnostic decision is unchanged.