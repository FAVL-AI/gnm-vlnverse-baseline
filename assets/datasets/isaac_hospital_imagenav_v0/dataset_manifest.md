# Isaac-Hospital-ImageNav-v0

Isaac-Hospital-ImageNav-v0 is an internal simulation dataset collected from our Isaac Sim hospital environment using the Yahboom front-facing RGB camera convention. It is not a public benchmark and does not constitute real-robot evidence.

Camera: Yahboom front-facing RGB camera (Isaac Sim) | Task: image-goal navigation / hospital live navigation

Episodes with bags: 24 | split (route/goal-level, provisional): {'train': 12, 'val': 4, 'test': 8, 'unassigned': 0}

| split | goals | episodes |
|---|---|---:|
| train | hospital_goal_A, hospital_fresh_short_F | 12 |
| val | hospital_goal_B, hospital_goal_C | 4 |
| test | hospital_holdout_short_D, hospital_holdout_medium_E, hospital_fresh_medium_G | 8 |

Regime rule: front-camera hospital data is NEVER mixed with the Kujiale top-down training regime except in an explicitly declared domain-adaptation experiment
