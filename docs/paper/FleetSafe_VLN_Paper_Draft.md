# FleetSafe-VLN: Safety-Certified Visual-Language Navigation with Isaac Sim and Yahboom ROSMASTER M3 Pro

**Status: Working Draft — not for citation yet. Results pending physical robot closure.**

---

## Abstract

We present **FleetSafe-VLN**, a safety-certified visual-language navigation (VLN) benchmark and runtime system that extends VLNVerse and the VLNTube data-generation pipeline with formal safety guarantees, a physical robot target, and a reproducible dashboard. FleetSafe-VLN combines Isaac Sim simulation, ROS 2 integration, GNM/ViNT/NoMaD visual-navigation backbones, and a Control Barrier Function Quadratic Programming (CBF-QP) safety shield. The robot target is the Yahboom ROSMASTER M3 Pro mecanum-wheel platform. Unlike prior VLN work that demonstrates navigation success rate alone, FleetSafe-VLN produces per-timestep safety certificates and a three-tier evidence hierarchy: certificate validity, trajectory optimality, and real-robot closure. All benchmark runs, safety logs, and dashboard states are captured as reproducible evidence bundles.

---

## 1. Introduction

Visual-language navigation (VLN) tasks require a robot to follow natural language instructions while navigating through a scene. VLNVerse and VLNTube have established strong simulation pipelines (USD scenes, scene graphs, walkable trajectories, instruction generation) but neither provides a certified safety layer or a physical deployment target beyond the simulation.

FleetSafe-VLN addresses three gaps:
1. **No safety guarantee**: existing VLN systems may physically harm humans or collide with obstacles even when navigation succeeds at the VLN metric level.
2. **No real-robot closure**: simulation-only results are not sufficient for hospital or warehouse deployment claims.
3. **No reproducible evidence**: existing papers report aggregate metrics without per-run verifiable certificates.

FleetSafe-VLN provides all three.

---

## 2. Related Work

**VLNVerse** (Lin et al.): Isaac Sim-based VLN benchmark with 4,000+ scenes, fine/coarse grained tasks, and the IAmGoodNavigator demo runner. FleetSafe-VLN uses VLNVerse as the benchmark reference and IAmGoodNavigator as the demo loader.

**VLNTube** (william13077/VLNTube): Data-generation pipeline converting USD scenes to scene graphs, walkable points, planned trajectories, and RGB/depth sequences via Isaac Sim rendering. FleetSafe-VLN indexes VLNTube's scene_graph, vistube, instube, and datatube modules and extends its outputs with CBF-QP safety labels.

**GNM/ViNT/NoMaD** (Shah et al., Sridhar et al.): General navigation models that consume image sequences and produce nominal velocity commands. FleetSafe-VLN wraps these as GNMAdapter with a 5-frame ring buffer and mock fallback.

**CBF-QP** (Ames et al.): Control Barrier Functions enforce safety constraints as a QP post-filter on the nominal velocity. FleetSafe-VLN's CBF-QP shield intercepts u_nom and returns a certified u_safe with per-timestep proof.

---

## 3. System Overview

```
Natural Language Instruction
        ↓
Language Grounding (VLN parser)
        ↓
Subgoal / Waypoint
        ↓
GNM / ViNT / NoMaD → u_nom  (nominal velocity command)
        ↓
FleetSafe CBF-QP Shield → u_safe  (certified safe command)
        ↓
/cmd_vel → Yahboom ROSMASTER M3 Pro  (real or simulated)
```

The system runs in three modes:
- `none`: baseline, u_safe = u_nom (no shield)
- `log_only`: shield runs but does not modify u_nom, logs interventions
- `cbf_qp`: shield modifies u_safe to maintain safety invariants

---

## 4. Data and Simulation

### 4.1 VLNVerse Episodes

IAmGoodNavigator provides 10 fine-grained and 10 coarse-grained demo episodes. Each episode includes:
- Start position and rotation
- Natural language instruction
- Reference path (waypoints)
- Goal position and radius
- Scene ID (e.g., `vlnverse/kujiale_0010`)

Download via `bash scripts/setup_iamgoodnavigator.sh --download`.

### 4.2 VLNTube Pipeline

VLNTube converts USD scenes to training data through four stages:
1. **scene_graph**: summarize objects and spatial relationships
2. **vistube**: sample walkable points, plan paths, render RGB/depth via Isaac Sim
3. **instube**: generate navigation instructions using Gemini vision API
4. **datatube**: export to Parquet/JSONL training format

FleetSafe indexes all four modules. Real data is present:
- `datasets/vlntube/prebuilt_data/`: trajectory Parquet + RGB/depth npy files
- `datasets/vlntube/room_meta/`: collision room metadata (Eyz/SceneMeta)
- `datasets/vlntube/scene_graph/`: scene summary zip (Eyz/SceneSummary)

---

## 5. GNM/ViNT/NoMaD Backbones

The `GNMAdapter` class (`fleetsafe_vln/backbones/gnm_adapter.py`) provides:
- 5-frame context ring buffer (matches GNM model input)
- Mock fallback when model weights are unavailable
- `predict(obs_images, goal_image) → (u_nom_vx, u_nom_wz)` API

Supported models: `gnm`, `vint`, `nomad`.

---

## 6. FleetSafe Safety Shield

### 6.1 CBF-QP

The CBF-QP shield (`fleetsafe_vln/safety/cbf_qp_shield.py`) solves:

```
min ||u - u_nom||²
s.t. Lf h(x) + Lg h(x) u + α h(x) ≥ 0
```

where `h(x) = d_human - d_safe` enforces minimum human-distance constraint.

### 6.2 Safety Certificates

The certificate logger (`fleetsafe_vln/safety/certificate_logger.py`) writes per-timestep JSONL:
```json
{"ts": 1234567890.0, "h": 0.42, "u_nom": [0.3, 0.1], "u_safe": [0.15, 0.05], "cbf_active": true, "qp_status": "optimal", "cert_safe": true}
```

### 6.3 Three Certificate Tiers

- **Tier 1 — Certificate validity**: `cert_safe = true` for every timestep
- **Tier 2 — Trajectory optimality**: navigation success rate ≥ baseline
- **Tier 3 — Real-robot closure**: physical Yahboom M3 Pro completes corridor

---

## 7. ROS 2 and Yahboom M3 Pro Deployment

Robot target: **Yahboom ROSMASTER M3 Pro** — mecanum wheel, depth camera, dual LiDAR options, Ubuntu/ROS 2, 12V Li-ion.

Key topics:
| Topic | Type | Direction |
|---|---|---|
| `/camera/image_raw` | sensor_msgs/Image | in |
| `/odom` | nav_msgs/Odometry | in |
| `/tf` | tf2_msgs/TFMessage | in |
| `/cmd_vel` | geometry_msgs/Twist | out |
| `/scan` | sensor_msgs/LaserScan | in |
| `/imu/data` | sensor_msgs/Imu | in |

### Status

**Yahboom URDF**: NOT present in public ROSMASTER-M3 repo. Must be pulled from real robot via `bash scripts/pull_yahboom_assets_from_robot.sh yahboom@<IP>`. Isaac demo is **BLOCKED** until URDF is available. Will NOT substitute TurtleBot3/JetBot/Carter.

---

## 8. Dashboard and Evidence Capture

The FleetSafe Command Center (`http://localhost:3000`) provides:
- `/dashboard/vln-hub`: VLN Hub with live imported data
- `/dashboard/demo`: live demo controls
- `/dashboard/evidence`: certificate evidence browser
- `/api/vln-hub/live`: aggregated JSON status

Evidence capture: `bash scripts/capture_live_evidence.sh` → `evidence/live_imported_vln_demo/<timestamp>/`

---

## 9. Experiments (Planned / In Progress)

### 9.1 VLNVerse Fine Grained — 10 episodes

| Mode | SR (planned) | SPL (planned) | CBF Interventions |
|---|---|---|---|
| Baseline (none) | TBD | TBD | 0 |
| FleetSafe log_only | TBD | TBD | N/A |
| FleetSafe cbf_qp | TBD | TBD | TBD |

*Not yet run. Isaac Sim and Yahboom URDF required.*

### 9.2 Physical Robot (Planned)

Hospital corridor: 5 runs per mode. Human crossings included.

---

## 10. Metrics

| Metric | Description |
|---|---|
| SR | Success Rate — reached goal within 3m radius |
| SPL | Success weighted by Path Length |
| nDTW | normalized Dynamic Time Warping |
| CBF_rate | fraction of timesteps where shield intervened |
| cert_safe | fraction of timesteps with `cert_safe=true` |
| cert_tier3 | physical robot completed episode |

---

## 11. Current Status

| Component | Status |
|---|---|
| IAmGoodNavigator cloned | ✓ 10 fine + 10 coarse episodes |
| VLNTube cloned | ✓ all 5 modules |
| Real VLNVerse data downloaded | ✓ parquet + npy + metadata |
| Backend VLN Hub endpoints | ✓ /api/vln-hub/live + imported-episodes |
| Dashboard VLN Hub page | ✓ 5 real evidence panels |
| CBF-QP shield | ✓ implemented |
| GNM adapter | ✓ mock fallback, weights TBD |
| Yahboom URDF | ✗ not in public repo |
| Isaac demo episode | ✗ needs Isaac Sim |
| FloatingCamera selected | ✗ needs Isaac Sim |
| Physical robot run | ✗ future work |

---

## 12. Limitations

- Yahboom M3 URDF/USD not available from public repo.
- Physical robot runs not yet completed.
- GNM model weights require separate download.
- VLNTube rendering pipeline requires Isaac Sim license.
- No GPU assumed in CI smoke tests.

---

## 13. Next Steps

1. Pull Yahboom URDF from real robot, import to Isaac
2. Run one full IAmGoodNavigator episode with FloatingCamera
3. Capture all 7 evidence screenshots
4. Run CBF-QP comparison on 10 fine episodes
5. Physical corridor run on Yahboom M3 Pro
6. Submit to arXiv / conference

---

## References

1. VLNVerse — https://sihaoevery.github.io/vlnverse/
2. IAmGoodNavigator — https://github.com/william13077/IAmGoodNavigator
3. VLNTube — https://github.com/william13077/VLNTube
4. GNM — Shah et al., General Navigation Models
5. ViNT — Sridhar et al., ViNT: A Foundation Model for Visual Navigation
6. NoMaD — Sridhar et al., NoMaD: Goal Masked Diffusion Policies
7. CBF — Ames et al., Control Barrier Functions: Theory and Applications
8. Yahboom ROSMASTER M3 — https://github.com/YahboomTechnology/ROSMASTER-M3
9. VLNVerse HuggingFace — https://huggingface.co/datasets/Eyz/VLNVerse_scene
