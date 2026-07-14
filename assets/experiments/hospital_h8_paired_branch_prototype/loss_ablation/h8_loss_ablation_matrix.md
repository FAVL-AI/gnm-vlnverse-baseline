# H8 loss-ablation matrix — predicted [Δx,Δy] per (ablation, design, goal)

Baseline = untrained H7r candidate. Same shared o_d; only the goal image changes.

| ablation | design | condition | pred_dx | pred_dy | pred_angle | exp_angle | angle_err |
|---|---|---|---|---|---|---|---|
| baseline | h8_proto_01_corridor_tjunction | goalA | 0.0156 | -0.0045 | -16.1 | 71.8 | 88.0 |
| baseline | h8_proto_01_corridor_tjunction | goalB | 0.0163 | -0.0052 | -17.9 | -0.0 | 17.9 |
| baseline | h8_proto_02_samestart_fork | goalA | 0.0125 | -0.0032 | -14.5 | 1.0 | 15.6 |
| baseline | h8_proto_02_samestart_fork | goalB | 0.0138 | -0.0033 | -13.3 | -49.9 | 36.6 |
| A | h8_proto_01_corridor_tjunction | goalA | 0.0309 | 0.095 | 72.0 | 71.8 | 0.2 |
| A | h8_proto_01_corridor_tjunction | goalB | 0.1096 | -0.0009 | -0.5 | -0.0 | 0.5 |
| A | h8_proto_02_samestart_fork | goalA | 0.1111 | 0.0015 | 0.8 | 1.0 | 0.3 |
| A | h8_proto_02_samestart_fork | goalB | 0.0689 | -0.0792 | -49.0 | -49.9 | 0.9 |
| A+B | h8_proto_01_corridor_tjunction | goalA | 0.0171 | 0.1205 | 81.9 | 71.8 | 10.1 |
| A+B | h8_proto_01_corridor_tjunction | goalB | 0.1191 | -0.0176 | -8.4 | -0.0 | 8.4 |
| A+B | h8_proto_02_samestart_fork | goalA | 0.0959 | 0.0124 | 7.4 | 1.0 | 6.3 |
| A+B | h8_proto_02_samestart_fork | goalB | 0.0575 | -0.0752 | -52.6 | -49.9 | 2.7 |
| A+B+C | h8_proto_01_corridor_tjunction | goalA | 0.0335 | 0.0887 | 69.3 | 71.8 | 2.5 |
| A+B+C | h8_proto_01_corridor_tjunction | goalB | 0.1109 | -0.0066 | -3.4 | -0.0 | 3.4 |
| A+B+C | h8_proto_02_samestart_fork | goalA | 0.11 | 0.0056 | 2.9 | 1.0 | 1.9 |
| A+B+C | h8_proto_02_samestart_fork | goalB | 0.0665 | -0.0774 | -49.3 | -49.9 | 0.6 |
| A+B+C+E | h8_proto_01_corridor_tjunction | goalA | 0.0536 | 0.2318 | 77.0 | 71.8 | 5.2 |
| A+B+C+E | h8_proto_01_corridor_tjunction | goalB | 0.0988 | 0.0089 | 5.2 | -0.0 | 5.2 |
| A+B+C+E | h8_proto_02_samestart_fork | goalA | 0.0898 | 0.0203 | 12.8 | 1.0 | 11.7 |
| A+B+C+E | h8_proto_02_samestart_fork | goalB | 0.0659 | -0.0426 | -32.9 | -49.9 | 17.0 |