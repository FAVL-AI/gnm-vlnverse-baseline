# Stage 3C blockers register

1. RESOLVED — camera model: originals are TOP-DOWN; first-person
   generation (Stage 3B) superseded; verified model z=2.4/f16/nadir/
   rotZ(yaw) (camera_model_verification.md).
2. RESOLVED — calibration for 0118/0203: same mirrored transform,
   free-fraction 1.000 on both (63 and 72 episodes projected).
3. RECORDED — 4/30 goal frames below the std threshold (featureless
   floor patches at the goal pose). Kept and flagged goal_frame_ok=false
   in the manifest; Stage 3D should resample goals with low std before
   rendering the full episode.
4. MINOR — residual translation/lighting differences vs original
   renderer (documented; acceptable for augmentation, monitored at
   Stage 4 training).
