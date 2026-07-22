# Historical data classification — immutable evidence register

Per-bag detail: `H8_HISTORICAL_DATA_CLASSIFICATION.csv` (157 rows).

## Governing rule

> Every bag recorded before this protocol is **immutable historical evidence**. None may be modified,
> relabelled as formal training evidence, or admitted to the H8 train/validation/test dataset.

Two independent reasons apply to **all 157**, and either alone is disqualifying:

1. **640×480 acquisition**, below the canonical 1280×720.
2. **No episode-specific goal image** — not repairable post hoc without fabricating ground truth.

They retain real value as demonstration, diagnostic and engineering evidence, and they are what makes
the H8 design defensible: the defects were found in our own data by our own audit.

## Classification

| Class | Bags | Status |
| --- | ---: | --- |
| `DEMONSTRATION_EVIDENCE` | **13** | Showable to a supervisor; proves the capture path works end to end |
| `DIAGNOSTIC_EVIDENCE` | **126** | Internal engineering diagnostics only |
| `PERMANENTLY_REJECTED` | **18** | No evidential value; retained only as a record that they were rejected |

### `DEMONSTRATION_EVIDENCE` (13)

Gate-verified `hospital.usd`, raised 0.12 m mount, clean full frame, ≥1 m executed motion, zero
collisions:

`h7r_corridor_01`, `h7r_corridor_02`, `h7r_reception_01`, `h7r_reception_02`, `h7r_turn_01`,
`h7r_turn_02`, `h7r_waiting_01`, `h7r_waiting_02`, `h8_d1_routeA_turn_up`, `h8_d1_routeB_straight`,
`h8_d2_routeA_fwdleft`, `h8_d2_routeB_fwdright`, `h8mx_val_lobby`.

*Permitted use:* supervisor demonstration of scene fidelity and the camera-raise fix; trajectory
length, collision rate, safety-intervention and provenance diagnostics; illustrations in a methods
section describing the pipeline.
*Prohibited use:* training, validation, test, or any SR/OSR/NE/SPL/nDTW claim.
*Reason:* all 13 declare the placeholder goal `h2_weave_J`. The 8 `h7r_*` are additionally already
consumed by the H7r pilot data-root, whose own specification (§9) records this exact defect.

### `DIAGNOSTIC_EVIDENCE` (126)

Includes the 20 gate-verified bags that fail an image or motion criterion, the 19 with hospital
prim-contact evidence but no gate, and the remainder with no admissible provenance.

*Permitted use:* internal engineering analysis — the camera-raise comparison, execution-stall
analysis, contact-report behaviour, throughput baselines.
*Prohibited use:* any external claim, any dataset, any figure presented as hospital navigation
evidence. Specifically, the H24 family, `full_topics_20260708`, `h6_smoke_uturn01_full` and
`h6rec_h6_uturn_01_a` self-label as hospital but render as washed-out untextured geometry
(colourfulness 0.03–2.46 against 8–24 for verified hospital frames) — **these must never appear in a
hospital deck.** This is the standing H6 correction rule, extended.

### `PERMANENTLY_REJECTED` (18)

- **All-black RGB streams (6):** `h2_ft_I_a`, `h2_ft_I_b`, `h2_ft_M_solo`, `h2_td_H_r2`,
  `h2_td_I_solo`, `h2_td_M_solo` — luminance 0.00, std 0.00, every frame identical; ~10,000 recorded
  frames containing nothing.
- **Blown-out static (1):** `h8mx_calib_lobby` — luminance 226.8, std 4.0, all frames identical,
  0.000 m of motion.
- **No RGB stream (11):** `smoke_drive_20260708` and the ten `yaw_test_*` bags.

*Permitted use:* none, beyond the record that they were rejected and why.

## Preservation requirements

1. **Do not delete.** These bags are the evidentiary basis for the H8 redesign; deleting them would
   remove the ability to reproduce the audit.
2. **Do not edit any bag, `metadata.yaml`, `trajectory.csv` or `episode_metadata.json`.** In
   particular, do **not** back-fill `start_pose_episode` from observed poses (118/140 disagree) and do
   **not** correct `policy_mode` in place (142 mislabelled). Those discrepancies are the finding.
3. **Annotate, do not rewrite.** Corrections are recorded in *new* sidecar files
   (`h8_historical_classification.json` per bag directory, or one repository-level register),
   never by mutating the original.
4. **Any future reference to these bags must carry the class label** — `DEMONSTRATION_EVIDENCE`,
   `DIAGNOSTIC_EVIDENCE` or `PERMANENTLY_REJECTED` — so a reader cannot mistake a diagnostic figure
   for a dataset result.
5. Storage: 195.44 GB. If space is needed for the H8-S capture (~50–110 GB at 1280×720), the
   `PERMANENTLY_REJECTED` bags are the **only** candidates for archival-and-removal, and only with
   their manifests and checksums retained. That requires a separate written decision.

## What the historical corpus legitimately proves

| Claim | Evidence |
| --- | --- |
| The scene-identity gate works and is fail-closed | 35 gate records, all PASS, on the real `hospital.usd` (1,909 prims) |
| The hospital scene renders photorealistically at robot height | `h7r_*` / `h8_*` contact sheets |
| The 0.12 m camera raise fixes the lower-frame obstruction | 39/39 unraised occluded vs 23/24 raised clean — a clean controlled comparison |
| The logging pipeline is arithmetically exact | derived vs declared path length and goal distance agree to 0.0000 m across 154 episodes |
| Collision telemetry via PhysX contact reports is feasible | 126 episodes, contacts naming real hospital prims |
| Shadow-mode GNM inference is fast enough to consider closed-loop | mean 8.1 ms, max 14.5 ms over 51 episodes |

These are genuine results and should be presented as such — as **engineering validation of the capture
path**, never as navigation performance.
