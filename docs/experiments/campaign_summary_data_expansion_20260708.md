# Campaign summary — scene-holdout, data expansion, governance, hospital dataset
**Branch:** data-expansion-scene-holdout (14 commits, 2e5709c → cd31fb7)

## Result table (all offline; CR = N/A — offline evaluator)
| # | Result | Key numbers | Status |
|---|---|---|---|
| 1 | Scene-holdout split | 191 train / 12 val / 50 test (kujiale_0271 frozen, scene-level) | validated |
| 2 | First scene-holdout baseline | SR 32.0 / OSR 56.0 / NE 5.58 / SPL 0.315 / TL 7.47 (n=50) | **incumbent reference** |
| 3 | EMA 0.999 repeat (same split) | SR 18.0 / OSR 50.0 / NE 5.91 / SPL 0.167 | rejected |
| 4 | Generated top-down pipeline | calibration 1.000 ×3 scenes; camera model verified (originals are TOP-DOWN); 130 eps, goal content 130/130 | validated, no perf claim |
| 5 | Expanded-data candidate (321 eps) | SR 26.0 / OSR 56.0 / NE 6.90 / SPL 0.247 / TL 9.32 | **rejected — negative result** |
| 6 | Governance | DriftGuard reject ×2; VerdictPlane deny ×2; Sentinel proxy-gap incidents | independent concurrence |
| 7 | Reference dataset audit | GNM/ViNT/NoMaD data mapped; all external sets require adapters | no superiority claims |
| 8 | Isaac-Hospital-ImageNav-v0 | 24 episodes, route-level split 12/4/8, converter proven | provisional, sim-only |
| 9 | Camera-state dashboard | live front-RGB demo; recorded episode final d2g 9.1 mm | acceptance-smoked |
| 10 | Hospital H1 (front-camera adaptation) | main evidence NE 3.14→0.32 m, SPL 0.285→0.935, nDTW 0.746→0.961 (n=8; SR/OSR saturated on short routes, treated cautiously); DriftGuard promote + VerdictPlane allow, scoped to the Isaac-Hospital-ImageNav-v0 simulation line; incumbent = camera-domain diagnostic only | **first promotion — internal sim, not real-robot, not full benchmark** |

## Claim-boundary table
| Claim | Status |
|---|---|
| Scene-level held-out baseline exists | VALID |
| EMA improves navigation | REJECTED (twice, scene-clean) |
| Generated matched-camera data improves generalization | REJECTED (Stage 4/5) |
| We beat GNM/ViNT/NoMaD | NEVER CLAIMED — banned |
| Full VLNVerse benchmark | NOT claimed |
| Real Yahboom sim-to-real | NOT claimed (Track E future) |
| Hospital promotion scope | Isaac-Hospital-ImageNav-v0 simulation line ONLY |
| CR from offline evaluator | FORBIDDEN — Isaac PhysX only |

## Key scientific findings
1. Original VLNTube frames are top-down — discovered by pose-exact
   re-rendering; reframes what the GNM learns (overhead floor appearance).
2. Dataset validity ≠ dataset usefulness: the expanded set passed every
   structural/camera gate yet reduced held-out SR by 6 pp. The model
   needs data matching route diversity and visual information structure
   of the original trajectories, not just camera geometry.
3. Validation loss is an unreliable proxy for held-out-scene navigation
   (EMA evidence, both splits).

## Validation summary
All campaign validators PASS (split, training, pilot batch [frozen
evidence; superseded by expanded], expanded set, expanded-data
training, reference audit, hospital dataset, governance cards).

## Known limitations
One held-out scene; 12-episode val split; offline metrics only for the
Kujiale line; hospital dataset provisional (24 episodes); generated
routes A*-smooth.

## Next-step recommendation (agreed order)
1) this push; 2) Hospital H1 (batch-convert 24 episodes; fine-tune vs
incumbent on held-out goals D/E/G); 3) route-diversity generation as
the follow-up to the negative result.
