# Paper Results Table — Track A GNM-VLNVerse Stop Policy

## LaTeX table

```latex
\begin{table*}[t]
\centering
\small
\caption{
Track A GNM-VLNVerse stopping results. SR denotes final success rate, OSR denotes oracle success rate, and NE denotes navigation error. Diagnostic oracle methods use ground-truth geometry and are not deployable. Deployable methods use only runtime GNM signals.
}
\label{tab:tracka_stop_policy_results}
\begin{tabular}{l l c c c p{5.2cm}}
\toprule
\textbf{Method} & \textbf{Protocol} & \textbf{SR $\uparrow$} & \textbf{OSR $\uparrow$} & \textbf{NE $\downarrow$} & \textbf{Key observation} \\
\midrule
GNM baseline & val & 20.0 & 46.7 & 6.51 & Reaches the goal region more often than it successfully stops. \\
Stop-threshold sweep & val & 20.0 & 46.7 & 6.51 & Distance-threshold tuning does not recover the stop gap. \\
Geometry-aware oracle stop & diagnostic & 46.7 & 46.7 & 3.79 & Confirms that the missing performance is recoverable through better stopping. \\
Hand-tuned waypoint gate & val & 26.7 & 26.7 & 5.34 & Improves SR, but collapses OSR due to premature stopping. \\
Logistic stop head & train $\rightarrow$ val & 20.0 & 46.7 & 6.51 & Simple calibrated stopping does not generalise. \\
Temporal neural stop head & train $\rightarrow$ val & \textbf{33.3} & 33.3 & \textbf{4.47} & Best deployable held-out result using only runtime GNM signals. \\
\bottomrule
\end{tabular}
\end{table*}
```

## Paper paragraph

The Track A results reveal that the GNM-VLNVerse baseline is limited by stopping reliability rather than only path following. The baseline achieves 20.0% final success rate (SR) but 46.7% oracle success rate (OSR), indicating that the agent often enters the goal region without executing a successful stop. A geometry-aware oracle stop rule recovers the full 46.7% SR upper bound, confirming that improved stopping can recover substantial performance; however, this oracle uses ground-truth geometry and is diagnostic only. Deployable scalar stopping rules are insufficient: distance-threshold tuning does not improve SR, and the best hand-tuned waypoint gate improves SR to 26.7% but collapses OSR to 26.7% due to premature stopping. A logistic stop head trained on Track A train and evaluated on held-out validation also fails to improve beyond the 20.0% baseline SR. In contrast, the temporal neural stop head uses only runtime GNM signals and improves held-out deployable SR to 33.3%, reducing NE to 4.47m. This demonstrates that short-term runtime history contains stopping evidence that scalar thresholds and simple logistic calibration fail to exploit, while the remaining gap to the 46.7% oracle upper bound motivates richer temporal supervision and sequence modelling.

## One-line contribution claim

A temporal neural stop head trained on Track A train and evaluated on held-out Track A validation improves deployable GNM-VLNVerse stopping from 20.0% to 33.3% SR using only runtime GNM signals.
