# Synthetic Fork Visual Similarity Matrix (DINO ViT-S/16 cosine)

Lower = more visually distinct. The designed goal branches (goalA_img blue vs goalB_img green, and center:N vs center:W) should be < 0.6.

| view | center:N | center:E | center:W | center:S | goalA_img | goalB_img |
|---|---|---|---|---|---|---|
| center:N | 1.0 | 0.731 | 0.654 | 0.668 | 0.927 | 0.676 |
| center:E | 0.731 | 1.0 | 0.728 | 0.876 | 0.692 | 0.732 |
| center:W | 0.654 | 0.728 | 1.0 | 0.685 | 0.658 | 0.946 |
| center:S | 0.668 | 0.876 | 0.685 | 1.0 | 0.648 | 0.688 |
| goalA_img | 0.927 | 0.692 | 0.658 | 0.648 | 1.0 | 0.689 |
| goalB_img | 0.676 | 0.732 | 0.946 | 0.688 | 0.689 | 1.0 |
