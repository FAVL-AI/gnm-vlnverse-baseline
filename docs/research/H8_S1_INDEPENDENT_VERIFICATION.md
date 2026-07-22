# H8-S1 Independent Verification and Regression-Isolation Review

**Review date:** 2026-07-22 · **Type:** independent, non-remediating, documentation-only.

No implementation, test, schema, fixture, bag, manifest or capture-configuration file was changed by
this review. No Isaac, Omniverse or live ROS 2 runtime was launched. Nothing was captured, trained,
inferred, pushed or tagged.

---

## 1. Commit under review

| Item | Value |
| --- | --- |
| **H8-S1 implementation commit** | **`9ffa5079253b3dda201028181558b3af238a0b5d`** |
| Subject | *Prepare H8 hospital dataset alignment and builder* |
| **Previous commit (`HEAD~1`)** | **`5df7c3407925fc67aa68544ab65510386e24fe15`** — *Enforce observed camera resolution for H8 admission* |
| Author / Committer | Frank Asante Van Laarhoven `<F.Van-Laarhoven2@newcastle.ac.uk>`, both, 2026-07-22 02:53:41 +0100 |
| Trailers | none |
| Files changed | 24 (23 added, 1 modified) |
| Amended / rebased? | **No.** Reflog shows `HEAD@{0}` and `HEAD@{1}` as ordinary `commit:` entries. The only `commit (amend)` in reflog is `d5a1bc6`, dated 2026-07-08, two weeks before S1 and unrelated. |
| Local and unpushed? | **Yes** — `h23-execfix` is `[ahead 1]` of `origin/h23-execfix`; `origin/h23-execfix..HEAD` contains exactly this commit. |
| Tags | none at `HEAD` or `HEAD~1`. |

**Correction to the S1 completion report.** `5df7c34…` is `HEAD~1`, not the S1 commit. The S1 commit
is `9ffa5079253b3dda201028181558b3af238a0b5d`. Git proves this; the earlier report omitted the full
hash. Resolved.

## 2. Baseline integrity

Branch `h23-execfix`, upstream `origin/h23-execfix`, ahead 1. **0 staged.** Working tree carries
**395 unrelated entries** (11 modified tracked, 384 untracked) — recorded, not cleaned, not modified.
No historical evidence file was touched: `git show --stat HEAD` matches zero paths under
`assets/experiments/rosbags/`, `episode_metadata.json`, `trajectory.csv` or `trajectory.jsonl`.
Rosbag count 157, unchanged. `datasets/isaac_hospital_h8` absent. `CL_BOUND_XY = 6.0` at
`scripts/gnm/h8_evidence_schema.py:40`, unchanged.

## 3. Alignment procedure — independently recomputed

The 15 required cases were recomputed with plain arithmetic written from
`H8_TIME_ALIGNMENT_POLICY.md`, **not** by reusing the implementation's helpers, then compared
against what the implementation returns.

**27 / 27 independent checks agree.** Cases verified: exact match; midpoint interpolation
(x = 0.015 from the bracket [0.05, 0.10]); stationary pose; constant linear motion; ±π yaw crossing;
missing earlier pose; missing later pose; duplicate timestamps; out-of-order timestamps; frame-ID
mismatch; clock mismatch; invalid quaternion; gap below / at / above 25 ms.

The yaw-wrap case is the one worth singling out: interpolating 175° → −175° returns
`|yaw| = 3.141592653589793` (i.e. ±180°). A naive linear-yaw implementation would return 0.0 —
a pose the robot never occupied. The shortest-arc slerp is correct.

Boundary semantics confirmed inclusive: `residual == tolerance` is accepted, `residual > tolerance`
rejects with `H8_ALIGNMENT_GAP_EXCEEDED`.

**Verdict: `PASS`.**

## 4. Provisional 25 ms tolerance

Derivation reconstructed from `assets/experiments/manifests/h8_s1_timing_characterisation.csv`
(8 bags: `h7r_reception_01`, `h8_d1_routeB_straight`, `h8mx_val_lobby`, `h7_reception_01`,
`h2_ft_I_a`, `h24_straight_a`, `h8mx_val_east_A`, `h6rec_h6_uturn_01_a`).

| Quantity | Value (all 8 bags) |
| --- | --- |
| Camera header `dt` — p50 / p95 / p99 / max | 0.05 s (20 Hz simulation time) |
| Pose header `dt` — p50 / p95 / p99 | 0.05 s (20 Hz) |
| Median image-to-nearest-pose gap | 0.016667 s |
| p95 gap | 0.016667 s |
| **p99 gap** | **0.016667 s** (one 60 Hz physics step) |
| Max observed gap | 0.016667 – 0.116667 s (episode edges) |
| Clock domains compatible | Yes — image header inside `/clock` span in every bag; `/clock` monotonic in every bag |
| Position displacement at 0.2 m/s over 25 ms | **0.005 m** — 1.0 % of τ = 0.50 m |
| Yaw displacement at 0.4 rad/s over 25 ms | **0.5730°** |

Ordering independently confirmed: `0.016667 < 0.025 < 0.05`. The tolerance is above the measured p99
residual (so every interior frame brackets) and below the publish period (so a dropped-partner pose
is refused rather than interpolated across).

**Disposition: `PROVISIONALLY JUSTIFIED`.** This review does **not** convert it into a final runtime
threshold. Session B retains ownership of confirmation at 1280×720, where the publish period may
change and the tolerance must follow it.

## 5. Schema and goal controls

All 33 negative schema fixtures reproduced. Goal-registry rejection independently exercised for:
placeholder goal, missing goal, ambiguous goal, hash mismatch, scene mismatch, map mismatch, split
mismatch, pose mismatch, camera mismatch, resolution mismatch.

**Processing-order verified against behaviour, not test names.** Two probes:

- Manifest with an unresolvable `goal_id` *and* an unalignable image series → exit 3, reason codes
  `['H8_GOAL_NOT_FOUND']`, episode not admitted.
- Structurally invalid goal registry (two records sharing a `goal_id`) → exit 2,
  `blocked_at = "goal_registry"`, **`len(episodes) == 0`**, and no `alignment` block was produced.

The required invariant holds: no frame, trajectory or plan work occurs until exactly one locked goal
record resolves.

**Verdicts: schema rejection `PASS`; goal substitution prevention `PASS`.**

## 6. Controller and checkpoint identity

| Control | Result |
| --- | --- |
| `gnm_closed_loop` requires `policy_in_loop=true` | Enforced — `H8_CONTROLLER_POLICY_MISMATCH` |
| `gnm_closed_loop` requires a checkpoint digest | Enforced — `H8_CONTROLLER_CHECKPOINT_MISSING` |
| Scripted follower claiming `policy_in_loop=true` | Rejected |
| Unknown controller mode | Rejected — `H8_CONTROLLER_MODE_UNKNOWN` |
| Missing controller mode | Rejected — `H8_CONTROLLER_MODE_MISSING` |
| Folder names establishing controller identity | Not possible — no path-derived inference exists in the validator |
| Caller Boolean alone establishing learned execution | Not sufficient — the digest requirement is independent of the flag |
| Shadow distinct from closed loop | Yes — `gnm_shadow` forces `policy_in_loop=false` |

The strongest control is the checkpoint requirement. A historical record can be internally
self-consistent (`policy_mode=gnm_closed_loop` *and* `closed_loop=true`) and still be false; only the
weights digest makes the claim falsifiable. **Note:** the digest is required to be *present*; it is
not yet verified against the referenced file. That is a reasonable S1 boundary but should be closed
before any closed-loop result is published.

**Verdict: `PASS`.**

## 7. Builder no-output boundary

Twenty paths exercised with a filesystem snapshot before and after each run: valid validate-only;
valid dry-run; valid emit-plan; placeholder goal; wrong resolution; start-pose mismatch; controller
mismatch; missing scene digest; alignment failure; missing navmesh (`--strict`); duplicate retry;
goal not found; goal hash mismatch; goal split mismatch; ambiguous registry; unknown controller;
missing authorisation; unsupported mount; absent contact telemetry; historical-like manifest.

**Output-boundary violations: 0 / 20.** In every case `--out-dir` was never created; `dataset_created`,
`images_written`, `trajectories_written`, `split_manifest_written` and `metrics_computed` were all
zero/false. The only file ever written was `plan.json` in the one case that explicitly requested
`--emit-plan` — a requested report, not a dataset artefact.

**Verdict: `PASS`.**

## 8. Retry and independence

The known pair is classified as one instance. Four evasion attempts were tried and **all four were
caught** as `H8_RETRY_NOT_INDEPENDENT` with `n_distinct_instances == 1`:

| Evasion | Caught |
| --- | --- |
| Renamed episode id (`…west_Z_20260909_235959`) | Yes |
| Suffixed / retry-style id | Yes |
| Reordered metadata keys | Yes |
| Insignificant float formatting (`2.0000000000` vs `2.0`) | Yes |

Detection is content-based — a digest over route instance, goal id, goal image hash, observed start
pose, goal pose, controller mode and trajectory/image digests, with `episode_id` and timestamps
deliberately excluded. Renaming cannot manufacture independence.

## 9. Metric readiness

All 18 metrics were evaluated under six scenarios (valid, no navmesh, no reference path, placeholder
goal, no stop event, no contact telemetry). **Undocumented states: 0. Zero is never substituted for
missing evidence.**

Confirmed: SR / OSR / SR–OSR gap / NE reject on a placeholder goal; SPL rejects without navmesh and
without reference path; nDTW / SDTW / CLS reject without an approved reference trajectory; collision
count and rate return `NOT_COMPUTED_MISSING_CONTACTS`; completion time is
`COMPUTABLE_DIAGNOSTIC_ONLY` and is never labelled SCT; stop timing and overshoot reject without a
stop event; latency rejects without matching timestamps.

Two behaviours were checked closely and found **correct, not defects**: nDTW and CLS remain valid
under a placeholder goal — they are path-fidelity measures against a reference route and are
goal-independent by definition (Ilharco et al.; Jain et al.), whereas SDTW = SR × nDTW correctly
inherits the goal requirement. OSR remains valid without a stop event while SR does not, per
Anderson et al. Recommendation 1.

**Verdict: `PASS`.**

## 10. Historical-manifest rejection

The real `assets/experiments/trajectories/h8mx_val_east_A_20260714_215023/episode_metadata.json`
was run through the S1 validator. Result: **15 reason codes**, exit 3, no output directory, no metric
computed, no admission — and the file verified **byte-identical** afterwards. Codes include
`H8_GOAL_ID_PLACEHOLDER`, `H8_ACQUISITION_RESOLUTION_MISMATCH`, `H8_SCENE_DIGEST_MISSING`,
`H8_CONTROLLER_CHECKPOINT_MISSING`, `H8_START_POSE_DECLARED_MISSING`,
`H8_CONTACT_TELEMETRY_UNAVAILABLE`. Each corresponds to a defect the forensic audit actually found.

## 11. Regression isolation — mandatory analysis

### Reproduction

| Command | Result |
| --- | --- |
| `pytest tests/ -k h8` | **2 failed, 569 passed, 2387 deselected** |
| `pytest tests/gnm/ -k h8` | 2 failed, 569 passed, 692 deselected |
| The two tests **alone** | **2 passed** |
| The four H8 regression files together (`recorded_mode`, `evidence_schema`, `resolver`, `provider`) | **240 passed, 0 failed** |
| `pytest tests/ -k h8` at **`HEAD~1`** in a clean detached worktree | **both tests still FAIL** |

### Root cause

Instrumenting the session with an external plugin (loaded via `PYTHONPATH`, no repository file
touched) showed **`none observed`** for first-introduction during any test — meaning the forbidden
modules are already in `sys.modules` *before the first test executes*. They enter at **pytest
collection**, when every module under `tests/` is imported; `-k` deselects tests but does not prevent
module import.

Probing each test module in a fresh interpreter identified the four contaminating modules:

| Module | Introduces |
| --- | --- |
| `tests/gnm/test_gnm_model.py` | `torch` |
| `tests/test_baseline_contract.py` | `torch` |
| `tests/test_visualnav_adapters.py` | `torch` |
| `tests/test_fleetsafe_perception_node.py` | `rclpy` |

Their imports are entirely expected — they are the model and ROS-node test suites.

### What the failing tests actually assert

Both tests do two separate things:

1. a **source-token scan** of one specific module's text (order-independent);
2. a **`sys.modules` check** that `omni`/`isaacsim`/`rclpy`/`torch`/`cv2` are absent
   (process-global, order-dependent).

Only (2) fails. (1) — the actual security property — passes in every configuration.

The failure is also **non-deterministic in which module trips it**: one run reported `torch`, another
`rclpy`, depending on collection order. Both are present at session end.

### Can the pollution hide a genuine violation?

Modelled directly. A **literal** forbidden import (`import torch`) is caught by the token scan in
both clean and polluted sessions — the primary control survives. A **dynamic** import
(`__import__("tor"+"ch")`, `importlib.import_module`) evades the token scan; in a clean session the
`sys.modules` check would catch it, but under pollution that assertion is already firing for
unrelated reasons, so a genuine violation would be indistinguishable from the known noise.
**The backstop is degraded, not the primary control.**

Independently confirmed that the S1 modules themselves are clean: no forbidden token in any of the
four source files, no `__import__`/`importlib` dynamic-import usage, and importing all four in a
fresh interpreter loads **zero** forbidden modules (107 modules total).

### Disposition

**`PRE-EXISTING TEST-ISOLATION DEFECT`** — proven at `HEAD~1`, where S1 files do not exist.
**S1 introduced neither failure.**

Severity **Medium**: the guarantee the gate makes concerns the integrated session, and "passes in
isolation" is not sufficient. A bounded remediation is required before Session A — but the remedy is
test hygiene (e.g. capture a module baseline at session start and assert no *new* forbidden module),
not an implementation change, and it is out of scope for this non-remediating gate.

**Verdict: `PASS WITH DOCUMENTED LIMITATIONS`.**

## 12. Literature corrections — independently reproduced

### VLNTube

| Claim | Independent result |
| --- | --- |
| Content digest | `965e4db0f8c59fa1d119de1858184bb447d954d8485cccee1db0c664b835bf75` — **reproduced exactly** |
| File count | 36 — confirmed |
| Licence | MIT, *Copyright (c) 2026 V3A Group, Responsible AI Research Centre, The University of Adelaide* — confirmed verbatim |
| Not a submodule | Confirmed — no `.gitmodules`, empty `git submodule status`, no nested `.git`, `git ls-files -s` shows only modes 100644/100755 (no 160000 gitlink) |
| Upstream revision `7ef6afe2…` | Recorded in the provenance manifest |
| Path/identifier references preserved | Yes — 173 tracked files reference `vlntube` (167 baseline + 6 new review documents); no legitimate path was removed |

### VLNVerse

No active `4,000+` claim survives outside the correction notices that document its withdrawal. The
paper draft now states 263 reported / 262 released / 4 local (1.5 %).

### ViNT

Reference 3 attributes ViNT to Shah et al. Other active documents
(`FLEETSAFE_VLN_RESEARCH_POSITION.md`, `REFERENCE_DATASET_AUDIT_GNM_VINT_NOMAD.md`) already
attribute correctly.

**Verdict: `PASS WITH MINOR FINDINGS`** — see `H8-S1REV-F-005`.

## 13. Findings

### `H8-S1REV-F-001` — alignment failure surfaces no report-level reason code · **Medium**

- **Requirement:** every fail-closed rejection carries a deterministic reason code (§25 of the S1 gate).
- **Expected:** an alignment rejection appears in `BuildReport.reason_codes`.
- **Observed:** a manifest whose image series cannot align exits 3 and is not admitted, but
  `rep.reason_codes == []`. The cause is visible only inside
  `episodes[0]["alignment"]["rejection_reasons"]`.
- **Reproduction:** `--manifest` with `image_stamps=[0.05, 99.0]` → exit 3, empty `reason_codes`,
  `{'H8_ALIGNMENT_EXTRAPOLATION_REFUSED': 1}` in the alignment block.
- **Origin:** S1. **Containment:** fail-closed behaviour is unaffected — the episode is rejected and
  no output is produced. Only the top-level diagnostic is incomplete.
- **Remediation:** propagate alignment rejection codes into `BuildReport.reason_codes`.
- **Session A effect:** none directly; should be fixed in the bounded remediation.

### `H8-S1REV-F-002` — two declared reason codes can never fire · **Low**

- `H8_METRIC_INPUT_UNAVAILABLE` and `H8_CONTACT_TELEMETRY_ZERO_WITHOUT_DETECTOR` are declared in
  `h8_s1_reason_codes.py` but are not referenced by any implementation module.
  `H8_METRIC_INPUT_UNAVAILABLE` was named explicitly in the S1 gate specification.
- **Containment:** the underlying conditions *are* covered — missing metric inputs surface as the
  specific `NOT_COMPUTED_*` states, and absent telemetry raises
  `H8_CONTACT_TELEMETRY_UNAVAILABLE`. The codes are redundant, not missing controls.
- **Remediation:** either wire them or remove them; a declared-but-unreachable code invites the
  belief that a control exists.

### `H8-S1REV-F-003` — active reason-code test coverage is 85 %, not 100 % · **Low–Medium**

- 56 codes declared, 54 reachable, **46 asserted in tests (85 %)**. The KPI target is 100 %.
- Untested: `H8_CONTROLLER_MODE_MISSING`, `H8_GOAL_CAMERA_MISMATCH`, `H8_GOAL_POSE_MISMATCH`,
  `H8_GOAL_RESOLUTION_MISMATCH`, `H8_MANIFEST_SCHEMA_INVALID`, `H8_MANIFEST_VERSION_UNSUPPORTED`,
  `H8_SCENE_IDENTITY_FAILED`, `H8_SUCCESS_CRITERION_NOT_PREREGISTERED`.
- **This review triggered all eight independently: 8 / 8 fire correctly.** The controls work; the
  regression net does not yet hold them.
- **Remediation:** add eight assertions in the bounded remediation.

### `H8-S1REV-F-004` — forbidden-import guards depend on a clean interpreter · **Medium** · pre-existing

- Full analysis in §11. Disposition `PRE-EXISTING TEST-ISOLATION DEFECT`; **not introduced by S1**.
- **Containment:** the source-token scan (the primary control) is order-independent and passes
  everywhere; the `sys.modules` backstop is unreliable in the integrated session and would not
  distinguish a dynamic forbidden import from the existing noise.
- **Remediation:** baseline-and-delta assertion instead of absolute absence. Bounded, test-only.

### `H8-S1REV-F-005` — a flagged publication-style claim was not corrected · **Low**

- `H8_LITERATURE_CORRECTION_PLAN.md` §3 flagged `docs/paper/FleetSafe_VLN_Paper_Draft.md:15`
  — *"VLNVerse and VLNTube **have established** strong simulation pipelines"* — because "established"
  implies published standing VLNTube does not have. Line 28 and the reference list were corrected;
  **line 15 was not**.
- **Remediation:** apply the wording the plan already specifies.

### `H8-S1REV-F-006` — commit identity differs from the documented default · **Low / informational**

- The S1 commit is authored `Frank Asante Van Laarhoven <F.Van-Laarhoven2@newcastle.ac.uk>`, whereas
  the documented default identity is `frankleroyvan@gmail.com`. Both name the same person and no
  third-party, tool or vendor attribution appears anywhere; there are no trailers.
- **Raised for the author's decision only.** Not remediated here — rewriting authorship would require
  amending a commit, which this gate forbids.

### `H8-S1REV-F-007` — 323 pre-existing ruff errors in non-S1 `h8_*` scripts · **Low** · pre-existing

- `ruff check scripts/gnm/h8_*.py` reports 323 errors, concentrated in `h8_track_b_*`,
  `h8_map_extension_enumerate.py`, `h8_loss_ablation.py`, `h8_action_probe.py`.
  **Zero are in S1 files** — S1 files and the older `h8_evidence_*` / `h8_trust_envelope` modules all
  pass. Recorded so that "ruff passes" is not over-claimed at repository scope.

## 14. Control verdicts

| Control | Verdict |
| --- | --- |
| Alignment procedure | **`PASS`** |
| 25 ms provisional tolerance | **`PROVISIONALLY JUSTIFIED`** |
| Schema rejection controls | **`PASS`** |
| Goal substitution prevention | **`PASS`** |
| Controller / checkpoint identity | **`PASS`** |
| Builder fail-closed / no-output boundary | **`PASS`** |
| Metric `NOT_COMPUTED` policy | **`PASS`** |
| Regression isolation | **`PASS WITH DOCUMENTED LIMITATIONS`** |
| Literature corrections | **`PASS WITH MINOR FINDINGS`** |
| **Overall H8-S1 independent review** | **`PASS WITH DOCUMENTED LIMITATIONS`** |

No Critical finding. No High finding. Two Medium (F-001, F-004), four Low.

## 15. Session A eligibility

**Technical eligibility:** all technical preconditions are met — alignment independently verified,
25 ms held as provisional only, goal substitution blocked, controller/checkpoint identity verified,
builder produces zero output across 20 paths, historical records rejected, path metrics
`NOT_COMPUTED` without navmesh, both regression failures classified and bounded, no unresolved
Critical or High finding.

**Governance preconditions:**

| Precondition | Status |
| --- | --- |
| Professor Bo Wei's written approval of τ = 0.50 m | **ABSENT** — no approval record exists in the repository |
| Free storage ≥ 100 GB | **SATISFIED** — 262 GB available (H8-S at 1280×720 estimated 50–110 GB) |
| Bounded remediation of F-001, F-003, F-004 | **OUTSTANDING** |

**Final disposition: `NOT ELIGIBLE`** — solely because supervisor approval of τ is absent and the
bounded remediation is outstanding. Technical eligibility is reported separately above and is
satisfied. Levels 3–5 remain unproven; hospital capture remains blocked.

## 16. Recommendation

1. **Bounded regression remediation** (test-only, no implementation change): propagate alignment
   reason codes to report level (F-001); add the eight missing reason-code assertions (F-003);
   convert the forbidden-import `sys.modules` guards to a baseline-and-delta assertion (F-004);
   apply the line-15 wording already specified in the correction plan (F-005).
2. **Supervisor approval** of τ = 0.50 m, in writing, recorded in the repository.
3. Storage is already confirmed; re-check immediately before Session A.
4. **Then** authorise Session A map extension.
