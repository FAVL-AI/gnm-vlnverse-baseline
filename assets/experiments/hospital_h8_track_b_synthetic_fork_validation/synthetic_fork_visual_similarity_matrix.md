# Synthetic Fork Visual Similarity Matrix (DINO ViT-S/16 cosine)

Lower = more visually distinct. The designed goal branches (goalA_img blue vs goalB_img green, and center:N vs center:W) should be < 0.6.

| view | center:N | center:E | center:W | center:S | goalA_img | goalB_img |
|---|---|---|---|---|---|---|
| center:N | 1.0 | 0.839 | 0.79 | 0.846 | 0.697 | 0.606 |
| center:E | 0.839 | 1.0 | 0.821 | 0.952 | 0.613 | 0.578 |
| center:W | 0.79 | 0.821 | 1.0 | 0.853 | 0.625 | 0.644 |
| center:S | 0.846 | 0.952 | 0.853 | 1.0 | 0.638 | 0.6 |
| goalA_img | 0.697 | 0.613 | 0.625 | 0.638 | 1.0 | 0.734 |
| goalB_img | 0.606 | 0.578 | 0.644 | 0.6 | 0.734 | 1.0 |
