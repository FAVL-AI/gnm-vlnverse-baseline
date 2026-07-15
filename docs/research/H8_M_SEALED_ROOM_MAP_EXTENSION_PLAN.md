# H8-M — Sealed-Room Map-Extension Plan (PLANNING ONLY)

**Status:** planning only. No collection, no training, no promotion, no push, no tag, no
closed-loop Isaac, **no `CL_BOUND_XY` change**. Plans how to reach/validate the currently
sealed reception/waiting-room areas so H8-M can support a **genuine multi-room held-out visual
split**. Changes no committed result.

**Provenance.** Follows `584e19e (visual-gap evidence)` and
`H8_S_LIMITED_CAUSAL_PILOT_SCOPE.md`. Verdict carried forward: `DIAGNOSTIC_ONLY_NOT_PROMOTED`,
incumbent retained.

**Professor-safe framing:**
> The map-extension recovery fixed the coordinate split problem but exposed a visual split
> problem: the drivable envelope is a single alcove, so H8-S cannot provide strong held-out
> visual distinctness. H8-M must first validate access to genuinely different rooms (reception /
> waiting) before any collection, and must judge distinctness with an embedding metric rather
> than crude aHash.

---

## 1. Why H8-S cannot provide strong held-out visual distinctness

- The reliably-drivable in-envelope space (|x| ≤ ~−3.4…+3.5, within the ±6 m `CL_BOUND_XY`
  watchdog) is **one alcove**: vending machine + wheelchair (east-facing) and waiting-chairs +
  water cooler (west-facing). All train/val/test goals are the **same room** at different
  scales/ends (visual-gap matrix: east test trio 0.89–0.96; seating vs lobby ≈0.78–0.81).
- Genuinely distinct **locations** (reception hall, waiting rooms, side corridors) are **not
  reachable** in the robot collision slab — even uninflated, no rooms/side-branches connect to
  the spawn corridor (they are sealed behind walls/narrow doorways in the z-slab [0.08, 0.55]).
- Therefore a **strong held-out visual split** (train/val/test goals in visually-different rooms)
  is impossible inside the current envelope; H8-S is limited to a within-alcove causal pilot.

## 2. Which sealed / deferred areas are needed

Target genuinely-distinct scenes for held-out val/test goals (from
`H8_CAUSAL_COLLECTION_DESIGN.md` §4 and the deferred zones in the map-extension analysis):
- **reception / front-desk hall** — distinct architecture and props;
- **waiting room(s)** — seating clusters distinct from the alcove's chairs;
- **elevator / bin / side-alcove** — small distinct landmarks;
- **a second corridor branch** — different wall features / signage;
- **same-room-different-object** and **visually-similar-but-different-location** families (DF09 /
  DF10), which need multi-object rooms and look-alike-but-distinct locations.

Each must be **render-confirmed** (real hospital context, no black occlusion) **and**
**drive-confirmed** (0 collisions) before use — the same two-stage gate that caught west_C.

## 3. Safety checks required before entering those areas

Reuse the locked pipeline; **do not weaken any check**:
- **Scene gate** (fail-closed hospital.usd identity) per episode.
- **Raised mount 0.12**; lower-frame black-occlusion ≈ 0 %.
- **Collision-report** ground truth: `total_collision_count = 0` required; no
  `manual_recovery`, no `controller_timeout`.
- **Pose/frame validity**: spawn at isaac-world coords directly (bringup = isaac-world; the
  navmap read-offset `(2.956, −6.240)` is for *reading the navmap only*).
- **Bounded per-episode timeout** (1200 s), **exact-PID cleanup** (no `pkill -f`), disk guard
  (≥100 G before render/drive).
- **Envelope discipline**: every candidate pose must satisfy `|x| ≤ 6, |y| ≤ 6` under the
  **unchanged** `CL_BOUND_XY = 6.0`. If a target room lies outside ±6 m, it is **not** entered by
  raising the bound (see §5) — it requires a spawn *inside* the room's own local ±6 m frame or a
  documented, reviewed change.

## 4. Map extension vs route re-authoring vs geometry review

Determine, per target room, which is actually required:
- **Route re-authoring only** — if the room is reachable in the collision slab via a drivable
  doorway from a valid spawn (test with a short drive; likely rare given the sealed finding).
- **Spawn-relocation** — spawn the robot *inside* the target room (its own local frame) rather
  than driving there through a sealed doorway; validate pose/scene/camera/clearance locally. This
  is the most promising path and needs **no** safety-bound change.
- **Simulator geometry review** — inspect `hospital.usd` in the z-slab [0.08, 0.55]: are the
  doorways genuinely too narrow after inflation, or is the navmap slab mis-set? A geometry/slab
  review may reveal drivable connections the navmap missed (the navmap could not predict the
  west collisions, so it is not authoritative either way).
- **Map extension** — extend the render-confirmed navigable map (new occupancy build at a
  corrected slab / with a spawn inside each room) to certify new coordinates before authoring.

Decision rule: prefer **spawn-relocation + local validation** (no bound change) over any global
map/bound change; escalate to geometry review only if spawn-relocation cannot place the robot in
a target room collision-free.

## 5. How to avoid changing safety bounds casually

- `CL_BOUND_XY = 6.0` is a hardcoded watchdog on absolute isaac-world position; it is a **safety
  mechanism**, not a map limit. It must **not** be raised to reach far rooms.
- Preferred alternative: **spawn inside the target room** so the whole validated drive stays
  within ±6 m of that room's local origin (the watchdog measures absolute position, so the room's
  world coordinates must themselves be within ±6 m — verify per room; if not, that is a
  documented blocker for review, not a silent bound edit).
- Any proposal to change `CL_BOUND_XY` (or make it relative-to-spawn) is a **separate,
  explicitly-reviewed** engineering change with its own justification and test — never bundled
  into a collection step.

## 6. Embedding-based distinctness gate (replaces crude aHash)

- **Why:** aHash (16×16 luminance) cannot separate semantically-different corridor scenes (it
  rated the seating view ≈0.80 vs lobby despite different furniture). It over-flags structural
  similarity and under-flags content similarity.
- **Method:** compute per-goal-image embeddings with a **CLIP or DINO** image encoder; use cosine
  similarity. Compute an SSIM cross-check.
- **Thresholds (to calibrate on H8-M data):** cross-split cosine below a validated threshold
  (e.g., ≤ 0.6 CLIP-cosine, calibrated so genuinely-different rooms pass and same-room views
  fail); within-split below a duplicate threshold.
- **Failure action:** reject a goal image that exceeds the cross-split threshold vs any other
  split; collapse within-split duplicates; if no split-distinct set survives, do not record.
- **Reporting:** publish both the embedding matrix and the aHash matrix so the distinctness basis
  is auditable.

## 7. Stop condition before any H8-M collection

Do **not** record H8-M until:
1. ≥ 2 genuinely-distinct rooms (beyond the alcove) are **render- and drive-validated**
   (scene-gate PASS, mount 0.12, 0 collisions, no black occlusion) via spawn-relocation, with the
   `CL_BOUND_XY` watchdog **unchanged**;
2. an **embedding-based** distinctness gate is implemented and calibrated, and the proposed
   train/val/test goal images pass its cross-split threshold;
3. the H8-S limited causal pilot has been reviewed and (if run) reported honestly;
4. the plan is reviewed and collection explicitly approved.

Until then, status remains `DIAGNOSTIC_ONLY_NOT_PROMOTED`, incumbent retained; H8-M is a
**planning track only**.

---

*No collection, training, promotion, push, tag, closed-loop testing, `CL_BOUND_XY` change, or
map recording is authorised by this document. Planning only — stop after writing.*
