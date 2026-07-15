# H8-S — Limited Causal Pilot: Re-Scope Note (PLANNING ONLY)

**Status:** planning only. No collection, no training, no promotion, no push, no tag, no 20/5/10,
no closed-loop Isaac, no design-gate re-run. Re-scopes H8-S after the map-extension +
drive-validation + visual-gap evidence. Changes no committed result.

**H8-S status:** `LIMITED_CAUSAL_PILOT`.

**Provenance.** Extends the committed chain
`… → 0d92459 (H8-S route design feasibility) → a741d76 (map-extension plan) → 2c9b4e1
(map-extension analysis) → 8413c09 (validation evidence) → 7878e81 (recovery evidence) →
584e19e (visual-gap evidence)`. Verdict carried forward: `DIAGNOSTIC_ONLY_NOT_PROMOTED`,
incumbent retained.

**Professor-safe framing:**
> The map-extension recovery fixed the coordinate split problem but exposed a visual split
> problem. Several test candidates are physically separate but visually too similar, so they
> would not support a strong held-out ImageNav claim. I am therefore re-scoping H8-S as a
> limited causal pilot and deferring the stronger multi-room held-out visual split to H8-M,
> where sealed reception/waiting-room areas must be validated first.

---

## 1. Why H8-S was re-scoped

- The frame-fit + map extension unlocked a ~14 m corridor, but **drive validation** showed only
  the lobby + east + mid-west band (|x| ≤ ~−3.4 to +3.5) is reliably drivable (west of −3.4 has
  reproducible collisions: val_A 25×2, west_C 7678; far-west |x|>6 is safety-envelope deferred).
- **Recovery** produced a coordinate-clean, per-split-proven set (train=lobby, val=midwest_B,
  test=east) — a real advance over the flagged H8-S coordinate leakage.
- But the **visual-gap audit** (584e19e) showed the drivable envelope is **one alcove** with two
  visually-distinct ends (vending east-facing / seating west-facing). The three east test views
  collapse to one vending view (aHash 0.89–0.96), and the only alternative (seating) is the same
  alcove (aHash ≈0.78–0.81 vs lobby; the crude gate cannot certify it as cross-split-distinct).
- **Coordinate-clean ≠ image-clean.** For ImageNav the goal image must be perceptually distinct
  or the goal signal is meaningless. The current envelope cannot support a *strong* held-out
  visual split, so a full held-out claim would be an overclaim.

## 2. What H8-S can still test (limited pilot)

- Whether the **goal-conditioned objective** (from `H8_GOAL_CONDITIONED_TRAINING_OBJECTIVE.md`
  / the committed 2×2 loss-ablation) makes the predicted action / stop respond to the goal on a
  **small, real, coordinate-clean** hospital set — beyond the memorised 2×2 prototype.
- **Within-envelope goal-conditioning**: at shared decision frames, does swapping the goal image
  change the predicted `[Δx, Δy]` / stop point (offline action-probe), on real recorded frames?
- A **coordinate-disjoint** train/val/test split (no goal-coordinate reuse) — the original H8-S
  defect is fixed.
- A first, honest **generalization signal to a held-out coordinate** (test = one east frame the
  model was not trained on), clearly labelled as *within-alcove, limited*.

## 3. What H8-S cannot claim

- **Not** a strong held-out visual benchmark.
- **Not** multi-room / cross-location visual generalization.
- **Not** full goal-conditioned ImageNav.
- **Not** proof the model uses the goal image in a way that transfers to visually-novel goals —
  because train/val/test goals are the same alcove at different scales/ends.
- No SOTA, no promotion, no autonomy claim.

## 4. Selected train / val / test policy

- **train:** `lobby` (proven, 0 collisions) + any other train-safe causal frames inside the
  drivable band (e.g., `midwest_A`, overlaps lobby — reserve only).
- **val:** `midwest_B` — the clean, most-distinct validation anchor (proven, 0 collisions,
  coordinate-disjoint west of lobby).
- **test:** **one** east / vending-machine frame only (`east_A`).
- Coordinate bands remain disjoint: val [−3.4, −2.9] · train [−2.31, 0.91] · test [1.4, 3.5]
  (gaps ≥ 0.49 m).

## 5. Dropped / deferred frames

- **`east_B`** — dropped: duplicate of `east_A` (aHash 0.93, same vending view).
- **`lookalike_test`** — dropped/deferred: duplicate of `east_B` (0.96) **and** its intended
  visual confuser `west_B` is `DEFERRED_SAFETY_ENVELOPE_LIMITED`, so the adversarial pairing is
  unresolved.
- **`west_C`** — `REJECTED_COLLISION` (7678 contacts; navmap-free but not drivable).
- **`val_A`** — `REJECTED_COLLISION` (25 contacts reproduced on retry).
- **`west_A` / `west_B` / hard-neg far-west** — `DEFERRED_SAFETY_ENVELOPE_LIMITED` (|x|>6).
- **Optional supplemental:** the seating / west-facing view (`searchW1`/`searchW2`) may be
  included **only** as a within-alcove *analysis* frame (does the goal image change behaviour
  when the goal is the seating end vs the vending end?), **not** as held-out proof.

## 6. Metrics and diagnostics

- **Offline action-probe** (`h8_action_probe.py`, generalised) — predicted `[Δx, Δy]` vs expected
  per goal at shared decision frames; goal-sensitivity score S; branch-choice accuracy — reported
  on the held-out **coordinate** (test), with the honest caveat that the goal is visually similar.
- **Mismatched-goal ablation** (`h7r_mismatched_goal_ablation.py`, generalised) — wrong goal must
  degrade the action/stop; endpoint shift signed toward the wrong goal, not jitter.
- **Standard metrics** (`metrics.py`, forced `--data-root`): TL, NE, SR, OSR, SPL, nDTW, CR;
  invariants OSR ≥ SR, CR = 0 offline; goal-conditioning must not collapse basic navigation.
- **Determinism**: cuDNN/cuBLAS deterministic (the `85ada39` fix); logged seed; multi-seed where
  claimed.
- **Distinctness reporting**: report the goal-image aHash matrix alongside results so the limited
  visual distinctness is visible, not hidden.

## 7. Acceptance gates (limited pilot)

1. **Design gate (coordinates)** passes — each split has ≥1 proven coordinate-disjoint zone; no
   goal-coordinate reuse (already true for train=lobby / val=midwest_B / test=east_A).
2. **Recorded-mode gate** passes on the real frames (scene-gate, mount 0.12, 0 collisions).
3. **Action-probe on the held-out coordinate** shows goal-sensitivity above baseline — reported
   as *within-alcove limited* evidence, **not** held-out visual generalization.
4. **Mismatched-goal ablation** shows goal dependence.
5. **Standard metrics** do not collapse.
6. **Honest labelling gate**: every artifact says `LIMITED_CAUSAL_PILOT`; no held-out-visual /
   multi-room / full-ImageNav wording.

A pilot pass justifies H8-M; it does **not** justify a held-out visual or generalization claim.

## 8. What must be deferred to H8-M

- The **strong multi-room held-out visual split** — genuinely different locations
  (reception / waiting rooms), currently sealed → `DEFERRED`.
- The **embedding-based distinctness gate** (CLIP/DINO cosine or SSIM) replacing crude aHash.
- Larger scale (20/5/10) and closed-loop Isaac — gated behind a multi-seed held-out pass on a
  visually-distinct set.
- See `H8_M_SEALED_ROOM_MAP_EXTENSION_PLAN.md`.

---

*No collection, training, promotion, push, tag, 20/5/10, closed-loop testing, or design-gate
re-run is authorised by this note. Planning only — stop after writing.*
