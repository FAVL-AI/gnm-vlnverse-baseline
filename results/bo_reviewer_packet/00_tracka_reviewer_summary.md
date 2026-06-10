# Track A Reviewer Summary — GNM-VLNVerse Stop-Policy Study

This packet summarises the staged Track A results for the GNM-VLNVerse baseline and stop-policy improvements.

## Core claim

The original GNM-VLNVerse baseline reaches the goal region more often than it successfully stops. Baseline SR is 20.0%, while OSR is 46.7%, showing that many failures are stop-policy failures rather than pure navigation failures.

A geometry-aware oracle stop rule recovers the full 46.7% SR upper bound, but it uses ground-truth geometry and is therefore diagnostic only. Deployable runtime stop policies must use only model/runtime signals.

The strongest deployable held-out method so far is the temporal neural stop head, which improves SR from 20.0% to 33.3% using only runtime GNM signals.

## Result ladder

| Version | Method                             | Train/Eval protocol   |           SR |   OSR |     NE (m) | Key conclusion                                         |
| ------- | ---------------------------------- | --------------------- | -----------: | ----: | ---------: | ------------------------------------------------------ |
| v0.1    | GNM baseline + Isaac live demo     | val                   |        20.0% | 46.7% |       6.51 | Baseline reproduced and live Isaac demo works          |
| v0.2    | Stop diagnostics + geometry oracle | diagnostic            | 46.7% oracle | 46.7% | 3.79 proxy | Stop policy is a major bottleneck                      |
| v0.3    | Deployable hand-tuned stop gates   | val                   |   26.7% best | 26.7% |       5.34 | Hand-tuned waypoint gate improves SR but collapses OSR |
| v0.4    | Stop-policy calibration sweep      | val                   |   26.7% best | 26.7% |       5.34 | Scalar threshold tuning cannot close the oracle gap    |
| v0.5    | Logistic learned stop head         | val-trained prototype |        26.7% | 46.7% |       6.09 | Prototype preserves OSR but is not held-out            |
| v0.6    | Logistic stop head train→val       | train → val           |        20.0% | 46.7% |       6.51 | Simple logistic calibration does not generalise        |
| v0.7    | Temporal neural stop head          | train → val           |    **33.3%** | 33.3% |   **4.47** | Best deployable held-out method so far                 |

## Important diagnostics

### 1. Baseline gap

* Baseline SR: 20.0%
* Baseline OSR: 46.7%
* Baseline NE: 6.51m

This indicates the agent often enters the goal region but fails to stop successfully.

### 2. Distance head calibration

The distance head has weak predictive usefulness for stopping. Its predicted distance has very low correlation with the true target distance, making fixed distance thresholds unreliable.

### 3. Geometry-aware oracle

The geometry-aware stop diagnostic reaches 46.7% SR, matching the baseline OSR. This proves there is recoverable performance if the stopping decision improves.

### 4. Hand-tuned waypoint gate

The best hand-tuned waypoint-norm gate reaches 26.7% SR, but OSR collapses to 26.7%. This means the gate often stops too early.

### 5. Logistic stop head

A val-trained logistic prototype can match 26.7% SR while preserving OSR, but under a proper train→val protocol it returns to baseline SR. This shows simple logistic calibration is insufficient for generalisable stopping.

### 6. Temporal neural stop head

The temporal neural stop head uses a short runtime history of:

* predicted distance,
* waypoint norm,
* rolling means,
* short-term trends.

It is trained on Track A train and evaluated on held-out Track A val. It improves held-out deployable SR to 33.3%, outperforming the baseline, hand-tuned gates, and logistic stop head.

## Current best deployable result

| Method                    |        SR |   OSR |   NE (m) | TL (m) | Stop fired | Mean stop step |
| ------------------------- | --------: | ----: | -------: | -----: | ---------: | -------------: |
| Temporal neural stop head | **33.3%** | 33.3% | **4.47** |   4.24 |      13/15 |           23.6 |

## Remaining headroom

The temporal neural stop head improves held-out SR but still falls short of the 46.7% geometry-aware oracle upper bound. This leaves 13.4 percentage points of recoverable SR.

## Paper-ready takeaway

The study shows that the GNM-VLNVerse Track A baseline is limited by stopping reliability. Scalar thresholds and simple logistic calibration do not generalise well. A temporal neural stop head trained on runtime traces improves held-out deployable SR from 20.0% to 33.3%, demonstrating that short-term runtime history contains useful stopping evidence. The remaining gap to the 46.7% oracle suggests future work should improve temporal supervision, calibration, and sequence modelling.
