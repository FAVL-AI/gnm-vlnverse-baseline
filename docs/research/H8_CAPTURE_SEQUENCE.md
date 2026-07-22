# H8 Capture Sequence — the eleven-step experimental order

Each step has an exit gate. **No step may begin before its predecessor's gate passes.** The ordering
is not administrative: several steps exist specifically because skipping them is what invalidated the
H1–H8MX corpus.

```text
 1. Lock dataset and metric protocol                    <- H8-S0 (this gate, no Isaac)
 2. Finish minimum trust / runtime-readiness gates      <- no Isaac
 3. Extend the navigable hospital map                   <- Session A (Isaac)
 4. Verify route and split independence                 <- Session A output, offline check
 5. Validate raised camera at 1280x720                  <- Session B (Isaac)
 6. Capture the goal-image bank                         <- Session C (Isaac)
 7. Lock goal pose and image hash for every instance    <- offline, before Session D
 8. Collect route images and trajectories               <- Session D (Isaac)
 9. Validate and convert the dataset                    <- offline
10. Train only after dataset validity passes            <- offline
11. Evaluate on untouched held-out instances            <- offline
```

---

## Step 1 — Lock dataset and metric protocol *(this gate)*

**Produces:** `H8_HOSPITAL_DATASET_PROTOCOL_V2.md`, `H8_EPISODE_SCHEMA_V2.json`,
`H8_METRIC_SPECIFICATION_V2.md`, this document, the goal-bank protocol, the session plans, the
historical classification and the literature correction plan.

**Gate:** Professor Bo Wei approves `tau = 0.50 m` and the success definition **in writing, before
any capture**. Schema validates as Draft-07. Controlled vocabularies fixed.

## Step 2 — Minimum trust and runtime-readiness gates *(no Isaac)*

Two blockers are clearable now and both are prerequisites for *any* dataset:

1. **Write and verify the image↔pose time-alignment procedure.** Bags are wall-stamped, trajectory
   logs sim-stamped, and wall exceeded sim by >3× in 74 % of historical episodes. Until an alignment
   with a stated tolerance exists and is tested, no per-frame supervision can be trusted.
2. **Author `build_h8_dataset_root.py`** (extending `build_h7r_dataset_root.py`) so the conversion
   path is review-ready before data exists.

Also here: the literature correction plan is executed, and the derived-image resize/crop/interpolation
policy is fixed and hashed.

**Gate:** alignment procedure written and unit-tested against historical bags (as a *test*, not to
admit them); builder skeleton reviewed.

## Step 3 — Extend the navigable hospital map *(Session A)*

Per `H8_MAP_EXTENSION_SESSION_PLAN.md`. **Creates no dataset episodes.**

**Gate:** scene digest recorded; navigable map v2 render-confirmed; navmap↔bringup frame resolved;
navmesh versioned; 1280×720 throughput verdict recorded.

## Step 4 — Verify route and split independence *(offline)*

Compute route overlap and leakage over the extended map. Confirm physically distinct val/test
far-goal coordinates exist. Assign `route_instance_id` such that a/b repetitions **share** an id.

**Gate:** `design_ready_to_record = true`; zero cross-split goal-coordinate reuse; zero a/b split
straddling. If distinct far-goals still do not exist, that is a reportable negative result — it is not
resolved by reusing coordinates.

## Step 5 — Validate raised camera at 1280×720 *(Session B)*

Confirm the 0.12 m raise eliminates the lower-frame obstruction at the new resolution (the raise is
provisionally locked on 640×480 evidence: 39/39 unraised bags occluded ~38 % of frame height, 23/24
raised clean). Measure publish rate, and camera/pose/command/contact synchronisation.

**Gate:** `black_band_fraction ≤ 0.01` across sampled frames; sustained rate and synchronisation
within the declared tolerance; contact telemetry confirmed available and recordable to a topic;
`/tf_static` confirmed published.

## Step 6 — Capture the goal-image bank *(Session C)*

Per `H8_GOAL_BANK_PROTOCOL.md`. Goals **before** routes, so substitution is structurally impossible.

**Gate:** every approved instance has a goal image captured at its own locked pose, arrival verified
within 0.05 m / 5°, image quality accepted.

## Step 7 — Lock goal pose and image hash *(offline)*

Run the five cross-split audits: hash uniqueness, cross-split disjointness, coordinate distinctness,
visual distinctness within a decision frame, and action separation (≥30° heading or ≥0.6 m distance).
Make records read-only.

**Gate:** all five pass. **No route capture begins otherwise.**

## Step 8 — Collect route images and trajectories *(Session D)*

Run **only** against pre-existing locked goal records. Record
`/camera/image_raw`, `/camera/camera_info`, `/odom`, `/tf`, `/tf_static`, `/clock`, `/cmd_vel` and the
contact topic. Emit `episode_manifest.json` (schema v2), scene-identity manifest and
`checksums.sha256` **into the bag directory**.

Reject incomplete episodes **immediately**: discard the partial bag, clear stale DDS shared memory,
resume. Bounded per-episode timeout with return-code capture; never process-pattern kills.

**Gate:** every admitted episode passes all thirteen acceptance gates in the protocol §8.

## Step 9 — Validate and convert the dataset *(offline)*

Recorded-mode acceptance (≥30° / ≥0.6 m separation, visual distinctness), goal-image hash cross-split
audit, artifact-completeness and leakage reports, then build the data-root with the derived-resize
policy recorded per image.

**Gate:** pre-training gate exits zero; provenance completeness = 1.0. **Non-zero ⇒ do not train.**

## Step 10 — Train *(offline)*

Only after step 9's gate passes.

**Gate:** no checkpoint is promoted or committed without explicit review.

## Step 11 — Evaluate on untouched held-out instances *(offline)*

Report `SR_0.50` primary, with `OSR_0.50`, the `SR_OSR_GAP_0.50`, `NE`, `TL`, and — only if the
navmesh supports them — `SPL`, `nDTW`, `SDTW`, `CLS`. Plus collision count and rate, completion time,
stop timing error, overshoot, pose-aligned success, latencies and provenance completeness.
Sensitivity at 0.25 / 0.50 / 0.75 / 1.00 m, clearly labelled as sensitivity.

**Gate:** `OSR ≥ SR` holds. Every table shows its `tau` and distance type. No metric is reported whose
required ground truth was unavailable. Track A (`tau = 3.0 m`) figures are never pooled with hospital
figures.

---

## Standing prohibitions across all steps

No historical bag is modified. No historical bag is relabelled as formal training evidence. No goal is
substituted post hoc. No threshold is chosen after seeing results. No scripted follower is labelled
`gnm_closed_loop`. Nothing is pushed or tagged without explicit authorisation.
