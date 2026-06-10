# CustomVLN-Office — Changelog

Branch: `feature/custom-vln-office`  
Purpose: independent Isaac Sim proof-of-method (no VLNVerse assets)

---

## Important distinction

This work is **entirely separate** from the official VLNVerse reproduction.

| | VLNVerse Reproduction | CustomVLN-Office |
|---|---|---|
| Branch | `gnm-vlnverse-baseline` | `feature/custom-vln-office` |
| Purpose | Official Track A benchmark | Independent proof-of-method |
| Scene assets | VLNVerse kujiale USD files | Isaac Sim USD primitives |
| Trajectories | VLNVerse collected data | Scripted + manual episodes |
| Official benchmark? | Yes — SR 20.0%, OSR 46.7%, NE 6.51 m | No — controlled demonstration |
| VLNVerse dependency | Required | None |

---

## 2026-06-09

### Initial CustomVLN-Office environment (`feat(gnm): add custom Isaac asset office navigation environment`)

**Scene:**
- 16 m × 10 m office/corridor layout
- Assets: Isaac Sim USD primitives (floor, walls, desks, chairs, cabinets, plants, shelf, meeting table, partition, lights, cameras)
- No VLNVerse kujiale USD files used

**Navigation tasks:**
- 8 episodes defined in `configs/custom_vln_office/tasks.yaml`
- 6 train (cvlo_ep001–cvlo_ep006), 2 val (cvlo_ep007–cvlo_ep008)
- Each episode: scripted waypoints, interpolated paths (10 steps/segment)

**Data collection:**
- Per-frame: RGB 480×360 JPEG, x/y/yaw, local waypoint label, action delta
- `traj_data.pkl`: position (T,2), yaw (T,), local_waypoints, rgb_paths, metadata
- `actions.jsonl`: frame_index, x, y, yaw, action_dx, action_dy, local_waypoint_x/y, rgb_image_path, distance_to_goal
- All metadata: `vlnverse_assets_used: false`

**Dry-run modes:**
- All scripts support `--dry-run` (no Isaac Sim required)
- Synthetic RGB frames (colour-gradient placeholders) in dry-run
- Complete dataset structure generated: `datasets/custom_vln_office/train/`, `datasets/custom_vln_office/val/`

**Scripts added:**
- `scripts/gnm/discover_isaac_assets.py` — probe Isaac Sim / Nucleus assets
- `scripts/gnm/create_custom_vln_office_scene.py` — build USD scene
- `scripts/gnm/collect_custom_vln_office_data.py` — collect RGB + labels
- `scripts/gnm/manual_custom_vln_office_drive.py` — keyboard manual drive
- `scripts/gnm/replay_custom_vln_office.py` — Isaac Sim replay with panels
- `scripts/gnm/evaluate_custom_vln_office.py` — dataset + nav metrics
- `scripts/gnm/run_custom_vln_office_demo.sh` — one-command dry-run demo

**Tests:**
- 15 tests in `tests/gnm/test_custom_vln_office.py` — all pass

**Reviewer docs:**
- `results/bo_reviewer_packet/12_custom_vln_office_independent_isaac_scene.md`
- `results/custom_vln_office/` — manifests, eval_summary.md, eval_summary.csv

---

## Pending

- Collect real RGB frames with Isaac Sim rendering (replace synthetic placeholders)
- Expand to 20–30 train episodes + 5 val episodes
- Fine-tune GNM on CustomVLN-Office data
- Evaluate and report CustomVLN-Office SR/NE metrics (clearly labelled as custom, not VLNVerse)
