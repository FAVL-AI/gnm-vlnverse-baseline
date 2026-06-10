# CustomVLN-Office

**CustomVLN-Office is separate from the official VLNVerse reproduction.**

It uses Isaac Sim assets and our own navigation tasks. It does not use VLNVerse scenes, trajectories, or labels.

---

## What it is

A 16 m × 10 m office/corridor navigation environment built entirely from Isaac Sim USD primitives. We scripted 8 episodes (6 train, 2 val) with our own waypoints, collected x/y/yaw + RGB frames, and derived ground-truth local waypoint labels from consecutive trajectory poses.

**This is a proof-of-method**, not an official benchmark result.

---

## What is NOT used from VLNVerse

- No kujiale scene USD files
- No VLNVerse trajectory pkl files
- No VLNVerse episode metadata or instructions
- No VLNVerse evaluation splits
- No VLNVerse RGB frames

---

## Official VLNVerse result (separate track)

The official GNM/VLNVerse reproduction lives on branch `gnm-vlnverse-baseline`:

- SR 20.0%, OSR 46.7%, NE 6.51 m (Track A baseline)
- 238 train + 15 val trajectories
- Scenes: kujiale_0092, kujiale_0118, kujiale_0203, kujiale_0271

CustomVLN-Office performance **cannot be compared** with this result.

---

## Quick start (no Isaac Sim)

```bash
# Asset discovery dry-run
python3 scripts/gnm/discover_isaac_assets.py --dry-run

# Scene creation dry-run (writes USDA text stub)
python3 scripts/gnm/create_custom_vln_office_scene.py --dry-run

# Data collection dry-run (generates synthetic dataset)
python3 scripts/gnm/collect_custom_vln_office_data.py --dry-run

# Full demo
bash scripts/gnm/run_custom_vln_office_demo.sh
```

## Isaac Sim (full)

```bash
conda run -n isaac python scripts/gnm/create_custom_vln_office_scene.py
conda run -n isaac python scripts/gnm/collect_custom_vln_office_data.py
EPISODE=cvlo_ep003 conda run -n isaac python scripts/gnm/replay_custom_vln_office.py
conda run -n isaac python scripts/gnm/manual_custom_vln_office_drive.py
```

---

## Files

| Path | Description |
|------|-------------|
| `configs/custom_vln_office/tasks.yaml` | 8 navigation episodes |
| `assets/custom_vln_office/scene_layout.usda` | USD scene (dry-run stub / Isaac Sim full) |
| `datasets/custom_vln_office/` | Collected episode data |
| `results/custom_vln_office/` | Manifests, eval summary |
| `results/bo_reviewer_packet/12_custom_vln_office_independent_isaac_scene.md` | Reviewer evidence doc |
| `CHANGELOG_CUSTOM_VLN_OFFICE.md` | This project's history |

---

## Tests

```bash
python3 -m pytest tests/gnm/test_custom_vln_office.py -v
```

15 tests, all passing (dry-run mode, no Isaac Sim required).
