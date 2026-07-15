# H8-M Route/Zone Design — Risk Register (DESIGN ONLY)

Planning only. No recording, no training, no closed-loop, no `CL_BOUND_XY` change. Risks are ranked; each has a mitigation and a gate that must clear before collection.

| # | risk | severity | affected zones | mitigation | gate |
|---|---|---|---|---|---|
| 1 | A drivable T-junction/fork within +/-6 m may not exist in hospital.usd (H8-S found only one straight alcove) | **critical** | recep_junction, recep_fork | render+drive search of the reception hall; if none, the true angular family is impossible in-envelope | Step C render+drive validation; acceptance requires >=1 true angular family |
| 2 | Target rooms may lie outside +/-6 m absolute (watchdog estops) | high | any distinct room | spawn-relocation INSIDE each room within its own +/-6 m; DEFER if room world-coords >6 m; never raise `CL_BOUND_XY` | envelope check (auto-DEFERRED here) |
| 3 | Distinct-room zones are all UNVALIDATED (no render, no drive) | high | all NEEDS_* zones | two-stage render+drive gate (caught west_C in H8-S) | Step C recorded-mode gate |
| 4 | Visual distinctness too weak (one-alcove repeat of H8-S) | high | waiting_seating, both vending, lookalike_confuser | CLIP/DINO cross-split gate; drop/merge/defer failures | Step B embedding distinctness |
| 5 | Target split scale (train>=12/val>=4/test>=6) not yet reachable | high | whole split | author multiple frames per validated zone; do NOT proceed if unmet | acceptance criteria |
| 6 | recep_fork duplicates recep_junction (same physical junction) | medium | recep_fork | dedupe at render time via embedding + geometry | Step B/C |
| 7 | Lookalike confuser could leak as a 'distinct' example | medium | lookalike_confuser | labelled hard-negative only; never counts toward distinctness | split-role rule |
| 8 | Proposed coordinates are hypothesized, not measured | medium | all | treat as design seeds; correct against the rendered scene | Step C |

**Overall:** the design is only as good as Step-C validation. If risk 1 does not clear (no in-envelope junction), H8-M cannot deliver a true angular branch-choice test and must be re-scoped rather than shipped as a larger H8-S.

