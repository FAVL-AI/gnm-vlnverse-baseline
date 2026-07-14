# H8 Visual Similarity Matrix (aHash 16x16; 1 − Hamming/256)

Higher = more similar. Crude screen for structurally-alike corridors — treat the pattern, not the absolute value, as decisive. Splits: lobby=train, midwest_A=train, midwest_B=val, east_A=test, east_B=test, lookalike_test=test, west_C=REJECTED, val_A=REJECTED, searchW1=west_cand, searchW2=west_cand.

| view | lobby | midwest_A | midwest_B | east_A | east_B | lookalike_ | west_C | val_A | searchW1 | searchW2 |
|---|---|---|---|---|---|---|---|---|---|---|
| lobby | 1.00 | 0.81 | 0.64 | 0.86 | 0.83 | 0.79 | 0.56 | 0.58 | 0.81 | 0.78 |
| midwest_A | 0.81 | 1.00 | 0.76 | 0.77 | 0.74 | 0.72 | 0.62 | 0.68 | 0.75 | 0.70 |
| midwest_B | 0.64 | 0.76 | 1.00 | 0.57 | 0.54 | 0.53 | 0.75 | 0.85 | 0.59 | 0.55 |
| east_A | 0.86 | 0.77 | 0.57 | 1.00 | 0.93 | 0.89 | 0.56 | 0.54 | 0.74 | 0.73 |
| east_B | 0.83 | 0.74 | 0.54 | 0.93 | 1.00 | 0.96 | 0.55 | 0.52 | 0.72 | 0.73 |
| lookalike_te | 0.79 | 0.72 | 0.53 | 0.89 | 0.96 | 1.00 | 0.53 | 0.51 | 0.70 | 0.71 |
| west_C | 0.56 | 0.62 | 0.75 | 0.56 | 0.55 | 0.53 | 1.00 | 0.73 | 0.47 | 0.52 |
| val_A | 0.58 | 0.68 | 0.85 | 0.54 | 0.52 | 0.51 | 0.73 | 1.00 | 0.57 | 0.49 |
| searchW1 | 0.81 | 0.75 | 0.59 | 0.74 | 0.72 | 0.70 | 0.47 | 0.57 | 1.00 | 0.77 |
| searchW2 | 0.78 | 0.70 | 0.55 | 0.73 | 0.73 | 0.71 | 0.52 | 0.49 | 0.77 | 1.00 |
