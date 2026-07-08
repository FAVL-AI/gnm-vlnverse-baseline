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

Hospital H1 shows that matching the training camera regime to the
deployment camera regime matters. A model trained on top-down
Kujiale/VLNTube imagery can run as a diagnostic baseline in the
hospital scene, but fine-tuning on internal front-facing Isaac hospital
episodes substantially improves held-out hospital route quality.
Because the test set is small (n=8) and the routes are short relative
to the 3 m success radius, SR/OSR are partially saturated and treated
cautiously; **NE, SPL and nDTW provide the main evidence**:
NE 3.14 m → 0.32 m; SPL 0.285 → 0.935; nDTW 0.746 → 0.961.

Scope of the promotion (DriftGuard promote, VerdictPlane allow):
- Promoted: the front-RGB fine-tuned model for
  Isaac-Hospital-ImageNav-v0 simulation experiments only.
- Not promoted: a real-robot model, a full VLNVerse benchmark model,
  or a general navigation model.
This is an internal Isaac Sim hospital front-camera experiment; it is
not real-robot evidence and not a full VLNVerse benchmark. The
top-down incumbent is a camera-domain diagnostic baseline, not a fair
final competitor. No claim is made about real Yahboom sim-to-real
performance yet.

This aligns the model line with the live dashboard and the future
Yahboom sim-to-real path (Track E). Next: more diverse hospital
episodes (H2), harder held-out goals (H3), then language (Track B).
