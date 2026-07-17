# H5 — mixed-family replay / joint-family fine-tune (PLAN ONLY)

Status: **planning only. No training, no dataset build, no promotion.** H4 stays a
non-promoted positive diagnostic; the incumbent remains the H1 hospital fine-tune.
This document is pre-registered for Frank's review before any H5 execution.

## 1. Goal & hypothesis
**Goal:** test whether mixing H4 route-family diversity with older-family replay
prevents the older-family regression **while preserving the H4 held-out gains.**

**Hypothesis (H5):** a joint fine-tune on H4 demonstrations *plus* selected clean
older families will (a) match H4's gain on the H4 held-out families and (b)
remove the regression on the prior held-out families (≥ incumbent), yielding the
first *promotable* hospital candidate.

**Pre-registered outcomes:**
- **A (promote):** H4 held-out ≥ incumbent (SR/SPL improve or match, NE not worse)
  AND prior held-out ≥ incumbent AND combined aggregate not worse → candidate
  promotable, pending human adjudication.
- **B (still specialized):** H4 held-out up but prior held-out still < incumbent →
  HOLD; replay insufficient; next = reweight/balance older families.
- **C (diluted):** prior held-out recovered but H4 held-out gain lost → HOLD;
  older families dominated; next = rebalance toward H4.

## 2. Hard constraints (from Frank, 2026-07-11)
- Do **not** promote H4. Do **not** rerun H4-only training.
- Prior held-out families (uturn/chain/ft_L) and H4 held-out families
  (008/012/016) **remain held out** — never in train — unless explicitly
  reassigned via a new split manifest.
- Evaluator `--data-root` forced explicitly for every eval (methodology lock).
- Fixed placeholder goal image ⇒ still not goal-image-conditioning evidence.

## 3. Training-set composition & new split manifest (design)
New root `datasets/isaac_hospital_h5` built from a fresh `split_manifest.json`.

**train (mixed):**
- H4 scripted-expert demos — 16 episodes / 8 navgen families (h4/train).
- H2.4 clean scripted-expert demos — 10 episodes / 5 families (h3clean/train:
  straight, 90turn, scurve, weave_J, corridor_I). Cleanest older set.
- *(optional, gated)* curated H1 demo families — only pure demonstrations from
  isaac_hospital_split/train (e.g. hospital_straight_short_A, livefinal_straight_
  short, goal-A/F baseline). **Must exclude physeval / collision-control episodes**
  (isaac_hospital_split/train contains physeval_collision_control*, physeval_ema_*
  etc. — not imitation demos). Cleanliness re-checked with the H4 validator before
  inclusion.

**val (selection, spans both distributions):** H4 val (015, 017) + H2.4 val
(h3clean/val: hospital_low_curvature_C, straight_medium_B, livefinal ×2) so
checkpoint selection does not over-favour one distribution.

**test (held out, evaluated separately — NEVER trained):**
- H4 held-out: 008, 012, 016 × {a,b} (n=6).
- Prior held-out: uturn, chain, ft_L (h3clean/test, n=6).

Leakage check: train ∩ (H4 held-out ∪ prior held-out) = ∅, asserted at build like
`build_h4_dataset_root.py`.

## 4. Replay strategy
- **First H5 run:** natural pooled concatenation (all clean train episodes, no
  reweighting) — the honest baseline. Approx train = 16 (H4) + 10 (H2.4) [+ curated
  H1] episodes.
- **If outcome B (still specialized):** balanced sampling — up-weight older
  families to parity with H4 episode count; re-run once.
- **If outcome C (diluted):** down-weight older families toward H4; re-run once.
- Each variant is a single pre-registered run with a stated expected direction —
  no unbounded tuning.

## 5. Training config (mirror the locked convention)
- `configs/gnm/gnm_h5_mixed_replay.yaml`, mirrors H3-clean/H4 exactly except
  `data.data_root=datasets/isaac_hospital_h5`, output/name.
- `training.init_ckpt = checkpoints/hospital_front_rgb_finetune/best.pt` (H1
  incumbent, weights-only, fresh optimizer).
- action_std [0.115528, 0.115528]; seed 42; epochs 50 (patience 10); batch 128;
  lr 1e-4; ctx 5; 96×96; max_goal_dist 20 — identical to incumbent for
  apples-to-apples comparison.
- Selection on the H5 val set only.

## 6. Evaluation protocol — 7 separate reports (per Frank)
Both candidate and incumbent, offline single-integrator, forced `--data-root`,
each n=6:
1. **H4 held-out families** (008/012/016).
2. **Prior held-out families** (uturn/chain/ft_L).
3. **Combined held-out aggregate** (n=12).
4. **Contacts/collisions** — training demos measured PhysX contacts (expect 0);
   offline CR=0 by construction; physics CR = N/A offline (no closed-loop).
5. **DriftGuard with BOTH improvement and regression guards** (§7).
6. **VerdictPlane** promotion decision.
7. **Human adjudication.**

## 7. DriftGuard dual-guard rule (H5)
Net **PROMOTE only if BOTH pass**, else HOLD/BLOCK:
- **Improvement guard (H4 held-out):** candidate SR & SPL ≥ incumbent AND NE not
  materially worse (>0.1 m).
- **Regression guard (prior held-out):** candidate SR & SPL ≥ incumbent AND NE not
  materially worse.
- Combined aggregate reported for context; a clean promote also requires the
  combined aggregate not worse than incumbent.
Reuses/extends `scripts/gnm/h4_governance_adjudicate.py` (already computes both
guards); H5 makes BOTH mandatory for promote.

## 8. Promotion criterion
Promotion requires: outcome A (both guards pass) + no contact/collision regression
+ VerdictPlane allow + human adjudication. Anything else = HOLD, incumbent
retained. Small-n (n=6/set) means even a pass needs explicit human sign-off, per
the H3-clean small-n gate refinement.

## 9. Claim boundary
Internal Isaac-Hospital-ImageNav-v0 simulation evidence; not real-robot, not a
public benchmark, not a general hospital-navigation solution. Fixed placeholder
goal image ⇒ evidence about route-family-diverse scripted imitation under the
current pipeline, NOT stronger goal-image conditioning.

## 10. Approval gates before any execution
1. Frank approves this H5 plan and the exact older-family replay selection.
2. Build `datasets/isaac_hospital_h5` + `split_manifest.json`; run leakage +
   H4-style validator; present the H5 quality/split table for review.
3. Only after table review: run the single first H5 training + the 7-report eval.
4. Present results; Frank adjudicates promote/HOLD. No auto-promotion.
