# H6 — Claim Boundary (canonical)

Internal **Isaac-Hospital-ImageNav-v0 simulation** evidence. This is the single
authoritative statement of what H6 does and does **not** claim; it governs every
H6 card, report, and the professor report.

## What H6 IS
- A **diagnostic coverage experiment**: does adding *clean hard-route families*
  (uturn/chain/ftL/sharpmulti/tightcorr) to **training** improve success on hard
  held-out route families — the gap H5 exposed?
- A **leakage-clean, decider-gated** dataset of 16 scripted-expert demonstrations
  (route_completed=True, 0 collisions) with a fresh held-out set of the same route
  *types* (uturn_02 / chain_02), and a controlled 3-model comparison
  (H1 incumbent vs H5 diagnostic vs H6 diagnostic) under identical hyperparameters.

## What H6 is NOT — explicit limitations
- **Fixed placeholder goal image** (`h2_weave_J`) on the H6 set ⇒ SR/NE there
  measure scripted-imitation *reproduction*, **NOT goal-image conditioning**. No
  goal-conditioning claim is admissible.
- **Scripted-expert demonstrations** (RouteFollower on the measured occupancy map,
  ExecFix holonomic base, PhysX-contact-verified), **not** learned-policy rollouts.
- **Simulation only** (Isaac Sim) — **not real-robot** evidence.
- **Offline Track-A** evaluation (collision rate CR = 0.0 by construction; not a
  closed-loop physics success rate).
- **Small n**: held-out sets are n = 4 (h6hard) / 6 (h4, prior) / 12 (combined);
  single-episode flips move SR by 0.17–0.25.
- **One seed** (42); **deterministic a/b variants** (b repeats a, so training
  instance-diversity is limited).
- **Not a public benchmark.**
- **Not promoted**: governance verdict `DIAGNOSTIC_ONLY_NOT_PROMOTED`, VerdictPlane
  deny, incumbent H1 retained.
- **No SOTA claim.**

## Result stated within the boundary
H6 has the best combined SR (0.25) and nDTW, preserves the H4 held-out gain, and
removes H5's prior-family regression — **but no model achieves SR > 0 or OSR > 0 on
the fresh hard held-out families.** The coverage hypothesis is **refined, not
confirmed**: hard-family training improves trajectory fidelity but does not, under a
fixed goal, produce success on unseen hard-family instances.

## Provenance note
Route `h6_chain_01` was re-authored inside the ±6 m runtime XY control-authority
bound after its original placement was rejected (`REJECT_XY_BOUND`); the original is
preserved as rejected evidence (`h6_excluded_routes.json`,
`hospital_h6_routes/rejected/h6_chain_01__rejected.json`). The ±6 m safety envelope
was **not** widened — the route was corrected to fit it.
