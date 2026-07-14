# H7r mismatched-goal ablation — does the candidate use the goal image?

Same H7r candidate, H7r test episodes. Goal POSITION = episode's own endpoint in every row; only the goal IMAGE is swapped. `mean_final_pos_delta_m` = how far the final stop moved vs the correct-goal rollout (0 = identical trajectory ending).

| goal_condition | n | SR | OSR | SPL | NE | nDTW | mean_final_pos_delta_m |
|---|---|---|---|---|---|---|---|
| correct | 2 | 1.000 | 1.000 | 0.908 | 2.54 | 0.646 | 0.000 |
| placeholder | 2 | 1.000 | 1.000 | 0.952 | 2.09 | 0.696 | 0.659 |
| mismatch_same_fam | 2 | 0.500 | 1.000 | 0.500 | 2.92 | 0.612 | 0.501 |
| mismatch_diff_fam | 2 | 1.000 | 1.000 | 0.879 | 2.50 | 0.654 | 0.497 |