# Professor update — data-expansion result and hospital dataset

We tested the hypothesis that adding matched-camera generated training
data improves scene-held-out generalization. It does not, under our
controlled protocol: the expanded 321-episode model scored SR 26.0 /
OSR 56.0 / NE 6.90 / SPL 0.247 vs the 191-episode incumbent's SR 32.0 /
OSR 56.0 / NE 5.58 / SPL 0.315 on the frozen test scene kujiale_0271
(one evaluation, n=50). The expanded generated dataset passed all
structural and camera-convention checks, but it did not improve
held-out scene performance. This shows that dataset validity and
dataset usefulness are different. The model needs training data that
matches not only the camera geometry, but also the route diversity and
visual information structure of the original trajectories.

The promotion machinery concurred independently: DriftGuard rejected
the candidate, VerdictPlane denied promotion, Sentinel recorded the
validation-vs-held-out proxy-gap incident.

Along the way we established: the original VLNTube frames use a
top-down camera (verified by pose-exact re-rendering — the trained
model navigates from overhead floor appearance); a calibrated,
validated generation pipeline (world-to-pixel proof at 1.000 on all
three train scenes); a reference dataset audit positioning our data
against GNM/ViNT/NoMaD (all external datasets require adapters; no
superiority claims); and Isaac-Hospital-ImageNav-v0 — an internal
front-camera simulation dataset (24 episodes, route-level splits) for
the hospital line. It is not real-robot evidence. Camera regimes are
now locked: Kujiale experiments are top-down; the hospital live demo
and future Yahboom work are front-facing robot RGB; the regimes stay
separate unless a domain-adaptation experiment is declared.

Next: fine-tune on our own hospital front-camera episodes (held-out
goals D/E/G), then revisit generation with route-diversity matched to
the original trajectories.
