"""H8-M Step A — route/zone DESIGN generator (PLANNING ONLY, no Isaac, no rendering).

Emits the H8-M candidate route/zone design from PROPOSED (hypothesized) coordinates. Computes
expected robot-frame actions + angular separations deterministically from the coordinates (no
hand-typed numbers). Nothing here is validated: every distinct-room zone is unproven because the
H8-S drivable envelope was a single straight alcove with no junction, and the reception/waiting/
side-corridor/junction interiors have NOT been render- or drive-validated. This script performs
NO recording, NO training, NO Isaac, and makes NO navigation claim.

Safety: the `CL_BOUND_XY = 6.0` watchdog is ABSOLUTE isaac-world position. Any pose with
|x| > 6 or |y| > 6 estops immediately, so a zone must lie entirely within +/-6 m OR it is
DEFERRED (a reviewed watchdog change is a separate task, NOT done here). Coordinates are
isaac-world (=bringup); spawn directly, no navmap offset.

Outputs -> assets/experiments/hospital_h8_m_route_zone_design/:
  h8m_zone_candidates.json, h8m_route_family_manifest.json, h8m_split_plan.json,
  h8m_design_risk_register.md, h8m_route_zone_design_report.md
Run with base python (numpy).
"""
import json, math
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "assets/experiments/hospital_h8_m_route_zone_design"
CL_BOUND_XY = 6.0
MIN_ANG_SEP_DIVERGENT = 30.0   # deg — a "true angular branch" needs at least this
# a genuine angular branch requires BOTH >=30 deg separation AND a divergent-branch family
# (a junction/fork/different-goal decision), not merely two angularly-offset objects in one room.
DIVERGENT_FAMILIES = {"branch_choice_t_junction", "shared_corridor_fork",
                      "same_start_different_goal"}
SPLIT_TARGET = {"train": 12, "val": 4, "test": 6}


def rf_action(o_d, goal, yaw):
    """World o_d->goal displacement rotated into the robot frame (yaw=approach heading)."""
    dx, dy = goal[0] - o_d[0], goal[1] - o_d[1]
    c, s = math.cos(yaw), math.sin(yaw)
    return (c * dx + s * dy, -s * dx + c * dy)


def ang(a):
    return math.degrees(math.atan2(a[1], a[0]))


def ang_sep(a, b):
    return math.degrees(math.atan2(abs(a[0] * b[1] - a[1] * b[0]), a[0] * b[0] + a[1] * b[1]))


def in_envelope(*pts):
    return all(abs(p[0]) <= CL_BOUND_XY and abs(p[1]) <= CL_BOUND_XY for p in pts)


# ── candidate zones (PROPOSED coordinates; isaac-world; yaw = approach heading) ──
# validated: DRIVE_VALIDATED (H8-S) | NEEDS_RENDER_VALIDATION | NEEDS_DRIVE_VALIDATION | DEFERRED
# distinctness/duplicate_risk are ESTIMATES pending the Step-B CLIP/DINO embedding check.
ZONES = [
    dict(zone_id="h8m_recep_junction", area="corridor junction (reception hall)",
         family="branch_choice_t_junction", split_role="test",
         spawn=[0.0, 0.0, 0.0], o_d=[0.6, 0.0], goalA=[2.5, 2.2], goalB=[2.5, -2.2],
         feasibility="NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION",
         distinctness="high", duplicate_risk="low",
         note="PRIMARY true angular branch (left vs right wing). Existence of a drivable "
              "junction within +/-6 m is UNPROVEN — highest-risk, most important zone."),
    dict(zone_id="h8m_recep_fork", area="shared-corridor fork (reception)",
         family="shared_corridor_fork", split_role="test",
         spawn=[0.0, 0.0, 0.0], o_d=[-0.5, 0.0], goalA=[1.5, 1.8], goalB=[1.5, -1.8],
         feasibility="NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION",
         distinctness="moderate", duplicate_risk="moderate",
         note="Second divergent family; may be the same physical junction as recep_junction "
              "(dedupe at render time)."),
    dict(zone_id="h8m_recep_desk_multiobj", area="reception desk (multi-object)",
         family="same_room_different_object", split_role="train",
         spawn=[0.5, 1.0, 0.0], o_d=[0.8, 0.5], goalA=[0.8, 2.0], goalB=[2.2, 0.8],
         feasibility="NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION",
         distinctness="moderate", duplicate_risk="moderate",
         note="Object-level grounding (desk vs signage/plant) within one room."),
    dict(zone_id="h8m_side_corridor", area="side corridor",
         family="same_start_different_goal", split_role="val",
         spawn=[2.0, -2.0, 1.5708], o_d=[2.0, -1.5], goalA=[2.0, 1.5], goalB=[4.0, -1.0],
         feasibility="NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION",
         distinctness="moderate", duplicate_risk="low",
         note="Straight-ahead vs into-a-room from one start; north-facing approach (yaw=pi/2)."),
    dict(zone_id="h8m_waiting_seating", area="waiting area (seating + water cooler)",
         family="same_room_different_object", split_role="train",
         spawn=[1.0, 0.1, 3.1416], o_d=[0.5, 0.1], goalA=[-1.5, 0.1], goalB=[-1.0, 1.0],
         feasibility="NEEDS_RENDER_VALIDATION",
         distinctness="low", duplicate_risk="high",
         note="West-facing seating end RENDERED in H8 visual search (searchW1/W2) but it is the "
              "SAME alcove as the vending views — LOW distinctness, must pass the embedding gate "
              "or be dropped; not a distinct room."),
    dict(zone_id="h8m_lobby_vending_nearfar", area="lobby vending alcove (H8-S)",
         family="near_far_stop_conditioning", split_role="train",
         spawn=[-1.0, -0.2, 0.0], o_d=[-1.0, -0.2], goalA=[-0.4, -0.2], goalB=[0.6, -0.2],
         feasibility="DRIVE_VALIDATED",
         distinctness="low", duplicate_risk="high",
         note="Carried forward from H8-S (0 collisions). SECONDARY distance/stop axis only "
              "(collinear, 0 deg). Same alcove as east/waiting."),
    dict(zone_id="h8m_east_vending_nearfar", area="east vending alcove (H8-S)",
         family="near_far_stop_conditioning", split_role="val",
         spawn=[1.4, 0.1, 0.0], o_d=[1.4, 0.1], goalA=[1.7, 0.1], goalB=[2.1, 0.1],
         feasibility="DRIVE_VALIDATED",
         distinctness="low", duplicate_risk="high",
         note="Carried forward from H8-S (0 collisions). SECONDARY distance/stop axis only."),
    dict(zone_id="h8m_lookalike_confuser", area="visually-similar distinct corridor ends",
         family="visually_similar_distinct_location", split_role="hard_negative",
         spawn=[3.0, 0.0, 0.0], o_d=[3.0, 0.0], goalA=[3.8, 0.6], goalB=[3.8, -0.6],
         feasibility="NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION",
         distinctness="low", duplicate_risk="high",
         note="Adversarial look-alike pair — LOW distinctness BY DESIGN; only valid as a "
              "labelled hard-negative if the embedding gate separates the two, never as a "
              "distinct held-out example."),
    dict(zone_id="h8m_hardneg_crossscene", area="cross-scene mismatch goal",
         family="hard_negative_mismatch", split_role="hard_negative",
         spawn=None, o_d=None, goalA=None, goalB=None,
         feasibility="DESIGN_ONLY",
         distinctness="n/a", duplicate_risk="n/a",
         note="Cross-scene wrong goal (placeholder assets/experiments/goals/h2_weave_J) paired "
              "to any decision frame for the mismatched-goal ablation. No new coordinates."),
]


def enrich(z):
    z = dict(z)
    if z["o_d"] is None:
        z.update(expected_action_A=None, expected_action_B=None, expected_action_angle_A_deg=None,
                 expected_action_angle_B_deg=None, expected_action_angle_separation_deg=None,
                 is_true_angular_branch=False, within_envelope=True, coord_note="no coordinates")
        return z
    yaw = z["spawn"][2] if z["spawn"] else 0.0
    aA = rf_action(z["o_d"], z["goalA"], yaw)
    aB = rf_action(z["o_d"], z["goalB"], yaw)
    sep = ang_sep(aA, aB)
    pts = [z["o_d"], z["goalA"], z["goalB"]] + ([z["spawn"][:2]] if z["spawn"] else [])
    env = in_envelope(*pts)
    z.update(
        expected_action_A=[round(aA[0], 3), round(aA[1], 3)],
        expected_action_B=[round(aB[0], 3), round(aB[1], 3)],
        expected_action_angle_A_deg=round(ang(aA), 1),
        expected_action_angle_B_deg=round(ang(aB), 1),
        expected_action_angle_separation_deg=round(sep, 1),
        goal_pair_angularly_separated=bool(sep >= MIN_ANG_SEP_DIVERGENT),
        is_true_angular_branch=bool(sep >= MIN_ANG_SEP_DIVERGENT
                                    and z["family"] in DIVERGENT_FAMILIES),
        within_envelope=bool(env),
        coord_note=("within +/-6 m envelope" if env else
                    "OUTSIDE +/-6 m CL_BOUND_XY -> DEFERRED (no bound change)"),
        proposed_embedding_check="CLIP or DINO cosine at Step B (primary); aHash + SSIM secondary",
    )
    if not env and z["feasibility"] != "DEFERRED":
        z["feasibility"] = "DEFERRED"
    return z


ZC = [enrich(z) for z in ZONES]

# integrity: no reused decision-frame / goal / coordinate across splits (proposed coords)
def coords_of(z, k):
    return tuple(z[k]) if z[k] else None
seen, reuse = {}, []
for z in ZC:
    for k in ("o_d", "goalA", "goalB"):
        c = coords_of(z, k)
        if c is None:
            continue
        if c in seen and seen[c][1] != z["split_role"]:
            reuse.append({"coord": list(c), "zones": [seen[c][0], z["zone_id"]],
                          "roles": [seen[c][1], z["split_role"]]})
        seen[c] = (z["zone_id"], z["split_role"])

OUT.mkdir(parents=True, exist_ok=True)

# ── 1. zone candidates ───────────────────────────────────────────────────────
(OUT / "h8m_zone_candidates.json").write_text(json.dumps({
    "status": "DESIGN_ONLY", "scene": "hospital.usd",
    "coordinate_frame": "isaac-world (=bringup); spawn directly, no navmap offset",
    "safety": {"CL_BOUND_XY": CL_BOUND_XY, "unchanged": True,
               "rule": "poses must be within +/-6 m absolute; outside -> DEFERRED, not a bound change"},
    "note": "All coordinates PROPOSED/hypothesized; distinct-room zones UNVALIDATED (no render, "
            "no drive). Distinctness/duplicate_risk are ESTIMATES pending Step-B CLIP/DINO.",
    "min_angular_separation_for_true_branch_deg": MIN_ANG_SEP_DIVERGENT,
    "zones": ZC,
}, indent=2) + "\n")

# ── 2. route-family manifest ─────────────────────────────────────────────────
families = {}
for z in ZC:
    families.setdefault(z["family"], []).append(z["zone_id"])
true_angular = [z["zone_id"] for z in ZC if z.get("is_true_angular_branch")]
(OUT / "h8m_route_family_manifest.json").write_text(json.dumps({
    "status": "DESIGN_ONLY",
    "required_families": ["branch_choice_t_junction", "same_start_different_goal",
                          "shared_corridor_fork", "same_room_different_object",
                          "visually_similar_distinct_location", "near_far_stop_conditioning",
                          "hard_negative_mismatch"],
    "families": families,
    "true_angular_branch_zones": true_angular,
    "has_true_angular_branch": bool(true_angular),
    "primary_axis": "angular branch-divergence (T-junction/fork)",
    "secondary_axis": "near/far stop-conditioning (H8-S carry-forward, collinear)",
}, indent=2) + "\n")

# ── 3. split plan ────────────────────────────────────────────────────────────
roles = {"train": [], "val": [], "test": [], "hard_negative": []}
for z in ZC:
    roles[z["split_role"]].append(z["zone_id"])
counts = {r: len(v) for r, v in roles.items()}
# feasibility: only DRIVE_VALIDATED zones are usable NOW; distinct rooms are unvalidated.
validated_now = [z["zone_id"] for z in ZC if z["feasibility"] == "DRIVE_VALIDATED"]
target_met = all(counts.get(r, 0) >= SPLIT_TARGET[r] for r in SPLIT_TARGET)
(OUT / "h8m_split_plan.json").write_text(json.dumps({
    "status": "DESIGN_ONLY_DRAFT",
    "target_min_distinct_decision_frames": SPLIT_TARGET,
    "draft_split_by_zone": roles, "draft_zone_counts": counts,
    "rules": ["no reused decision frame across splits", "no reused goal image across splits",
              "no coordinate reuse across splits", "route-family balance where possible",
              "the held-out TEST split must contain >=1 true angular branch family"],
    "cross_split_coordinate_reuse": reuse,
    "coordinate_integrity_ok": bool(not reuse),
    "test_has_true_angular_branch": bool(set(roles["test"]) & set(true_angular)),
    "drive_validated_zones_now": validated_now,
    "target_scale_met_by_current_candidates": bool(target_met),
    "feasibility_verdict": "NOT_YET_FEASIBLE_AT_TARGET_SCALE",
    "feasibility_reason": (
        "Only the 2 H8-S alcove zones are drive-validated NOW, and both are collinear "
        "(secondary axis). Every distinct-room and angular-branch zone is UNVALIDATED. One "
        "decision frame per zone was drafted, so the current candidate set yields far fewer than "
        "train>=12/val>=4/test>=6 distinct frames. Reaching the target requires (a) render+drive "
        "validation of >=3-4 genuinely distinct rooms incl. a true junction, and (b) authoring "
        "multiple decision frames per validated zone. Per H8-M acceptance, collection must NOT "
        "proceed until that scale and the embedding distinctness gate are met."),
}, indent=2) + "\n")

# ── 4. risk register ─────────────────────────────────────────────────────────
rr = ["# H8-M Route/Zone Design — Risk Register (DESIGN ONLY)", "",
      "Planning only. No recording, no training, no closed-loop, no `CL_BOUND_XY` change. "
      "Risks are ranked; each has a mitigation and a gate that must clear before collection.", "",
      "| # | risk | severity | affected zones | mitigation | gate |",
      "|---|---|---|---|---|---|",
      "| 1 | A drivable T-junction/fork within +/-6 m may not exist in hospital.usd (H8-S found "
      "only one straight alcove) | **critical** | recep_junction, recep_fork | render+drive search "
      "of the reception hall; if none, the true angular family is impossible in-envelope | Step C "
      "render+drive validation; acceptance requires >=1 true angular family |",
      "| 2 | Target rooms may lie outside +/-6 m absolute (watchdog estops) | high | any distinct "
      "room | spawn-relocation INSIDE each room within its own +/-6 m; DEFER if room world-coords "
      ">6 m; never raise `CL_BOUND_XY` | envelope check (auto-DEFERRED here) |",
      "| 3 | Distinct-room zones are all UNVALIDATED (no render, no drive) | high | all NEEDS_* "
      "zones | two-stage render+drive gate (caught west_C in H8-S) | Step C recorded-mode gate |",
      "| 4 | Visual distinctness too weak (one-alcove repeat of H8-S) | high | waiting_seating, "
      "both vending, lookalike_confuser | CLIP/DINO cross-split gate; drop/merge/defer failures | "
      "Step B embedding distinctness |",
      "| 5 | Target split scale (train>=12/val>=4/test>=6) not yet reachable | high | whole split "
      "| author multiple frames per validated zone; do NOT proceed if unmet | acceptance criteria |",
      "| 6 | recep_fork duplicates recep_junction (same physical junction) | medium | recep_fork | "
      "dedupe at render time via embedding + geometry | Step B/C |",
      "| 7 | Lookalike confuser could leak as a 'distinct' example | medium | lookalike_confuser | "
      "labelled hard-negative only; never counts toward distinctness | split-role rule |",
      "| 8 | Proposed coordinates are hypothesized, not measured | medium | all | treat as design "
      "seeds; correct against the rendered scene | Step C |", "",
      "**Overall:** the design is only as good as Step-C validation. If risk 1 does not clear "
      "(no in-envelope junction), H8-M cannot deliver a true angular branch-choice test and must "
      "be re-scoped rather than shipped as a larger H8-S.", ""]
(OUT / "h8m_design_risk_register.md").write_text("\n".join(rr) + "\n")

# ── 5. design report ─────────────────────────────────────────────────────────
def zrow(z):
    if z["o_d"] is None:
        return (f"| {z['zone_id']} | {z['family']} | {z['split_role']} | — | — | — | "
                f"{z['feasibility']} | {z['distinctness']} |")
    return (f"| {z['zone_id']} | {z['family']} | {z['split_role']} | "
            f"{z['expected_action_angle_A_deg']} / {z['expected_action_angle_B_deg']} | "
            f"{z['expected_action_angle_separation_deg']} | "
            f"{'YES' if z['is_true_angular_branch'] else 'no'} | {z['feasibility']} | "
            f"{z['distinctness']} |")


rep = ["# H8-M Step A — Route/Zone Design Report (DESIGN ONLY)", "",
       "**Status: DESIGN ONLY.** No recording, no model, no benchmark claim, no autonomy claim, "
       "no promotion. No Isaac was run; no `CL_BOUND_XY` change. All coordinates are "
       "PROPOSED/hypothesized and every distinct-room zone is UNVALIDATED (render+drive gates are "
       "Steps B-C). Purpose: design the H8-M candidate set so H8-M does not become a larger H8-S.", "",
       "## What H8-M must fix (from the H8-S diagnostic)",
       "H8-S gave a clean negative: the objective produced partial goal response (branch-choice "
       "recovered) but failed readiness (S 0.30 < 0.5, weak distance scaling) and its collinear "
       "one-alcove geometry could not test angular branch-choice. H8-M therefore needs **distinct "
       "rooms, more decision frames, a true angular junction, and embedding-based distinctness** "
       "before any collection.", "",
       "## Candidate zones",
       "| zone | family | split | exp angle A/B (deg) | ang sep (deg) | true angular branch | "
       "feasibility | distinctness (est.) |",
       "|---|---|---|---|---|---|---|---|",
       *[zrow(z) for z in ZC], "",
       f"A **true angular branch** needs expected angular separation >= "
       f"{MIN_ANG_SEP_DIVERGENT:.0f} deg. Zones flagged YES: "
       f"{', '.join(true_angular) if true_angular else 'NONE'}.", "",
       "## True angular branch-divergence (the core H8-S fix)",
       "`h8m_recep_junction` (test) is the PRIMARY angular family: goalA (left/north wing) and "
       "goalB (right/south wing) from a shared reception `o_d` give expected actions that diverge "
       f"by {next(z['expected_action_angle_separation_deg'] for z in ZC if z['zone_id']=='h8m_recep_junction')} "
       "deg — a real left-vs-right branch, not near/far scaling. `h8m_recep_fork` is a second "
       "divergent candidate. **Both are UNVALIDATED**: whether a drivable junction exists within "
       "the +/-6 m envelope is the single biggest open risk (risk #1). **If Step-C render+drive "
       "validation finds no drivable junction within the +/-6 m envelope, H8-M must be re-scoped "
       "rather than presented as a stronger benchmark.** Near/far stop-conditioning (the two H8-S "
       "vending zones) is retained only as a SECONDARY axis.", "",
       "## Visual distinctness planning",
       "Primary gate = **CLIP/DINO embedding cosine** (Step B); aHash + SSIM are secondary/"
       "auditable only. Per-zone estimates (pending rendering): the reception/junction/side-"
       "corridor zones are estimated **moderate-high** distinctness (genuinely different rooms); "
       "the two vending zones and `waiting_seating` are **low** (same alcove as H8-S — flagged, "
       "must pass the cross-split embedding gate or be dropped/merged); `lookalike_confuser` is "
       "**low by design** (adversarial hard-negative only). Duplicate risks: `recep_fork` vs "
       "`recep_junction` (same junction), and the three alcove views among each other.", "",
       "## Draft split",
       f"Target (H8-M acceptance): **train >= {SPLIT_TARGET['train']}, val >= {SPLIT_TARGET['val']}, "
       f"test >= {SPLIT_TARGET['test']}** distinct decision frames, no reused frame/goal-image/"
       "coordinate across splits, route-family balance, and >=1 true angular family in TEST.",
       f"- Draft by zone: train {roles['train']}, val {roles['val']}, test {roles['test']}, "
       f"hard-negative {roles['hard_negative']}.",
       f"- Coordinate integrity (no cross-split coordinate reuse): "
       f"**{'OK' if not reuse else 'REUSE FOUND: ' + json.dumps(reuse)}**.",
       f"- TEST contains a true angular branch: **{bool(set(roles['test']) & set(true_angular))}**.",
       "",
       "**Feasibility verdict: NOT_YET_FEASIBLE_AT_TARGET_SCALE.** Only the 2 H8-S alcove zones "
       "are drive-validated now, and both are collinear (secondary axis). Every distinct-room and "
       "angular-branch zone is unvalidated, and one decision frame was drafted per zone, so the "
       "current candidates yield far fewer than the target counts. Reaching the target requires "
       "(a) Step-C render+drive validation of >=3-4 genuinely distinct rooms incl. a true "
       "junction, and (b) authoring multiple decision frames per validated zone. **Per H8-M "
       "acceptance, collection must not proceed until the scale and the embedding gate are met.**",
       "",
       "## Claim boundary",
       "- **Design only** — no recording, no model, no training, no rollout.",
       "- **No benchmark claim, no autonomy claim, no promotion**; incumbent retained; status "
       "`DIAGNOSTIC_ONLY_NOT_PROMOTED`.",
       "- Coordinates are hypothesized design seeds to be corrected against the rendered scene; "
       "expected actions/angles are exact functions of those proposed coordinates only.",
       "- `CL_BOUND_XY` unchanged; sealed-room access must use safe spawn-relocation + local "
       "validation, never a casual safety-bound change.", "",
       "## Next (separate gated step, not authorised here)",
       "Step B — embedding distinctness search on rendered candidate goal images (calibrate "
       "T_dup/T_cross); then Step C recorded-mode gate. No recording/training/closed-loop until "
       "reviewed.", "",
       "## Artifacts",
       "`assets/experiments/hospital_h8_m_route_zone_design/`: `h8m_zone_candidates.json`, "
       "`h8m_route_family_manifest.json`, `h8m_split_plan.json`, `h8m_design_risk_register.md`, "
       "`h8m_route_zone_design_report.md`. Harness: `scripts/gnm/h8m_route_zone_design.py`. "
       "No Isaac, no images, no checkpoints, no datasets."]
(OUT / "h8m_route_zone_design_report.md").write_text("\n".join(rep) + "\n")

print(json.dumps({
    "zones": len(ZC), "true_angular_branch_zones": true_angular,
    "coordinate_integrity_ok": not reuse,
    "test_has_true_angular_branch": bool(set(roles["test"]) & set(true_angular)),
    "draft_counts": counts, "target": SPLIT_TARGET,
    "feasibility": "NOT_YET_FEASIBLE_AT_TARGET_SCALE",
    "deferred_zones": [z["zone_id"] for z in ZC if z["feasibility"] == "DEFERRED"],
}, indent=2))
print("H8-M ROUTE/ZONE DESIGN WRITTEN ->", OUT)
