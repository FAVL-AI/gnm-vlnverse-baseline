# H7r hospital pilot — diagnostic training summary (professor-ready)

**This is not a final hospital benchmark.** It is a small, controlled hospital-pilot training check to see whether the corrected scene-gated, raised-camera data can produce a measurable navigation signal.

## What was done
- Re-recorded 8 hospital routes (train 4 / val 2 / test 2) in the verified Isaac `hospital.usd` with the front camera raised +0.12 m (level horizon) — the lower-third occlusion of the first pilot is removed (0.0% black).
- One small diagnostic fine-tune: weights-only from the retained H1 incumbent, fresh optimizer, seed 42, checkpoint selected on the hospital validation split.
- Evaluated the incumbent and the candidate on the **same** hospital held-out test (forced data-root), plus sanity and out-of-domain diagnostics.

## Result (hospital held-out test, n=2)
SR = reached & stopped at goal; OSR = ever reached goal (≥ SR); SPL = success × path efficiency; NE = final distance to goal (m); nDTW = path match.

| | SR | OSR | SPL | NE (m) | nDTW |
|---|---|---|---|---|---|
| H1 incumbent | 0.00 | 1.00 | 0.00 | 15.4 | 0.08 |
| **H7r candidate** | **1.00** | **1.00** | **0.91** | **2.5** | **0.65** |

Both held-out route instances (turn + waiting) that the incumbent fails, the candidate reaches. The candidate also beats a procedural-scene (H6) reference model on the same test.

## Honest scope
- **Diagnostic only, not promoted.** n=2 held-out episodes, single seed, fixed placeholder goal image (this measures imitation fidelity, not goal-image conditioning).
- Out-of-domain (procedural H4) success stays 0 — the model is hospital-specialised; there is no catastrophic OOD break (navigation error actually improves).
- The incumbent was trained on the earlier occluded-camera hospital data, so part of its held-out failure is the raised-camera visual shift; the candidate also beating the H6 procedural model on the same test is the cleaner evidence it learned route behaviour.
- Conclusion: **the 8-episode raised-camera hospital pilot can train and yields a clear, correct-direction navigation signal.** This is the first hospital dataset candidate suitable for diagnostic review — and it justifies (only with approval) a larger 20/5/10 collection with multiple seeds before any promotion claim.