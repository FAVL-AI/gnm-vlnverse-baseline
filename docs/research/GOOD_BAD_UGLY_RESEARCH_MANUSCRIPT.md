# Research Investigation Manuscript — The Good, the Bad, and the Ugly

Living forensic record of the GNM-VLNVerse / FleetSafe Phase-2 programme.
Rules: no marketing language; failures are recorded as failures; negative
results stay negative; every claim links to a commit, episode ID, table,
manifest or validation target; validated evidence is separated from
interpretation; deprecated material is marked; decisions record *why*.
Companion documents: `docs/experiments/PROJECT_BASELINE_STATUS.md` (claim
boundaries), `docs/experiments/2026-07-08_isaac_hospital_stop_decision_campaign.md`
(challenges 1–18).

Section template: Hypothesis / Setup / Result / Good / Bad / Ugly /
Root Cause / Mitigation / Decision / Insight / Limitation / Next Gate.

---

## 1. Baseline reset (commit 8e8eacb)
**Hypothesis:** older replay-only and placeholder evidence was inflating
apparent progress. **Setup:** audit of all docs/claims against artifacts.
**Result:** v2.1–v2.4.2 rosbag/topic gates were *Pending* against a
placeholder stage; no rosbag file existed anywhere. **Good:** clean
baseline status doc with a deprecation register. **Bad:** a campaign-log
line had claimed a "real recorded rosbag" that did not exist. **Ugly:**
the false line was ours — caught by grepping for the actual .db3 files.
**Root cause:** procedure docs read as achievement docs. **Mitigation:**
deprecation banners; claim-guard validators that fail on banned phrases.
**Decision:** only live-pipeline evidence is valid. **Insight:** claims
must be regenerable from artifacts, not from documents. **Limitation:**
Track A offline results remain valid *as offline evaluation only*.
**Next gate (then):** live drive loop.

## 2. DDS visibility bug (commit 2a1942f)
**Hypothesis:** Isaac→CLI topic invisibility was a transport/profile
problem. **Result:** it was a stale `ros2` daemon cache plus a too-short
discovery spin in the test harness. **Good:** all six topics bidirectional
after `ros2 daemon stop`. **Bad:** hours of transport theorising.
**Ugly:** the CLI itself was silently broken when spawned from Isaac
(conda PYTHONPATH poisoning py3.10 ros2cli) — two independent faults
looked like one. **Root cause:** environment leakage + daemon cache.
**Mitigation:** `env -i` scrubbed CLI pattern; daemon restart in checks.
**Decision/Insight:** debug one directional path at a time; a subprocess
inherits your poison. **Next gate:** first rosbag (recorded same day).

## 3. First real rosbag / 4. Camera publisher (commits 2a1942f, 013e02c)
**Hypothesis:** control+state, then camera, could be recorded end-to-end.
**Result:** smoke bag (9,906 msgs) then full-topic bag (image 1,376,
camera_info 1,374). **Good:** the URDF import created camera frames; one
authored Camera prim + ROS2CameraHelper completed the sensor chain.
**Bad:** bags are ~1.2 GB per 15 s with images — kept out of git with
SHA-256 manifests. **Ugly:** the unattended hold-mode robot kept stale
wheel velocity targets, drove off the 40 m world and free-fell to
z = −5.8×10⁶ m (challenge 18). **Root cause:** command-hold without
explicit zeroing. **Mitigation:** hold modes zero wheels; later, every
stop path verifies residual motion. **Insight:** execution-layer safety
failures are silent and catastrophic; zeroing must be explicit.
**Next gate:** trajectory logging.

## 5. Trajectory logging (commit 9a8f791)
**Hypothesis:** rosbags prove topics; behaviour needs per-step logs.
**Result:** trajectory.jsonl/csv + metadata per episode; validator with
seven checks. **Good:** ground-truth behavioural layer; small enough to
commit. **Bad:** wall-vs-sim duration mismatch (headless runs ~4×
realtime) initially failed the bag-duration check. **Ugly:** none.
**Mitigation:** validator compares wall-to-wall. **Insight:** the log
schema later caught *every* subsequent scientific error (wrong spawn,
degenerate EMA, identical-trajectory explanations). **Next gate:** shadow
inference.

## 6. GNM shadow inference (commit bfcc3a2)
**Hypothesis:** the published GNM checkpoint can run online without
authority. **Result:** 261/261 forward passes at 13.1 ms mean on CUDA;
scripted controller kept /cmd_vel on every row. **Good:** repo already
had a full adapter layer; the missing piece was only the public weights
(acquired, SHA-256 manifested, gitignored). **Bad:** goal image was not
scene-aligned — inference-path evidence only. **Ugly:** no GNM backbone
checkpoint existed anywhere locally despite configs referencing one; the
Track A eval had run elsewhere. **Root cause:** config paths never
populated on this machine. **Mitigation:** checkpoint provenance manifest;
honest scope notes in metadata. **Insight:** shadow-first prevents
breaking a working pipeline while proving a model runs. **Next gate:**
bounded authority.

## 7. GNM closed-loop control (commit 662ea1d)
**Hypothesis:** GNM can hold bounded authority safely. **Result:** 8 s
episode, 1.593 m at the 0.20 m/s clamp, watchdog armed, zeroing verified
(2.6 mm). **Good:** full safety envelope (clamps, bounds, watchdog,
e-stop, zero-hold) worked first time it was needed. **Bad:** raw policy
intent needed clipping every step. **Ugly:** the first authority run
e-stopped at step 0 — my gross-bounds guard was miscalibrated because
"raw" used an unbounded derivation (~2.5 m/s); kept as evidence episode
`gnm_closed_loop_20260708_031640`. **Root cause:** raw must mean
policy-intent at model-config limits, not unclamped geometry.
**Mitigation:** raw defined at 0.3/0.7 model limits; e-stop guards true
insanity. **Insight:** the e-stop firing wrongly *proved the e-stop*.
**Next gate:** scene-aligned goals.

## 8. Scene-aligned goal capture / 9. Goal-conditioned smoke (d5a1bc6, 7613a66)
**Hypothesis:** with a goal that exists in the scene, GNM will move
toward it. **Result:** d2g 1.399 → **0.498 min** → 0.573 final; the robot
passed its nearest point and kept driving. **Good:** the overshoot — the
project's core thesis phenomenon — reproduced live for the first time.
**Bad:** commanded yaw (≤0.18 rad/s) produced almost no rotation.
**Ugly:** USD parent-prim spawn transforms silently do not survive
articulation init: the first hospital episode spawned at the origin;
caught only because start-d2g telemetry disagreed with the design.
**Root cause:** articulation pose must go through the articulation API.
**Mitigation:** `arti.set_world_pose` spawns; mis-spawned run kept as
evidence. **Insight:** telemetry cross-checks catch silent simulator
defects. **Next gate:** stop-head shadow.

## 10. Stop-head shadow integration (commit a48d3e4)
**Hypothesis:** the trained Track A stop head fires near goals when fed
live signals. **Result (synthetic stage):** 579 evaluations at 0.26 ms —
**probability ≈ 0.000 throughout; never fired.** **Good:** the checkpoint
is self-describing (normalisation, threshold, stable-k) and runs online
at negligible cost; the raw GNM dist_pred *contained* the overshoot
pattern (min exactly at true nearest). **Bad:** domain gap — live
dist_pred floor 3.2 vs much lower near-goal training values; 20 Hz
cadence shrinks trend features. **Ugly:** an "it fired!" would have been
publishable-looking and wrong; only the honest no-fire path in the
validator kept the record straight. **Mitigation:** quantified the gap;
hospital-scene episodes planned as nearer-distribution test.
**Insight:** learned components carry their training distribution with
them. **Next gate:** yaw, then hospital episodes.

## 11. Yaw-authority investigation (commit da91bf3)
**Hypothesis (8 candidates):** mapping error, geometry, colliders,
friction, drives, signs, odometry, clamps. **Result:** signs correct,
zeroing clean, straight-line perfect; yaw_tracking_ratio 0.03–0.15 at
normal commands, 0.23–0.27 at 1.0 rad/s, across a three-point friction
sweep (default/0.35/0.15). **Good:** a metric, not an anecdote; the
sublinear μ-response *proves* a geometric moment balance. **Bad:**
capability classified FAIL below 1.0 rad/s. **Ugly:** the approximation
choice (sphere wheel colliders, made to fix beaching) created the yaw
limitation — one fix caused the next finding. **Root cause:** skid-steer
on L/W≈0.91 without mecanum rollers: lateral grip cancels the yaw moment.
**Mitigation:** straight/low-curvature study designs; ranked fixes
(mecanum modelling / labelled sim aid). **Insight:** execution-layer
limits must be characterized *before* policy claims, or policies get
blamed for actuation. **Next gate:** hospital shadow episodes.

## 12. Hospital-scene shadow episodes (commit 2dfea2f)
**Hypothesis:** nearer the training distribution, the stop head fires.
**Result:** episode A (2 m straight): GNM dist_pred 9.1→1.2 and the head
**fired at 0.258 m while approaching** (prob→1.0); episodes B/C: silent
(dist_pred floors 2.2/4.4). **Good:** first live in-distribution firing;
would-have-stopped analysis: stop-at-signal ends 0.133 m closer than
no-stop. **Bad:** sharp firing boundary tied to GNM's own prediction
bottoming near 1. **Ugly:** none new — the spawn defect (sec. 9) was
found here. **Insight:** the head is a *threshold on a miscalibrated
scalar*; boundary characterization became the next experiment by
necessity. **Next gate:** recalibration study.

## 13. Stop-boundary recalibration (commit b448a2d)
**Setup:** 12 candidate rules over the three live episode logs.
**Result:** probability sweeps useless (input-distribution, not
threshold); `dist_pred≤4.5, k=3` fired 3/3 in-sample with zero false
stops → recommended candidate. **Good:** measured trade-off table
(false-stop/late-stop per rule). **Bad:** n=3, one lobby, in-sample
threshold — stated. **Ugly:** early trend-reversal rules false-stopped at
~2.8 m out in B. **Insight:** in-sample recommendations are hypotheses,
not results. **Next gate:** held-out authority A/B.

## 14. Stop-authority held-out failure (commit 8b625eb)
**Result:** the absolute gate fired **early** on both fresh reverse-route
pairs (true d2g 1.479/1.103) and ended *farther* from the goal than the
no-stop baseline (+0.992/+0.608 m). **REJECTED** per pre-registered rule.
**Good:** the authority machinery was flawless (gate-only stops, 2.8/3.0 mm
residuals, clean stop-type separation); the held-out design did its job.
**Bad:** candidate one falsified. **Ugly:** an in-sample "3/3, zero false
stops" number would have looked excellent in a paper — and was wrong the
moment the route reversed. **Root cause:** GNM dist_pred scale is
route/view-dependent. **Insight:** held-out validation must gate any
authority. **Next gate:** route-invariant rules.

## 15. Normalized threshold rejection (commits e3be33a, 91c9716)
**Hypothesis:** normalising by each episode's initial prediction removes
route dependence. **Offline study:** tuned on A/B/C only; on held-out
D/E logs `normalized_pred (≤0.5×init, k=3)` was the only rule with a
counterfactual win (D at 0.173 m). **Live rerun on fresh goals F/G:**
fired at ratios 0.46/0.48 as designed — **but early again** (true d2g
1.056/1.449), worse than baseline (+0.065/+0.961 m). **REJECTED.**
**Good:** two falsifications now *prove* the failure family:
simple thresholds on GNM's predicted distance do not transfer.
**Bad/Ugly:** even the privileged ground-truth-d2g rule fires early
(true distance has local reversals during heading corrections) —
"passed closest approach" is intrinsically noisy from one scalar.
**Decision:** threshold-family authority abandoned; in-domain retraining
or multi-signal rules required, held-out-first. **Insight:** this is the
thesis argument, demonstrated live twice. **Next gate:** grow the live
corpus for in-domain stop-head retraining.

## 16. MobileNetV2 + EMA Ablation and Isaac Physics Collision-Rate Evaluation (this commit)
**Hypothesis:** EMA may improve the MobileNetV2-GNM baseline by
stabilising training/evaluation weights.
**Setup:** MobileNetV2 baseline vs EMA 0.9999 vs EMA 0.999, same
four-scene split (12,421 train / 817 val samples; 238/15 episodes), seed
42, identical config except `training.ema_decay`; offline VLN evaluation
(SR/OSR/NE/SPL), then Isaac physics smoke rollout for Collision Rate
(PhysX chassis-contact events; 3 straight-route episodes per checkpoint
plus a deliberate-collision positive control).
**Result:** offline — baseline SR 13.3/OSR 46.7/NE 6.14/SPL 0.133;
EMA 0.9999 degenerate (TL 0.13 m; nominal SR 20.0 is a start-inside-radius
artifact); EMA 0.999 SR 6.7/NE 6.93 despite best val loss (0.23 vs 0.36).
Isaac — NE 0.82 m both checkpoints; **CR 0.00 measured** (0 contacts over
17.9 m), positive control logged 27 contacts on `SM_ReceptionDesk_01a`.
**The Good:** CUDA/W&B/MLOps setup validated (`Training on cuda`, 3
offline W&B runs, 16-artifact registry, `make validate-training-mlops`);
all three runs completed; offline metrics recorded; Isaac rollout added a
real Collision Rate; PhysX chassis-contact logging validated; the
positive collision control confirmed contact reporting works.
**The Bad:** the offline evaluator cannot measure Collision Rate; the
held-out split has only 15 episodes (one episode = 6.7 pp SR); SR/OSR
saturate on short Isaac routes (all under the 3 m radius); the EMA
comparison remains preliminary.
**The Ugly:** EMA 0.9999 was degenerate for this training horizon (the
shadow lagged near initialization and "scored" by standing still);
Collision Rate would have been misleading if reported as 0.0 from the
offline evaluator (it prints CR=0.000 by construction); a positive
control was *needed* to prove the measured zeros were real.
**Root Cause:** the offline evaluator lacks physical contact simulation;
EMA decay must match training duration (~4,700 steps < one 0.9999
half-life); short routes make SR/OSR uninformative.
**Mitigation:** CR separated into the Isaac physics rollout; EMA 0.999
added as a decay-horizon sanity ablation (labelled as such, never as the
original condition); positive collision control added; NE/CR treated as
the informative metrics in the short-route physics smoke.
**Decision:** per the pre-registered rule the **original MobileNetV2
baseline is kept**; EMA is reported as a completed ablation; CR is valid
only from Isaac contact evidence. Both checkpoints saturate the safety
clamp on straight routes, so executed trajectories converge (raw intents
differ: ~0.5 vs ~0.7 m/s, logged per row).
**Scientific Insight:** training-quality metrics and physics-safety
metrics must be reported separately — EMA is a training-stability
ablation, while Collision Rate requires contact-aware simulation.
Validation loss is an imperfect proxy for navigation SR.
**Limitations:** small held-out offline split; the Isaac physics
evaluation is a smoke test, not a full benchmark; robust navigation and
campaign-level claims remain pending.
**Next Evidence Gate:** expand VLNVerse data for training/validation with
scene-level held-out testing preserved, and run a larger Isaac physics
evaluation after the selected checkpoint is finalized.
Evidence: `assets/experiments/training_ablation/mnv2_ema_20260708/`,
`assets/experiments/isaac_physics_eval/isaac_physics_smoke_20260708/`,
`assets/experiments/training/mobilenet_ema_ablation_20260708/`,
`make validate-isaac-physics-eval`, `make validate-training-mlops`.

## 17. EfficientNet pause decision
**Decision:** EfficientNet paused to avoid confounding the EMA
training-stability question with a backbone-capacity change; resumed only
after the MobileNetV2 baseline and EMA ablation are reproducible.
Full text: `assets/experiments/training_ablation/mnv2_ema_20260708/appendix_efficientnet.md`.
**Insight:** one variable per ablation; compute budget favours the
lightweight controlled baseline first.

---
*Deprecated/superseded evidence is listed in
`docs/experiments/PROJECT_BASELINE_STATUS.md` and must not be cited as
current. This manuscript records interpretation; the validators and
per-episode artifacts record the evidence.*

## 18. Method-choice decision: adapted VLNVerse/VLNTube subset before full protocol
**Hypothesis/Question:** isolate EMA's effect before scaling to the full
benchmark protocol. **Setup:** documented four-scene subset
(`dataset_manifest.json`: 238 train / 15 held-out episodes, zero overlap,
trajectory-level holdout stated honestly); two-stage evaluation.
**Good:** clean ablation, reproducibility (episode-level manifest,
leakage check), real CR from Isaac. **Bad:** smaller data, preliminary
statistics, not a full benchmark; scene-level holdout not yet possible.
**Ugly:** the offline evaluator's fake-CR risk (prints 0.000 by
construction); the yaw-control limitation restricting physics routes;
prior out-of-sample stop-rule failures showing what happens without
held-out gates. **Mitigation:** dataset manifest, protocol-alignment
appendix, method-choice justification, Isaac physics CR with positive
control, held-out validation everywhere. **Decision:** adapted subset
retained; full protocol is the explicit next stage. **Insight:** every
method choice must answer why this protocol, what we gain/lose, what
failed, and what claim is now valid. **Next gate:** data expansion with
scene-level holdout. Evidence:
`assets/experiments/training_ablation/mnv2_ema_20260708/{dataset_manifest.json,protocol_alignment_vlnverse_vlntube.md,method_choice_justification.md}`.

## 19. Data expansion and scene-level held-out split (data-expansion-scene-holdout branch)
**Hypothesis:** increasing VLNVerse/VLNTube training and validation
coverage while preserving scene-level held-out testing will produce a
more reliable estimate of MobileNetV2-GNM generalization than the current
four-scene, trajectory-level split.
**Setup:** inventory of every local VLNTube data source (train/val
episode dirs, scene envs, prebuilt_data, upstream external/VLNTube,
HF download path), then a scene-level re-partition of the existing 253
episodes recorded in `dataset_manifest_scene_holdout.json`.
**Result:** train 191 (kujiale_0092/0118/0203) / val 12 (trajectory-level
within train scenes) / **test 50 = ALL episodes of kujiale_0271, fully
held out by scene** — 3.3× the previous 15-episode evaluation split.
`make validate-scene-holdout-split` asserts zero scene/trajectory/episode
overlap and that every path and goal image exists.
**The Good:** a true scene-level holdout now exists locally; the test
scene has never been seen by any retrained model; the upstream
`scene_splits.json` (176 trainval / 33 val_unseen / 53 test scenes)
gives the scaling target for full-protocol alignment later.
**The Bad:** all four local scenes are upstream *trainval* scenes, so the
local holdout cannot align with the upstream test list yet; holding out
0271 costs 47 training episodes (191 vs 238).
**The Ugly:** both expansion routes are currently blocked and were
verified honestly: the HF dataset repo
(frankleroyvan/fleetsafe-gnm-vlnverse) was never published (Repository
Not Found), and the upstream vistube generation pipeline is hardwired to
the original authors' server paths and needs composed scene USDs —
`vlntube_index.json` records `usd_scene_count: 0` locally (envs contain
Meshes/Materials/occupancy but no scene USDs).
**Root Cause:** the local corpus was delivered as pre-generated episode
folders; the generation stack behind it was never localized.
**Mitigation:** manifest-based split (no files moved, evaluator layout
untouched); expansion blockers and the concrete unblock path recorded in
the manifest's `expansion_status`.
**Decision:** kujiale_0271 is the frozen local test scene; no model may
be selected or tuned on it; no performance claims from this split until
models are retrained under it.
**Scientific Insight:** a smaller but scene-clean test set beats a larger
leaky one; split design must precede data generation so new trajectories
land only in train scenes.
**Limitation:** one held-out scene; upstream-scale scene diversity
(262 scenes) remains future work.
**Next Evidence Gate:** rebuild scene USDs from the local
Meshes/Materials, run vistube A* generation for TRAIN scenes only, then
retrain MobileNetV2-GNM under the scene-holdout split and report
SR/OSR/NE/SPL on kujiale_0271.

## 20. First scene-level held-out baseline + EMA repeat (Stage 1–2 of the data-expansion ladder)
**Hypothesis:** the scene-holdout split gives the first honest
generalization estimate; EMA repeated under it isolates the EMA condition
from split effects. **Setup:** MobileNetV2-GNM baseline and EMA 0.999
trained on 191 episodes (3 scenes), checkpoint selection on the
12-episode val split only, then exactly ONE evaluation per checkpoint on
the 50 held-out kujiale_0271 episodes (`--split test`). Same seed 42,
same config; EMA the only difference. **Result:** baseline SR 32.0 /
OSR 56.0 / NE 5.58 / SPL 0.315 (live weights); EMA 0.999 SR 18.0 /
OSR 50.0 / NE 5.91 / SPL 0.167 (EMA shadow) — worse on every metric.
**Good:** a real scene-generalization number now exists with n=50 (each
episode = 2 pp, vs 6.7 pp before); the one-shot test protocol held; the
EMA verdict now rests on a scene-clean split. **Bad:** EMA 0.999 tracked
validation loss well in the earlier ablation yet degrades held-out-scene
navigation — the loss-vs-SR proxy gap reappears at scene level.
**Ugly:** none new — the guardrails (single test evaluation, val-only
selection) were followed by construction via the symlinked split tree.
**Root Cause (EMA):** consistent with the ablation: at this data scale
and horizon, weight averaging does not help this model class navigate
unseen scenes. **Mitigation/Decision:** baseline retained as the Stage-1
reference; EMA not promoted; EMA 0.9999 remains a documented sensitivity
check only. Scene-holdout numbers are NOT comparable to the old
trajectory-level table. **Insight:** split design changes the measured
picture (SR 13.3→32.0 across splits is a protocol difference, not an
improvement claim). **Limitation:** one held-out scene; offline metrics
only; CR remains Isaac-only. **Next Evidence Gate (Stage 3):** scene-USD
reconstruction → vistube generation for TRAIN scenes only → Stage 4
retrain → Stage 5 comparison against this reference on untouched
kujiale_0271. Evidence:
`assets/experiments/training/scene_holdout_mnv2_baseline_20260708/`,
`make validate-scene-holdout-training`.

## 21. Stage 3B: First generated train-scene episode from composed Isaac USD
**Hypothesis:** with the composed stages usable (Stage 3A), a locally
generated episode can match the existing dataset format exactly and pass
through the unmodified loader. **Setup:** coordinate calibration on
kujiale_0092, A* route on the eroded occupancy map, headless-Isaac
rendering at 224×224 along the route, packaging as frames +
traj_data.pkl + metadata under `datasets/vlntube_generated/` (never
mixed into original data).
**Result — gate PASSED:** `gen_kujiale_0092_0000` (19 frames, 1.91 m
route) yields 18 valid samples through the unmodified `GNMDataset`
(obs (15,96,96) context stack, goal, action, dist all correct).
**The Good:** the calibration is closed-form and *proven*: the world→
pixel transform projects every trajectory point of all 66 existing
kujiale_0092 episodes onto free space at exactly 1.000. The stage's
world bounds match occupancy.json to 12 decimals.
**The Bad:** the first auto-selected route renders wall-heavy views;
forward-clearance route scoring is required before mass generation.
Camera height (1.2 m) is assumed, not recovered from the original
generator.
**The Ugly:** the coordinate x-axis is MIRRORED between world and pixel
space — every unmirrored convention failed (0.30–0.59 free-fraction),
offset searches "improved" toward overfit corners, and rooms.json
polygons turned out to be offset from the wall raster (a trap for any
polygon-based calibration). Two evidence-based hypotheses (bounds match,
top-down footprint) pointed to the mirror before the decisive
trajectory-projection test confirmed it.
**Root Cause:** the original exporter mirrored x when rasterising the
occupancy map; nothing documents this.
**Mitigation/Decision:** calibration recorded with its full evidence
chain and rejected hypotheses; automatic seeded route selection replaces
hardcoded points; kujiale_0271 untouched (validator-enforced).
**Insight:** calibrate against ground-truth trajectories, not metadata
artifacts — the 1.000 test is reusable for the other two train scenes.
**Limitation:** this stage validates ONE generated train-scene episode
through the existing loader. It does not yet claim improved model
performance or full data expansion.
**Next Evidence Gate (Stage 3C):** route-quality scoring, per-scene
calibration for kujiale_0118/0203, then +50–100 seeded episodes —
followed by Stage 4 retraining and the Stage 5 frozen-scene comparison.
Evidence: `assets/experiments/data_expansion/generated_episode_smoke_20260708/`,
`make validate-generated-episode-smoke`.

## 22. Stage 3C: route-quality-controlled generated train batch
**Hypothesis:** with per-scene calibration proofs and a verified camera
model, a quality-scored pilot batch (10 episodes × 3 train scenes) can
pass the unmodified loader and be fit for retraining.
**Setup:** route policy (A* on 3-px-eroded free space, clearance ≥ 0.25 m
at every point, 2–6 m length, ≤1.5× curvature, dedup, goal-frame content
check), seeded generation, batch loader validation.
**Result — validator PASS:** 30 episodes, 1,098 frames, 1,068 samples
through the unmodified GNMDataset; calibration free-fraction 1.000 on
all three train scenes; goal-content 26/30.
**The Good:** the calibration proof transferred perfectly to
kujiale_0118/0203 (1.000 each); generation is fast (~50 s/scene for 10
episodes) so Stage 3D scaling is cheap.
**The Bad:** 4/30 goal frames are featureless floor patches (recorded,
flagged); small renderer/lighting differences vs originals remain.
**The Ugly — the finding that changed everything:** rendering at the
exact recorded poses of an original episode exposed that the ORIGINAL
VLNTube frames are TOP-DOWN (bird's-eye), not first-person. The Stage 3B
smoke episode used a first-person camera and was therefore
out-of-distribution; it was superseded and regenerated. Grid tests
pinned the original model: nadir, z = 2.4 m, focal 16 mm, image rotation
rotateXYZ(0,0,deg(yaw)). This also reframes what the trained GNM
actually does: it navigates from overhead floor appearance, not
first-person views — a fact worth its own discussion in the paper.
**Root Cause:** nothing in the dataset documents the camera model;
only pose-exact re-rendering could reveal it.
**Mitigation/Decision:** camera model locked and documented with
comparison sheets; route policy adjusted honestly (first-person
wall-facing checks are N/A for a top-down camera); pilot accepted.
**Insight:** verify the camera model against the data before generating
a single training frame — a plausible-looking generator can be silently
out-of-distribution.
**Limitation:** exact claim wording — this stage validates
route-quality-controlled generation for train-side scenes. It does not
yet claim improved model performance. The frozen scene-held-out baseline
remains SR 32.0 / OSR 56.0 / NE 5.58 / SPL 0.315 until retraining and
one-time evaluation are completed.
**Next Evidence Gate (Stage 3D):** goal-pose resampling for weak goal
frames, scale to +50–100 episodes, then Stage 4 retrain and the Stage 5
one-time frozen-scene comparison. Evidence:
`assets/experiments/data_expansion/generated_train_batch_20260708/`,
`make validate-generated-train-batch`.

## 23. Stage 3D: scaled top-down generated training data
**Hypothesis:** with the goal-content precheck, generation can scale to
+100 episodes with zero weak goals, staying strictly inside the
top-down VLNTube camera regime.
**Setup:** weak-goal resampling (4 Stage-3C episodes, all kujiale_0118,
deleted and regenerated under precheck), then 34/37/33 new episodes
(seeds 11/12/13) with cross-batch dedup; camera locked to the verified
nadir model on every episode and asserted by the validator.
**Result — validator PASS:** 130 generated episodes (44/43/43 per train
scene), 4,402 frames, 4,272 samples through the unmodified GNMDataset,
**goal content 130/130** (pilot was 26/30).
**The Good:** the precheck works as designed — render the goal frame
first, reject weak routes before paying for episode rendering; the
whole 100-episode expansion took minutes.
**The Bad:** kujiale_0118 rejects ~50% of candidate routes at the
goal-content gate (large featureless floor regions) — a scene-specific
data-quality tax.
**The Ugly:** the 0118 run produced exactly 37 strong candidates for a
37-episode request — zero headroom; a one-route shortfall would have
crashed the run. The oversampling factor is now the documented knob.
**Root Cause:** goal-frame information content varies strongly by scene
texture at the top-down camera scale.
**Mitigation/Decision:** precheck retained; oversampling factor noted in
blockers; two-camera-regime rule locked in camera_model_lock.md (Kujiale
training = top-down only; hospital front-camera demo = separate, never
mixed).
**Insight:** data-quality gates belong BEFORE the expensive render, and
per-scene pass rates are themselves a useful scene diagnostic.
**Limitation (exact claim):** this stage expands train-side top-down
VLNTube-style data generation. It does not claim improved model
performance until the model is retrained and evaluated once on the
frozen scene-held-out test scene kujiale_0271.
**Next Evidence Gate:** Stage 4 retrain (191 original + 130 generated,
val-only selection) → Stage 5 one-shot evaluation on kujiale_0271 vs
SR 32.0 / OSR 56.0 / NE 5.58 / SPL 0.315.
Evidence: `assets/experiments/data_expansion/generated_train_expanded_20260708/`,
`make validate-generated-train-expanded`.

## 24. Reference Dataset Audit: GNM, ViNT, NoMaD, and VLNTube/Kujiale training-data choice
**Hypothesis:** the project's data choices must be positioned against
the GNM/ViNT/NoMaD data philosophy before any method comparison.
**Setup/Result:** audit doc + 9-row dataset matrix + small experiment
plan (`make validate-reference-dataset-audit` PASS). GNM's public
training data (RECON, TartanDrive, SCAND, modified GoStanford2 — plus
unreleased data), ViNT's foundation-scale mixture and NoMaD's addition
of HuRoN/SACSoN are all front-camera real-robot regimes; our local
VLNTube/Kujiale corpus is top-down synthetic.
**Good:** the two-regime firewall now has a documented external
justification; Experiment C (adapter-based compatibility smoke on
GoStanford2) is scoped without touching training.
**Bad:** the GNM mixture is partly unreleased — exact-data reproduction
is impossible and bounds all comparison claims.
**Ugly:** none — this is a paper-positioning stage.
**Decision:** Level-1 internal data comparison only for now; "we beat
GNM/ViNT/NoMaD" is a banned claim, validator-enforced.
**Next gate:** Experiment C compatibility smoke, after the Stage 4/5
result is closed.

## 25. Expanded top-down training data: scene-held-out result (Stage 4/5)
**Hypothesis:** adding matched-camera, top-down generated train-side
VLNTube-style episodes improves scene-held-out generalization on the
frozen kujiale_0271 test scene.
**Setup:** 321 train episodes (191 original + 130 generated, symlinked
combined root, zero 0271 leakage), same 12-episode val for selection
only, seed 42, ONE post-training test evaluation.
**Result — HYPOTHESIS REJECTED:** expanded model SR 26.0 / OSR 56.0 /
NE 6.90 / SPL 0.247 / TL 9.32 vs incumbent SR 32.0 / OSR 56.0 /
NE 5.58 / SPL 0.315 / TL 7.47. Worse on SR, SPL and NE; longer
trajectories. Incumbent retained.
**The Good:** the ladder worked exactly as designed — a controlled
one-shot frozen-scene test caught that perfectly-validated generated
data (130/130 goal content, matched camera, loader-clean) does not
automatically transfer; the independent governance chain concurred
(DriftGuard reject on all three checks, VerdictPlane deny, Sentinel
proxy-gap incident).
**The Bad:** a full generation stage produced no downstream gain.
**The Ugly:** every data-quality gate we built passed while the data
still hurt performance — data validity and data USEFULNESS are
different properties, and only the held-out test separates them.
**Root-cause hypotheses (testable, ranked):** (1) A*-smooth generated
routes are information-poor vs original human-tour-style trajectories;
(2) 4-scene coverage was already saturated at 191 episodes;
(3) the 12-episode val split cannot select for unseen-scene behaviour.
**Decision:** incumbent 191-episode baseline remains the reference;
expanded candidate rejected; no retraining variations without a new
pre-registered hypothesis.
**Insight:** "more validated data" is not "better data" — route/view
diversity, not volume, is the next lever.
**Limitation:** result is one scene (kujiale_0271); claim wording per
the pre-registered boundary.
**Next Evidence Gate:** route-diversity generation experiment (curved/
multi-room routes mimicking original trajectory statistics) OR the
Isaac-Hospital internal dataset track — Frank's call.
Evidence: `assets/experiments/training/expanded_topdown_20260708/`,
`make validate-expanded-data-training`.
