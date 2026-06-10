#!/usr/bin/env bash
# Manual test-drive demo helper.
# Prints launch commands, controls, output locations, and pipeline steps.

set -euo pipefail

cat <<'EOF'
================================================================
  GNM/VLNVerse — Manual Test Drive Demo Helper
================================================================

LAUNCH COMMANDS
---------------
Dry-run (no Isaac required — prints controls and output schema):
  python3 scripts/gnm/manual_testdrive.py --dry-run

CustomVLN-Office interactive drive:
  MODE=custom_office conda run -n isaac python scripts/gnm/manual_testdrive.py

VLNVerse scene (kujiale_0271) interactive drive:
  MODE=vlnverse SCENE=kujiale_0271 conda run -n isaac python scripts/gnm/manual_testdrive.py

CONTROLS
--------
  W          move forward
  S          brake / move backward
  A          rotate left
  D          rotate right
  Q          strafe left
  E          strafe right
  Space      stop
  G          mark current pose as GOAL
  P          save episode to disk
  R          reset episode (clear recording)
  Esc / X    exit

WHERE EPISODES ARE SAVED
------------------------
  CustomVLN-Office:
    datasets/manual_testdrive_custom_office/<timestamp>/
      rgb/000000.jpg  rgb/000001.jpg  ...
      traj_data.pkl
      actions.jsonl
      metadata.json

  VLNVerse:
    datasets/manual_testdrive_vlnverse/<scene_id>_<timestamp>/
      (same structure)

REPLAY A SAVED EPISODE
-----------------------
  python3 scripts/gnm/replay_manual_testdrive.py \
    --episode datasets/manual_testdrive_custom_office/<episode>

  python3 scripts/gnm/replay_manual_testdrive.py --dry-run

CONVERT TO GNM FORMAT
----------------------
  python3 scripts/gnm/convert_manual_testdrive_to_gnm.py \
    --input  datasets/manual_testdrive_custom_office \
    --output datasets/manual_gnm_format

  python3 scripts/gnm/convert_manual_testdrive_to_gnm.py --dry-run

⚠️  WARNING
-----------
Manual test-drive is data-collection and proof-of-pipeline evidence ONLY.
It is NOT an official VLNVerse Track A benchmark result.

Official Track A results remain:
  SR  = 20.0%
  OSR = 46.7%
  NE  = 6.51 m

Manual episodes must NOT be mixed into the official 238 train / 15 val split
unless explicitly converted and documented.

================================================================
EOF
