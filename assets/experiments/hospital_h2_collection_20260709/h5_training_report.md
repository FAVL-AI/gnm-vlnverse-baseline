# H5-run-1 mixed-family replay — training report

Ran once, exactly as pre-registered. Weights-only init from the H1 incumbent;
trained on 24 clean demos (16 H4 NavGen + 8 H2.4 older); selected on H5 val
(both distributions); evaluated on H4 held-out, prior held-out, and combined,
all with forced `--data-root`. **Outcome B — NOT promoted; incumbent retained.**

## Split & preconditions
Disk 103 GB ≥ 100 GB. Leakage-free, allowlist-enforced, no H1 episodes present
(`h5_split_manifest.json`). Train 24 / Val 4 / test_h4 6 / test_prior 6 /
test_combined 12. Best val action loss 0.0709; candidate sha (see card).

## 1. H4 held-out vs incumbent (n=6)
| metric | incumbent | H5 candidate | Δ |
|---|---|---|---|
| SR | 0.000 | **0.333** | +0.333 |
| SPL | 0.000 | **0.333** | +0.333 |
| NE (m) | 14.04 | **5.02** | −9.02 |
| nDTW | 0.167 | **0.382** | +0.215 |
→ **H4 gain PRESERVED** (matches the H4-only candidate). Improvement guard **PASS**.

## 2. Prior held-out vs incumbent (n=6)
| metric | incumbent | H5 candidate | Δ |
|---|---|---|---|
| SR | 0.167 | 0.000 | **−0.167** |
| OSR | 0.667 | 0.333 | −0.334 |
| SPL | 0.167 | 0.000 | **−0.167** |
| NE (m) | 12.76 | **7.19** | −5.57 |
| nDTW | 0.276 | 0.289 | +0.013 |
→ SR/SPL **still regress** (though NE improves, better than H4-only's 8.15 m).
Regression guard **FAIL**. The SR gap is a **single episode** (1/6 → 0/6) at n=6.

## 3. Combined held-out aggregate (n=12)
| metric | incumbent | H5 candidate | Δ |
|---|---|---|---|
| SR | 0.083 | **0.167** | +0.084 |
| OSR | 0.833 | 0.667 | −0.166 |
| SPL | 0.083 | **0.167** | +0.084 |
| NE (m) | 13.40 | **6.10** | −7.30 |
| nDTW | 0.222 | **0.336** | +0.114 |
→ Candidate better on SR/SPL/NE/nDTW; worse on OSR. Context only — not a
substitute for the per-set guards.

## 4. Contact / collision summary
Training demos: 0 measured PhysX contacts (24/24). Offline CR = 0.000 on all
three eval sets. Physics CR = **N/A offline**. **No collision regression.**

## 5. DriftGuard improvement guard (H4 held-out) — **PASS**
SR & SPL improve, NE improves. (`h5_driftguard_decision.json`)

## 6. DriftGuard regression guard (prior held-out) — **FAIL**
SR & SPL below incumbent. Net gate = **HOLD** (both guards required).

## 7. VerdictPlane — **deny**
`model.promote` denied: dual-guard not satisfied.

## 8. Human adjudication recommendation — **DO NOT PROMOTE (Outcome B)**
H5 is the **strongest candidate so far** — it preserved the H4 held-out gain,
improved NE on every set (prior held-out 12.76→7.19 m; combined 13.40→6.10 m),
and improved combined SR/SPL/nDTW. But the pre-registered rule requires **both**
guards, and the prior-held-out SR/SPL non-regression was not achieved. Retain H5
as diagnostic evidence; incumbent H1 retained.

**Scientific reading:** replaying older *train* families (H2.4) does **not** by
itself restore *success* on older *held-out* families whose route types no
training set covers (uturn/chain/ft_L). This is a **coverage** gap, not merely a
distribution-balance gap — NE improved broadly, but binary success on the
uncovered hard families did not. The fixed placeholder goal image bounds this to
route-family-diverse scripted imitation, not goal-image conditioning.

**Next options (not started):** H5-run-2 rebalanced older sampling; **H6** —
reassign uturn/chain/ft_L-type route families into *training* (new split
manifest, fresh held-out) to test the coverage hypothesis directly; or accept H5
as diagnostic-only.

## Binary outcome
**Outcome B** (improves one distribution / ties or fails the other) → **do not
promote; retain as diagnostic evidence.** Incumbent = H1 hospital fine-tune.
