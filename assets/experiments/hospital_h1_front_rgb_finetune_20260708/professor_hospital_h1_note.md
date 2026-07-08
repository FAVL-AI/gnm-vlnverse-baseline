# Professor note — Hospital H1: front-camera adaptation

Hospital H1 tests whether internal front-facing Isaac hospital data can
adapt the navigation model to the camera regime used by the live
Yahboom-style dashboard. This is a simulation-domain experiment, not
real-robot sim-to-real evidence yet.

Setup: Isaac-Hospital-ImageNav-v0 (24 episodes converted from our own
recorded rosbags; front-facing RGB), route/goal-level split — train
goals A/F (12), validation B/C (4, checkpoint selection only), test
D/E/G (8, fully held out, evaluated once per model). Fine-tune
initialised from the top-down incumbent's weights with a fresh
optimizer.

Result: the top-down-trained incumbent — expected to be out-of-domain
because it was trained on top-down Kujiale/VLNTube imagery and is being
evaluated on front-facing hospital camera imagery — reaches NE 3.14 m /
SPL 0.285 on the held-out goals. Twelve front-camera episodes of
fine-tuning bring the same architecture to NE 0.32 m / SPL 0.935
(SR/OSR are partially saturated by short routes and are caveated).
The measured domain gap and its closure are exactly what this
experiment was designed to expose. DriftGuard promoted the candidate
and VerdictPlane allowed the promotion — scoped to the hospital
internal simulation line only.

This aligns the model line with the live dashboard and the future
Yahboom sim-to-real path (Track E). Next: more diverse hospital
episodes (H2), harder held-out goals (H3), then language (Track B).
