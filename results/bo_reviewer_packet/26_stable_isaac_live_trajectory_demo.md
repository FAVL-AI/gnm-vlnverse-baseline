# Stable Isaac Live Trajectory Demo

This demonstration provides a stable Isaac Sim live replay using real GNM/VLNVerse trajectory data rendered in a lightweight Isaac stage.

## Purpose

The full VLNVerse/Kujiale USD scenes can load in Isaac Sim, but on the current workstation they may trigger native Isaac/Kit instability inside `libcarb.assets.plugin.so` and `libcarb.tasking.plugin.so` during longer GUI sessions.

To support a reliable live demonstration, this script replays real VLNVerse trajectory data inside a lightweight Isaac stage containing:

- floor plane
- boundary walls
- simple obstacles
- start marker
- goal marker
- trajectory breadcrumbs
- moving robot marker

This separates live motion validation from heavy photorealistic USD asset debugging.

## Script

```bash
conda activate isaac
python scripts/gnm/isaac_live_trajectory_demo.py
