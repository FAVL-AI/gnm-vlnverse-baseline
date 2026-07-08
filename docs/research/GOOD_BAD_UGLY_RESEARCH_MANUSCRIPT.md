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
