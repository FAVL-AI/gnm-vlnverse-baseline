# Route-quality policy — generated train batch

Applied per candidate route before rendering (generate_vlntube_batch.py,
POLICY dict; seed recorded per episode):
1. free-space validity: A* entirely on the occupancy free space eroded
   3 px (~0.15 m safety margin)
2. minimum wall clearance: distance-transform clearance ≥ 0.25 m at
   EVERY path point (min and median recorded per episode)
3. path length: 2.0–6.0 m
4. low-curvature preference: A* path length ≤ 1.5× start–goal distance
5. dedup: start/goal quantised to 6-px cells; duplicate pairs rejected
6. goal-frame content: rendered final frame std ≥ 15 (not black/empty),
   recorded as goal_frame_ok
7. forward-clearance/wall-facing checks: intentionally N/A — the
   verified camera model is top-down (see camera_model_verification.md)
8. scenes: train-side only; the generator refuses kujiale_0271 by
   assertion, and the batch validator independently re-checks
