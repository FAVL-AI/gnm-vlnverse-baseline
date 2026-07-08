# Coordinate calibration report — Stage 3B (kujiale_0092)

**Result: closed-form calibration, verified at free-fraction 1.000.**

World→pixel: `col = (x_max − x)/scale`, `row = (y − y_min)/scale`,
scale 0.05 m/px, bounds from `occupancy.json` (which match the composed
stage's Isaac world bounds — y_min to 12 decimal places). Free space =
`occupancy.png > 128`. The x-axis is mirrored between world and pixel
space; this single fact is why every unmirrored convention failed.

Evidence chain: (1) stage bounds vs occupancy bounds; (2) top-down Isaac
render of the building footprint vs the map's exterior region (implied
the mirror); (3) decisive test — projecting every trajectory point of
all 66 existing kujiale_0092 episodes lands on free space at exactly
1.000 under the mirrored convention (0.30–0.59 under all others).
rooms.json polygons were inconclusive (offset from the wall raster) and
were not used.

Honest note: camera height 1.2 m was chosen, not recovered from the
original generator; the first generated route renders wall-heavy views —
route-quality (forward-clearance) scoring is queued for Stage 3C.
