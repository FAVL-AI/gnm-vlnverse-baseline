# Claim boundaries — Hospital H1
Hospital H1 tests whether internal front-facing Isaac hospital data can
adapt the navigation model to the camera regime used by the live
Yahboom-style dashboard. This is a simulation-domain experiment, not
real-robot sim-to-real evidence yet.
- NOT a full VLNVerse benchmark. NOT real-robot evidence. NOT a global
  GNM comparison. No top-down/front-camera data mixing.
- SR/OSR partially saturated on short routes (stated in the table).
- Fine-tune data are our own policy/scripted rollouts (imitation
  caution: distribution reflects prior controllers).
- n=8 held-out episodes; provisional dataset (24 episodes total).
- Promotion scope: hospital internal simulation line only.
