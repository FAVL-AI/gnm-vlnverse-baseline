# Isaac Sim Hospital Environment (standard experiment scene)

The Isaac Sim **Hospital** environment is the standard scene for all Isaac
experiments and demos in this repository.

## Source

```
https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd
```

Streamed on first use and cached locally by omni.client, so only the first
run downloads assets.

## How it is used

`scripts/gnm/isaac_live_trajectory_demo.py` references the hospital USD into
the stage, places the recorded VLNVerse Track A trajectory markers (start,
goal, breadcrumbs, robot) in the reception lobby, and captures:

- `assets/deck/isaac_sim_tracka_start_view_toward_goal.png` — first-person
  view from the start pose looking out to the goal
- `assets/deck/isaac_sim_tracka_trajectory_replay.png` — reception-lobby
  overview after the replay completes

Every run also exports the fully composed stage to:

- `assets/isaac/tracka_hospital_replay_stage.usda` — reopenable scene
  (hospital reference + markers + cameras)

## Layout notes (learned the hard way)

- The trajectory is centred on the world origin, which lands in the
  **reception lobby**.
- The lobby is small: the entrance vestibule at roughly (0, -6.5) is glass,
  and (5.5, -4.8) is already outside the building. Keep cameras on the
  start-to-goal sight line, below the ~3 m ceiling.
- The environment ships its own light rig; the demo adds only a dome light
  (intensity 1000) so markers never render black.

## Running

```bash
cd ~/robotics/gnm-vlnverse-baseline
DISPLAY=:0 ~/miniforge3/envs/isaac/bin/python -u scripts/gnm/isaac_live_trajectory_demo.py
```

(The `isaac` conda env exists at `~/miniforge3/envs/isaac` even though it
does not appear in `conda env list`.)
