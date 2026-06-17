# Track A and Track B Completion Gates

## Overview

This document defines the completion gates for Track A and Track B.

A **completion gate** is a specific, checkable condition. The track is not
complete until every gate passes. Each gate must have matching evidence in the
repository — a test, a result file, a documented metric, or a passing script.

Claims must not be made ahead of the evidence. If a gate is pending, the track
is pending.

---

## Track A — Visual Navigation and Stopping Reliability

Track A answers:

> Can the robot navigate visually toward a goal and stop correctly when it arrives?

Track A is not just "does the robot move." It is a controlled study of navigation
quality, stopping reliability, and the gap between entering the goal region and
stopping reliably at it.

### Track A Completion Gates

#### Gate A1 — GNM Baseline Reproduced

- [ ] Public GNM checkpoint loads without error.
- [ ] GNM runs inference on at least one VLNVerse/Kujiale episode.
- [ ] Baseline SR, OSR, and NE are reproduced within ±2% of published values.
- [ ] Evidence file: `results/bo_reviewer_packet/00_tracka_reviewer_summary.md`

SR means **Success Rate** — fraction of episodes where the robot reached and
stopped at the goal.

OSR means **Oracle Success Rate** — fraction of episodes where the robot entered
the goal region at any point, whether or not it stopped correctly.

NE means **Navigation Error** — mean distance from the robot's final position to
the goal.

Current values:

| Metric | Baseline GNM |
|---|---|
| SR | 20.0% |
| OSR | 46.7% |
| NE | 6.51 m |

#### Gate A2 — Stopping Gap Diagnosed

- [ ] The SR/OSR gap (26.7 percentage points) is documented and explained.
- [ ] Evidence file shows that most failures are stopping failures, not
  navigation failures.
- [ ] Temporal stop head result documented: SR 33.3%, NE 4.47 m.

#### Gate A3 — Stop Policy Study Complete

- [ ] Logistic stop head tested and documented.
- [ ] Temporal neural stop head trained on Track A train split.
- [ ] Temporal stop head evaluated on held-out Track A validation split.
- [ ] Feature ablation results documented.
- [ ] All stop-policy tests pass in `tests/gnm/`.

#### Gate A4 — Dataset Manifest Verified

- [ ] 238 training trajectories confirmed.
- [ ] 15 validation trajectories confirmed.
- [ ] Four Kujiale/VLNVerse scenes documented (kujiale_0092, 0118, 0203, 0271).
- [ ] Dataset manifest file: `results/bo_reviewer_packet/28_dataset_scene_manifest.md`
- [ ] Scene-level split documented.
- [ ] No data leakage between train and validation splits.

#### Gate A5 — Yahboom Canonical Topic Verification Passes

- [ ] `python3 scripts/gnm/verify_yahboom_live_topics.py --strict` passes with
  Isaac Sim running and Yahboom stage loaded.
- [ ] All five canonical topics publish non-zero messages:
  `/camera/image_raw`, `/odom`, `/tf`, `/scan`, `/cmd_vel`
- [ ] No Nova Carter topic names in any Yahboom recording.

This gate is the prerequisite for A6 and all subsequent gates.

#### Gate A6 — First Valid Yahboom Isaac Rosbag2 Episode

- [ ] At least one rosbag2 episode recorded from Yahboom in Isaac Sim.
- [ ] All five canonical topics present in the bag with non-zero message counts.
- [ ] Episode metadata file written with start state, goal state, and timestamp.
- [ ] `collect_isaac_rosbag_episode.sh` (without `--dry-run`) completes.
- [ ] Bag replay confirms topic availability.

#### Gate A7 — Yahboom Rosbag2 Converts to GNM Format

- [ ] `convert_rosbag_to_gnm_dataset.py` (without `--dry-run`) completes on
  the Yahboom episode.
- [ ] Output contains: context images, goal image, waypoints, odometry,
  scan summary, success label.
- [ ] Waypoint labels are numerically valid (no NaN, no zero-length vectors).
- [ ] Dataset manifest updated with Yahboom episode counts.

#### Gate A8 — GNM Evaluates on Yahboom Data

- [ ] GNM runs inference on at least one Yahboom-format episode.
- [ ] Output shape is correct (waypoint prediction is a 2D vector).
- [ ] SR, OSR, and NE reported for Yahboom evaluation split.
- [ ] Results saved to `results/gnm_fleetsafe_v2/`.

#### Gate A9 — GNM+FleetSafe Evaluated

- [ ] FleetSafe CBF-QP safety filter is active in the loop.
- [ ] GNM-only vs GNM+FleetSafe comparison runs on the same episode set.
- [ ] Evaluation CSV and Markdown written by `eval_gnm_vs_fleetsafe.sh`.
- [ ] Intervention count and minimum clearance documented.
- [ ] SR is not lower with FleetSafe than without, unless the difference is
  explained by conservatism.

CBF means **Control Barrier Function** — a mathematical safety rule that keeps
the robot outside dangerous regions.

QP means **Quadratic Program** — an optimisation that finds the safest command
closest to the original command.

#### Gate A10 — All Track A Tests Pass

- [ ] `python3 -m pytest tests/gnm -q` passes with no failures.
- [ ] `bash scripts/gnm/run_reproducibility_pack.sh` exits with `[SUCCESS]`.
- [ ] No Track A claim is made without a passing test backing it.

---

## Track B — Language Grounding and Instruction-Aware Navigation

Track B answers:

> Can the robot connect a language instruction to its navigation behaviour in a
> measurable way?

Example language instruction:

> "Go to the office door. Move past the sofa. Stop near the kitchen entrance."

Track B is not just "does the robot move when given an instruction." It is a
controlled study of whether the language signal measurably changes the robot's
behaviour compared to a control condition that does not use the instruction.

### Track B Completion Gates

#### Gate B1 — Task and Dataset Defined

- [ ] The language grounding task is clearly defined and separated from Track A.
- [ ] Instruction/annotation format is documented.
- [ ] Data manifest exists with instruction count, environment count, and split.
- [ ] No Track A episodes are re-labelled as Track B data without documentation.

#### Gate B2 — Language Signal is Isolatable

- [ ] A control experiment exists that uses the same observations without the
  language signal.
- [ ] The control experiment baseline is documented.
- [ ] Language-dependence is shown by comparison to this control.

This is the key Track B scientific requirement. If the model performs the same
with and without the language instruction, there is no grounding evidence.

#### Gate B3 — Held-out Validation Exists

- [ ] A held-out validation split is defined that was not used during training.
- [ ] Validation instructions or annotations are not seen during training.
- [ ] The split is documented in the data manifest.
- [ ] Validation metrics are reported separately from training metrics.

#### Gate B4 — Baseline Language-Grounding Result Documented

- [ ] At least one language-grounding method is evaluated on the held-out split.
- [ ] Metrics are reported (task success rate, language-relevance score, or
  equivalent).
- [ ] The result is compared to the control condition from Gate B2.
- [ ] The difference is statistically described (not just "it improved").

#### Gate B5 — Track B Tests Pass

- [ ] Tests for Track B exist under `tests/gnm/` or equivalent.
- [ ] Tests verify: data format, model loads, evaluation runs, claim boundary.
- [ ] `python3 -m pytest tests/gnm -q` passes with no failures.

#### Gate B6 — Track B Claim Boundary Is Clear

- [ ] The Track B document explicitly states what is and is not claimed.
- [ ] Track B does not overclaim language understanding beyond what evidence shows.
- [ ] Track A and Track B results are reported separately and not mixed.

---

## Shared Gates for Both Tracks

These gates apply to both Track A and Track B before either is considered complete.

| Gate | Requirement |
|---|---|
| No external attribution | No AI attribution, tool branding, or co-author trailers in any file |
| Reproducibility | All results can be reproduced from the reproducibility pack |
| Attribution-free commits | No generated-by notes in commit messages or documentation |
| Tests pass | `python3 -m pytest tests/gnm -q` exits with zero failures |
| Pack passes | `bash scripts/gnm/run_reproducibility_pack.sh` exits with `[SUCCESS]` |
| Clean working tree | `git status --short` shows no unintended modifications at release time |

---

## Current Status

| Gate | Status |
|---|---|
| A1 — Baseline reproduced | Complete |
| A2 — Stopping gap diagnosed | Complete |
| A3 — Stop policy study | Complete |
| A4 — Dataset manifest | Complete |
| A5 — Canonical topic verification | Pending (requires live Isaac Sim) |
| A6 — First Yahboom rosbag2 episode | Pending (v2.4) |
| A7 — GNM dataset conversion | Pending (v2.5) |
| A8 — GNM evaluation on Yahboom | Pending (v2.6) |
| A9 — GNM+FleetSafe evaluation | Pending (v2.7) |
| A10 — All tests pass | Ongoing |
| B1 — Task and dataset defined | Pending |
| B2 — Language signal isolatable | Pending |
| B3 — Held-out validation | Pending |
| B4 — Baseline result | Pending |
| B5 — Track B tests | Pending |
| B6 — Claim boundary clear | Pending |
