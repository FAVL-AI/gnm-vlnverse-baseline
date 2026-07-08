# Coordinate calibration summary — all train scenes

Method (identical to the Stage 3B kujiale_0092 proof): project every
trajectory point of every existing episode of the scene onto the
occupancy map under `col=(x_max−x)/scale, row=(y−y_min)/scale` and
measure the fraction landing on free pixels (>128).

| Scene | Episodes projected | Free-fraction | Verdict |
|---|---:|---:|---|
| kujiale_0092 | 68 | **1.000** | PASS |
| kujiale_0118 | 63 | **1.000** | PASS |
| kujiale_0203 | 72 | **1.000** | PASS |

The x-mirror convention is universal across scenes. rooms.json polygons
were NOT used (known to be offset from the wall raster). kujiale_0271
was not calibrated or inspected — its calibration will use the same
method only if/when it is ever needed for evaluation rendering, which
the current offline evaluator does not require.
