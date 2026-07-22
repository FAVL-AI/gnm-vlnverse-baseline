# H8-S1R — Bounded Diagnostic and Test-Isolation Remediation

## Scope

H8-S1R was restricted to:

1. alignment diagnostic propagation;
2. active reason-code regression coverage;
3. forbidden-import test isolation;
4. correction of one active VLNTube claim.

It did not authorise Isaac Sim, Omniverse, live ROS 2, capture, dataset creation, training, inference, modification of historical evidence, pushing, or tagging.

## H8-S1REV-F-001 — Alignment diagnostic propagation

**Verdict: CLOSED**

Alignment rejection codes are now propagated from the nested alignment result into the builder’s top-level `reason_codes`.

The regression test confirms:

- exit code is exactly `3`;
- the episode is not admitted;
- nested rejection diagnostics remain available;
- nested reason codes appear in the top-level report;
- no dataset directory is created;
- zero images are written;
- zero trajectories are written;
- no split manifest is written;
- zero metrics are computed.

This change affects reporting only. Alignment acceptance and rejection semantics were not changed.

## H8-S1REV-F-003 — Active reason-code coverage

**Verdict: CLOSED**

Taxonomy totals:

- declared reason codes: 56;
- `ACTIVE_REACHABLE`: 54;
- `DEPRECATED_UNUSED`: 1;
- `DEFERRED_TO_LATER_IMPLEMENTATION`: 1;
- `RESERVED_NOT_ACTIVE`: 0.

The eight previously uncovered active codes now have deterministic tests:

- `H8_CONTROLLER_MODE_MISSING`;
- `H8_GOAL_CAMERA_MISMATCH`;
- `H8_GOAL_POSE_MISMATCH`;
- `H8_GOAL_RESOLUTION_MISMATCH`;
- `H8_MANIFEST_SCHEMA_INVALID`;
- `H8_MANIFEST_VERSION_UNSUPPORTED`;
- `H8_SCENE_IDENTITY_FAILED`;
- `H8_SUCCESS_CRITERION_NOT_PREREGISTERED`.

Active coverage is **54/54, or 100%**.

`H8_METRIC_INPUT_UNAVAILABLE` is `DEPRECATED_UNUSED` because the specific `NOT_COMPUTED_*` states identify missing metric evidence more precisely.

`H8_CONTACT_TELEMETRY_ZERO_WITHOUT_DETECTOR` is `DEFERRED_TO_LATER_IMPLEMENTATION`. The current control uses `H8_CONTACT_TELEMETRY_UNAVAILABLE` and `NOT_COMPUTED_MISSING_CONTACTS`.

## H8-S1REV-F-004 — Forbidden-import isolation

**Verdict: CLOSED**

The static source-token scan remains the primary order-independent control.

The runtime backstop now imports each target module in an isolated subprocess and inspects only the modules introduced by that target.

The tests confirm:

- clean S1 modules pass;
- literal forbidden imports fail the static scan;
- dynamic forbidden imports fail the runtime backstop;
- unrelated preloaded `torch` and `rclpy` do not fail clean targets;
- genuine target imports of `torch` or `rclpy` fail;
- repeated runs are deterministic;
- temporary stub modules are removed;
- genuine pre-existing modules are preserved.

## H8-S1REV-F-005 — VLNTube wording

**Verdict: CLOSED**

The active paper now distinguishes:

- VLNVerse as a published simulation framework;
- VLNTube as a vendored software data-generation dependency.

VLNTube remains identified by its repository, MIT licence, upstream revision and local content digest. It is not represented as a peer-reviewed publication.

## Verification

- Alignment-propagation test: 1 passed.
- New active reason-code tests: 8 passed.
- Taxonomy consistency tests: 5 passed.
- Combined schema and taxonomy tests: 61 passed.
- Import-isolation tests: 20 passed.
- Matching H8 pytest selection: 604 passed, 0 failed, 2387 deselected.
- Python compilation: passed.
- Ruff on bounded files: passed.
- `git diff --check`: passed.

The matching H8 selection is not the complete repository test suite.

## Evidence boundary

H8-S1R establishes:

- top-level alignment diagnostic propagation;
- complete active reason-code regression coverage;
- order-independent forbidden-import testing;
- correct active VLNTube software wording.

H8-S1R does not establish:

- final alignment tolerance;
- Isaac runtime validity;
- navmap-to-bringup transform validity;
- hospital scene digest;
- versioned navmesh validity;
- formal hospital dataset validity;
- model validity;
- training readiness;
- data-capture permission.

Levels 3–5 remain unproven.

## Overall verdict

**PASS**

All four authorised findings are closed.

## Session A status

Technical controls are ready for an independent closure review.

Overall Session A eligibility remains **NOT ELIGIBLE** until:

1. H8-S1R receives independent closure verification;
2. Professor Bo Wei approves the primary hospital success radius `τ = 0.50 m` in writing;
3. free storage is rechecked immediately before Session A and remains at least 100 GB;
4. Session A is explicitly limited to map extension, scene-digest generation, navmap-frame reconciliation and versioned navmesh creation;
5. no dataset route collection occurs during Session A.

Hospital dataset capture remains blocked.
