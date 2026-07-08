# Reviewer-response notes — MobileNetV2 + EMA ablation

**C1. Why use Exponential Moving Average?**
EMA maintains a smoothed copy of model weights during training: instead of
evaluating only the final noisy SGD/Adam iterate, we evaluate an averaged
set of weights. It can reduce stochastic update noise and improve
stability, calibration, and generalization, and is a low-cost training
stabilizer rather than an architectural change.

**C2. Did other papers use EMA?**
Yes — as a general training technique. Weight averaging originates in
stochastic approximation (Polyak averaging), and EMA-style weight/teacher
averaging is established in deep learning:
- Polyak & Juditsky (1992), "Acceleration of Stochastic Approximation by
  Averaging," SIAM J. Control Optim., DOI: 10.1137/0330046.
- Tarvainen & Valpola (2017), "Mean Teachers are Better Role Models."
- Morales-Brotons, Vogels & Hendrikx (2024), "Exponential Moving Average
  of Weights in Deep Learning."
We test EMA as a lightweight training-stability ablation motivated by this
literature; we do not claim EMA is standard specifically in GNM/VLN.

**C3. Are the metrics the same as other papers?**
SR, OSR, NE, and SPL are standard VLN / embodied-navigation metrics
(R2R-style evaluation). SR: stopped close enough to the goal; OSR: passed
close enough at any point; NE: final distance to goal; SPL: success
penalized by path inefficiency. Collision Rate is not universal in classic
VLN papers; it is a physics-aware addition appropriate for VLNVerse-style
continuous simulation. In this report: SR, OSR, NE and SPL are reported
using the offline VLN evaluation harness. Collision Rate is not available
from this offline evaluator (collision-free by construction) and is
therefore marked N/A pending Isaac physics rollout evaluation.

**C4. More VLNVerse data: training or testing?**
Additional VLNVerse data will be generated primarily to expand training
and validation coverage. Final testing must remain held out, preferably at
scene level, to avoid train/test leakage. The current run uses the
controlled four-scene kujiale split (238 train / 15 held-out episodes).

**C5. Why was EfficientNet paused?**
See appendix_efficientnet.md: paused to avoid confounding the EMA
training-stability question with a backbone-capacity change.
