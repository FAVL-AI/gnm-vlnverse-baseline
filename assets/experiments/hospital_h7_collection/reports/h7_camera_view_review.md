# H7 Camera-View Review — front RGB acceptability for hospital ImageNav

**Question (Frank's decision gate):** is the current front-RGB camera view acceptable
for H7 hospital ImageNav training, given the documented black lower-third — or should
the pilot be re-recorded with an adjusted camera first?

**Scope:** review only. No training, no promotion, no push, no tag, no re-record.
All evidence is from the **real Isaac 5.1 `hospital.usd`** with the Yahboom M3Pro robot
present (so the robot-body occlusion is faithfully reproduced).

---

## 1. What the committed H7 recorded frames actually show

Measured from the **actual recorded `/camera/image_raw` frames** committed in `8b43e7a`
(not re-renders), per episode (`reports/h7_camera_view_metrics.csv`):

| episode | black px % | bottom black band % | usable % | mean luma |
|---|---|---|---|---|
| h7_reception_01 | 42.4 | 38.3 | 57.6 | 22.9 |
| h7_reception_02 | 42.3 | 38.4 | 57.7 | 23.5 |
| h7_corridor_01 | 42.1 | 38.3 | 57.9 | 22.1 |
| h7_corridor_02 | 42.3 | 38.3 | 57.7 | 21.7 |
| h7_turn_01 | 40.2 | 38.3 | 59.8 | 54.1 |
| h7_turn_02 | 41.1 | 38.3 | 58.9 | 39.4 |
| h7_waiting_01 | 40.9 | 38.3 | 59.1 | 25.4 |
| h7_waiting_02 | 40.8 | 38.3 | 59.2 | 25.9 |
| **AGGREGATE** | **41.5** | **38.3** | **58.5** | — |

**Reading:**
- The occlusion is a **fixed geometric band**: the **bottom 38.3%** of every frame is
  pure black (luma 0) in all 8 episodes — invariant across route, pose, and lighting.
  This is the robot near-field/body in front of the level `camera_link/rgb_camera`
  (same sensor as H1–H6), not scene-dependent noise.
- Above the band, the upper ~58–60% carries the hospital: corridor walls, ceiling
  lights, reception desk, wheelchair, vending machine, doorways — landmarks are
  present and **start/current/goal frames are visually meaningful** for ImageNav.
- Per-frame acceptability today: **partially acceptable** — usable content exists, but
  ~40% of every input tensor is dead pixels (wasted capacity; the near-ground floor
  the robot is about to traverse is never seen).

## 2. Three camera settings compared (real hospital.usd + robot)

Standalone render harness `scripts/gnm/hospital_h7_camera_review.py` loads hospital.usd
+ robot, poses the robot at start/mid/goal of two representative routes
(**reception_01**, **turn_01**), and renders each camera variant. The standalone
**current** setting reproduces the recorded band at **38.3%** exactly → the comparison
is faithful. Per-variant means (`reports/h7_camera_view_metrics.csv`, 6 poses each):

| option | config | mean black % | mean usable % | trade-off |
|---|---|---|---|---|
| **current** | level `(90,0,-90)`, mount 0 | **41.8** | 58.2 | as recorded; lower third dead |
| **pitch_up** | upward pitch ~15° `(105,0,-90)` | **10.7** | 89.2 | recovers band but tilts view to ceiling; loses near-ground floor; horizon no longer level |
| **raise_mount** | level, mount **+0.12 m** | **3.4** | 96.6 | near floor + walls + landmarks all visible; **horizon stays level** |

Contact sheets: `camera_option_contact_sheets/h7_camera_{current,pitch_up,raise_mount}_contact_sheet.png`
Comparison grid: `camera_option_contact_sheets/h7_camera_options_comparison.png`

**Visual read of the grid:**
- **current** — clean upper 2/3, hard black lower third.
- **pitch_up** — the black band nearly disappears, but the frame rotates upward: ceiling
  and lights dominate, and the **floor the robot must drive over drops out of view**.
  For ImageNav (where near-ground traversability matters) this trades one blind spot
  for another and breaks the level horizon shared with H1–H6.
- **raise_mount (+12 cm)** — occlusion essentially gone (3.4%), the near floor,
  wheelchair, vending machine and corridor are all visible, and the **horizon stays
  level** (same optical axis as the established sensor, just higher). Best usable
  field of the three.

## 3. Recommendation

**Do NOT train on the current 8-episode H7 pilot as-is. Re-record the pilot with the
raised-mount camera (+0.12 m, level) before any H7 training.**

Rationale:
- The current view wastes ~40% of every frame and never sees the near-ground floor —
  a real handicap for a traversability-driven ImageNav policy, and an avoidable one.
- **raise_mount** removes the occlusion (41.8% → 3.4% black, 96.6% usable) while
  preserving the **level horizon and optical axis** of the H1–H6 sensor, so the change
  is a clean mount-height adjustment, not a new/incompatible sensor geometry.
- **pitch_up** is rejected: it hides the near-ground floor and tilts the view, which is
  worse for navigation and inconsistent with the prior sensor convention.

This matches Frank's decision gate: the current camera is **not** clean enough to
approve diagnostic training as-is, and an adjusted setting (raised mount) is clearly
better and physically plausible → the correct next step is to **re-record the 8-episode
pilot with the approved camera**, then review before training.

## 4. What changes if raise_mount is approved

- One-line mount edit in the bringup camera author (`camera_link/rgb_camera` local
  translate `+0.12 m` in Z; rotation unchanged `(90,0,-90)`).
- Re-run the **same gated 8-episode campaign** (`hospital_h7_record_campaign.sh`,
  `--scene hospital --scene-gate`, per-episode collision/timeout/disk guards, strict
  exclusion rule) — routes, splits, and protocol unchanged.
- Re-verify the 10-point dataset gate and the black-band metric (expect ≈3–4%), then
  bring the refreshed pilot back for the training decision.

## 5. Artifacts (this review)
- `reports/h7_camera_view_review.md` (this file)
- `reports/h7_camera_view_metrics.csv` (per-episode recorded + per-option comparison)
- `camera_option_contact_sheets/` — 3 per-option contact sheets + 1 comparison grid
- `camera_review_npy/` — 30 raw variant renders + `camera_review_manifest.json`
  (scene-identity gate PASSed before rendering)
- Provenance: `scripts/gnm/hospital_h7_camera_review.py` (render),
  `scripts/gnm/hospital_h7_camera_review_build.py` (sheets + metrics)

**Status: review complete. No training, no re-record, no commit performed — awaiting
Frank's decision on the camera setting.**
