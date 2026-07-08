# Route-invariant stop recalibration report

Absolute predicted-distance gate: **REJECTED** (held-out failure, commit 8b625eb).

- **rel_min_margin** (recalibration_candidate): no parameterisation fired all tuning episodes without false stops
- **trend_reversal_prog** (recalibration_candidate): params {'rise_k': 3, 'min_prog': 1.0}, tune 3/3, held-out 2/2 [authcmp_D_baseline: fires@1.41m (early); authcmp_E_baseline: fires@2.4m (early)] transfer_ok=True
- **normalized_pred** (recalibration_candidate): params {'frac': 0.5}, tune 3/3, held-out 2/2 [authcmp_D_baseline: fires@0.173m (early); authcmp_E_baseline: fires@1.023m (early)] transfer_ok=True
- **hybrid_min_rise_motion** (recalibration_candidate): no parameterisation fired all tuning episodes without false stops
- **true_d2g_reversal** (privileged_diagnostic): params {'margin': 0.05}, tune 3/3, held-out 2/2 [authcmp_D_baseline: fires@1.479m (early); authcmp_E_baseline: fires@2.469m (early)] transfer_ok=True
- **absolute_dist_pred_gate** (REJECTED): rejected out-of-sample in commit 8b625eb: fired early on held-out reverse route (stop at true d2g 1.479/1.103 m), worse than no-stop baseline by +0.992/+0.608 m
- **live_domain_logistic_fit** (exploratory): deferred: only 3 independent tuning episodes; fitting would be in-sample noise. Requires a larger live episode set before it is meaningful.

Preferred candidate: **normalized_pred** {'frac': 0.5}

No improvement claim: authority rerun on fresh held-out goals is required first.

## Interpretation caveats

1. Baseline "final" distances (0.485/0.493 m) are bounded by episode
   length: the no-stop baseline never stops, so fixed-length logs
   understate real-world overshoot. Counterfactual comparisons here are
   therefore conservative toward stop rules.
2. Even the privileged ground-truth-d2g reversal rule fires early on both
   held-out routes: true distance-to-goal has local reversals during
   heading corrections, so "passed closest approach" detection from any
   single scalar trend is intrinsically noisy at this cadence.
3. normalized_pred is selected for a future held-out authority rerun with
   its E-route early stop (1.02 m) explicitly on record; selection is not
   an improvement claim.
