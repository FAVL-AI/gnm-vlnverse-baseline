# Isaac-Hospital-ImageNav-v0 — small experiment plan

RQ-H: Does training on our own front-camera Isaac hospital episodes
improve live hospital ImageNav behaviour compared with a model trained
on top-down VLNTube/Kujiale data?

Experiment H1: fine-tune MobileNetV2-GNM on hospital front-camera train
episodes (goals A, F). Experiment H2: compare against the
Kujiale-top-down-trained incumbent inside the hospital scene (both
evaluated identically). Experiment H3: ONE evaluation on the fully
held-out test goals (D, E, G) — never used for tuning or selection.

Guards: no frame-level splits; no regime mixing without a declared
domain-adaptation experiment; no real-robot claims (simulation only);
split is provisional until more episodes are recorded (24 today).
