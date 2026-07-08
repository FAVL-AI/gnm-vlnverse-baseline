# Stage 3C plan (do not start until reviewed)

1. Add forward-clearance route scoring; prefer 3–5 m routes with
   corridor-like clearance profiles.
2. Compare one generated frame side-by-side with an original episode
   frame at a nearby pose; adjust camera height/FOV if clearly off.
3. Recreate the path-fix symlink + calibrate kujiale_0118 and
   kujiale_0203 with the same 1.000-verification method (their own 
   existing episodes as ground truth).
4. Generate +50–100 episodes across the three TRAIN scenes only, under
   seeded reproducible sampling; register every episode in a
   dataset_manifest update with checksums.
5. Stage 4: retrain on original 191 + generated; Stage 5: single test
   evaluation on frozen kujiale_0271 vs the reference
   SR 32.0 / OSR 56.0 / NE 5.58 / SPL 0.315.
