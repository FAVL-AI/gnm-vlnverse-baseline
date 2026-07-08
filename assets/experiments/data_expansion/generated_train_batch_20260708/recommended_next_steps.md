# Stage 3D plan (after review)

1. Resample goal poses whose rendered goal frame std < 15 before
   committing to a route (cheap: render goal frame first, then episode).
2. Scale to +50–100 episodes across the three train scenes (new seeds,
   dedup against the pilot batch).
3. Stage 4: retrain MobileNetV2-GNM on original 191 + generated
   episodes (same config/seed protocol); Stage 5: ONE evaluation on
   frozen kujiale_0271 vs SR 32.0 / OSR 56.0 / NE 5.58 / SPL 0.315.
