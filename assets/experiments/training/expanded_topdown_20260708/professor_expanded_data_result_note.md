# Professor note — expanded top-down training data: scene-held-out result

The expanded-data model was trained with 191 original plus 130 generated
top-down train-side episodes and evaluated once on the frozen
scene-held-out test scene kujiale_0271. This tests the effect of
matched-camera generated training data. It is not a full VLNVerse
benchmark submission.

| Model | Train eps | SR | OSR | NE (m) | SPL | TL (m) | CR | n |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| Incumbent baseline | 191 | **32.0** | 56.0 | **5.58** | **0.315** | 7.47 | N/A — offline | 50 |
| Expanded candidate | 321 | 26.0 | 56.0 | 6.90 | 0.247 | 9.32 | N/A — offline | 50 |

**Result: the expanded-data candidate is NOT promoted.** SR fell 6 pp,
SPL fell 0.068, NE worsened by 1.32 m, and trajectories lengthened —
the pre-registered interpretation applies: the generated data increased
volume but not useful distributional coverage. The incumbent 191-episode
baseline remains the accepted reference.

Governance (independent, from exported evidence): DriftGuard =
reject_candidate (SR/SPL/NE checks all fail); VerdictPlane promote_model
= deny; Sentinel incident = scene_holdout_generalization_failure.

Why this is a useful result, not a failure of process: the pipeline did
exactly what it was built to do — a one-shot frozen-scene test caught
that plausible-looking generated data (130/130 goal-content pass,
perfect loader compatibility, matched camera) does not automatically
transfer. Leading hypotheses for Stage 3E+ follow-up: (1) generated
routes are A*-smooth and information-poor compared with original
human-tour-style trajectories (straighter, fewer view changes);
(2) train-scene coverage was already saturated at 191 episodes for this
tiny 4-scene world; (3) the 12-episode val split cannot select between
models that differ mainly on unseen-scene behaviour. Each is testable.
