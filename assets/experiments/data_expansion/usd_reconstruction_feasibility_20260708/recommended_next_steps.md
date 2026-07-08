# Recommended next steps (Stage 3B)

1. Recreate the path-fix symlink for the two other TRAIN scenes only
   (kujiale_0118, kujiale_0203); leave kujiale_0271 untouched.
2. Calibrate the occupancy→world transform: render frames at 3 known
   rooms.json polygon centroids with a horizontal camera; verify visible
   room type matches the polygon's room_type.
3. Build `scripts/gnm/generate_vlntube_episodes.py`: A* on occupancy.png
   between sampled free-space start/goal pairs; step the camera along
   the path in Isaac; write numbered frames + traj_data.pkl
   ({position (N,2), yaw (N,)}) matching the existing loader format.
4. Acceptance gate for "generation works": ONE episode from
   kujiale_0092 loads through the existing dataset code and renders a
   coherent frame sequence.
5. Then scale: target +50–100 episodes across the three train scenes;
   register every new episode in a dataset_manifest update; scene-level
   test split remains frozen.
6. Retrain (Stage 4) and compare against the Stage-1 scene-holdout
   reference (SR 32.0 / OSR 56.0 / NE 5.58 / SPL 0.315) on the untouched
   kujiale_0271 (Stage 5).
