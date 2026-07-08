# Camera-model lock — Stage 3D

RULE (locked): all generated Kujiale/VLNTube training episodes use the
verified TOP-DOWN/nadir camera only — z = 2.4 m, focal 16 mm, 224×224,
image rotation rotateXYZ(0, 0, deg(yaw)) — the same convention as the
original VLNTube frames (verification: Stage 3C
camera_model_verification.md, pose-exact comparisons).

No first-person Kujiale training data is generated for the current
MobileNetV2-GNM model. The hospital live dashboard (Yahboom front RGB
camera) is a SEPARATE camera regime for the live ImageNav demo and its
frames are never mixed into Kujiale training data. Every episode's
metadata.json records the camera block; the expanded-batch validator
asserts z=2.4/focal 16/rotateXYZ(0,0,deg(yaw)) on every episode.
