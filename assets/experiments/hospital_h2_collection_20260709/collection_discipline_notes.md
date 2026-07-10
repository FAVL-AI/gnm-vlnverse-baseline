# H2 collection discipline (canonical wording)

We isolate failed recordings, label them explicitly, exclude them from
training/evaluation, and re-record when needed; we do not silently hide
or reuse corrupted episodes.

Professor/reviewer explanation: The hospital data collection process
recorded both successful and failed attempts. Failed or partial
recordings were not discarded silently; they were logged as degradation
events, marked ineligible for training/evaluation, and re-recorded when
needed. This gives us a transparent dataset construction process rather
than a curated-only success set.

Pipeline hardening note (methodology wording): We hardened the episode
collection pipeline after a suspend/resume stall. Instead of killing
jobs by process-name patterns, each episode is now executed inside a
bounded timeout wrapper with explicit return-code logging. This makes
failures auditable: clean episodes, timeouts, crashes, and partial
recordings are separated in the dataset manifest rather than silently
mixed into training data.

## Hygiene-barrier rule (permanent, locked 2026-07-09)

Every automated Isaac/ROS2 episode must end with a hygiene barrier:
1. terminate the episode process tree, not only the parent PID
2. confirm no orphan ros2 bag record processes remain
3. confirm stale DDS/shared-memory segments are cleared
4. only then start the next episode

Evidence wording: The repeated rc124 failures were traced to orphan
recorder child processes rather than the navigation policy. Parent
timeout termination left ros2 bag recorder children alive as DDS
participants, which accumulated stale shared-memory state and caused
later episodes to wedge. We corrected this with a per-episode hygiene
barrier: terminate the full process tree, verify zero recorders, purge
stale DDS/shared-memory segments, and then launch the next bounded
episode.

## Two-condition cleanliness rule (locked 2026-07-10)

An episode is clean only if both conditions pass:
1. process result is clean, usually rc0
2. artifact completeness is clean: finalized rosbag, metadata,
   trajectory log, frames, commands, stop reason, and checksums present

Three integrity layers captured by the quality table:
1. Process integrity: return_code, timeout_flag, chain_killed
2. Artifact integrity: finalized bag, metadata, frames, trajectory,
   command labels, stop reason
3. Dataset eligibility: training_eligible, evaluation_eligible,
   imitation_eligible

H2 report explanation (exact): We found that a clean process return
code is not enough to declare an episode usable. One episode returned
rc0, but the rosbag recorder child had not finalized the bag. We
therefore require artifact-completeness checks in addition to
return-code checks. Episodes with incomplete artifacts are retained in
the attempt ledger but marked ineligible for training and evaluation.

## H2.1 verdict and H2.2 methodology (locked 2026-07-10)

H2.1 showed that recording reliability alone is not enough. A route can
record cleanly and still be scientifically unusable because the geometry
is defective, the route contains mid-path contact, or the learned policy
cannot act as an expert demonstrator for unseen goals.

Research lesson: Policy rollouts are evaluation evidence, not expert
demonstration data, unless the policy is already known to be competent
on that route family.

H2.2 changes: (1) endpoint-only probes are replaced by FULL-ROUTE
scripted prechecks — the complete reference path is executed with
contact monitoring; sustained brushing or mid-route grind rejects the
route. (2) Demonstrations are collected by a scripted reference-path
follower (waypoint executor); learned policies are used only for
evaluation rollouts.

## Follower-v2 verdict and research finding (locked 2026-07-10)

Follower-v2 prechecks produced one demonstration-ready route and four
diagnostic rejects. J_v2 passed as a contact-free near-goal execution.
H/I failed because the route curvature exceeded the platform's
practical turn radius. K/M failed because longer execution exposed true
mid-route geometry defects. Therefore, H2.2 continues with one approved
demonstration route and a targeted redesign cycle for the remaining
four routes.

Research finding: The execution layer is now a measured bottleneck:
demonstration collection is not limited only by dataset scripting, but
by whether the reference-path executor can track routes under the
platform's yaw-authority constraints.

HARD STOP CONDITION: if the redesign cycle produces fewer than 4 PASS
routes total (including J_v2), pause H2.2 data collection and elevate
the mecanum/yaw-authority execution-layer fix to the critical path.

## H2.3 locked wordings (2026-07-10)

Yaw result (exact): Yaw calibration showed a severe commanded-vs-realised
yaw gap. The maximum reliable measured yaw rate was approximately
0.190 rad/s at a commanded 1.0 rad/s. While moving, commanded yaw
produced only ~0.9-1.6% realised yaw across tested forward speeds.
Therefore, curved-while-moving route execution is infeasible on the
current platform configuration; feasible scripted execution must use
stop-and-turn behaviour with explicit turn-time budgets.

Map result (exact): The measured occupancy map confirms that the
hand-authored map was incomplete. The K/M grind zone and two newly
discovered near-misses were detected by physics-derived occupancy but
missed by the semantic polygons.

Decider status (exact): The decider reproduced 10/13 failure-corpus
diagnoses. The three disagreements were inspected: two were
replay-design isolation errors, and one was a conservative rejection of
a route segment the robot did not physically reach. Therefore, the
decider is replay-tested and conservative, but final validation is
pending corrected isolation runs and control-validation results.

Decider validation requirements (all six must hold before "validated"):
corrected isolation replay; H_v3 conservative rejection accepted-as-
intended or documented as known false reject; J remains
PASS_DEMONSTRATION; artifact-incomplete case remains rejected; policy
rollouts on unseen goals remain evaluation-only; control-validation
tasks pass under RouteFollower v3.

Paper-level conclusion: The failed hospital data-collection attempts
were not random failures. They exposed two measurable prerequisites for
trustworthy navigation data generation: execution feasibility under the
robot's true yaw dynamics, and map feasibility under measured collision
geometry. H2.3 turns those prerequisites into an explicit
execution-feasibility decider.

## Controller update wording (locked, for the H2.3 report)

Follower v3 failed turn-heavy validation tasks by budget starvation,
not collision or orbiting. Telemetry showed that small steering
corrections fell inside the measured yaw deadband. Follower v3.1
therefore uses deadband-aware bang-bang steering: full-command point
turns when misaligned, no weak yaw corrections during straight driving.

v3.1 pass rule (all nine): straight completes; 90-degree turn
completes; S-curve completes; U-turn completes; waypoint chain
completes; contacts within threshold; no orbiting; no sustained grind;
completion within turn-time-sized budget.
