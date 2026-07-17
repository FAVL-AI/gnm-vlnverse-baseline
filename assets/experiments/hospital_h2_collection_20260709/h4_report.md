# H4 route-family-diversity demonstration set — collection report

Front-camera (Yahboom RGB, Isaac Sim) scripted-expert demonstrations over
route-family-diverse navgen routes. Recording chain: 24/24 episodes rc0,
`ALL_H4REC_DONE`, disk guard never fired (chain-final 94 GB free). Validator:
`VALIDATOR_OK`. Training remains NOT started; this report is the review gate.

## 1. Quality table
`h4_quality_table.csv` (24 rows, 27 columns incl. mandated disk/process-control
fields). Every episode: `return_code=0`, `route_completed=True`,
`total_contacts=0` (measured, PhysX base_link contact report),
`artifact_integrity=complete`, `front_rgb_verified=True` (640×480, consistent),
`recording_integrity=ok`, `process_control_method=timeout_wrapper_per_episode_rc_capture`,
`kill_method_if_any=none`, `runtime_degradation_event=none`, bag 1.7–1.8 GB.

## 2. Validator output (`h4_counts.json`, `h4_validator_report.json`)
- all_recording_integrity_ok: true
- all_artifact_complete: true
- all_contacts_zero: true
- all_rc_zero: true
- Verdict: **VALIDATOR_OK**

## 3. Imitation-eligible count
**16** — the 8 train families × 2 variants (000, 001, 002, 005, 007, 009, 011,
013). Firewall: only `split=train` is imitation-eligible. This is +6 demos and
+3 families over the H2.4/H3-clean incumbent (10 demos / 5 families).

## 4. Held-out test coverage
**3 novel families / 6 episodes** (008, 012, 016 × 2). Preserved earlier
held-out families (uturn, chain, ft_L) remain held out per the approval table,
so cross-family generalization can be measured against both new and prior
held-out families. Validation split: 2 families / 2 episodes (015, 017).

## 5. Exclusions and degradation events
- **Zero exclusions in the clean H4 chain** — no rc124, no partial recordings,
  no stalls, guard never fired.
- **9 re-records** (`re_recorded_from=superseded_paused_or_exhausted_attempt`):
  families 000/001/002/005 (both variants) + 007_a. These trace to the already
  logged `disk_exhaustion_during_h4_recording` and `self_match_process_kill`
  events (see `runtime_degradation_events.json`); their earlier bags were
  deleted at the point of failure and re-recorded clean. Trajectory logs and
  ledger for the deleted attempts are retained.
- **Known scope limitations (not defects):** (a) goal image is the fixed
  placeholder `h2_weave_J` for all episodes — the imitation signal is the
  demonstrated trajectory + front-camera stream, NOT goal-image conditioning; a
  goal-conditioned evaluation needs per-route goal frames. (b) demonstrations
  are scripted-expert (holonomic executor), not a learned policy — the intended
  imitation setup. (c) 16 train demos is modest for family transfer; the
  H3-clean **tie** (per-family volume did not transfer) is the standing prior
  that H4 is designed to test via family diversity.

## 6. Binary recommendation
**YES — H4 training may be CONSIDERED.** The evidence gate is cleared: 16 clean,
contact-free, integrity-verified imitation-eligible demonstrations across 8
route families, with 2 validation and 6 held-out-test episodes over 3 novel
families, firewall intact. This authorizes *consideration* only; it is a
diversity-hypothesis test (not a guaranteed gain over the tied incumbent), and
actual training start remains Frank's go/hold decision.
