# H8-M Visual Similarity Matrix — DINO cosine (primary)

Goal images only. **DINO ViT-S/16 cosine is the primary distinctness metric**; aHash/SSIM are secondary (see CSV). Higher = more similar. Rows/cols grouped; `split` in brackets.

| goal view | recep_junction | recep_junction | recep_fork__go | recep_fork__go | recep_desk_mul | recep_desk_mul | side_corridor_ | side_corridor_ | waiting_seatin | waiting_seatin | lobby_vending_ | lobby_vending_ | east_vending_n | east_vending_n | lookalike_conf | lookalike_conf | placeholder_h2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| recep_junction__goal [test] | 1.00 | 0.28 | 0.32 | 0.33 | 0.49 | 0.19 | 0.33 | 0.29 | 0.22 | 0.16 | 0.22 | 0.19 | 0.23 | 0.22 | 0.17 | 0.24 | 0.35 |
| recep_junction__goal [test] | 0.28 | 1.00 | 0.45 | 0.55 | 0.38 | 0.38 | 0.40 | 0.51 | 0.35 | 0.45 | 0.45 | 0.39 | 0.37 | 0.41 | 0.29 | 0.51 | 0.49 |
| recep_fork__goalA [test] | 0.32 | 0.45 | 1.00 | 0.66 | 0.48 | 0.33 | 0.69 | 0.43 | 0.33 | 0.35 | 0.45 | 0.31 | 0.29 | 0.32 | 0.25 | 0.52 | 0.51 |
| recep_fork__goalB [test] | 0.33 | 0.55 | 0.66 | 1.00 | 0.48 | 0.41 | 0.57 | 0.55 | 0.40 | 0.47 | 0.54 | 0.42 | 0.41 | 0.44 | 0.35 | 0.56 | 0.54 |
| recep_desk_multiobj_ [trai] | 0.49 | 0.38 | 0.48 | 0.48 | 1.00 | 0.23 | 0.47 | 0.32 | 0.27 | 0.24 | 0.30 | 0.26 | 0.26 | 0.31 | 0.19 | 0.39 | 0.42 |
| recep_desk_multiobj_ [trai] | 0.19 | 0.38 | 0.33 | 0.41 | 0.23 | 1.00 | 0.26 | 0.70 | 0.46 | 0.47 | 0.78 | 0.87 | 0.85 | 0.84 | 0.77 | 0.49 | 0.48 |
| side_corridor__goalA [val] | 0.33 | 0.40 | 0.69 | 0.57 | 0.47 | 0.26 | 1.00 | 0.41 | 0.29 | 0.27 | 0.32 | 0.26 | 0.27 | 0.30 | 0.19 | 0.41 | 0.43 |
| side_corridor__goalB [val] | 0.29 | 0.51 | 0.43 | 0.55 | 0.32 | 0.70 | 0.41 | 1.00 | 0.50 | 0.60 | 0.81 | 0.74 | 0.73 | 0.78 | 0.47 | 0.62 | 0.70 |
| waiting_seating__goa [trai] | 0.22 | 0.35 | 0.33 | 0.40 | 0.27 | 0.46 | 0.29 | 0.50 | 1.00 | 0.77 | 0.54 | 0.51 | 0.47 | 0.50 | 0.40 | 0.35 | 0.40 |
| waiting_seating__goa [trai] | 0.16 | 0.45 | 0.35 | 0.47 | 0.24 | 0.47 | 0.27 | 0.60 | 0.77 | 1.00 | 0.61 | 0.49 | 0.46 | 0.50 | 0.39 | 0.51 | 0.47 |
| lobby_vending_nearfa [trai] | 0.22 | 0.45 | 0.45 | 0.54 | 0.30 | 0.78 | 0.32 | 0.81 | 0.54 | 0.61 | 1.00 | 0.84 | 0.80 | 0.82 | 0.59 | 0.59 | 0.61 |
| lobby_vending_nearfa [trai] | 0.19 | 0.39 | 0.31 | 0.42 | 0.26 | 0.87 | 0.26 | 0.74 | 0.51 | 0.49 | 0.84 | 1.00 | 0.91 | 0.88 | 0.71 | 0.51 | 0.55 |
| east_vending_nearfar [val] | 0.23 | 0.37 | 0.29 | 0.41 | 0.26 | 0.85 | 0.27 | 0.73 | 0.47 | 0.46 | 0.80 | 0.91 | 1.00 | 0.91 | 0.69 | 0.47 | 0.53 |
| east_vending_nearfar [val] | 0.22 | 0.41 | 0.32 | 0.44 | 0.31 | 0.84 | 0.30 | 0.78 | 0.50 | 0.50 | 0.82 | 0.88 | 0.91 | 1.00 | 0.67 | 0.52 | 0.54 |
| lookalike_confuser__ [hard] | 0.17 | 0.29 | 0.25 | 0.35 | 0.19 | 0.77 | 0.19 | 0.47 | 0.40 | 0.39 | 0.59 | 0.71 | 0.69 | 0.67 | 1.00 | 0.37 | 0.36 |
| lookalike_confuser__ [hard] | 0.24 | 0.51 | 0.52 | 0.56 | 0.39 | 0.49 | 0.41 | 0.62 | 0.35 | 0.51 | 0.59 | 0.51 | 0.47 | 0.52 | 0.37 | 1.00 | 0.73 |
| placeholder_h2_weave [hard] | 0.35 | 0.49 | 0.51 | 0.54 | 0.42 | 0.48 | 0.43 | 0.70 | 0.40 | 0.47 | 0.61 | 0.55 | 0.53 | 0.54 | 0.36 | 0.73 | 1.00 |
