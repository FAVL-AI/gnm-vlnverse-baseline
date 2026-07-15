# H8-S Limited Pilot — Mismatched-Goal Ablation (offline, distance axis)

**Scope:** offline probe on the **test** frame (`east_A`) `o_d`, swapping only the goal image. Conditions: correct near / correct far (own alcove), same-family wrong goal (val/midwest_B far image — same alcove, different corridor position), placeholder (cross-scene `h2_weave_J`). A goal-USING model changes the predicted action across conditions; a goal-collapsed model predicts ~the same action regardless.

(The rollout-based `h7r_mismatched_goal_ablation.py` needs `traj_data.pkl` trajectories and cannot run on the 3-frame limited set; this offline probe is the honest substitute. The full rollout ablation remains deferred to H8-M.)

| variant | correct_near mag (m) | correct_far mag (m) | same-family mag (m) | placeholder mag (m) | mag spread (m) | collapsed |
|---|---|---|---|---|---|---|
| baseline | 0.014 | 0.013 | 0.013 | 0.010 | 0.004 | True |
| A | 0.519 | 0.505 | 0.503 | 0.542 | 0.039 | False |
| A+B | 0.475 | 0.523 | 0.433 | 0.655 | 0.222 | False |
| A+B+C | 0.641 | 0.761 | 0.350 | 0.954 | 0.604 | False |
| A+B+C+E | 0.806 | 0.846 | 0.610 | 0.748 | 0.237 | False |

- **collapsed = True** means all four goal conditions produced action magnitudes within 0.02 m of each other (the goal image is effectively ignored).
- **correct near vs far** and **correct vs placeholder** magnitude deltas per variant:
  - `baseline`: near-vs-far delta 0.001 m; correct-vs-placeholder delta 0.002 m.
  - `A`: near-vs-far delta 0.014 m; correct-vs-placeholder delta 0.037 m.
  - `A+B`: near-vs-far delta 0.047 m; correct-vs-placeholder delta 0.132 m.
  - `A+B+C`: near-vs-far delta 0.120 m; correct-vs-placeholder delta 0.193 m.
  - `A+B+C+E`: near-vs-far delta 0.040 m; correct-vs-placeholder delta 0.098 m.

**Reading:** a limited-pilot goal-USE signal requires (a) near != far and (b) correct != placeholder. On one training frame this is memorisation-limited; interpret as a diagnostic, not a generalization claim. No promotion; incumbent retained.

