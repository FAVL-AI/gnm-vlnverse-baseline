# H6 — Hard-Route-Family Coverage Diagnostic

**Isaac-Hospital-ImageNav-v0 (internal simulation).** Diagnostic coverage
experiment — **not a promoted model.** It tests whether adding *clean hard-route
families* to training fixes the failure mode observed in H5.

- **Governance verdict:** `DIAGNOSTIC_ONLY_NOT_PROMOTED` — VerdictPlane **deny**,
  incumbent **H1 retained**. (DriftGuard dual-guard vs. incumbent computed
  `net_gate=promote`, but promotion is administratively blocked pending explicit
  human approval — and, as §6 explains, that gate passes on an SR **tie at 0**,
  not on any hard-family success gain.)
- **Claim boundary:** scripted-expert demonstrations; **fixed placeholder goal
  image** (`h2_weave_J`) ⇒ this is *not* goal-image-conditioning evidence; not
  real-robot; not a public benchmark; no SOTA claim. Held-out sets are small
  (n = 4 / 6 / 12).

---

## 1. H5 diagnosis (what we were left with)
H5 (mixed-family replay: 16 H4 NavGen + 8 H2.4 older demos, weights-only init
from H1) sharply improved trajectory fidelity over the incumbent (combined
NE 13.40 → 6.10 m, nDTW 0.222 → 0.336) and recovered success on one H4 held-out
family (navgen_016). **But it did not solve success on uncovered hard families,
and it regressed on a prior held-out family:** prior-held-out SR 0.167 → 0.000
(it *lost* the `ftL` family H1 could do), which blocked promotion. Reading:
replaying older *training* families did not restore *success* on hard held-out
route types no training set covers — a **coverage gap**, not merely a balance gap.

## 2. H6 change (the intervention)
Add **clean hard-route-family coverage** directly to training. Five hard route
types were authored, feasibility-gated (static decider **+ a new ±6 m runtime
XY control-authority bound**, after one route was caught driving out of the
controllable envelope), recorded, and split so that **fresh instances of the
same hard types are held out**. Everything else is held identical to H1/H4/H5
(MobileNetV2-GNM, seed 42, 50 epochs, lr 1e-4, action_std 0.1155, weights-only
init from the retained H1 incumbent, fresh optimizer, selection on validation).

## 3. H6 data quality
16/16 recordings `RECORDED_OK`: **route_completed = True, 0 collisions**, max
contact-streak 0, clean DDS/proc teardown, ~1.96 GB bag each (31.4 GB total),
disk never below 354 GB (150 GB guard). Conversion: 16/16 complete, 2,841 frames
(stride 12). **Leakage-clean** at both recording and conversion (episode- and
family-disjoint). One original route was rejected for leaving the ±6 m bound and
is preserved as rejected evidence. Single fixed goal confirmed (`h2_weave_J`).

## 4. Train / val / test split (H6 dataset)
| Split | n | Families |
|---|---|---|
| train | 10 | uturn_01, chain_01, ftL_01, sharpmulti_01, tightcorr_01 (×a,b) |
| val (selection) | 2 | compound_01 (×a,b) |
| **test_h6hard** (fresh held-out) | 4 | **uturn_02, chain_02** (×a,b) — same *types*, unseen *instances* |

Evaluation also reuses the preserved H5 held-out sets: **test_h4** (n=6),
**test_prior** (n=6), **test_combined** (n=12). `--data-root` is forced on every
eval (checkpoint-embedded corpus ignored).

## 5. Results — H1 vs H5 vs H6 (Track A, offline)
Aggregate per held-out set (SR/OSR/SPL, NE in m, nDTW):

| Set (n) | Model | SR | OSR | SPL | NE↓ | nDTW↑ |
|---|---|---|---|---|---|---|
| **test_h6hard (4)** — *fresh hard* | H1 | 0.00 | 0.00 | 0.00 | 21.36 | 0.021 |
| | H5 | 0.00 | 0.00 | 0.00 | **8.25** | **0.159** |
| | **H6** | 0.00 | 0.00 | 0.00 | 10.58 | 0.111 |
| **test_h4 (6)** — H4 held-out | H1 | 0.00 | 1.00 | 0.00 | 14.04 | 0.167 |
| | H5 | 0.333 | 1.00 | 0.333 | **5.02** | **0.382** |
| | **H6** | 0.333 | 1.00 | 0.301 | 6.15 | 0.378 |
| **test_prior (6)** — continuity | H1 | 0.167 | 0.667 | 0.167 | 12.76 | 0.276 |
| | H5 | 0.000 | 0.333 | 0.000 | **7.19** | 0.290 |
| | **H6** | **0.167** | 0.500 | **0.167** | 7.73 | **0.325** |
| **test_combined (12)** | H1 | 0.083 | 0.833 | 0.083 | 13.40 | 0.222 |
| | H5 | 0.167 | 0.667 | 0.167 | **6.10** | 0.336 |
| | **H6** | **0.250** | 0.750 | **0.234** | 6.94 | **0.351** |

Per-family success (successes / n; NE m):

| Set / family | H1 | H5 | H6 |
|---|---|---|---|
| test_h6hard / uturn_02 | 0/2 · 26.3 | 0/2 · 11.3 | 0/2 · 13.7 |
| test_h6hard / chain_02 | 0/2 · 16.4 | 0/2 · 5.2 | 0/2 · 7.4 |
| test_h4 / navgen_016 | 0/2 · 8.8 | 2/2 · 1.6 | **2/2 · 1.0** |
| test_h4 / navgen_008,012 | 0/2 · 16.7 | 0/2 · 6.7 | 0/2 · 8.7 |
| test_prior / ftL | 1/2 · 3.1 | **0/2 · 5.6 (lost)** | **1/2 · 3.6 (kept)** |
| test_prior / uturn, chain | 0/4 · 17.6 | 0/4 · 8.0 | 0/4 · 9.8 |

**Three findings:**
1. **Best overall balance:** H6 has the highest combined SR (0.25) and nDTW (0.351).
2. **Fixes the H5 regression:** H6 keeps the `ftL` prior family H5 lost → no prior-heldout regression (SR 0.167 = incumbent), while preserving the H4 gain (navgen_016 2/2).
3. **Core hypothesis NOT supported:** on the fresh hard held-out families, **all three models score SR = 0 and OSR = 0**. Adding hard-family training cut endpoint error vs. the incumbent (NE 21.4 → 10.6 m) but never brought the robot within the 3 m success radius — and did **not** beat H5 there.

## 6. Metric → failure interpretation
- **OSR = 0 on test_h6hard (all models):** the robot **never once** comes within
  3 m of the fixed reference endpoint on the fresh hard families. This is a true
  *coverage/reachability* failure, not a stopping-policy failure. Contrast
  test_h4, where OSR = 1.0 but SR < 1.0 (the robot *passes* the goal but doesn't
  *stop* there — a stopping-head issue, a different problem).
- **NE without SR:** hard-family training roughly halved NE vs. incumbent
  (21.4 → 10.6 m) yet stayed well above the 3 m threshold → "closer, still failing."
- **H6 < H5 on the hard set** (NE 10.58 vs 8.25): training on 10 hard *a-instances*
  did **not** generalize to the held-out *b-instances* better than mixed replay;
  the rising validation loss during fine-tuning is consistent with over-fitting
  the specific training instances on a small set.
- **Collisions:** CR = 0.0 offline by construction; the underlying recordings were
  0-contact with route_completed = True, so no safety regression is introduced.

## 7. Limitations
- **Fixed placeholder goal** on test_h6hard ⇒ SR/NE there measure imitation-
  fidelity reproduction, **not goal-image conditioning**. No goal-conditioning
  claim is admissible.
- **Small n** (4 / 6 / 12): single-episode flips move SR by 0.17–0.25; the
  prior-heldout and H4 successes each rest on one family.
- **Scripted-expert imitation**, offline Track-A metrics, one seed, simulation
  only — not real-robot, not a benchmark.
- Only 10 training episodes / 5 hard types; b-variants are deterministic repeats
  of a-variants, so train diversity is limited.

## 8. Next decision
**Accept H6 as diagnostic evidence; do not promote** (incumbent H1 retained).
The coverage hypothesis is **refined, not confirmed**: adding hard-family
*training* improves trajectory fidelity and removes H5's prior-family regression,
but does **not** yield *success* on fresh hard held-out families under a fixed
goal. Recommended next step before any promotion path: (a) increase hard-family
*instance* diversity (more distinct routes, not a/b repeats) to test type-level
generalization, and (b) move to a **non-fixed (goal-conditioned) evaluation** so
success on hard families is measured against real goal images rather than a
single placeholder. Both are new experiments, gated on your approval.
