# H7r diagnostic evaluation matrix

Track A, single-integrator offline rollout. **Every run forced `--data-root`** (locked methodology). CR=0 structurally offline. Goal image = fixed placeholder `h2_weave_J` (imitation-fidelity, not goal-conditioning).

| role | model | corpus/split | n | SR | OSR | SPL | NE_m | nDTW |
|---|---|---|---|---|---|---|---|---|
| PRIMARY | H1 incumbent | h7r/test | 2 | 0.000 | 1.000 | 0.000 | 15.43 | 0.078 |
| PRIMARY | H7r candidate | h7r/test | 2 | 1.000 | 1.000 | 0.908 | 2.54 | 0.646 |
| PRIMARY | H6 procedural (OOD ref) | h7r/test | 2 | 0.500 | 1.000 | 0.500 | 3.62 | 0.550 |
| SANITY | H7r candidate | h7r/val | 2 | 1.000 | 1.000 | 1.000 | 2.06 | 0.633 |
| SANITY | H7r candidate | h7r/train | 4 | 1.000 | 1.000 | 0.951 | 2.17 | 0.664 |
| SANITY | H1 incumbent | h7r/val | 2 | 0.000 | 1.000 | 0.000 | 15.08 | 0.080 |
| OOD | H7r candidate | h4/test | 6 | 0.000 | 0.667 | 0.000 | 4.27 | 0.362 |
| OOD | H1 incumbent | h4/test | 6 | 0.000 | 1.000 | 0.000 | 14.04 | 0.167 |

**Headline (H7r held-out test, n=2):** candidate turns incumbent failure into success — SR 0.000→1.000, SPL 0.000→0.908, NE 15.43→2.54 m, nDTW 0.078→0.646. SANITY rows are reporting-only (selection/train splits). OOD rows are out-of-domain diagnostics (procedural H4), not hospital claims.