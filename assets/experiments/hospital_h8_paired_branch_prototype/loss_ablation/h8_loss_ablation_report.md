# H8 Minimal 2×2 Loss-Ablation Diagnostic

**Scope: tiny diagnostic only.** No promotion, no push, no tag, no 20/5/10, no closed-loop Isaac testing, no generalizable goal-conditioning claim. Uses ONLY the committed 2×2 H8 paired-branch prototype (2 decision frames × 2 goals = 4 samples). Weights-only init from the H7r candidate, fresh optimizer, seed 42, 400 steps, lr 0.001; deterministic cuDNN/cuBLAS (run-to-run reproducible on this setup). No checkpoint written to the repo.

## Question
Can the new goal-conditioned objective make the action head produce goal-dependent predicted `[Δx, Δy]` at the shared decision frames — i.e. break the ≤2° goal-collapse the action-probe found (baseline)?

**Pass target (this tiny diagnostic only):** branch-choice ≥ 0.75, S ≥ 0.5, mean pred action change ≥ 15°, direction toward the correct branch.

## Progression (action-probe recomputed after each ablation)

| variant | branch-choice | goal-sensitivity S | pred action change (°) | mean angle err (°) | diagnostic |
|---|---|---|---|---|---|
| baseline (H7r, untrained) | 0.50 | 0.024 | 1.50 | 39.5 | — |
| A | 1.00 | 0.993 | 61.12 | 0.5 | ✅ pass |
| A+B | 1.00 | 1.217 | 75.14 | 6.9 | ✅ pass |
| A+B+C | 1.00 | 1.019 | 62.50 | 2.1 | ✅ pass |
| A+B+C+E | 1.00 | 0.948 | 58.74 | 9.8 | ✅ pass |

Losses: **A** action imitation `||a_pred−a_target||`; **B** goal-contrastive (separation + triplet repulsion at each shared o_d); **C** branch-classification auxiliary (at a shared o_d the obs half is constant, so branch class must flow through `goal_feat`); **E** goal-dropout (zeroed goal → neutral action target).

## Per-variant observations

- **Plain imitation (A) alone already breaks collapse** (change 61.1°, S 0.993, error 0.5°): at a shared o_d the two goals have different targets, so the imitation loss cannot fit both without using `goal_feat`. This shows the collapse in H7r was a **data** problem (one route per start), not an architectural inability to condition on the goal.
- **Cleanest passing variant by angle error: `A`** (0.5° mean error).
- **Over-separation (S > 1) in A+B, A+B+C**: the goal-contrastive / branch terms push the two predictions *further apart than the targets require*, raising S above 1 and slightly increasing angle error — unnecessary on this tiny, already-separable set (may help / need re-tuning on the larger H8 set).
- **`A+B+C+E` passes but is the weakest variant** (9.8° mean error, highest among passing variants) — the goal-dropout term (E), which maps a zeroed goal to the neutral mean action, adds no benefit on this tiny already-separable set and slightly increases error; it needs re-tuning before use on the larger H8 dataset.

## Reproducibility correction

- **Initial CUDA training was non-deterministic:** an early run gave unstable results that shifted between executions — one variant's diagnostic verdict even flipped (pass↔fail) run-to-run, which is unacceptable for committed evidence.
- **Fix:** deterministic cuDNN/cuBLAS was enabled (`cudnn.deterministic=True`, `cudnn.benchmark=False`, `CUBLAS_WORKSPACE_CONFIG=:4096:8`, per-ablation seeding of torch/numpy/CUDA).
- **Verification:** after the fix, **run 1 and run 2 are byte-identical** (the results JSON diff is empty). The numbers above are reproducible on this setup. Note the earlier transient "E regressed" observation was a non-determinism artifact; under the deterministic run all four trained variants pass.

## Interpretation & decision

- **The objective can break goal-collapse.** Baseline (untrained H7r) predicts ~the same action for both goals (pred action change 1.50°). After training with the goal-conditioned objective, the predicted action becomes goal-responsive (see progression; best variant `A+B`), meeting the tiny-diagnostic pass target.
- This **justifies building a larger H8 causal dataset** and training the full objective.
- **CRITICAL CAVEAT (must not be dropped):** this uses only **two decision frames**. A pass proves only that the loss can move the model *away from goal-collapse* by fitting/memorising these frames — it does **NOT** prove generalizable goal-conditioned navigation. That requires many distinct decision frames with a **held-out** split (the H8 collection).
- **No promotion, no SOTA claim, no full-autonomy claim.** Incumbent retained; status remains `DIAGNOSTIC_ONLY_NOT_PROMOTED`. No checkpoint is committed.

## Claim boundary
- Supervised imitation + auxiliary losses on 4 memorised samples; offline action-probe of the instantaneous predicted action; no rollout, no physics, no autonomy.
- Expected actions = committed recorded-acceptance robot-frame directions o_d→goal (also the training targets); a pass therefore means the action head *can* express goal-dependent outputs, not that it has learned a generalizable goal representation.

## Artifacts
`assets/experiments/hospital_h8_paired_branch_prototype/loss_ablation/`: `h8_loss_ablation_report.md`, `h8_loss_ablation_results.json`, `h8_loss_ablation_matrix.{csv,md}`, `h8_loss_ablation_direction_diagram.png`. Harness: `scripts/gnm/h8_loss_ablation.py`. (Checkpoints/weights NOT written to the repo.)
