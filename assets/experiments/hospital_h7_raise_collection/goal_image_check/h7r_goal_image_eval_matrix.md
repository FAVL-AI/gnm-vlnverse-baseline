# H7r goal-image eval matrix — scene-aligned vs fixed-placeholder goal

No training. OSR>=SR invariant holds by construction. Scene-aligned = each episode's own final recorded frame (the eval default that the committed results used); placeholder = fixed h2_weave_J for all episodes.

| model | split | goal_condition | n | SR | OSR | SPL | NE | nDTW |
|---|---|---|---|---|---|---|---|---|
| incumbent | test | scene_aligned | 2 | 0.000 | 1.000 | 0.000 | 15.43 | 0.078 |
| incumbent | test | placeholder | 2 | 0.000 | 1.000 | 0.000 | 16.90 | 0.060 |
| candidate | test | scene_aligned | 2 | 1.000 | 1.000 | 0.908 | 2.54 | 0.646 |
| candidate | test | placeholder | 2 | 1.000 | 1.000 | 0.952 | 2.09 | 0.696 |
| candidate | val | scene_aligned | 2 | 1.000 | 1.000 | 1.000 | 2.06 | 0.633 |
| candidate | val | placeholder | 2 | 1.000 | 1.000 | 1.000 | 1.78 | 0.652 |
| candidate | train | scene_aligned | 4 | 1.000 | 1.000 | 0.951 | 2.17 | 0.664 |
| candidate | train | placeholder | 4 | 1.000 | 1.000 | 1.000 | 1.67 | 0.713 |
| incumbent | val | scene_aligned | 2 | 0.000 | 1.000 | 0.000 | 15.08 | 0.080 |
| incumbent | val | placeholder | 2 | 0.000 | 1.000 | 0.000 | 17.10 | 0.058 |