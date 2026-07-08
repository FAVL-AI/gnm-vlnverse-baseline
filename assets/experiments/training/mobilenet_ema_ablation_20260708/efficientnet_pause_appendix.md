# Appendix: Why EfficientNet Was Paused

EfficientNet was paused to preserve a controlled ablation design. The
current experiment is intended to test whether Exponential Moving Average
improves the existing MobileNetV2-based GNM baseline. Introducing
EfficientNet at the same time would change the backbone capacity,
parameterization, feature hierarchy, and computational profile, making it
difficult to determine whether any performance change came from EMA or
from the stronger backbone.

MobileNetV2 remains the correct baseline for this stage because it is
lightweight, already integrated into the current training pipeline, and
suitable for controlled comparison under the available compute budget.
The EMA experiment does not change the navigation architecture; it only
evaluates whether a smoothed copy of the MobileNetV2-GNM weights improves
training stability and evaluation performance.

EfficientNet will be resumed after the MobileNetV2 baseline and
MobileNetV2 + EMA ablation are fully trained, evaluated, and compared
using the same VLNVerse metrics: Success Rate, Oracle Success Rate,
Navigation Error, Success weighted by Path Length, and Collision Rate.
This sequencing avoids confounding backbone comparison with
training-stabilization effects.
