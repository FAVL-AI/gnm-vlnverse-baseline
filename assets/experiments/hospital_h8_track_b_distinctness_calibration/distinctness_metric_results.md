# Track-B Distinctness Metric Results (per pair)

Methodology only. DINO cosine is the incumbent gate metric (threshold < 0.60); it is **not** changed here. Lower cosine = more distinct. SAME pairs should score HIGH, DISTINCT low; HARD_NEGATIVE (look-alikes) test whether a metric wrongly scores different-but-similar goals as SAME.

| pair | label | DINO | CLIP | aHash | SSIM | note |
|---|---|---|---|---|---|---|
| syn_R4_identity_N | SAME | 1.0 | 1.0 | 1.0 | 1.0 | identical frame (sanity anchor): center N == goalA(N) thumbn |
| syn_R1_northSame | SAME | 0.6858 | 0.7041 | 0.7031 | 0.6954 | north branch: junction-centre view vs close goal view (same  |
| syn_R2_northSame | SAME | 0.5878 | 0.5779 | 0.5938 | 0.4917 | north branch: junction-centre vs close goal view |
| syn_R3_northSame | SAME | 0.9259 | 0.9154 | 0.75 | 0.6505 | north branch: junction-centre vs close goal view |
| syn_R4_northSame | SAME | 0.7566 | 0.7774 | 0.7188 | 0.4585 | north branch: junction-centre vs close goal view |
| syn_R1_westSame | SAME | 0.6298 | 0.712 | 0.7344 | 0.8117 | west branch: junction-centre vs close goal view |
| syn_R4_westSame | SAME | 0.808 | 0.7524 | 0.5156 | 0.4892 | west branch: junction-centre vs close goal view |
| hosp_eastVend_nearfar | SAME | 0.9175 | 0.9182 | 0.9531 | 0.8132 | near vs far view of the SAME east vending area (same goal ob |
| hosp_lobbyVend_nearfar | SAME | 0.8327 | 0.8948 | 0.9375 | 0.7909 | near vs far view of the SAME lobby vending area |
| syn_R1_NvsW | DISTINCT | 0.7956 | 0.7737 | 0.9062 | 0.9481 | R1 gate pair: north (blue) vs west (green) branches, 90 deg  |
| syn_R2_NvsW | DISTINCT | 0.6163 | 0.7134 | 0.9375 | 0.8403 | R2 gate pair: north vs west branches |
| syn_R3_NvsW | DISTINCT | 0.6535 | 0.7257 | 0.8594 | 0.7272 | R3 gate pair: north vs west branches |
| syn_R4_NvsW | DISTINCT | 0.6912 | 0.7125 | 0.9688 | 0.7187 | R4 gate pair: north vs west branches |
| syn_R4_NvsE | DISTINCT | 0.6708 | 0.7038 | 0.875 | 0.6143 | north (blue,round) vs east (orange,boxy) branches |
| syn_R4_WvsS | DISTINCT | 0.6318 | 0.5891 | 0.6406 | 0.413 | west (green,pointed) vs south (red,columned) branches |
| hosp_eastVend_vs_waiting | DISTINCT | 0.46 | 0.7005 | 0.875 | 0.5477 | different rooms: east vending vs waiting seating |
| hosp_fork_vs_sidecorr | DISTINCT | 0.6841 | 0.9341 | 0.625 | 0.8031 | different zones: reception fork vs side corridor |
| hosp_recepJunction_AB | DISTINCT | 0.2898 | 0.2619 | 0.6875 | 0.1059 | reception junction two intended branches |
| hosp_waiting_vs_desk | DISTINCT | 0.2552 | 0.3166 | 0.75 | 0.2914 | waiting seating vs reception desk |
| whfull_p13_aisle_ends | HARD_NEGATIVE | 0.5864 | 0.8843 | 0.6094 | 0.2197 | two ENDS of the same straight aisle (look alike, different l |
| mshelf_p00_openfloor | HARD_NEGATIVE | 0.6664 | 0.8437 | 0.7656 | 0.3009 | open-hall probe: two perpendicular views of the same open fl |
| hosp_lookalike_AB | HARD_NEGATIVE | 0.3719 | 0.5245 | 0.375 | 0.4638 | designed look-alike confuser: visually similar, semantically |
| mshelf_p00_vs_p32 | HARD_NEGATIVE | 0.5816 | 0.7772 | 0.4062 | 0.2322 | two DIFFERENT open-floor probes (different location) that lo |
| whsimple_p00_perp | HARD_NEGATIVE | 0.6786 | 0.8684 | 0.4688 | 0.4537 | open warehouse hall: two perpendicular views look alike (ope |
| office_p03_perp | HARD_NEGATIVE | 0.6648 | 0.8757 | 0.4688 | 0.4426 | open office bullpen: two views look alike |
