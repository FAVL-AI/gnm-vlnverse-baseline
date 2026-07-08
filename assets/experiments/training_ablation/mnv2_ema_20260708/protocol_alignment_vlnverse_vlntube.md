# How Our VLNVerse/VLNTube Usage Compares to the Original Protocol

## 1. Original VLNVerse/VLNTube protocol
VLNTube / YouTube-VLN-style work constructs large-scale VLN data from
house-tour videos as path–instruction pairs and evaluates
language-conditioned navigation with standard VLN metrics (SR, OSR, NE,
SPL/TL). VLNVerse extends the problem toward versatile, embodied,
realistic simulation with physics-aware evaluation, and includes
Collision Rate as a physical interaction metric.

## 2. Our current adapted protocol
We use a controlled four-scene VLNVerse/VLNTube subset (kujiale_0092,
_0118, _0203, _0271; 238 train episodes / 15 held-out evaluation episodes
— exact list in `dataset_manifest.json`). The model is MobileNetV2-GNM
evaluated as a goal-conditioned (image-goal) visual navigation baseline;
language is not the active control signal. The 15-episode held-out split
makes offline results preliminary and high-variance. This is not yet the
full original VLNVerse benchmark protocol.

## 3. What is comparable
SR, OSR, NE and SPL are standard VLN-style navigation metrics and are
comparable in kind. The offline held-out evaluation fairly compares the
MobileNetV2 baseline vs EMA variants under one split/seed/config/
evaluator. Isaac physics rollout provides a real Collision Rate — as a
smoke physics evaluation until scaled to a full campaign.

## 4. What is not yet comparable
- Full VLNVerse benchmark completion cannot be claimed.
- Full VLNTube-scale training cannot be claimed.
- Language-instruction following cannot be claimed (the pipeline uses
  goal images, not language commands).
- Scene-level generalization cannot be claimed: the current holdout is
  trajectory-level within the same four scenes.
- Collision Rate cannot be claimed from the offline evaluator.

## 5. Why our adaptation is still valid
The controlled subset is exactly what a focused MobileNetV2 + EMA
ablation requires: same split, seed, config and evaluator across
conditions, so the comparison is internally fair. Isaac physics
evaluation adds contact-based Collision Rate that the offline evaluator
cannot provide. This is an incremental controlled experiment, not a full
benchmark claim.

## 6. Required wording for paper/report
"Our current use of VLNVerse/VLNTube is an adapted controlled subset for
MobileNetV2-GNM training and ablation. It should not be interpreted as a
full VLNVerse benchmark submission. We report standard offline VLN
metrics on a held-out split and separately report Isaac Sim physics
metrics, including Collision Rate, from contact-aware simulation
rollouts."
