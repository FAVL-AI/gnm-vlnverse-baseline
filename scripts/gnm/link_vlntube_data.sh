#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: bash scripts/gnm/link_vlntube_data.sh /path/to/vlntube"
  exit 1
fi

SRC="$(readlink -f "$1")"
DST="datasets/vlntube"

mkdir -p "$DST"

for split in train val; do
  if [ ! -e "$SRC/$split" ]; then
    echo "ERROR: missing $SRC/$split"
    exit 1
  fi

  rm -rf "$DST/$split"
  ln -s "$SRC/$split" "$DST/$split"
done

if [ -e "$SRC/envs" ]; then
  rm -rf "$DST/envs"
  ln -s "$SRC/envs" "$DST/envs"
  ENVS_STATUS="$DST/envs  -> $SRC/envs"
else
  ENVS_STATUS="$DST/envs  -> not linked; Isaac visual replay will need VLNVerse USD env assets"
fi

echo "Linked:"
echo "  $DST/train -> $SRC/train"
echo "  $DST/val   -> $SRC/val"
echo "  $ENVS_STATUS"
echo
echo "Verify:"
echo "  python3 scripts/gnm/check_demo_ready.py"
echo "  python3 scripts/gnm/replay_gnm_demo.py --list-scenes"
