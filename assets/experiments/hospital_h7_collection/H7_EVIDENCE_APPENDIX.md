# Appendix H7 — Evidence for the "H7-Hospital pilot PASS" claim

**Purpose.** The statement *"the H7-Hospital pilot passed the 10-point gate"* is a
load-bearing claim. This appendix lets a reviewer trace it end-to-end to primary,
independently verifiable evidence: the exact recording command, the route list, a
fail-closed scene-identity gate log, per-bag rosbag topic proof, and SHA-256
checksums over the raw data. Nothing here is a re-render or a prose summary — every
row is transcribed from, or hashed over, a recorded artifact on disk.

Scene: **verified Isaac Sim 5.1 `hospital.usd`** scene (asset URL fixed in every gate
manifest) — **not** a physical hospital and **not** a real robot.
Repo: `gnm-vlnverse-baseline`, branch `h23-execfix`. This evidence package is frozen as a
single commit ("Add reproducible H7 and H7R pilot evidence appendix"); the freeze hash is
recorded on the deck evidence footer and retrievable with
`git log -1 -- assets/experiments/hospital_h7_collection/H7_EVIDENCE_APPENDIX.md`.

## Formal verdict (bounded)

> **H7 and H7R: APPROVED AS PROVENANCE-BACKED ISAAC SIM HOSPITAL-SCENE PILOT EVIDENCE,
> WITH A DOCUMENTED CAMERA-RESOLUTION NONCONFORMITY.**

**Covered:** scene identity · route identity · ROS 2 bag existence · required topic
presence · recorded-message evidence · file-integrity verification · reproducible
evidence generation.

**Not covered:** dataset (H8) admission · training readiness · **camera-resolution
conformity** · goal conditioning · model performance · physical-hospital or real-robot
deployment · any safety-performance or state-of-the-art claim.

---

## 0. Two pilots (read this first)

There are **two** 8-episode pilots. Both passed the gate; they differ only in camera
mount height.

| Pilot | prefix | Camera | Lower-third occlusion | Role |
|---|---|---|---|---|
| **H7 baseline** | `h7_` | fixed (H1–H6 sensor) | ~38.3 % black band | camera baseline; superseded |
| **H7r raised-mount** | `h7r_` | `camera_link/rgb_camera` +0.12 m, level horizon | **0.0 %** (removed) | **dataset of record** |

The raised-mount pilot (`h7r_`) supersedes the baseline as the dataset of record; the
baseline is retained as auditable camera-baseline evidence. All five evidence classes
below are produced for **both** pilots.

---

## 1. The claim, mapped to the 10-point gate

Every criterion below is asserted by a specific artifact (paths in §7). Values shown
are for **H7r** (dataset of record); the H7 baseline meets criteria 1–9 identically
(criterion 10 differs by design — that is the reason the baseline was superseded).

| # | Gate criterion | Result (8 episodes) | Evidence file |
|---|---|---|---|
| 1 | `route_completed = True` | 8/8 True | `…_recording_quality_table.md` |
| 2 | `total_contacts = 0` | 8/8 zero | `…_collision_contact_report.json` |
| 3 | `emergency_stop = False` | 8/8 False | `…_recording_quality_table.md` |
| 4 | no XY-bound / `stop_reason = None` | 8/8 None | `…_recording_quality_table.md` |
| 5 | scene-identity gate PASS **before record** | 8/8 PASS | `…_scene_gate_index.md` (§4) |
| 6 | bag present, contains `/camera/image_raw` | 8/8 present | `…_rosbag_topic_proof.md` (§5) |
| 7 | artifact-completeness | 8/8 complete | `…_artifact_completeness.json` |
| 8 | excluded episodes | 0 excluded | `…_excluded_episodes.json` |
| 9 | leakage / split disjoint | clean, 4/2/2 | `…_leakage_report.json`, `…_split_manifest.json` |
| 10 | (H7r) lower-third black ≈ 0 %, `camera_mount_raise_m = 0.12` | 8/8, mean 0.0 % | `…_recording_quality_table.md` |

**Integrity of the raw data** backing criteria 1–6 and 10 is pinned by SHA-256
checksums over each bag and trajectory (§6).

---

## 2. Command used (exact, reproducible)

Every episode was recorded by the harness `scripts/robots/m3pro_ros2_bringup.py` under a
disciplined orchestrator. The per-episode command (from
`scripts/gnm/hospital_h7_raise_record_campaign.sh:50-52`):

```bash
source /opt/ros/humble/setup.bash
timeout 1800 "$HOME/miniforge3/envs/isaac/bin/python" -u \
  scripts/robots/m3pro_ros2_bringup.py \
    --scene hospital --scene-gate --camera-raise 0.12 \
    --gnm-control --route-follow <route.json> --holonomic-base \
    --collision-report --episode --episode-name <episode_id> \
    --goal-id h2_weave_J --steps 6000
```

- `--camera-raise 0.12` → H7r (dataset of record); omit / `0.0` → H7 baseline.
- `--scene-gate` runs the **fail-closed** scene-identity check just before
  `ros2 bag record`; on failure the harness `sys.exit(5)` and records nothing (§4).
- Orchestrators (disk guard ≥100 G, `timeout 1800` per episode, exact-PID orphan-recorder
  cleanup — never `pkill -f` — stale-DDS shm removal, systemic-abort on `rc≠0`):
  - baseline: `scripts/gnm/hospital_h7_record_campaign.sh`
  - raised-mount: `scripts/gnm/hospital_h7_raise_record_campaign.sh`

Routes were authored on the render-confirmed free lobby floor by
`scripts/gnm/hospital_h7_author_routes.py`; **collision-report is ground truth**
(the AABB navmap over-marks free space and was rejected — see `navmap/navmap_meta.json`).

---

## 3. Route list (8 routes, 4 families × 2 instance variants)

Source of truth: `assets/experiments/hospital_h7_collection/routes/` (shared by both
pilots) + manifest `routes/h7_routes_manifest.json`. Coords lie on render-confirmed free
floor `x∈[-2.6,1.5] y∈[-0.8,1.1]`, avoiding desk / wheelchair / vending / glass doors /
walls. Split is instance-disjoint (H6 protocol): val/test are **unseen route instances of
trained families**.

| route_id | family | waypts | length_m | split (H7r) |
|---|---|---|---|---|
| h7_reception_01 | reception_to_corridor | 3 | 3.91 | train |
| h7_corridor_01 | corridor_straight | 3 | 2.50 | train |
| h7_turn_01 | turn_t_junction | 3 | 2.20 | train |
| h7_waiting_01 | waiting_to_doorway | 3 | 3.42 | train |
| h7_reception_02 | reception_to_corridor | 3 | 3.68 | val |
| h7_corridor_02 | corridor_straight | 3 | 2.50 | val |
| h7_turn_02 | turn_t_junction | 3 | 2.20 | test |
| h7_waiting_02 | waiting_to_doorway | 3 | 3.07 | test |

Split manifest with resolved episode IDs:
`hospital_h7_raise_collection/reports/h7r_split_manifest.json`.

---

## 4. Scene-identity gate log (fail-closed proof of the verified Isaac Sim hospital scene)

The gate proves the data was recorded in the **verified Isaac Sim `hospital.usd`** scene
— not procedural H6, and not a physical hospital. It runs *before* `ros2 bag record`; a
failing gate records nothing. Every episode below therefore has a PASS manifest.

- Per-episode manifests: `assets/experiments/hospital_h7_scene_gate/<episode_id>.json`
- Consolidated indexes (generated): `…/reports/h7_scene_gate_index.{md,csv}` and
  `…/reports/h7r_scene_gate_index.{md,csv}`

Each manifest pins: the exact `hospital.usd` asset URL, `asset_is_hospital_usd=true`,
`hospital_prim_count` (1909) ≥ `min_hospital_prims` (1000), `scene_mode=hospital`,
empty `procedural_landmark_prims` (no Pillar_*/Wall_*/Landmark/Ground cubes),
`front_camera_path=/World/M3Pro/camera_link/rgb_camera`, resolution, `failed_reasons=[]`,
`isaac_sim_version=5.1.0.0`. Example (`h7r_reception_01`):

```json
{ "asset_is_hospital_usd": true, "scene_identity_pass": true,
  "observed": { "hospital_prim_count": 1909,
                "front_camera_path": "/World/M3Pro/camera_link/rgb_camera",
                "procedural_landmark_prims": [] },
  "failed_reasons": [], "isaac_sim_version": "5.1.0.0" }
```

---

## 5. Rosbag topic proof

Each recorded bag's own `metadata.yaml` (rosbag2 v5, sqlite3) records the topics and
per-topic message counts. The generated topic-proof tables transcribe this for all 8
episodes and flag whether the expected ImageNav topic set is present.

- Generated: `…/reports/h7_rosbag_topic_proof.{md,csv}` and
  `…/reports/h7r_rosbag_topic_proof.{md,csv}`
- Expected topics (all present in 8/8 bags):
  `/camera/image_raw` (`sensor_msgs/msg/Image`), `/camera/camera_info`
  (`sensor_msgs/msg/CameraInfo`), `/odom` (`nav_msgs/msg/Odometry`),
  `/tf` (`tf2_msgs/msg/TFMessage`), `/clock` (`rosgraph_msgs/msg/Clock`),
  `/cmd_vel` (`geometry_msgs/msg/Twist`).
- `/camera/image_raw` message counts per episode: **2117–2124** (H7r); 2090–2122 (H7).

Independently reproducible with:

```bash
source /opt/ros/humble/setup.bash
ros2 bag info assets/experiments/rosbags/<episode_id>
```

---

## 6. Checksums (raw-data integrity)

The raw bags (~1.9 GB each) and trajectories are **untracked** (too large to commit), so
their integrity is pinned by SHA-256 so anyone who receives the bags can verify them.

- Bag checksums (`.db3` + `metadata.yaml`, `sha256sum -c` compatible, repo-relative
  paths): `…/reports/h7_bag_checksums.sha256`, `…/reports/h7r_bag_checksums.sha256`
- Committed-artifact checksums (routes, gate manifests, quality tables, generated
  tables): `…/reports/h7_evidence_checksums.sha256`,
  `…/reports/h7r_evidence_checksums.sha256`
- Combined index: `hospital_h7_collection/H7_EVIDENCE_MANIFEST.json`

Verify from the repo root (requires the raw bags present):

```bash
cd /home/favl/robotics/gnm-vlnverse-baseline
sha256sum -c assets/experiments/hospital_h7_raise_collection/reports/h7r_bag_checksums.sha256
sha256sum -c assets/experiments/hospital_h7_collection/reports/h7_bag_checksums.sha256
```

**These are two distinct verification operations that prove different things.**
`sha256sum -c` (above) verifies *file integrity* — the bytes on disk match the frozen
hashes. `ros2 bag info <bag_dir>` (§5) inspects *ROS 2 bag metadata* — topic set and
per-topic message counts. Run both; neither substitutes for the other.

All evidence tables in §4–§6 are regenerated deterministically by
`scripts/gnm/hospital_h7_build_evidence_appendix.py` (parses bag metadata, hashes bags +
artifacts, indexes gate manifests — it recomputes no results).

---

## 7. Camera-resolution nonconformity (open limitation, disclosed not rewritten)

The scene-gate manifests declared an **expected resolution of 1280×720**, while the
recorded `/camera/image_raw` stream is **640×480**. The original gate's resolution check
was **declarative only** — it confirmed a resolution was declared but did **not** compare
the observed stream against the declaration — so the mismatch passed silently at capture
time. Consequently:

- **Unaffected** (still supported): scene identity, ROS 2 bag existence, checksum
  integrity, route identity, topic presence.
- **Not demonstrated**: camera-resolution conformity. H7/H7R make **no** resolution-
  conformity claim.

Per research-integrity practice the historical manifests are **preserved unchanged** (not
back-edited to appear as though 640×480 was declared before capture). The full treatment,
both values, and the forward fix are in
`H7_H7R_CAMERA_RESOLUTION_VARIANCE_AND_H8_MITIGATION.md`. The forward fix is implemented:
`hospital_scene_identity_gate.verify_hospital_scene(enforce_resolution=True)` fails closed
when observed ≠ declared (opt-in; H7/H7R verdicts unchanged), with a negative test in
`tests/gnm/test_hospital_resolution_gate.py`.

---

## 8. Artifact index

Baseline reports live under `hospital_h7_collection/reports/`; raised-mount reports under
`hospital_h7_raise_collection/reports/` (prefix `h7r_`).

| Evidence | Baseline (H7) | Raised-mount (H7r) |
|---|---|---|
| Quality table (criteria 1,3,4,10) | `reports/h7_recording_quality_table.{md,csv}` | `reports/h7r_recording_quality_table.{md,csv}` |
| Collision/contact (criterion 2) | `reports/h7_collision_contact_report.json` | `reports/h7r_collision_contact_report.json` |
| Scene-gate index (criterion 5) | `reports/h7_scene_gate_index.{md,csv}` | `reports/h7r_scene_gate_index.{md,csv}` |
| Rosbag topic proof (criterion 6) | `reports/h7_rosbag_topic_proof.{md,csv}` | `reports/h7r_rosbag_topic_proof.{md,csv}` |
| Artifact completeness (criterion 7) | `reports/h7_artifact_completeness.json` | `reports/h7r_artifact_completeness.json` |
| Excluded (criterion 8) | `reports/h7_excluded_episodes.json` | `reports/h7r_excluded_episodes.json` |
| Leakage + split (criterion 9) | `reports/h7_leakage_report.json` | `reports/h7r_leakage_report.json`, `reports/h7r_split_manifest.json` |
| Campaign ledger (rc per episode) | `reports/h7_campaign_ledger.csv` | `reports/h7r_campaign_ledger.csv` |
| Bag checksums | `reports/h7_bag_checksums.sha256` | `reports/h7r_bag_checksums.sha256` |
| Per-episode gate manifests | `hospital_h7_scene_gate/h7_*.json` | `hospital_h7_scene_gate/h7r_*.json` |
| Routes (shared) | `hospital_h7_collection/routes/h7_*.json` | ← same |
| Dataset card / claim boundary | `hospital_h7_collection/h7_{dataset_card,claim_boundary}.md` | `hospital_h7_raise_collection/h7r_{dataset_card,claim_boundary}.md` |

---

## 9. Claim boundary (what H7 PASS does NOT assert)

- **Not a training/promotion claim.** A diagnostic H7r fine-tune exists but is
  `DIAGNOSTIC_ONLY_NOT_PROMOTED` (n=2 test, single seed, fixed placeholder goal).
- **Not goal-conditioning evidence.** One fixed goal image (`h2_weave_J`) across all
  episodes → imitation-fidelity data, not goal-image conditioning.
- **Not real-robot evidence.** Isaac Sim only.
- **Not SOTA / navigation-quality.** 8 episodes, one scripted expert, one seed, offline.
- **Not procedural H6.** H7 must not be merged with the scene-agnostic H6 diagnostic.
- **Smoke/valcheck runs are excluded** from the 8-episode dataset (e.g.
  `h7_reception_01_smoke_*`, `h7_valcheck_*`) and are not part of any gate count.

*Regeneration: run `scripts/gnm/hospital_h7_build_evidence_appendix.py`, which hashes and
transcribes recorded artifacts only and recomputes no experimental result. This appendix
cites recorded evidence.*
