# Stage 3B blockers register

1. RESOLVED — coordinate convention: x-mirror found and verified 1.000
   (see coordinate_calibration_report.md).
2. RESOLVED — hardcoded route landed on furniture after the 3-px safety
   erosion; replaced with seeded automatic free-pair selection with a
   near-straight (low-curvature) constraint.
3. OPEN — route view quality: the first generated route faces walls for
   much of its length. Stage 3C needs forward-clearance scoring when
   sampling start/goal pairs (reject routes whose forward ray hits an
   obstacle within ~1.5 m for most steps).
4. OPEN — camera height/FOV not recovered from the original data
   generator; 1.2 m assumed. Visual comparison against original frames
   recommended before mass generation.
5. MINOR — per-frame render loop costs ~12 orchestrator steps for the
   first frame then converges; ~19-frame episode renders in ~1 min.
