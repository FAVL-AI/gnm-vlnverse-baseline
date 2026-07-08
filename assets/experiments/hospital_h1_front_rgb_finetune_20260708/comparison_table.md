# Hospital H1 — camera-domain adaptation result (internal simulation)

Held-out test: goals D/E/G, 8 episodes, evaluated exactly once per model.

| Model | Trained on | SR | OSR | NE (m) | SPL | TL (m) | nDTW | CR |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Top-down incumbent (diagnostic) | 191 Kujiale top-down eps | 62.5 | 100* | 3.14 | 0.285 | 5.95 | 0.746 | N/A — offline |
| **Front-RGB fine-tune (promoted)** | init from incumbent + 12 hospital front-camera eps | **100*** | 100* | **0.32** | **0.935** | 2.77 | 0.961 | N/A — offline |

\* Hospital test routes are short (2–4 m) relative to the 3 m success
radius, so SR/OSR are partially saturated; **NE, SPL and nDTW carry the
signal** (NE 3.14 → 0.32 m; SPL 0.285 → 0.935).

Label: camera-domain adaptation / hospital internal simulation
experiment. The top-down incumbent is a DIAGNOSTIC baseline measuring
the domain gap, not a fair final competitor — it was trained on a
different camera convention.

Governance: DriftGuard promote; VerdictPlane allow (hospital line
only); Sentinel camera_regime_domain_shift diagnostic recorded.
