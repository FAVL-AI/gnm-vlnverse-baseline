# H8-S Limited Pilot — Standard Navigation Metrics (limited-only)

**These metrics are secondary for this pilot and are NOT computable offline on the committed 3-decision-frame set.** Every VLNVerse metric consumes a full ordered rollout trajectory (`actual_path` vs reference/goal), which requires a simulator rollout — not available from 3 static decision frames. They are reported **N/A (requires rollout)**, not fabricated. The main scientific gate for this pilot is the distance/stop-axis goal-sensitivity in `h8sl_training_report.md`.

| metric | value | reason |
|---|---|---|
| TL (trajectory length) | N/A | requires rollout trajectory |
| NE (nav error) | N/A | requires executed path vs goal |
| SR (success rate) | N/A | requires rollout + success threshold |
| OSR (oracle SR) | N/A | requires rollout path |
| SPL | N/A | requires rollout + shortest-path length |
| nDTW | N/A | requires executed vs reference path |
| CR (collision rate) | N/A offline | contacts=0 at collection; needs physics rollout |

Related committed facts (not a substitute for rollout metrics): all four source episodes recorded **0 collisions** and passed the scene gate at collection; the limited pilot's goal-conditioning signal is measured offline on the distance axis instead. Full rollout metrics are **deferred to H8-M** (simulator rollout on a genuinely distinct, embedding-gated set).

