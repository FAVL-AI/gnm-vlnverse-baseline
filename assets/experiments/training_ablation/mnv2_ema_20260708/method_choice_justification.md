# Why We Used VLNVerse/VLNTube as a Controlled Adapted Subset

## 1. Scientific question
"Does EMA improve the current MobileNetV2-GNM baseline under a controlled
VLNVerse/VLNTube training/evaluation setup, and can the selected trained
checkpoint be validated in Isaac Sim with physically measured Collision
Rate?" This is NOT yet: full VLNVerse benchmark completion, full
VLNTube-scale language-instruction VLN, final robust hospital navigation,
or a safety/FleetSafe claim.

## 2. Original protocol (summary)
Large-scale video-derived path–instruction VLN data (VLNTube/YouTube-VLN);
language-conditioned evaluation with SR/OSR/NE/SPL-TL; VLNVerse adds
realistic embodied simulation and physics-aware metrics incl. Collision
Rate. The original protocol is broader than our controlled ablation.

## 3. Our adapted protocol
Documented four-scene subset; MobileNetV2-GNM as goal/image-conditioned
baseline; baseline vs EMA under identical split/seed/config/evaluator;
offline SR/OSR/NE/SPL; separate Isaac physics rollouts for Collision
Rate; exact episodes in `dataset_manifest.json`.

## 4. Why this adapted method
**A. Experimental control:** the supervisor asked for a MobileNetV2 + EMA
ablation; the full protocol would change data scale, language grounding,
scene distribution and physics complexity simultaneously.
**B. Compute/time realism:** the RTX 4080 Super handles controlled
MobileNetV2-GNM training and short Isaac rollouts; full-scale
generation/training should be staged.
**C. Causal attribution:** the subset isolates EMA — any change is
attributable to EMA, not data scale, backbone, language or physics.
**D. Safety and physical evidence:** offline VLN cannot measure Collision
Rate; Isaac chassis-contact rollout measures it directly.
**E. Research hygiene:** this project has already shown misleading claims
arise when replay, offline evaluation, and live physics are mixed —
offline and physics metrics are therefore deliberately separated.

## 5. What we gain from our method
Controlled baseline-vs-EMA comparison; reproducible split + episode
manifest; fast iteration; a clear keep/replace decision; real Isaac CR
rather than a fake offline zero; CUDA/W&B/MLOps traceability; a
professor-ready evidence package; a clean bridge to later full-benchmark
evaluation.

## 6. What the full original protocol would add
Larger-scale training data; stronger generalization evidence;
language-instruction alignment; scene- and task-level benchmark
comparability; better statistical power; stronger SR/OSR/NE/SPL claims;
benchmark-level comparison with other VLN methods; richer CR evaluation
across diverse scenes. But: it would no longer be a clean EMA-only
ablation unless redesigned; it needs more compute, more data generation,
stricter held-out splits; and language-pipeline validation before any VLN
(rather than image-goal) claim.

## 7. Why not the full protocol yet
The current task is the EMA ablation; the current dataset/evaluator setup
exists and is reproducible; the full protocol would confound the
ablation; EfficientNet was paused for the same control reason; the full
protocol is the next stage after the controlled ablation and manifest are
complete.

## 8. Challenges and failures that shaped this decision
- The offline evaluator prints CR=0.0 by construction — not a real
  collision metric; corrected to N/A offline + Isaac physics evaluation.
- The 4-scene / 15-episode held-out split is small and high-variance —
  results are preliminary.
- Yaw authority in Isaac is weak on curved routes (sphere-collider
  mecanum approximation) — physics smoke uses straight/low-curvature
  routes.
- Prior stop-authority threshold rules failed out-of-sample twice —
  demonstrating why held-out evaluation and precise claims matter.
- EMA 0.9999 is too slow for short runs (shadow lagged ~near init) —
  EMA 0.999 added as a decay-horizon sanity ablation.
- EfficientNet paused to prevent backbone confounding.
- More VLNVerse data: primarily training/validation expansion; final
  testing must remain held out (preferably scene-level).

## 9. Hypotheses going forward
H1. EMA may improve MobileNetV2-GNM if decay is matched to training
horizon. H2. More VLNVerse/VLNTube data improves generalization only with
scene/trajectory-level held-out evaluation. H3. Isaac Collision Rate will
expose failures invisible to offline SR/OSR/NE/SPL. H4. Full VLNVerse
protocol is necessary for benchmark-level claims. H5. Language-conditioned
VLN claims require reintroducing instruction following. H6. Curved-path
physics claims require fixing or explicitly modelling yaw/mecanum
behaviour.

## 10. Decision record
Keep the adapted subset for the controlled EMA ablation; measure CR via
Isaac physics rollout; no full-VLNVerse-benchmark claim; no VLNTube
language-instruction claim; expand data next for training/validation;
preserve final held-out testing; resume EfficientNet only after
MobileNetV2 + EMA is complete.

## 11. Paper/professor wording
"Our current use of VLNVerse/VLNTube is a controlled adapted protocol,
not a full benchmark submission. We use the documented subset to isolate
the MobileNetV2 + EMA training ablation, report standard offline VLN
metrics on held-out episodes, and separately measure Collision Rate
through Isaac Sim contact-aware rollouts. This design prioritizes causal
attribution and physical metric integrity before scaling to the full
VLNVerse/VLNTube protocol."
