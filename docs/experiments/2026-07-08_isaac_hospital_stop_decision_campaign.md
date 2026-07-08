# Experiment Log — Isaac Hospital Stop-Decision Visualisation Campaign

**Date:** 2026-07-07 → 2026-07-08
**Repo:** `~/robotics/gnm-vlnverse-baseline`, branch `isaac-hospital-demo` (base commit `9436164` on `main@60a0ac4`)
**Status:** Phase 1 (replay visualisation from real evaluation data) — complete. Phase 2 (live GNM-in-Isaac + ROS 2 rosbag pipeline) — planned, not started.

---

## 1. Objective and hypotheses

**Objective.** Produce deck- and paper-grade visual evidence for the Track A
stopping-reliability study inside a realistic hospital scene, using only
*real* recorded trajectories and *real* per-episode stop-policy outcomes.

**H1.** The temporal stop head terminates inside the 3 m success radius on
episodes where the deployable baseline rule either never fires or fires
outside it. (Supported by the per-episode CSVs; episode
`kujiale_0203_25_0` is the clearest instance: temporal stops at step 14/16
at 1.40 m — success; deployable never fires and ends at 4.55 m — failure.)

**H2.** Visualising the recorded path plus each policy's actual stop
position in a single 3-D scene makes the failure modes (never-fire drift,
premature stop, near-miss) legible to a non-specialist audience in a way
per-episode tables do not.

## 2. Environment

| Item | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 4080 (16 GB) |
| Driver | 580.159.03 (fixed 2026-07-07 via `linux-modules-nvidia-580-open-6.8.0-124-generic`; was broken before that) |
| Isaac Sim | 5.1.0, pip install in conda env `isaac` (env exists at `~/miniforge3/envs/isaac` but is missing from `conda env list` — invoke its python directly) |
| Scene | Isaac 5.1 **Hospital** environment, streamed from the official asset bucket and cached locally (standing standard — see `docs/ISAAC_HOSPITAL_ENVIRONMENT.md`) |
| Display | Deck captures ran headful on `DISPLAY=:0` at 1280×720; campaign renders ran headless at the same resolution |

## 3. Setup

Two scripts, both keeping the perception contract honest (recorded data in,
rendering out; nothing re-simulated):

1. `scripts/gnm/isaac_live_trajectory_demo.py` — locked deck demo. Loads
   the hospital, places the recorded `kujiale_0092_0_3` trajectory in the
   reception lobby, captures the two **approved, frozen** views
   (first-person start→goal; reception overview), exports the composed
   stage. Outputs in `assets/deck/`.
2. `scripts/gnm/isaac_stop_decision_replay.py` — campaign runner. For each
   validation episode: the dataset demonstration path (blue breadcrumbs),
   start (green), goal (red) with dotted 3 m success circle, and — for the
   **temporal stop head** (purple) and **deployable baseline** (orange) — a
   dotted circle at each policy's recorded termination **distance** from
   the goal, taken verbatim from the results CSVs. The Yahboom M3Pro
   placeholder replays the demonstration path with recorded per-step yaw.
   Records overview video (`replay.mp4`), three keyframes, two stills,
   `metrics.json`, `scene.usda`, and a campaign `run_manifest_*.json`
   (GPU, driver, asset provenance with SHA-256 prefixes, git HEAD).

   *Why distances, not positions:* mid-campaign verification caught that
   the evaluation rolled out the GNM agent (its path ≠ demonstration path)
   and did **not** persist the rollout trajectories, so termination
   positions are unknowable after the fact. Distances are exact; a policy
   circle inside the red ring reads as success, outside as failure. First
   drafts that pinned stop markers onto the demonstration path were wrong
   and were discarded.

**Models evaluated (Track A, 15-episode val split, from
`results/bo_reviewer_packet/`):**

| Policy | SR % | OSR % | NE (m) | stop fired | mean stop step |
|---|---|---|---|---|---|
| baseline_dist / stable_dist_k3 / hybrid | 20.0 | 46.7 | 6.51 | 0/15 | — |
| waypoint_norm_k3 | 26.7 | 26.7 | 5.34 | 15/15 | 5.7 |
| **temporal_neural_stop_head @0.50** | **33.3** | 33.3 | 4.47 | 13/15 | 23.6 |

**Robot platform.** Yahboom ROSMASTER M3 Pro. In-scene model is the
primitive visible-placeholder USD
(`assets/robots/yahboom_m3_pro/yahboom_m3pro_visible_placeholder.usda`,
displayed at 1.5× for camera legibility — recorded in the manifest); no
photoreal mesh import exists yet. The physical M3Pro has a real recorded
rosbag episode (`docs/v2.4_yahboom_first_rosbag_episode.md`) and ROS 2
OmniGraph publisher stubs are already sketched in the placeholder stage
(`/camera/image_raw`, `/odom`, `/tf`, `/scan`, `/cmd_vel`) — the on-ramp
for Phase 2.

## 4. Episodes selected (real per-episode outcomes)

| Episode | Temporal stop head | Deployable baseline | Story |
|---|---|---|---|
| `kujiale_0203_25_0` | stop @14/16, 1.40 m, **success** | never fired, 4.55 m, fail | Headline contrast |
| `kujiale_0203_16_3` | stop @10/12, 6.39 m, fail (premature) | never fired, 12.09 m, fail (drift) | Double failure, different modes |
| `kujiale_0092_91_1` | stop @39/41, 4.06 m, fail (near-miss) | never fired, 4.28 m, fail | Fires but just outside radius |

Outputs per episode: `assets/experiments/<episode_id>/`.

## 5. What went well

- Driver fix held; all Isaac runs stable, no crashes across ~10 launches.
- Hospital scene streams once (~4 min) then loads from cache in seconds;
  headless batch of 3 episodes with stills renders in ~70 s.
- The locked deck views were approved on sight ("EXCELLENT VIEW") and are
  now frozen in the committed script + exported stage.
- Per-episode stop-decision data joined cleanly to local `val` trajectory
  dirs (15/15 match) — no re-simulation needed for honest failure visuals.
- Slide 5 updated programmatically and a dedicated two-image slide 6 added,
  with backups at every step.

## 6. Challenges, root causes, mitigations

| # | Challenge | Root cause | Mitigation (now in place) |
|---|---|---|---|
| 1 | First capture entirely black | `ctx.new_stage()` has no lights; RTX renders unlit geometry black | Dome light added; documented |
| 2 | Goal marker invisible from ground level (first cube scene) | Hard-coded obstacle overlapped the goal position | Scene replaced by hospital env; lesson: never let set-dressing intersect data-driven markers |
| 3 | Overview camera outside the building (twice) | Lobby is small: entrance vestibule at (0,−6.5) is glass; (5.5,−4.8) is beyond the SE wall | Cameras constrained to the proven start→goal sight line, below the ~3 m ceiling; rule documented |
| 4 | Success ring rendered as opaque red slab | RTX ignores `displayOpacity` primvar on the filled disk | Dotted circle of 64 small spheres |
| 5 | Reception desk filled the overview foreground on transplanted episodes | Fixed camera offset landed above the desk for some trajectory placements | Overview eye moved ahead of the start eye and aimed at the path centroid |
| 6 | `conda activate isaac` appears to fail | env missing from conda registry though directory intact | invoke `~/miniforge3/envs/isaac/bin/python` directly |
| 7 | Background shells killed themselves when stopping the demo | `pkill -f` pattern matched the compound command's own text | bracket patterns (`dem[o]`) and pkill in a separate call |
| 8 | One texture warning: `TX_Cart_01a_NRM.png` failed to read | Asset bucket file empty/unreadable | Cosmetic (a cart normal map); noted, not blocking |
| 9 | Deck update script single-use | It keys on placeholder text that its first run removes | Documented; subsequent swaps replace the picture shape by name, keeping geometry |
| 10 | Stop markers initially pinned to the wrong path | `stop_step` indexes the agent rollout, but rollout trajectories were never persisted — cross-checking `final_dist_m` against demonstration-frame distances exposed the mismatch | Switched to exact termination-distance circles; Phase 2 requirement added: log agent paths per episode |
| 11 | Imported M3Pro USD composed empty when referenced | Isaac 5.1 URDF importer leaves `defaultPrim` unset in the modular root layer | Import script sets `defaultPrim=/yahboom_m3pro` post-import |
| 12 | Robot invisible in every close-range render (looked like a composition bug) | `UsdGeom.Camera` default near-clip is 1.0 stage units — a 0.3 m robot within 1 m of the camera is entirely clipped | All authored cameras now set `clippingRange (0.02, 10000)`; recorded as a standing Isaac gotcha |
| 13 | Importer dropped all primitive URDF visuals (7 unresolved references) | Isaac 5.1 modular importer only materialises mesh visuals | Import script re-authors box/cylinder/sphere visuals from the URDF spec into the imported stage |

## 7. Insights

- **Replay ≠ rollout.** Everything rendered here is a visualisation of
  recorded trajectories and recorded stop decisions. Slide and caption text
  must say so (slide 6 caption does). Live behaviour claims require the
  Phase 2 pipeline.
- **The honest goal image already exists** — it is the final recorded frame
  of each trajectory (e.g. `assets/deck/tracka_goal_observation.jpg`), not
  a render of the visualisation scene. The policy conditions on that frame.
- **Failure modes are visually distinct** in the hospital scene: never-fire
  baselines glide past the dotted ring; the premature temporal stop on
  `16_3` is conspicuously far short of it. H2 holds on inspection.
- **Spatial transplant caveat:** kujiale-recorded paths are re-based into
  the hospital lobby (uniformly scaled to ≤8 m span; factor recorded per
  episode). Fine for decision visualisation; wrong for any claim about the
  hospital geometry itself.

## 8. Audit trail

- Deck backups: `GNM-VLNVerse_...(new).bak-20260707-1920 / -2342 / -20260708-0004.pptx` (+ every later swap makes one).
- Committed: `9436164` (demo script, deck script, environment doc, exported stage).
- Campaign provenance: `assets/experiments/run_manifest_*.json` records GPU,
  driver, git HEAD, CSV SHA-256 prefixes, robot asset and display scale.
- Source benchmarks: Track A expanded audit (tag
  `v2.7-tracka-expanded-baseline-oracle-audit`, CI-green), per-policy packs
  under `results/bo_reviewer_packet/`.
- Deck images and their real-data counterparts on the Desktop and in
  `assets/deck/`.

## 9. Phase 2 progress (2026-07-08)

**Done — articulated M3Pro USD exists and is verified.**
`scripts/robots/import_yahboom_urdf.py` converts the spec-derived URDF
headlessly (settings per `docs/YAHBOOM_URDF_TO_USD_IMPORT.md`) into the
canonical `assets/robots/yahboom_m3_pro/yahboom_m3pro.usd` (modular layout
with `configuration/` layers), then post-fixes two importer defects:
missing `defaultPrim` and dropped primitive visuals (challenges 11/13).
Verified: 7 visuals + 4 continuous mecanum wheel joints + articulation root
at `/yahboom_m3pro/base_footprint`; composes when referenced; renders at
true 0.29 m footprint. No Yahboom-provided URDF/meshes exist anywhere
(previously searched), so the spec-derived URDF with documented dimension
provenance remains the source of truth. ROS 2 Humble confirmed installed.

**Remaining:**

1. Wire ROS 2 publishers on the articulated robot in the hospital scene
   (`/camera/image_raw`, `/odom`, `/tf`, `/cmd_vel`; OmniGraph stubs in the
   visible-placeholder stage are the reference).
2. Run GNM inference on the simulated camera feed; record genuine rosbags
   per episode (the six-run campaign table becomes real), logging agent
   trajectories per `PHASE2_REQUIREMENTS.md`.
3. Photoreal M3Pro mesh (nice-to-have; primitive model is honest and
   dimensionally traceable).
4. Extend the manifest schema to rosbag runs (topics, durations, bag hashes).
