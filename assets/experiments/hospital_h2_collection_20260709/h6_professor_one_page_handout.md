# H6 Hard-Route Coverage Diagnostic — Camera-Only ImageNav

Frank Asante Van Laarhoven · 2026-07-13 · prepared for Prof. Bo Wei
Internal Isaac-Hospital-ImageNav-v0 simulation · branch `h23-execfix`, commit `bfb595f`

> **Headline.** H6 is the strongest *diagnostic* result so far, **but not a promotion result**.
> It shows hard-route coverage improves aggregate performance and fixes the older-family
> regression seen in H5, but fresh hard-family generalisation still fails.

### 1. Research question
Does adding *clean hard-route families* (uturn / chain / ftL / sharp-multi-turn / tight-corridor)
to **training** produce success on **held-out hard-route families** — i.e. is the H5 shortfall a
route-family *coverage* gap rather than a data-balance gap?

### 2. Why H6 was needed after H5
H5 (mixed-family replay) improved trajectory fidelity but **regressed on a prior family**:
prior-held-out SR fell 0.167 → 0.000 (it lost the `ftL` family the incumbent could do), and it
still reached no success on hard families. This blocked promotion and motivated a direct coverage test.
[`h6_professor_report.md` §1; `h6_per_family_failure_table.json`]

### 3. What was collected
- **16 / 16 clean** scripted-expert recordings — `route_completed = True`, **0 collisions**, clean
  DDS/process cleanup. [`h6_recording_quality_table.csv`]
- **Leakage-clean** split (episode- and family-disjoint), single fixed goal image.
  [`h6_conversion_leakage_report.json`]
- **Train / val / fresh-hard split = 10 / 2 / 4** (train = 5 hard types ×2; val = compound-turn ×2;
  fresh-hard held-out = uturn_02 / chain_02 ×2). [`h6_conversion_leakage_report.json`]

### 4. Training / evaluation setup
MobileNetV2-GNM, weights-only initialisation from the retained **H1 incumbent** with a fresh
optimizer, seed 42, checkpoint selected on the H6 validation split. Evaluation is offline Track-A
over three checkpoints (H1, H5, H6) on four held-out sets, with the data root forced on every run.
[`h6_professor_report.md` §4; `h6_eval_matrix.csv` / `h6_eval_matrix.json`]

### 5. Key results (offline Track-A) [`h6_eval_matrix.csv`, `h6_per_family_failure_table.csv`]
| Held-out set (n) | Metric | H1 | H5 | **H6** |
|---|---|---|---|---|
| H4 held-out (6) | SR / NE (m) | 0.00 / 14.04 | 0.333 / 5.02 | **0.333 / 6.15** |
| **Fresh hard (4)** | SR / OSR / NE | 0.00 / 0.00 / 21.36 | 0.00 / 0.00 / 8.25 | **0.00 / 0.00 / 10.58** |
| Prior held-out (6) | SR / NE | 0.167 / 12.76 | 0.000 / 7.19 | **0.167 / 7.73** |
| Combined (12) | SR / nDTW | 0.083 / 0.222 | 0.167 / 0.336 | **0.250 / 0.351** |

- **Best combined SR = 0.25** and **best combined nDTW = 0.351** (both H6).
- **H4 gain preserved** (family `navgen_016` 2/2).
- **H5 prior-family regression removed** (`ftL` recovered to 1/2, matching the incumbent).
- **Fresh hard families still fail: SR = 0 and OSR = 0** for all three models.

### 6. Main interpretation
Route-family coverage **helps aggregate quality** and **repairs the older-family regression**, but the
model **never reaches within the 3 m success radius on unseen hard-family instances** (OSR = 0). Because
the held-out instances are only a/b repeats of the trained routes, this indicates **simple a/b variants
are not enough** for hard-family generalisation. [`h6_professor_report.md` §6]

### 7. Limitations [`h6_claim_boundary.md`; `h6_adjudication.json`]
Diagnostic only — **not promoted** (VerdictPlane deny; H1 incumbent retained). **Fixed placeholder
goal ⇒ not goal-conditioning evidence.** Scripted-expert demonstrations; simulation only; offline
Track-A; small n (4 / 6 / 12); one seed; deterministic a/b variants. Not real-robot; not a public
benchmark; no state-of-the-art claim.

### 8. Next experiment
Collect **instance-diverse hard-route data** (distinct routes, not a/b repeats) and evaluate under a
**non-fixed, goal-conditioned** protocol against real goal images.

> **Conclusion.** H6 supports the coverage-gap diagnosis but does not confirm hard-family
> generalisation. The next step is instance-diverse hard-route data and non-fixed goal-conditioned
> evaluation.
