# Camera and Task Conventions (canonical)

Claim boundary (exact, project-wide): Current Kujiale/VLNTube
experiments use a top-down RGB camera convention. The hospital live
dashboard and future Yahboom sim-to-real work use a front-facing robot
RGB camera convention. These regimes are kept separate unless a
domain-adaptation experiment is explicitly declared.

The live navigation model uses front-facing robot RGB images, not a
top-down map. The model receives a current camera image and a goal
camera image, both from the same robot-eye camera convention.

## Convention table

| Track | Dataset/Environment | Camera view | Input modality | Model type | Claim boundary |
|---|---|---|---|---|---|
| A (ImageNav, current Kujiale line) | VLNTube/Kujiale local + generated | top-down/nadir RGB (verified) | current image + goal image | MobileNetV2-GNM | scene-holdout study; not full VLNVerse benchmark |
| A (ImageNav, hospital/Yahboom line) | Isaac hospital + Isaac-Hospital-ImageNav-v0 | Yahboom front-facing RGB | current image + goal image | GNM-family (fine-tune pending H1) | simulation only; not real-robot evidence |
| B (LanguageNav, future) | TBD | front-facing RGB | current image + text instruction | TBD | future work; no language claims now |
| C (Vision-Language ImageNav, merge) | TBD | front-facing RGB | image + goal image + instruction | TBD | after A+B have evidence |
| D (FleetSafe safety layer) | any of A–C | n/a (acts on actions/state) | proposed action + state + uncertainty + constraints | safety filter (CBF/governance) | final thesis layer; added after navigation evidence |
| E (Real Yahboom sim-to-real) | Yahboom-Real-ImageNav-v0 (future) | real front-facing RGB | current + goal image | transfer of A | no real-robot success claims until this exists |

## Task taxonomy (stop calling everything "VLN")
- **ImageNav / image-goal navigation** (Track A, active): current RGB +
  goal RGB → waypoint/action.
- **LanguageNav** (Track B, future): current RGB + text → waypoint/action.
- **Vision-Language Navigation** (Track C, merge stage): image + goal
  image + language → waypoint/action.
- **FleetSafe safety layer** (Track D): proposed action → safe /
  modified / blocked action.

## Live hospital demo wording (required)
The live navigation dashboard shows Start State, Current State, and
Goal State as front-facing RGB images from the Yahboom robot camera
convention. The main view is the robot-eye camera image, not a 3D
spectator view or top-down map.

## Roadmap (annual-presentation form)
Year 1 — controlled ImageNav evidence: top-down Kujiale/VLNTube
scene-holdout experiments; MobileNetV2-GNM baseline; generated top-down
training data (validated pipeline; expansion hypothesis tested and
rejected); Isaac hospital front-camera live demo as a separate internal
simulation line.
Year 2 — front-facing hospital ImageNav: Isaac-Hospital-ImageNav-v0;
train/fine-tune front-camera model; held-out hospital routes/goals.
Year 2–3 — Track B LanguageNav: instruction following + evaluation.
Year 3 — Track C Vision-Language ImageNav: combine goals + language.
Final thesis layer — Track D FleetSafe safety filter (delay/uncertainty-
aware action checking), then Track E Isaac + real Yahboom sim-to-real.

The clean research story: first the robot reaches a visual goal from
camera images; second it follows language instructions; third we
combine visual and language goals; fourth we add the execution-time
safety layer; fifth we validate in Isaac and then on the real Yahboom.
