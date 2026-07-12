# H6 — coverage-hypothesis test (PLAN ONLY)

Status: **planning only. No collection, no training, no promotion.** H5 accepted
as Outcome-B diagnostic; incumbent = H1 hospital fine-tune, retained.

## 1. Goal & hypothesis
**Goal:** test the coverage hypothesis directly — that H4/H5 regressed on prior
held-out success because the hard route types (uturn, chain, ft_L-like) are
**absent from training**, not because replay was unbalanced.

**Hypothesis (H6):** adding hard-route-type coverage to training, while preserving
a fresh held-out of the same/related hard types, will restore prior-family SR/SPL
non-regression **without losing H4 gains**.

## 2. Coverage table (measured now — `h6_coverage_table.csv`)
| route_type | train | val | heldout | status |
|---|---|---|---|---|
| straight | 2 | 0 | 0 | covered |
| single_90turn | 2 | 0 | 0 | covered |
| scurve | 1 | 1 | 0 | covered |
| corridor | 1 | 1 | 0 | covered |
| multi_turn_weave | 2 | 0 | 0 | covered |
| navgen_single_turn | 8 | 1 | 4 | covered |
| navgen_multi_turn | 4 | 1 | 0 | covered |
| navgen_amber_zone | 4 | 0 | 2 | covered |
| **uturn_HARD** | **0** | **0** | 2 | **UNCOVERED in train** |
| **chain_HARD** | **0** | **0** | 2 | **UNCOVERED in train** |
| **ftL_sharp_HARD** | **0** | **0** | 2 | **UNCOVERED in train** |

The three failing types have **zero** training/validation representation. This is
the coverage gap, proven.

## 3. HARD CONSTRAINT discovered: H6 needs a collection phase
Only **6 hard-type episodes exist** (2 uturn + 2 chain + 2 ft_L), all currently
held-out. A leakage-clean coverage test **cannot** be built by reshuffling:
- Moving the 6 into train ⇒ no held-out of that type ⇒ nothing to measure.
- Splitting them (e.g. train uturn+chain / hold out ft_L) ⇒ n=2 held-out and it
  tests cross-hard-type transfer, not the clean hypothesis.

**Therefore H6 requires H6-collection: generate NEW hard-route-family scripted-
expert demonstrations** via the proven H4 pipeline (NavGen route sampling on the
measured occupancy map → Execution Feasibility Decider gate → ExecFix holonomic
base → RouteFollower scripted expert → PhysX-contact-verified rosbags →
converter). The pipeline is known-feasible for these types: the existing
uturn/chain/ft_L episodes were themselves scripted-expert demos from it, and
ExecFix restored tight-turn yaw (min radius 0.375 m), so uturn/chain/sharp-L
routes now pass the decider's continuous-yaw feasibility check.

## 4. Target H6 split design (built only after collection + Frank's approval)
**train:** H4 (16) + H2.4-clean (8) + **NEW hard-family train subset** (target:
representative uturn/chain/ft_L/sharp-multi-turn families ×2 variants).
**val:** H4 val (015,017) + H2.4 val (scurve_b, I_b) + **1 new hard-family val**
(both distributions + a hard sample for selection).
**held-out test — three separately reported sets:**
1. **H4 held-out (preserved):** 008/012/016 — measures H4-gain retention.
2. **FRESH hard held-out (new):** new hard families NOT in train — measures
   generalisation to unseen hard families of the trained types.
3. **Prior held-out (continuity anchor):** the existing 6 (uturn/chain/ft_L) kept
   **held-out, never trained** — measures whether hard-type coverage restores
   success on the ORIGINAL regression set (the decisive comparison to H1/H4/H5).

## 5. Held-out replacement justification
The prior held-out (6 existing hard episodes) is **retained** as the continuity
anchor so H6 is directly comparable to H4/H5 on the same set. It is NOT moved into
train. Coverage enters training only through **newly collected** hard families;
generalisation is then tested on a **fresh** hard held-out (different specific
families of the same types). This preserves both the historical comparison and a
clean family-level generalisation test.

## 6. Leakage design
- **Episode-level:** train ∩ (any held-out) = ∅ (allowlist build, asserted, as in
  H4/H5).
- **Family-level:** the FRESH hard held-out families must be **distinct families**
  from any hard family in train (the generalisation claim requires family
  disjointness). The prior held-out already shares no family with train.
- Documented in an H6 leakage report at build time.

## 7. Excluded-episode report (to be emitted at build)
Exclude: all H1 corpus (physeval*/collision-control/authcmp/normcmp/dash/
livefinal), any rc≠0 / partial / timed-out recording, any policy-generated
rollout (scripted-expert only), any goal-content-defective or placeholder-
defective episode, any non-front-RGB evidence. Same allowlist + validator
discipline as `validate_h4_dataset.py`.

## 8. Counts (target, pending collection scope)
- New hard collection target: **6 hard families ×2 = 12 demos** (≈4 families/8 to
  train, 2 families/4 to fresh held-out, spread across uturn/chain/ft_L/sharp).
- Resulting train ≈ 16 + 8 + 8 = **32**; val ≈ 4 + 2 = **6**; held-out = 6 (H4) +
  4 (fresh hard) + 6 (prior) = **16**, reported as 3 separate sets + combined.
- Exact counts fixed after the collection quality table passes review.

## 9. Training (mirror locked convention, on approval)
`configs/gnm/gnm_h6_coverage.yaml`: weights-only init from H1 incumbent, fresh
optimizer, action_std [0.115528, 0.115528], seed 42, 50 epochs, select on H6 val;
all evals force `--data-root`.

## 10. Promotion rule (unchanged, strict)
Promote only if ALL: (1) H4 held-out preserved/improved, (2) prior-family held-out
SR/SPL no longer regresses, (3) combined aggregate improves, (4) no
contact/collision regression, (5) DriftGuard improvement + regression guards both
pass, (6) VerdictPlane allow, (7) human adjudication. Small-n needs human sign-off.

## 11. Claim boundary
Internal Isaac-Hospital-ImageNav-v0 simulation evidence; fixed placeholder goal
image ⇒ evidence about route-family-diverse scripted imitation under the current
pipeline, NOT stronger goal-image conditioning; not real-robot, not a public
benchmark.

## 12. Approval gates before any execution
1. Frank approves the H6 plan and the **hard-family collection scope** (how many
   uturn/chain/ft_L/sharp families, and the train-vs-fresh-held-out split of them).
2. Run H6-collection (decider-gated, ExecFix, scripted expert); present the
   collection quality table (H4-style) for review — no training yet.
3. On approval: build the H6 split manifest + coverage table + leakage/excluded
   reports; present for review.
4. Only then: train once + the 3-set (+combined) eval with dual guards; adjudicate.

## Paper conclusion recorded for H5
H5 mixed-family replay improved aggregate trajectory quality and preserved gains
on the new H4 families, but did not restore binary success on older hard route
families — supporting the coverage-gap diagnosis: replaying available older
families is insufficient when the failing route types are absent from training.
