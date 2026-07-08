# Next: Stage 4 / Stage 5
1. Stage 4: retrain MobileNetV2-GNM on original 191 + 130 generated
   train episodes (same config/seed protocol; val = the same 12
   episodes; checkpoint selection on val only). Data root: a combined
   symlink tree (original train + vlntube_generated/train).
2. Stage 5: evaluate ONCE on frozen kujiale_0271 (--split test) and
   compare against SR 32.0 / OSR 56.0 / NE 5.58 / SPL 0.315.
3. Report either outcome honestly; export updated MLOps run cards and
   let DriftGuard judge the expanded-data candidate vs the incumbent.
