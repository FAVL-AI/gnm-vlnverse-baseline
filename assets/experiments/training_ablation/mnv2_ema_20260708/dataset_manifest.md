# Dataset manifest — MobileNetV2+EMA offline VLN evaluation

Dataset: VLNVerse/VLNTube at `datasets/vlntube` | config `configs/gnm/gnm_base.yaml` | 96×96 | git e7222b4 (isaac-hospital-demo)

Split: **238 train episodes** (12,421 samples) / **15 held-out eval episodes** (817 samples). Scenes (both splits — trajectory-level holdout, stated honestly): kujiale_0092, kujiale_0118, kujiale_0203, kujiale_0271

Leakage check: train∩eval episodes = 0; trajectory overlap = 0; scene-level holdout = false (four-scene setup).

| episode_id | scene | frames | path (m) | start | goal |
|---|---|---:|---:|---|---|
| kujiale_0092_kujiale_0092_91_1 | kujiale_0092 | 51 | 8.456 | (1.44,6.28) | (-0.93,-1.44) |
| kujiale_0092_kujiale_0092_9_2 | kujiale_0092 | 39 | 6.982 | (1.49,-2.60) | (1.93,6.32) |
| kujiale_0118_kujiale_0118_25_3 | kujiale_0118 | 50 | 7.362 | (4.30,1.61) | (6.80,-1.01) |
| kujiale_0118_kujiale_0118_31_0 | kujiale_0118 | 51 | 7.797 | (2.54,3.38) | (6.13,-3.68) |
| kujiale_0118_kujiale_0118_40_4 | kujiale_0118 | 69 | 10.389 | (4.40,-1.76) | (-5.87,-0.89) |
| kujiale_0203_kujiale_0203_15_3 | kujiale_0203 | 41 | 5.589 | (-6.97,5.57) | (-4.66,0.52) |
| kujiale_0203_kujiale_0203_16_3 | kujiale_0203 | 54 | 7.337 | (-6.71,1.60) | (-7.64,-3.49) |
| kujiale_0203_kujiale_0203_22_4 | kujiale_0203 | 62 | 6.906 | (-2.33,-0.56) | (-7.78,-2.92) |
| kujiale_0203_kujiale_0203_25_0 | kujiale_0203 | 47 | 6.711 | (-6.56,-0.36) | (-7.72,-2.87) |
| kujiale_0203_kujiale_0203_32_2 | kujiale_0203 | 59 | 7.192 | (-7.37,-0.36) | (-6.49,1.93) |
| kujiale_0203_kujiale_0203_43_1 | kujiale_0203 | 44 | 4.649 | (-3.13,4.06) | (-3.84,-2.29) |
| kujiale_0203_kujiale_0203_49_3 | kujiale_0203 | 63 | 7.323 | (-6.97,-0.87) | (-1.94,-5.04) |
| kujiale_0271_kujiale_0271_15_1 | kujiale_0271 | 67 | 11.672 | (-3.71,1.52) | (2.96,2.30) |
| kujiale_0271_kujiale_0271_24_4 | kujiale_0271 | 61 | 9.745 | (-2.66,3.01) | (4.27,-2.91) |
| kujiale_0271_kujiale_0271_7_3 | kujiale_0271 | 74 | 13.102 | (-0.47,3.51) | (-2.65,3.40) |

Every SR/OSR/NE/SPL number in the offline table was computed on exactly these 15 episodes (evaluator n=15 confirmed).
