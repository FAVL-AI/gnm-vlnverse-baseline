# H8-M Track B — Scene Scouting Plan (PLANNING ONLY)

**Status: planning only.** No collection, no training, no promotion, no push, no tag, no
recording, no drive-validation, no 20/5/10, no closed-loop Isaac testing; `CL_BOUND_XY`
unchanged. This document identifies *candidate* scenes and the gates a scene must pass; it
authorises no rendering, driving, or training. Any scene render-scan is a separate, later,
explicitly-approved step.

**Context reference:** the H8-M re-scope decision (commit `670219e`,
`docs/research/H8_M_RESCOPING_AFTER_JUNCTION_SCAN.md`) and the depth-aware junction scan evidence
(commit `ff93e46`).

---

## 1. Purpose

The depth-aware junction scan showed that `hospital.usd` **cannot support angular branch-choice**
under the current verified ±6 m safe envelope: the apparent junctions were textured walls, not
navigable branches (RGB/luma/DINO falsely accepted 7 of 8 candidates; depth openness corrected
all of them to `WALL_ONLY`; zero render-valid junctions). H8-M therefore splits into two tracks.
Track A keeps `hospital.usd` as the distance/stop-axis and hospital-scene visual-validity
environment. **Track B needs a different scene that actually contains a real fork / T-junction**
so the angular branch-choice test is well-posed. This plan is the scouting step for Track B: it
selects candidate scenes and defines the gates each must clear *before* any model work.

## 2. Scene requirements

A Track-B candidate scene must provide:

- a **real T-junction or fork** (two corridors diverging from one decision point), not a straight
  corridor with side walls;
- **two visually valid goal branches** (each branch renders as an actual open corridor);
- a **decision frame with open depth** ahead (the junction is visible and reachable);
- an **expected action-angle separation ≥ 30°** between the two branches;
- **visually distinct goal images** (the two branches are genuinely different, not the same wall
  twice — embedding-distinct);
- **safe spawn-relocation** to place the agent at the decision point within a bounded, watchdog-
  respecting envelope (no `CL_BOUND_XY` change; if the junction sits outside the current safe
  envelope, that is a spawn-relocation/new-scene question, never a watchdog edit);
- **render-validity and depth-openness checks** passable (both branches: median central depth
  ≥ 3.0 m via `distance_to_image_plane`; < 2.0 m ⇒ `WALL_ONLY`);
- a **later drive-validation possibility** (the branches must be plausibly drivable, to be
  confirmed in a separate Step-C gate — not asserted here).

## 3. Candidate scene types

Consider (type-level only; specific asset selection and render-scan are later, approved steps):

- **Office corridor with a branch** — office/indoor USD environments typically include corridor
  intersections; strong candidate for a clean, well-lit T-junction.
- **Warehouse corridor fork** — aisle intersections give wide, high-depth branches; good depth
  openness, but watch for visually *similar* aisles (embedding-distinctness risk).
- **A hospital wing, only if a different validated area exists** — reuse the hospital domain only
  if a genuinely different, drivable, junction-bearing region is validated first (do **not**
  re-search the current envelope without a new validated map/room-access path).
- **Indoor navigation scene with a clear junction** — any indoor USD with a documented
  intersection and open branches.
- **Simple synthetic junction scene** — a constructed corridor-fork, used **only as a diagnostic
  fallback and clearly labelled as synthetic** (never presented as a real-scene benchmark).

## 4. Validation gates (before any model training)

Each candidate must pass, in order, before Track-B training is even proposed:

1. **Render-validity gate** — decision + both goal views render (non-blank, luma ≥ threshold,
   lower-frame black ≤ threshold).
2. **Depth-openness gate** — both branches median central depth ≥ 3.0 m (`distance_to_image_plane`).
3. **Embedding visual-distinctness gate** — the two branch images are distinct (DINO cosine below
   threshold); not the same corridor twice.
4. **Design action-separation gate** — expected action-angle separation ≥ 30°.
5. **Drive-validation gate** — the decision point and both branches are actually drivable
   (separate Step-C check, bounded, watchdog-respecting).
6. **Recorded-mode gate** — decision/branch episodes reproduce in recorded mode before any
   closed-loop step.
7. **Action-probe gate** — the model's predicted action responds to goal branch identity (the
   causal probe), evaluated on held-out branches.

A candidate that fails any gate is re-scoped or dropped — never forced through.

## 5. Metrics and diagnostics

Track B must still report, honestly and only where the underlying evidence exists:

- **TL, NE, SR, OSR, SPL, nDTW, CR** — only where a rollout actually exists (no offline
  fabrication; mark N/A otherwise, as in H8-S);
- **action-probe** (goal-branch sensitivity of predicted actions);
- **mismatched-goal ablation** (correct-goal vs placeholder/substitute response);
- **branch-choice accuracy** (does the model pick the branch matching the goal image);
- **goal-sensitivity score** (magnitude/direction of response to goal change);
- **visual-distinctness audit** (embedding separation of the branches used);
- **leakage audit** (train/val/test branch and scene-region separation; no goal image leaks
  across splits).

## 6. Claim boundary

Track B remains **diagnostic until multi-seed and closed-loop evidence exist**. Specifically:
**no SOTA**, **no promotion** (incumbent retained; `DIAGNOSTIC_ONLY_NOT_PROMOTED`), and
**no full autonomy claim**. A single-seed or recorded-only result is a diagnostic signal, not a
benchmark.

## 7. Output recommendation — scouting shortlist

Produce a small shortlist (**3–5 candidate scenes or scene regions**), each characterised by:

- **expected junction type** (T-junction / fork / cross / aisle intersection),
- **expected validation risk** (e.g. depth-openness risk, embedding-similarity risk, lighting/
  render-validity risk, drivability risk),
- **render-scan-first?** — whether the candidate is worth a bounded render-scan (render-validity +
  depth-openness only) before any heavier validation.

Initial type-level shortlist to evaluate (asset selection + render-scan are later approved steps):

| # | candidate (type-level) | expected junction | main validation risk | render-scan first? |
|---|---|---|---|---|
| 1 | Office indoor USD — corridor intersection | T-junction | lighting/render-validity; confirm depth openness | Yes |
| 2 | Warehouse USD — aisle intersection | fork / cross | branch **visual similarity** (embedding-distinctness) | Yes |
| 3 | Indoor-nav USD with documented junction | T-junction | drivability of both branches | Yes |
| 4 | Alternate validated hospital wing (only if newly validated) | fork | requires a NEW validated map/room-access path first | No (blocked until map validated) |
| 5 | Synthetic corridor-fork (diagnostic fallback, clearly labelled) | fork | not a real-scene benchmark; label as synthetic | Yes (diagnostic only) |

Recommended first action after approval: a **bounded render-scan (render-validity + depth-openness
only)** on candidates #1–#3, mirroring the hospital junction-scan method, before any distinctness,
drive, or training work.

---

## Professor-safe explanation

The hospital scene is still valuable, but only for the distance/stop-axis track. The depth-aware
scan showed that it cannot support angular branch-choice because the apparent junctions were
textured walls, not navigable branches. So H8-M now splits into two honest tracks: hospital for
stop/distance diagnostics, and a separate junction-capable scene for angular goal-conditioning.
