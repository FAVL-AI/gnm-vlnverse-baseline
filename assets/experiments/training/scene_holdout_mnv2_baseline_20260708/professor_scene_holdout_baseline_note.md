# Professor note — first scene-level held-out baseline

This is the first MobileNetV2-GNM baseline trained and evaluated under a
scene-level held-out split. The test scene kujiale_0271 was not used for
training, validation, tuning, or checkpoint selection. This is not a
full VLNVerse benchmark.

The previous result was trajectory-level held-out, so it was useful for
controlled ablation but not strong enough for scene generalization. The
new split holds out kujiale_0271 entirely as a test scene. Retraining
MobileNetV2-GNM under this split gives us the first honest scene-level
generalization baseline. This becomes the reference point for later data
expansion.

| Model | EMA | SR | OSR | NE (m) | SPL | Collision Rate | Weights | n |
|---|---|---:|---:|---:|---:|---|---|---:|
| MobileNetV2 baseline | none | **32.0** | **56.0** | **5.58** | **0.315** | N/A — offline | live model | 50 |
| MobileNetV2 + EMA | 0.999 | 18.0 | 50.0 | 5.91 | 0.167 | N/A — offline | EMA shadow | 50 |

EMA was repeated under the exact same scene-level held-out split, so any
difference between baseline and EMA is attributable to the EMA training
condition rather than a different dataset split. EMA 0.999 underperformed
the baseline on every metric on the held-out scene and is not promoted.
EMA 0.9999 was not rerun as a main candidate (prior evidence: decay too
slow for this training horizon); it remains available as a documented
sensitivity check only.

Numbers from this split must not be compared to the previous 15-episode
trajectory-level table — the split changed. Collision Rate remains
Isaac-only and is never taken from the offline evaluator. Test-scene
results were produced by exactly one evaluation per checkpoint after
training completed (protocol in comparison_scene_holdout.json;
checkpoint SHA-256s, CUDA verification, W&B run records and full
commands in this folder).

Next: scene-USD reconstruction and vistube trajectory generation for the
three train scenes only, then retraining with expanded data and
re-evaluating against this reference point on the untouched kujiale_0271.
