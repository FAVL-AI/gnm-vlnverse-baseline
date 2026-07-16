# H8 Synthetic Fork — Tiny Pilot Recording Report

**Status: PILOT CAPTURE — `SYNTHETIC_DIAGNOSTIC_ONLY`.** Scripted, policy-free capture; no policy/model inference, no training, no rollout metrics, no action-probe. `CL_BOUND_XY` unchanged (6.0).

- **PILOT: PASS**  fail_reasons: []
- examples: 8  instances: 1
- leakage_safe: False  meets_min_scale: False (a tiny pilot is EXPECTED below min scale — reported limitation, not a certified dataset)
- leakage-audit reasons/limitations: ['below_min_scale', 'single_instance_not_leakage_safe']

Claim boundary: SYNTHETIC_DIAGNOSTIC_ONLY; harness/schema validation pilot only; not a dataset; not hospital/real-scene/benchmark/full-ImageNav evidence; no SOTA; no promotion; no autonomy; not training authorization; CL_BOUND_XY unchanged.

## Pilot capture summary (evidence)

This is a **`SYNTHETIC_DIAGNOSTIC_ONLY`** run: a **real tiny pilot capture was executed** through the committed executable capture path. It is a harness/schema validation pilot — **not a dataset**, and **not training authorization**.

- **Executable capture path commit: `82f60f9`** (`Implement synthetic fork pilot capture path`).
- **Pilot config commit: `c646225`** (`configs/gnm/h8_synthetic_fork_recorded_mode_pilot.yaml`).
- **All expected pilot artifacts produced** — pilot manifest, pilot image index, pilot action-label table, pilot contact log, pilot provenance table, pilot leakage-audit report, pilot recording report (+ the tiny RGB images).
- **8 real pilot records/images** (`n_examples = 8`; 10 RGB PNGs = 2 decision-frame views + 8 branch-goal views).
- **Images are non-empty** — every decision and goal frame rendered non-black; zero zero-byte files.
- **IDs are unique** — 2 distinct decision frames (`pilot_inst0_df0`, `pilot_inst0_df1`); 8 unique goal-image IDs.
- **Scripted labels are populated** — every record has an `action_class` (STRAIGHT / TURN_LEFT_90 / TURN_RIGHT_90), all `policy_driven = False`.
- **Route-family labels are populated** — `N_vs_W_90` (primary) and `N_vs_E_90` (optional secondary).
- **Provenance metadata is present** — scene, config, gate history, harness recorded for every record.
- **Contact log contains 16 entries** (decision + goal per unit): **obstacle contacts 0**, **ambiguous contacts 0**, **support contacts 24** — support classified separately from obstacle.
- **Support prims are `Floor`, `N_floor_strip`, `E_floor_strip`, `W_floor_strip`** — all **floor cues, not wall/panel/prop obstacle contacts**.
- **Leakage audit ran on the real records**: `n_examples = 8`, `n_instances = 1`, `leakage_safe = False`, `meets_min_scale = False`, reasons include **`below_min_scale`** and **`single_instance_not_leakage_safe`**.
- **This is an EXPECTED pilot limitation** — a single-instance, below-scale tiny pilot is **not a trainable dataset**.

### Boundary

- **No train/val/test dataset was created.**
- **No policy/model inference.** **No action-probe.** **No rollout metrics** (no TL/NE/SR/OSR/SPL/nDTW/CR).
- **No benchmark claim.** **No hospital evidence.** **No real-scene / real-world evidence.** **No full goal-conditioned ImageNav claim.** **No SOTA.**
- **No promotion** (`DIAGNOSTIC_ONLY_NOT_PROMOTED`). **No autonomy claim.** **Not training authorization.**
- **`CL_BOUND_XY = 6.0` unchanged** (read-only mirror; harness sources untouched by this run).
