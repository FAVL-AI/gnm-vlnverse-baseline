# H2.2 Hard-Stop Report (2026-07-10)

PASS route count after v3 redesign cycle: 1 (J only) < required 4.
Per the registered hard-stop rule: H2.2 data collection is PAUSED and
the mecanum/yaw-authority execution-layer fix is elevated to the
critical path, together with a measured hospital occupancy map.

Failure labels in force: follower_turn_radius_exceeds_waypoint_curvature,
sustained_contact, mid_route_geometry_defect,
incorrect_hand_authored_map, yaw_authority_execution_bottleneck.

Professor-facing conclusion: H2.2 showed that the remaining bottleneck
is not simply data volume. Three independent collection strategies —
learned-policy rollouts, stop-and-turn scripted execution, and
arc-following scripted execution — all exposed the same execution-layer
limitation: the platform cannot reliably track curved routes under the
current mecanum/yaw model. In parallel, repeated K/M failures revealed
an incorrect hand-authored obstacle map. Therefore, further data
collection is paused until the execution model and measured occupancy
map are corrected.

Research value: this is not a failed experiment. This is a controlled
diagnosis showing that data collection is blocked by execution-layer
fidelity and map correctness.

Next approval gate (H2.3): can the robot track scripted reference
routes using a measured yaw model and a measured occupancy map?
The H2.2 corpus is NOT sufficient for H3.

## H2.3 outcome (2026-07-10, strict pre-registration honored)

H2.3 produced a strict Outcome B. The measured-cost iteration improved
control validation substantially, from 2/5 to 4/5 completed tasks, with
the remaining chain task stopping one waypoint short and no contacts.
However, the pre-registered pass rule required all multi-turn tasks to
complete. Therefore, H2.3 does not pass, H2.4 remains closed, and
H3-clean remains denied. The result confirms that the critical
bottleneck is the yaw/mecanum execution layer rather than data volume
or logging reliability.

Near-boundary finding: measured-cost budgets improved controller
validation from 2/5 to 4/5 completed tasks. The remaining failure
reached waypoint 5/6 with 0 contacts, no orbit, and no grind. This
shows the repair direction is correct, but still insufficient under
the pre-registered gate.

Scientific interpretation: Follower v3.1 plus measured-cost budgets
makes simple and moderate multi-turn routes executable, but routes
with many point turns remain marginal because each deadband-forced
correction cycle costs approximately 8-12 seconds. These costs
compound with route complexity. Therefore, the bottleneck is no longer
random route design; it is the platform's yaw/execution-layer
limitation.

Next branch: H2.4 is not next. H2.3-ExecFix (measured mecanum/yaw
repair) is next. Acceptance gate: (1) commanded-vs-actual yaw improves
materially; (2) minimum reliable yaw rate increases; (3) turn radius
decreases or point-turn reliability improves; (4) straight, 90-degree,
S-curve, U-turn, and chain validation all complete; (5) contacts
within threshold; (6) no orbiting or sustained grind; (7) RouteFollower
can execute at least 4 route families after decider approval. No new
hospital demonstrations until this repair passes control validation.
