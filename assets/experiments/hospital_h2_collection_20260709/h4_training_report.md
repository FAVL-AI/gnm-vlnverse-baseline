# H4 diagnostic route-family-diversity fine-tune — training report

Diagnostic, not a promotion run. Init weights-only from the H1 hospital
incumbent; trained only on the 16 H4 scripted-expert demonstrations; selected on
H4 validation; evaluated once on the H4 held-out families, with the prior
held-out families reported separately. Result: **first measurable held-out
transfer in the H-track — but with a cross-distribution regression. NOT promoted.**

## 1. Pre-training disk check
`/` free **104 GB** ≥ 100 GB floor (`h4_prestart_checks.json`). Reclaim was
~10.5 GB of re-downloadable HF Coder model cache only; **no bags/logs/evidence
deleted.** All 9 pre-start checks PASS.

## 2. Exact train/val/test split (`datasets/isaac_hospital_h4/split_manifest.json`)
- **train (16 / 8 families):** 000, 001, 002, 005, 007, 009, 011, 013 × {a,b}
- **val (2 / 2 families):** 015_a, 017_a  — checkpoint selection only
- **held-out test (6 / 3 families):** 008, 012, 016 × {a,b} — evaluated once
- **prior held-out (separate):** uturn, chain, ft_L (h3clean/test) — never in train
- Firewall asserted at build: rc0 + artifact complete + contacts 0 + scripted-
  expert only; superseded/policy rollouts excluded; splits disjoint.

## 3. Training command / config (`configs/gnm/gnm_h4_navgen_diversity.yaml`)
```
WANDB_MODE=offline python scripts/gnm/04_train_gnm.py \
  --cfg configs/gnm/gnm_h4_navgen_diversity.yaml
```
init_ckpt `checkpoints/hospital_front_rgb_finetune/best.pt` (weights only, fresh
optimizer); seed 42; epochs 50 (early-stopped, patience 10); batch 128; lr 1e-4;
ctx 5; 96×96; max_goal_dist 20; action_std [0.115528, 0.115528] (same as
incumbent + H3-clean). Train 2,782 / Val 338 samples. **Best val action loss
0.044052 @ epoch 14.** Candidate: `checkpoints/h4_navgen_diversity_finetune/best.pt`
(sha256 ee5930d9…).

## 4. Held-out metrics vs incumbent (offline, single-integrator, n=6 each)
**Primary — H4 held-out families (008/012/016):**
| metric | incumbent H1 | candidate H4 | Δ |
|---|---|---|---|
| SR | 0.000 | **0.333** | +0.333 |
| OSR | 1.000 | 1.000 | 0 |
| SPL | 0.000 | **0.333** | +0.333 |
| NE (m) | 14.04 | **5.02** | −9.02 |
| nDTW | 0.167 | **0.411** | +0.244 |
| TL (m) | 14.46 | 4.84 | — |

**Prior held-out — uturn/chain/ft_L (reported separately):**
| metric | incumbent H1 | candidate H4 | Δ |
|---|---|---|---|
| SR | 0.167 | 0.000 | **−0.167** |
| OSR | 0.667 | 0.333 | **−0.334** |
| SPL | 0.167 | 0.000 | **−0.167** |
| NE (m) | 12.76 | 8.15 | −4.61 |
| nDTW | 0.276 | 0.293 | +0.017 |

Reading: the candidate learned the navgen route distribution (cross-family
transfer to unseen navgen families) but regressed on the older non-navgen
families. The gain is **within-navgen-distribution**, not general.

## 5. Contact / collision summary
- Training demonstrations: **0 PhysX chassis contacts** across all 16 (measured,
  base_link contact report) — see `h4_quality_table.csv`.
- Offline eval CR = 0.000 on both held-out sets (single-integrator, no physics).
- Physics collision rate: **N/A offline** — no closed-loop Isaac rollout in this
  diagnostic. **No collision regression** (CR unchanged).

## 6. DriftGuard result (`h4_driftguard_decision.json`)
- Primary H4 held-out: **PROMOTE** (SR/SPL improve, NE improves).
- Prior held-out regression guard: **BLOCK** (SR/SPL regress).
- **Net gate: HOLD (regression on prior held-out)** — not a clean promotion.

## 7. VerdictPlane result (`h4_verdictplane_record.json`)
`model.promote` → **deny**: net DriftGuard gate is not a clean promote; the
prior-held-out navigation regression blocks auto-promotion.

## 8. Human adjudication recommendation
**DO NOT PROMOTE. Hold H4 as a positive diagnostic.** This is the H-track's
first measurable held-out transfer (H3-clean was a tie), which **supports the
route-family-diversity hypothesis within the navgen route distribution** — a
real, reportable finding. But it is not a clean win: the fine-tune regressed on
the older uturn/chain/ft_L families, i.e. it specialized to navgen at the cost of
cross-distribution robustness. n=6 per set (SR 0.333 = 2/6). Incumbent
`h1_hospital_front_rgb_finetune` **retained**. Suggested next decision: mixed-
/joint-family retrain (or older-family replay) to remove the regression, then a
combined held-out non-regression check — or accept H4 as diagnostic-only. The
fixed placeholder goal image means this is **not** evidence of stronger
goal-image conditioning.
