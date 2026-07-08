# Weak-goal resampling report — Stage 3D

Stage 3C flagged 4/30 goal frames below the content threshold
(std < 15): gen_kujiale_0118_0700 (3.1), _0705 (2.2), _0707 (3.2),
_0709 (3.3) — **all four in kujiale_0118**, whose floor has large
featureless dark regions at the top-down camera scale.

Fix: a goal-content PRECHECK was added to the generator — the goal-pose
frame is rendered FIRST and the route is rejected if its std < 15,
before any episode frames are rendered. The four weak episodes were
deleted and replaced under this precheck.

Precheck effectiveness (candidates surviving the goal-content gate):
kujiale_0092 66/68, kujiale_0118 **37/74** (half rejected — confirming
the scene diagnosis), kujiale_0203 66/66. Result: **130/130 episodes in
the expanded set pass the goal-content check** (Stage 3C pilot was
26/30). The contact sheet shows post-resampling goal frames per scene.
