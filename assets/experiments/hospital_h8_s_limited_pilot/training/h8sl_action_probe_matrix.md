# H8-S Limited Pilot — Action-Probe Matrix (distance/stop axis)

Predicted `[dx,dy]` (robot-frame meters) at each shared decision frame `o_d`, swapping only the goal image (near=goalA/near_stop, far=goalB/far_continue). `pred_mag_m` = |[dx,dy]| is the distance signal; `exp_mag_m` = expected o_d->goal distance. `dist_head` = normalized temporal-distance head (secondary). Baseline = untrained H7r candidate.

| variant | split | zone | condition | pred_dx | pred_dy | pred_mag_m | dist_head | pred_angle_deg | exp_mag_m | stop |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | train | lobby | near | 0.0153 | -0.007 | 0.0168 | 0.8724 | -24.7 | 0.6 | False |
| baseline | train | lobby | far | 0.0147 | -0.0073 | 0.0164 | 0.9122 | -26.3 | 1.6 | False |
| baseline | val | midwest_B | near | 0.0167 | -0.0013 | 0.0168 | 0.9105 | -4.3 | 0.4 | False |
| baseline | val | midwest_B | far | 0.0158 | -0.0013 | 0.0159 | 0.9146 | -4.6 | 1.0 | False |
| baseline | test | east_A | near | 0.0125 | -0.0064 | 0.0141 | 0.9081 | -27.2 | 0.3 | False |
| baseline | test | east_A | far | 0.0112 | -0.0063 | 0.0128 | 0.9252 | -29.3 | 0.7 | False |
| A | train | lobby | near | 0.4955 | 0.0005 | 0.4955 | 0.0146 | 0.1 | 0.6 | True |
| A | train | lobby | far | 1.2005 | 0.0014 | 1.2005 | 0.0488 | 0.1 | 1.6 | True |
| A | val | midwest_B | near | 0.4828 | 0.0016 | 0.4828 | 0.0105 | 0.2 | 0.4 | True |
| A | val | midwest_B | far | 0.4819 | 0.0014 | 0.4819 | 0.0107 | 0.2 | 1.0 | True |
| A | test | east_A | near | 0.5188 | 0.0024 | 0.5188 | 0.0192 | 0.3 | 0.3 | True |
| A | test | east_A | far | 0.5049 | 0.0015 | 0.5049 | 0.018 | 0.2 | 0.7 | True |
| A+B | train | lobby | near | 0.4038 | 0.0024 | 0.4038 | 0.0021 | 0.3 | 0.6 | True |
| A+B | train | lobby | far | 1.2085 | 0.0009 | 1.2085 | 0.0458 | 0.0 | 1.6 | True |
| A+B | val | midwest_B | near | 0.5313 | 0.0016 | 0.5313 | 0.0172 | 0.2 | 0.4 | True |
| A+B | val | midwest_B | far | 0.5314 | 0.0016 | 0.5314 | 0.0169 | 0.2 | 1.0 | True |
| A+B | test | east_A | near | 0.4755 | 0.0032 | 0.4755 | 0.0089 | 0.4 | 0.3 | True |
| A+B | test | east_A | far | 0.5226 | 0.0049 | 0.5227 | 0.0072 | 0.5 | 0.7 | True |
| A+B+C | train | lobby | near | 0.3571 | 0.0013 | 0.3571 | 0.0014 | 0.2 | 0.6 | True |
| A+B+C | train | lobby | far | 1.1933 | -0.0005 | 1.1933 | 0.0568 | -0.0 | 1.6 | True |
| A+B+C | val | midwest_B | near | 0.4217 | 0.0011 | 0.4217 | 0.009 | 0.1 | 0.4 | True |
| A+B+C | val | midwest_B | far | 0.4219 | 0.0011 | 0.4219 | 0.009 | 0.1 | 1.0 | True |
| A+B+C | test | east_A | near | 0.6407 | 0.0037 | 0.6407 | 0.0089 | 0.3 | 0.3 | True |
| A+B+C | test | east_A | far | 0.7612 | 0.003 | 0.7612 | 0.0183 | 0.2 | 0.7 | True |
| A+B+C+E | train | lobby | near | 0.6262 | 0.0004 | 0.6262 | 0.0248 | 0.0 | 0.6 | True |
| A+B+C+E | train | lobby | far | 0.7496 | 0.0005 | 0.7496 | 0.0369 | 0.0 | 1.6 | True |
| A+B+C+E | val | midwest_B | near | 0.6315 | 0.0002 | 0.6315 | 0.0278 | 0.0 | 0.4 | True |
| A+B+C+E | val | midwest_B | far | 0.6732 | 0.0004 | 0.6732 | 0.0299 | 0.0 | 1.0 | True |
| A+B+C+E | test | east_A | near | 0.8062 | 0.0012 | 0.8062 | 0.0401 | 0.1 | 0.3 | True |
| A+B+C+E | test | east_A | far | 0.846 | 0.0014 | 0.846 | 0.0416 | 0.1 | 0.7 | True |
