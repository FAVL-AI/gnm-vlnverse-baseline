"""Build the H2 quality table — EVERY attempt, clean and failed.

Transparent construction, not a curated success set. Failed collection
attempts are part of the audit trail, not hidden errors.
"""

import csv
import glob
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "assets/experiments/hospital_h2_collection_20260709"
DS = REPO / "datasets/isaac_hospital_imagenav_v0/unassigned"

GOAL_SPLIT = {"h2_long_turn_H": "train", "h2_corridor_I": "train",
              "h2_weave_J": "train", "h2_near_desk_K": "train",
              "h2_test_long_L": "test", "h2_test_occluded_M": "test"}
DIFF = {"h2_long_turn_H": "long_multi_turn", "h2_corridor_I":
        "occluded_corridor", "h2_weave_J": "weave_near_obstacle",
        "h2_near_desk_K": "near_desk_turn", "h2_test_long_L": "test_long",
        "h2_test_occluded_M": "test_occluded"}

# attempt ledger: (attempt_id, goal, collector, rc, integrity,
#                  failure_stage, degradation_event, rerecorded_from)
FT = "hospital_front_rgb_finetune"
TD = "topdown_incumbent_diagnostic"
ATTEMPTS = [
 ("h2_ft_H_a", "h2_long_turn_H", FT, 0, "clean", None, None, None),
 ("h2_ft_I_a", "h2_corridor_I", FT, 0, "clean", None, None, None),
 ("h2_ft_J_a", "h2_weave_J", FT, 0, "clean", None, None, None),
 ("h2_ft_K_a", "h2_near_desk_K", FT, 0, "clean", None, None, None),
 ("h2_ft_H_b", "h2_long_turn_H", FT, 0, "clean", None, None, None),
 ("h2_ft_I_b", "h2_corridor_I", FT, 0, "clean", None, None, None),
 ("h2_ft_J_b", "h2_weave_J", FT, 0, "clean", None, None, None),
 ("h2_ft_K_b", "h2_near_desk_K", FT, 0, "clean", None, None, None),
 ("h2_td_H", "h2_long_turn_H", TD, 137, "excluded_partial_recording",
  "control_loop_start_wedge", "recording_stall_after_suspend_resume", None),
 ("h2_td_H_r", "h2_long_turn_H", TD, 124, "excluded_partial_recording",
  "control_loop_start_wedge", "orphaned_bag_recorder_dds_pollution", None),
 ("h2_td_I_r", "h2_corridor_I", TD, 124, "excluded_partial_recording",
  "control_loop_start_wedge", "orphaned_bag_recorder_dds_pollution", None),
 ("h2_td_J", "h2_weave_J", TD, 124, "excluded_partial_recording",
  "control_loop_start_wedge", "orphaned_bag_recorder_dds_pollution", None),
 ("h2_td_K", "h2_near_desk_K", TD, 124, "excluded_partial_recording",
  "control_loop_start_wedge", "orphaned_bag_recorder_dds_pollution", None),
 ("h2_ft_L", "h2_test_long_L", FT, 124, "excluded_partial_recording",
  "control_loop_start_wedge", "orphaned_bag_recorder_dds_pollution", None),
 ("h2_ft_M", "h2_test_occluded_M", FT, 137, "excluded_partial_recording",
  "control_loop_start_wedge", "orphaned_bag_recorder_dds_pollution", None),
 ("h2_td_L", "h2_test_long_L", TD, 0, "clean", None, None, None),
 ("h2_td_M", "h2_test_occluded_M", TD, 0, "excluded_partial_recording",
  "bag_not_finalized_orphaned_recorder",
  "orphaned_bag_recorder_dds_pollution", None),
 ("h2_td_H_r2", "h2_long_turn_H", TD, 0, "rerecorded_clean", None, None,
  "h2_td_H"),
 ("h2_td_I_r2", "h2_corridor_I", TD, 124, "excluded_partial_recording",
  "control_loop_start_wedge", "orphaned_bag_recorder_dds_pollution",
  None),
 ("h2_td_K_r2", "h2_near_desk_K", TD, 124, "excluded_partial_recording",
  "control_loop_start_wedge", "orphaned_bag_recorder_dds_pollution", None),
 ("h2_ft_L_r2", "h2_test_long_L", FT, 124, "excluded_partial_recording",
  "control_loop_start_wedge", "orphaned_bag_recorder_dds_pollution", None),
 ("h2_ft_M_r2", "h2_test_occluded_M", FT, 124,
  "excluded_partial_recording", "control_loop_start_wedge",
  "orphaned_bag_recorder_dds_pollution", None),
 ("h2_td_L_dup", "h2_test_long_L", TD, None, "excluded_partial_recording",
  "chain_killed_for_recovery", "orphaned_bag_recorder_dds_pollution", None),
 ("h2_td_M_dup", "h2_test_occluded_M", TD, None,
  "excluded_partial_recording", "chain_killed_for_recovery",
  "orphaned_bag_recorder_dds_pollution", None),
 ("h2_td_J_r2", "h2_weave_J", TD, 0, "rerecorded_clean", None, None,
  "h2_td_J"),
 ("h2_td_I_solo", "h2_corridor_I", TD, 0, "rerecorded_clean", None, None,
  "h2_td_I_r2"),
 ("h2_td_K_solo", "h2_near_desk_K", TD, 0, "rerecorded_clean", None, None,
  "h2_td_K_r2"),
 ("h2_ft_L_solo", "h2_test_long_L", FT, 124,
  "excluded_partial_recording", "scene_load_before_control_loop",
  "transient_asset_or_setup_stall", None),
 ("h2_ft_M_solo", "h2_test_occluded_M", FT, 0, "rerecorded_clean", None,
  None, "h2_ft_M_r2"),
 ("h2_ft_L_solo2", "h2_test_long_L", FT, 0, "rerecorded_clean", None,
  None, "h2_ft_L_solo"),
 ("h2_td_M_solo", "h2_test_occluded_M", TD, 0, "rerecorded_clean", None,
  None, "h2_td_M"),
 # ── H2.1 spawn-repair recordings (all probe-precleared) ──
 ("h21_ft_H_a", "h2_long_turn_H", FT, 0, "rerecorded_clean", None, None,
  "h2_ft_H_a"),
 ("h21_ft_H_b", "h2_long_turn_H", FT, 0, "rerecorded_clean", None, None,
  "h2_ft_H_b"),
 ("h21_ft_I_a", "h2_corridor_I", FT, 0, "rerecorded_clean", None, None,
  "h2_ft_I_a"),
 ("h21_ft_I_b", "h2_corridor_I", FT, 0, "rerecorded_clean", None, None,
  "h2_ft_I_b"),
 ("h21_ft_K_a", "h2_near_desk_K", FT, 0, "rerecorded_clean", None, None,
  "h2_ft_K_a"),
 ("h21_ft_K_b", "h2_near_desk_K", FT, 0, "rerecorded_clean", None, None,
  "h2_ft_K_b"),
 ("h21_ft_M", "h2_test_occluded_M", FT, 0, "rerecorded_clean", None, None,
  "h2_ft_M_solo"),
 ("h21_td_M", "h2_test_occluded_M", TD, 0, "rerecorded_clean", None, None,
  "h2_td_M_solo"),
]


ROUTE_DEFECTS = {
    "h2_ft_H_a": "spawn_defect", "h2_ft_H_b": "spawn_defect",
    "h2_td_H_r2": "spawn_defect",
    "h2_ft_I_a": "spawn_defect", "h2_ft_I_b": "spawn_defect",
    "h2_td_I_solo": "spawn_defect",
    "h2_ft_K_a": "route_design_defect", "h2_ft_K_b": "route_design_defect",
    "h2_td_K_solo": "route_design_defect",
    "h2_ft_M_solo": "spawn_defect", "h2_td_M_solo": "spawn_defect",
    # H2.1 route-design verdicts from full-rollout telemetry:
    # K grinds mid-route identically to pre-repair (probe only covered
    # spawn vicinity); M grinds mid-route under both collectors.
    "h21_ft_K_a": "mid_route_geometry_defect",
    "h21_ft_K_b": "mid_route_geometry_defect",
    "h21_ft_M": "mid_route_geometry_defect",
    "h21_td_M": "mid_route_geometry_defect",
    "h21_ft_H_a": "route_valid_but_navigation_failed",
    "h21_ft_H_b": "route_valid_but_navigation_failed",
    "h21_ft_I_a": "collision_tainted",
    "h21_ft_I_b": "collision_tainted",
}


def quality_of(meta, contacts):
    final = meta.get("final_d2g_m")
    if final is None:
        return "unlabelled"
    tags = []
    if contacts and contacts > 0:
        tags.append("collision")
    if final <= 1.0:
        tags.append("success")
    elif final <= 3.0:
        tags.append("imperfect")
    else:
        tags.append("failure_far_from_goal")
    return "+".join(tags)


def main():
    rows = []
    for (aid, goal, coll, rc, integ, stage, event, rr) in ATTEMPTS:
        row = {"episode_id": aid, "goal_id": goal, "route_id": DIFF[goal],
               "collector_policy": coll, "return_code": rc,
               "recording_integrity": integ,
               "failure_stage": stage or "",
               "runtime_degradation_event": event or "",
               "rerecorded_from": rr or "",
               "timeout_flag": rc == 124,
               "partial_recording_flag": integ ==
               "excluded_partial_recording",
               "split": GOAL_SPLIT[goal],
               "expected_difficulty": DIFF[goal]}
        eligible = integ in ("clean", "rerecorded_clean")
        conv = sorted(DS.glob(f"{aid}_2*"))
        if eligible and conv:
            m = json.loads((conv[-1] / "metadata.json").read_text())
            row.update(n_frames=m["n_frames"],
                       final_d2g_m=m.get("final_d2g_m"),
                       contacts=m.get("collisions"),
                       checkpoint=str(m.get("checkpoint", ""))[:60])
            src = REPO / m["source_trajectory"] / "episode_metadata.json"
            sm = json.loads(src.read_text()) if src.exists() else {}
            row.update(min_d2g_m=sm.get("min_distance_to_goal_m"),
                       path_length_m=sm.get("total_distance_m"),
                       stop_reason=sm.get("cl_stop_reason") or
                       "step_budget_complete",
                       estop=sm.get("cl_emergency_stop", False),
                       trajectory_quality=quality_of(
                           {"final_d2g_m": sm.get(
                               "final_distance_to_goal_m",
                               m.get("final_d2g_m"))},
                           m.get("collisions")))
        else:
            eligible = False
            row.update(n_frames="", final_d2g_m="", min_d2g_m="",
                       path_length_m="", contacts="", checkpoint="",
                       stop_reason="n/a_partial", estop="",
                       trajectory_quality="n/a_excluded")
        defect = ROUTE_DEFECTS.get(aid)
        if defect:
            row["failure_stage"] = defect
            row["runtime_degradation_event"] = (
                "route_design_defect_hand_placed_spawn")
            row["trajectory_quality"] = "route_design_defect"
            eligible = False
        row["training_eligible"] = eligible and coll == FT and \
            row["split"] == "train"
        q = str(row["trajectory_quality"])
        row["imitation_eligible"] = (row["training_eligible"]
                                     and "collision" not in q
                                     and ("success" in q or
                                          "imperfect" in q))
        row["evaluation_eligible"] = eligible and row["split"] == "test"
        row["domain_shift_evidence"] = eligible and coll == TD
        row["telemetry_note"] = ("latency/camera-age: not logged per-step "
                                 "in this collection - explicitly "
                                 "unavailable") if eligible else ""
        rows.append(row)

    cols = ["episode_id", "goal_id", "route_id", "collector_policy",
            "return_code", "recording_integrity", "failure_stage",
            "runtime_degradation_event", "rerecorded_from", "timeout_flag",
            "partial_recording_flag", "split", "expected_difficulty",
            "n_frames", "path_length_m", "final_d2g_m", "min_d2g_m",
            "contacts", "stop_reason", "estop", "trajectory_quality",
            "training_eligible", "imitation_eligible",
            "evaluation_eligible", "domain_shift_evidence",
            "checkpoint", "telemetry_note"]
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "h2_quality_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    clean = [r for r in rows if r["recording_integrity"] in
             ("clean", "rerecorded_clean")]
    excl = [r for r in rows if r["partial_recording_flag"]]
    print(f"Total recording attempts: {len(rows)}")
    print(f"Clean eligible episodes:  {len(clean)}")
    print(f"Excluded partial/timeout: {len(excl)}")
    print(f"train-eligible (imitation candidates): "
          f"{sum(1 for r in rows if r['training_eligible'])}")
    print(f"imitation-eligible (no collisions): "
          f"{sum(1 for r in rows if r['imitation_eligible'])}")
    print(f"evaluation-eligible (test): "
          f"{sum(1 for r in rows if r['evaluation_eligible'])}")
    print(f"domain-shift evidence (incumbent, clean): "
          f"{sum(1 for r in rows if r['domain_shift_evidence'])}")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
