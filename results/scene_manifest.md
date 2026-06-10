# Scene Manifest — VLNVerse Scenes Used

## Public sources

| Resource | URL |
|----------|-----|
| Vision-Language Navigation Verse project page | https://sihaoevery.github.io/vlnverse/ |
| Scene assets (Hugging Face) | https://huggingface.co/datasets/Eyz/VLNVerse_scene |

Only the four required scenes were downloaded.
The full VLNVerse scene dataset is large (many scenes) and was not downloaded in full.
Scene Universal Scene Description (USD) files are not committed to this repository.

---

## Downloaded scenes

| Scene ID | Role in standard split | Role in scene holdout |
|----------|----------------------|-----------------------|
| `kujiale_0092` | train + val | train |
| `kujiale_0203` | train + val | train |
| `kujiale_0118` | train + val | train |
| `kujiale_0271` | train + val | **holdout test** |

### kujiale_0092

Apartment floor-plan with hallway, living room, large windows, and a dining area.
Training trajectories: 66.  Validation trajectories: 2.

### kujiale_0118

Apartment with corridor, wardrobe area, and open living space.
Training trajectories: 60.  Validation trajectories: 3.

### kujiale_0203

Multi-room apartment with kitchen, bedroom corridor, and bathroom areas.
Training trajectories: 65.  Validation trajectories: 3.

### kujiale_0271

Large apartment with distinct room layout — held out entirely in scene-holdout config.
Training trajectories: 47.  Validation trajectories: 7.

---

## Scene assets location (local, gitignored)

Scene USD files are stored under `datasets/vlntube/envs/` on the local machine.
They are gitignored and must be re-downloaded to reproduce:

```
datasets/vlntube/envs/kujiale_0092/start_result_navigation.usd
datasets/vlntube/envs/kujiale_0118/start_result_navigation.usd
datasets/vlntube/envs/kujiale_0203/start_result_navigation.usd
datasets/vlntube/envs/kujiale_0271/start_result_navigation.usd
```

Each scene folder also contains:
- `occupancy.json` / `occupancy.png` — floor-plan occupancy map
- `rooms.json` — room-level metadata
- `room_in_images.json` — room-to-image mapping

---

## Why only four scenes?

The full VLNVerse scene dataset contains many apartments.
For this experiment we selected four scenes that provide sufficient variety
(corridor, open plan, multi-room) while keeping data generation tractable
on a single RTX 4080 SUPER GPU with NVIDIA Isaac Sim.
