# H8 Metric Specification v2

Locked definitions for the hospital experiment. Every formula is transcribed from the primary source
named against it (see `../../gnm_hospital_dataset_audit_20260722T000354Z/literature/metric_definitions.md`).

**Universal rule: no metric may be computed when its required ground truth is unavailable.** A metric
with missing inputs is reported as `NOT_COMPUTED` with the missing input named. It is never
approximated, defaulted, or silently omitted from a table.

**Universal threshold:** `tau = 0.50 m` primary, pre-registered. Sensitivity at 0.25 / 0.50 / 0.75 /
1.00 m. Track A legacy retains `tau = 3.0 m` and is never pooled with hospital figures.

---

## 1. SR_0.50 — Success Rate

- **Formula:** `SR = (1/N) * sum_i S_i`, where `S_i = 1` iff, at the moment the agent emits its stop
  action: `d(p_final, g) <= 0.50 m` AND `|v_linear| <= 0.05 m/s` sustained `>= 1.0 s`.
- **Units:** dimensionless fraction, reported as %.
- **Required inputs:** terminal pose at the stop action; goal pose; `tau`; linear speed series;
  explicit stop event.
- **Missing-data behaviour:** no stop event emitted → `S_i = 0` (Anderson et al. Rec. 1: the episode is
  *unsuccessful*, not excluded). Missing goal or `tau` → `NOT_COMPUTED` for the whole metric.
- **Failure revealed:** the agent does not finish at the goal, or cannot commit to stopping.
- **Status:** standard (Anderson et al. 2018), with a project-specific speed-and-dwell clause added.
- **Note:** evaluation is at the stop action, **not** at a favourable earlier time.

## 2. OSR_0.50 — Oracle Success Rate

- **Formula:** `OSR = (1/N) * sum_i 1[ min_t d(p_t, g) <= 0.50 ]`.
- **Required inputs:** full pose sequence; goal pose; `tau`.
- **Missing-data behaviour:** missing goal → `NOT_COMPUTED`.
- **Failure revealed:** the agent reached the goal region but failed to stop there.
- **Invariant:** `OSR >= SR` always. A violation is a computation bug, not a result.
- **Status:** standard.

## 3. SR_OSR_GAP_0.50

- **Formula:** `GAP = OSR_0.50 - SR_0.50`.
- **Required inputs:** both of the above.
- **Failure revealed:** **stopping failure isolated from navigation failure. This is the primary RQ1
  statistic** — a large gap means the policy can get there but cannot stop.
- **Status:** standard, and the headline number for Track A's research question.

## 4. NE — Navigation Error

- **Formula:** `NE = d(p_final, g)`, geodesic where a navmesh exists, otherwise Euclidean **with the
  distance type declared in the results table**.
- **Units:** metres.
- **Required inputs:** terminal pose; goal pose; distance function.
- **Missing-data behaviour:** missing goal → `NOT_COMPUTED`.
- **Failure revealed:** how badly the stop was placed.
- **Status:** standard.

## 5. TL — Trajectory Length

- **Formula:** `TL = sum_t || p_t - p_{t-1} ||`.
- **Units:** metres.
- **Required inputs:** pose sequence only.
- **Failure revealed:** excess wandering; degenerate non-motion.
- **Status:** standard. **Computable on the historical corpus today** — derived values matched declared
  values to 0.0000 m across 154 episodes.

## 6. SPL — Success weighted by Path Length

- **Formula:** `SPL = (1/N) * sum_i S_i * l_i / max(p_i, l_i)` (Anderson et al. 2018).
- **Required inputs:** binary success `S_i`; **geodesic** shortest-path length `l_i` from a navmesh;
  executed path length `p_i`.
- **Missing-data behaviour:** `navmesh_version` absent or `reference_path.source = UNAVAILABLE` →
  `NOT_COMPUTED`. **Euclidean distance must not be substituted for the geodesic.**
- **Failure revealed:** reaches the goal by a wasteful route.
- **Status:** standard.

## 7. nDTW

- **Formula:** `nDTW = exp( -DTW(P, R) / (|R| * d_th) )` (Ilharco et al. 2019).
- **Required inputs:** ordered **oracle** reference path `R`; agent path `P`; pointwise distance
  function; `d_th`; `|R|`.
- **Locked parameter:** `d_th = 0.50 m`, matching `tau`. **Declared here and never varied per result.**
  (The 3 m value in the source paper is Matterport3D-specific and is not transferable to a hospital
  lobby of a few metres extent.)
- **Missing-data behaviour:** no oracle path → `NOT_COMPUTED`. The commanded waypoint list is **not**
  an oracle and must not be used as `R`.
- **Failure revealed:** reaches the goal by a path that ignores the intended route.
- **Caution:** the score scales with reference sampling density, so `|R|` sampling must be fixed and
  declared once for the whole dataset.
- **Status:** standard.

## 8. SDTW

- **Formula:** `SDTW = SR * nDTW`.
- **Required inputs:** everything SR needs plus everything nDTW needs.
- **Missing-data behaviour:** either input missing → `NOT_COMPUTED`.
- **Failure revealed:** path fidelity conditioned on actually succeeding.
- **Status:** standard.

## 9. CLS — Coverage weighted by Length Score

- **Formula:** `CLS = PC * LS` (Jain et al. 2019), where `PC` is path coverage of the reference
  (order-invariant) and `LS` the length score.
- **Required inputs:** oracle reference path; geodesic `d`; `d_th`; `PL(R)`; `PL(P)`.
- **Locked parameter:** `d_th = 0.50 m` as above.
- **Missing-data behaviour:** no oracle path or no geodesic → `NOT_COMPUTED`.
- **Failure revealed:** covers only part of the intended route, or shortcuts it.
- **Status:** standard.

## 10. Collision count

- **Formula:** `C_i = |{ contact events in episode i }|`.
- **Units:** count.
- **Required inputs:** contact telemetry with a **declared detector scope**.
- **Missing-data behaviour:** `contact_telemetry_available = false` → `NOT_COMPUTED` for that episode
  and the episode is excluded from the CR denominator, with the exclusion reported.
- **Failure revealed:** severity of contact, not merely incidence.
- **Status:** project-specific. Historical detector was `physx_contact_report_base_link` — **chassis
  only**, which may miss contacts on other links; v2 requires the scope to be declared and widened.

## 11. CR — Collision Rate

- **Formula:** `CR = (episodes with C_i > 0) / N`. Report the step-normalised variant
  `CR_step = (colliding steps) / (total steps)` alongside.
- **Missing-data behaviour:** as above; the denominator must state how many episodes were excluded.
- **Failure revealed:** the agent hits the environment.
- **Status:** adapted. **Not comparable to published CR** — GNM/ViNT/NoMaD do not specify their
  collision detector.

## 12. Completion time

- **Formula:** `T_i = t_end - t_start` in **simulation time**, declared as such.
- **Units:** seconds.
- **Required inputs:** episode start/end in a single declared clock.
- **Missing-data behaviour:** clock ambiguity unresolved → `NOT_COMPUTED`.
- **Failure revealed:** the agent is slow.
- **Status:** standard. Wall time is reported separately and never mixed — wall exceeded sim by >3× in
  74 % of historical episodes.

## 13. Stop timing error

- **Formula:** `E_stop = t_stop - t_first_entry`, where `t_first_entry` is the first time
  `d(p_t, g) <= tau`. Negative = stopped early (before entering); positive = stopped late.
- **Units:** seconds. Report the distance-domain analogue too.
- **Required inputs:** verified goal-region crossing; explicit stop event; `tau`.
- **Missing-data behaviour:** never entered the region → `NO_ENTRY` (distinct from a numeric zero);
  no stop event → `NO_STOP`.
- **Failure revealed:** stopping too early or too late — the core RQ1 failure mode.
- **Status:** project-specific.

## 14. Overshoot distance

- **Formula:** `O = ` path length travelled after `t_first_entry`.
- **Units:** metres.
- **Required inputs:** goal region entry time; pose sequence after entry.
- **Missing-data behaviour:** `NO_ENTRY` as above.
- **Failure revealed:** failure to arrest motion in time.
- **Status:** project-specific.

## 15. Pose-aligned success (secondary)

- **Formula:** `S_pose = 1[ d <= 0.50 AND |yaw_err| <= 30 deg AND stationary >= 1.0 s ]`.
- **Required inputs:** everything SR needs, plus goal yaw and terminal yaw.
- **Missing-data behaviour:** goal yaw absent → `NOT_COMPUTED`.
- **Failure revealed:** arrives at the right place facing the wrong way — a genuine image-goal failure
  that position-only SR cannot see.
- **Status:** project-specific. **Reported alongside the primary SR, never replacing it.**

## 16. Inference latency

- **Formula:** `L = t_action - t_observation`, per inference. Report mean, p95 and max.
- **Units:** milliseconds.
- **Required inputs:** timestamped observation and action events.
- **Missing-data behaviour:** absent timestamps → `NOT_COMPUTED`.
- **Failure revealed:** the policy is too slow to close the loop safely.
- **Status:** standard. **Must declare shadow vs closed-loop mode** — the historical figures
  (mean 8.1 ms, max 14.5 ms over 51 episodes) are *shadow-mode* and are not deployed-controller latency.

## 17. Command latency

- **Formula:** `L_cmd = t_cmd_published - t_action_decided`.
- **Units:** milliseconds.
- **Required inputs:** command publish timestamps and decision timestamps in **one** clock.
- **Missing-data behaviour:** wall↔sim alignment unverified → `NOT_COMPUTED`.
- **Failure revealed:** actuation lag between decision and motion.
- **Status:** standard.

## 18. Provenance completeness

- **Formula:** `PC = (episodes with a complete v2 manifest set) / N`.
- **Required inputs:** the §10 per-episode artefacts.
- **Failure revealed:** results cannot be traced back to a verified capture.
- **Status:** project-specific, and a **gating** metric: `PC < 1.0` blocks dataset promotion.

---

## Reporting rules

1. Every table states its `tau` and its distance type (geodesic vs Euclidean).
2. `NOT_COMPUTED` appears explicitly; blanks are prohibited.
3. Primary result is `tau = 0.50 m`. Sensitivity rows are labelled as such.
4. Hospital and Track A (`tau = 3.0 m`) figures never appear in the same column without both
   thresholds shown.
5. Shadow-mode and closed-loop latencies are never pooled.
6. Report seeds, and confidence intervals where N permits — three of the ten reviewed baseline papers
   report none, which is a gap we should not reproduce.
