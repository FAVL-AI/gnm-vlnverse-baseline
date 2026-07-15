# Synthetic Fork Visual Similarity Matrix (DINO ViT-S/16 cosine)

Lower = more visually distinct. The designed goal branches (goalA_img blue vs goalB_img green, and center:N vs center:W) should be < 0.6.

| view | center:N | center:E | center:W | center:S | goalA_img | goalB_img |
|---|---|---|---|---|---|---|
| center:N | 1.0 | 0.675 | 0.696 | 0.568 | 0.885 | 0.671 |
| center:E | 0.675 | 1.0 | 0.748 | 0.78 | 0.665 | 0.736 |
| center:W | 0.696 | 0.748 | 1.0 | 0.635 | 0.694 | 0.883 |
| center:S | 0.568 | 0.78 | 0.635 | 1.0 | 0.578 | 0.654 |
| goalA_img | 0.885 | 0.665 | 0.694 | 0.578 | 1.0 | 0.703 |
| goalB_img | 0.671 | 0.736 | 0.883 | 0.654 | 0.703 | 1.0 |
