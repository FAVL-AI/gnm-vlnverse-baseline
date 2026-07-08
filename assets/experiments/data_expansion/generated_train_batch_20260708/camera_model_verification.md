# Camera model verification — Stage 3C

**Finding that changed the generator: the original VLNTube frames are
TOP-DOWN (bird's-eye), not first-person.** Rendering at the exact
recorded poses of original episode `kujiale_0092_kujiale_0092_0_3`
proved it: a horizontal 1.2 m camera produced first-person interior
views sharing no content with the originals; a nadir camera reproduced
the same furniture at the same poses (toilet/counter at idx 5-12, round
tray-table + bench at idx 36, armchair + plant at idx 47).

Verified parameters (grid-tested against originals):
- orientation: straight down, image rotation `rotateXYZ(0, 0, deg(yaw))`
  (offsets −90/+90/180 produce visibly wrong furniture layouts)
- height: z = 2.4 m (below ceiling), focal 16 mm (≈66° horizontal FOV)
  — matches original furniture scale (tray-table spans ~35% of width)
- image size: 224×224, matching original frames

Residuals (honest): small translation/rotation differences remain vs
originals (different renderer and possibly slight pose-index offsets);
lighting differs (our dome light vs the original renderer's baked look).
Comparison sheets: cam_verify (horizontal — mismatch), cam_verify3
(nadir grid — match), cam_rot (orientation offsets).

Consequence for route policy: first-person "wall-facing" penalties are
irrelevant for a top-down camera; quality is clearance, length,
curvature and goal-frame content variance. The Stage 3B smoke episode
(first-person camera) is superseded and was regenerated under the
verified model.
