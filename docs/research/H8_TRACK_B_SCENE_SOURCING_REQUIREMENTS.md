# H8-M Track-B — Scene Sourcing Requirements

**Status: requirement definition (no execution).** No scene scanning, no rendering, no collection,
no training, no promotion, no push, no tag, no recording, no drive-validation, no 20/5/10, no
closed-loop Isaac testing; `CL_BOUND_XY` unchanged. This document defines what a Track-B scene must
provide and the gates it must pass; it authorises no rendering or training. Its purpose is to stop
random scene-hunting and give a clean, professor-facing research boundary.

**Evidence references (committed):** hospital junction scan `ff93e46`; re-scope `670219e`; Track-B
scouting plan `1a944cb`; asset inventory `f767565`; office+warehouse_simple scan `21444e3`;
warehouse_full scan `4e919ef`.

---

## 1. Why new scene sourcing is required

`hospital.usd`, `office_isaac`, `warehouse_simple`, and `warehouse_full` do **not** provide a
render-valid angular branch-choice setup under the current gates. Across four scenes the automated
depth+embedding gate produced repeated false positives (open floor / a shelf / a straight aisle
scoring just under the distinctness threshold), each caught only by mandatory contact-sheet visual
verification. No scene contained a real navigable T/Y/cross junction with two visually-distinct,
angularly-divergent branches. Track B therefore needs a **different, deliberately-sourced scene**
rather than more opportunistic scanning of Isaac stock assets.

## 2. Evidence summary

- **`hospital.usd`** — no render-valid junction in the safe ±6 m envelope; depth-aware junction
  scan returned zero navigable forks (the reachable area is a single straight corridor + lobby).
- **`office_isaac`** — no confirmed render-valid junction; open-plan bullpen and under-lit (most
  probes rendered near-black), so the office scan is partly inconclusive; lit regions show an open
  bullpen, not a corridor junction.
- **`warehouse_simple`** — a single large open hall; automated gate false-positived probe `p32`
  (open floor vs a shelf, DINO just under threshold); visual verification + open-floor guard
  rejected it → zero junctions.
- **`warehouse_full`** — open floor (centre) + straight parallel aisles along the racks; automated
  gate false-positived probe `p13`; contact-sheet verification showed a straight aisle (goalA/goalB
  are opposite ends of one aisle, sep 180°; the decision view is a rack face), downgraded → zero
  junctions. Final counts: 14 `OPEN_FLOOR_NOT_JUNCTION`, 7 `RENDER_VALID_BUT_VISUALLY_WEAK`, 4
  `WALL_ONLY`, 0 `RENDER_VALID_JUNCTION`.

**All four scenes have failed the Track-B render-valid-junction gate: `hospital.usd`,
`office_isaac`, `warehouse_simple`, and `warehouse_full`.** `hospital.usd` remains useful **only
for distance/stop-axis diagnostics** (Track A), not angular branch-choice. The current
`office_isaac`, `warehouse_simple`, and `warehouse_full` assets **do not support angular
branch-choice**. RGB / depth / embedding gates can still false-positive (open floor, a shelf, a
straight aisle) **without mandatory contact-sheet verification**.

## 3. Required scene geometry

The new scene must contain:

- a **real T-junction, Y-junction, or cross-junction** (an actual corridor/aisle fork);
- **two navigable branches diverging by at least 30°** (perpendicular T-arms, a Y fork, or a
  cross — not two ends of one straight corridor);
- **branch-specific goal views** (each branch leads somewhere visibly different);
- a **decision frame with open depth toward both branches** (the junction is visible and reachable,
  median central depth ≥ 3.0 m down each branch);
- **no wall-only false positives** (a branch that is actually a wall/rack < 2.0 m is not a branch);
- **no open-floor-only false positives** (a point open in all directions with no bounding corridor
  walls is an open hall, not a junction);
- **no purely collinear near/far setup** (goalA and goalB must not be opposite ends of the same
  straight corridor — sep ≈ 180° with no real angular divergence is the H8-S degenerate case).

## 4. Required visual properties

The new scene must support:

- **visually valid goal A and goal B** (rendered, non-blank, adequately lit);
- **branch-specific visual cues** (each branch is recognisably different);
- **embedding distinctness** (goal A vs goal B DINO cosine below the distinctness threshold, with
  margin — not a marginal near-threshold pass);
- **no blank / black / wall-only goal images**;
- **no excessive darkness or occlusion** (the scene must be lit well enough to render valid views;
  the office failure was largely a lighting problem).

## 5. Required validation gates (before training)

In order, each must pass — a failure at any gate stops progression:

1. **Scene-load gate** — the scene loads (reference authored, populated, non-degenerate footprint).
2. **Render-validity gate** — decision + both goal views render (non-blank, luma OK, low black).
3. **Depth-openness gate** — both branches median central depth ≥ 3.0 m.
4. **Open-floor guard** — reject points open in all four cardinal directions ≥ 4.0 m (open hall).
5. **Visual / human contact-sheet verification** — mandatory before any `RENDER_VALID_JUNCTION`.
6. **Embedding distinctness gate** — goal A vs goal B genuinely distinct (with margin).
7. **Action-angle separation gate** — branches diverge ≥ 30° (and not a collinear 180° straight
   corridor).
8. **Drive-validation gate** — both branches and the decision point are actually drivable (bounded,
   watchdog-respecting; a separate Step-C check).
9. **Recorded-mode gate** — decision/branch episodes reproduce in recorded mode.
10. **Leakage audit** — no decision frame, goal image, or coordinate reused across train/val/test.

## 6. Minimum dataset target

Proposed minimum before any Track-B training is considered meaningful:

- **train ≥ 12 decision frames**,
- **val ≥ 4 decision frames**,
- **test ≥ 6 decision frames**,
- **no reused decision frame across splits**,
- **no reused goal image across splits**,
- **no coordinate reuse across splits**.

A dataset below this scale is a diagnostic pilot, not a benchmark (as with H8-S).

## 7. Claim boundary

- **No angular branch-choice training** until the scene passes the render gates **and** drive
  validation.
- **No full goal-conditioned ImageNav claim** from the current scenes.
- **No SOTA.**
- **No promotion** (incumbent retained; `DIAGNOSTIC_ONLY_NOT_PROMOTED`).
- **No autonomy claim.**

## 8. Recommended next action

Select or acquire **one** scene with a **documented corridor fork / T-junction** (a warehouse with
real cross-aisles, an office/building USD with a corridor intersection, or a maze/indoor-nav asset
with a labelled junction). If no suitable real-world-like asset is available, **build a small,
verified diagnostic fork scene** — a clean T/Y/cross of bounded corridors — and **label it
synthetic / diagnostic-only** (never presented as real-scene or benchmark evidence). Run the
bounded render-scan (gates 1–7) on that one scene before any drive, recording, or training work.

---

## Professor-safe wording

The negative result is now strong and useful: hospital, office, simple warehouse, and full
warehouse all fail to provide a real angular branch-choice scene. The repeated false positives show
why RGB, depth, and embeddings are not enough without contact-sheet verification. Training remains
blocked until we source a scene with a genuine navigable T/Y/cross junction.
