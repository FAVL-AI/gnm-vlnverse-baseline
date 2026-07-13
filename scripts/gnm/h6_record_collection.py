#!/usr/bin/env python3
"""H6 16-episode recording collection (FULL mode: rosbag + trajectory).

8 H6 route families x2 variants (a,b) = 16 recordings, using the proven,
precheck-passed recipe (scripted RouteFollower expert, holonomic base,
--gnm-control, --collision-report, --steps 6000) WITH --episode so the full
rosbag is recorded. Reuses the audited precheck-harness hygiene helpers
(disk guard, clean_dds, bounded timeout + rc capture, proc/DDS-shm cleanup
checks, disk logging) and enforces the campaign STOP conditions. Emits a
recording ledger (json + csv).

Preconditions asserted: prechecks must be 8/8 PASS for all 8 families.

STOP conditions (halt the whole campaign):
  1 disk free falls below DISK_GUARD_GB
  2 two consecutive launch/timeout failures
  3 any route hits the XY bound (cl_stop_reason=left_xy_bounds / e-stop)
  4 sustained contact over threshold (streak>MAX_STREAK or total>MAX_TOTAL)
  5 artifact completeness fails (missing/empty rosbag or trajectory)
  6 cleanup/DDS not clean after an episode

Scope: recording only. No conversion, no training, no promotion here.
"""
import csv, json, subprocess, sys, time
from pathlib import Path
from datetime import datetime

# reuse the audited precheck-harness hygiene helpers (single source of truth)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import h6_precheck_verdicts as pc

REPO, ROUTES_DIR, TRAJ_DIR, LOGS_DIR, OUT_DIR = (
    pc.REPO, pc.ROUTES_DIR, pc.TRAJ_DIR, pc.LOGS_DIR, pc.OUT_DIR)
ISAAC_PY, BRINGUP, ROS_SETUP, GOAL_ID = pc.ISAAC_PY, pc.BRINGUP, pc.ROS_SETUP, pc.GOAL_ID

DISK_GUARD_GB      = 150            # recording gate: halt if free < this
EPISODE_TIMEOUT_S  = 1500
STEPS              = 6000
MAX_TOTAL_CONTACTS = pc.MAX_TOTAL_CONTACTS   # 20
MAX_CONTACT_STREAK = pc.MAX_CONTACT_STREAK   # 10
VARIANTS           = ["a", "b"]
FAMILIES           = pc.FAMILIES             # 8 (route_id, route_type, split)
LEDGER_JSON        = OUT_DIR / "h6_recording_ledger.json"
LEDGER_CSV         = OUT_DIR / "h6_recording_ledger.csv"


def prechecks_all_pass():
    p = OUT_DIR / "h6_precheck_verdict_table.json"
    if not p.exists():
        return False, "precheck table missing"
    ok = {r["route_id"] for r in json.loads(p.read_text())
          if r.get("precheck_verdict") == "PASS"}
    need = {f[0] for f in FAMILIES}
    return need <= ok, f"{len(need & ok)}/{len(need)} families precheck-PASS"


def record_one(rid, rtype, split, variant):
    rec = {"route_id": rid, "route_type": rtype, "split_target": split,
           "variant": variant, "episode_label": f"h6rec_{rid}_{variant}",
           "disk_before_gb": pc.free_gb()}
    route_file = ROUTES_DIR / f"{rid}.json"
    if rec["disk_before_gb"] < DISK_GUARD_GB:
        rec.update(cleanup_status="not_run", disk_after_gb=pc.free_gb(),
                   status="ABORT_DISK_GUARD")
        return rec, "stop_disk"

    pc.clean_dds()  # clean before
    name = rec["episode_label"]
    log = LOGS_DIR / f"{name}_{datetime.now():%Y%m%d_%H%M%S}.log"
    rec["log_path"] = str(log.relative_to(REPO))
    inner = (f"source {ROS_SETUP} 2>/dev/null; "
             f"'{ISAAC_PY}' -u '{BRINGUP}' --gnm-control "
             f"--route-follow '{route_file}' --holonomic-base --collision-report "
             f"--episode --episode-name {name} --goal-id {GOAL_ID} --steps {STEPS}")
    t0 = time.time()
    with open(log, "w") as lf:
        p = subprocess.run(
            ["timeout", "--signal=INT", "--kill-after=60", str(EPISODE_TIMEOUT_S),
             "bash", "-c", inner], stdout=lf, stderr=subprocess.STDOUT)
    rec["return_code"] = p.returncode
    rec["timeout"] = (p.returncode == 124)

    ed = pc.newest_new_dir(name, t0)
    launch_ok = ed is not None
    if launch_ok:
        rec["episode_dir"] = str(ed.relative_to(REPO))
        meta = {}
        try:
            meta = json.loads((ed / "episode_metadata.json").read_text())
        except Exception:
            pass
        rec["route_completed"]       = meta.get("route_completed")
        rec["cl_stop_reason"]        = meta.get("cl_stop_reason")
        rec["cl_emergency_stop"]     = meta.get("cl_emergency_stop")
        rec["total_collision_count"] = meta.get("total_collision_count")
        rec["first_collision_step"]  = meta.get("first_collision_step")
        rec["steps"]                 = meta.get("steps_logged")
        rec["distance_m"]            = meta.get("total_distance_m")
        rec["max_contact_streak"]    = pc.contact_streak(ed / "trajectory.jsonl")
        bag = meta.get("rosbag_path")
        rec["rosbag_path"] = bag
        bagp = (REPO / bag) if bag else None
        db3 = list(bagp.glob("*.db3")) if (bagp and bagp.exists()) else []
        rec["rosbag_db3_bytes"] = sum(f.stat().st_size for f in db3) if db3 else 0
        rec["artifact_complete"] = bool(rec["rosbag_db3_bytes"] > 0
                                        and (ed / "trajectory.jsonl").exists())
    else:
        rec["artifact_complete"] = False

    pc.clean_dds()  # clean after
    stale, shm = pc.stale_isaac_ros_procs(), pc.dds_shm_debris()
    rec["stale_procs_after"] = stale
    rec["dds_shm_after"] = shm
    rec["cleanup_status"] = "clean" if (not stale and not shm) else "DIRTY"
    rec["disk_after_gb"] = pc.free_gb()

    # per-episode status + which STOP condition (if any) it triggers
    streak = rec.get("max_contact_streak") or 0
    tot = rec.get("total_collision_count") or 0
    left_bounds = (rec.get("cl_stop_reason") == "left_xy_bounds"
                   or bool(rec.get("cl_emergency_stop")))
    if not launch_ok or rec["timeout"]:
        rec["status"] = "FAIL_LAUNCH"
        return rec, "launch_fail"
    if left_bounds:
        rec["status"] = "STOP_XY_BOUNDS"
        return rec, "stop_xy_bounds"
    if streak > MAX_CONTACT_STREAK or tot > MAX_TOTAL_CONTACTS:
        rec["status"] = "STOP_SUSTAINED_CONTACT"
        return rec, "stop_contact"
    if not rec["artifact_complete"]:
        rec["status"] = "STOP_ARTIFACT_INCOMPLETE"
        return rec, "stop_artifact"
    if rec["cleanup_status"] != "clean":
        rec["status"] = "STOP_CLEANUP_DIRTY"
        return rec, "stop_cleanup"
    if not bool(rec.get("route_completed")):
        rec["status"] = "INCOMPLETE_ROUTE"       # recorded but did not complete
        return rec, "incomplete"
    rec["status"] = "RECORDED_OK"
    return rec, "ok"


CSV_COLS = ["episode_label", "route_id", "route_type", "split_target", "variant",
            "return_code", "timeout", "route_completed", "cl_stop_reason",
            "total_collision_count", "max_contact_streak", "first_collision_step",
            "steps", "distance_m", "rosbag_path", "rosbag_db3_bytes",
            "artifact_complete", "episode_dir", "log_path", "disk_before_gb",
            "disk_after_gb", "cleanup_status", "status"]


def write_ledger(rows):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LEDGER_JSON.write_text(json.dumps(rows, indent=2))
    with open(LEDGER_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    LOGS_DIR.mkdir(exist_ok=True)
    ok, msg = prechecks_all_pass()
    print(f"[h6-record] precheck gate: {msg}", flush=True)
    if not ok:
        print("[h6-record] ABORT: prechecks are not 8/8 PASS; refusing to record.", flush=True)
        return 2
    plan = [(rid, rtype, split, v) for (rid, rtype, split) in FAMILIES for v in VARIANTS]
    print(f"[h6-record] start {datetime.now()} free={pc.free_gb()}GB "
          f"episodes={len(plan)} guard>={DISK_GUARD_GB}G steps={STEPS} (FULL mode, rosbag ON)", flush=True)
    rows, consec_fail, halt = [], 0, None
    for rid, rtype, split, variant in plan:
        print(f"[h6-record] === {rid} variant {variant} ({rtype}, {split}) free={pc.free_gb()}GB ===", flush=True)
        rec, outcome = record_one(rid, rtype, split, variant)
        rows.append(rec)
        write_ledger(rows)  # persist after every episode
        print(f"[h6-record] {rec['episode_label']}: {rec['status']} "
              f"completed={rec.get('route_completed')} contacts={rec.get('total_collision_count')} "
              f"streak={rec.get('max_contact_streak')} bag_bytes={rec.get('rosbag_db3_bytes')} "
              f"cleanup={rec.get('cleanup_status')} rc={rec.get('return_code')}", flush=True)
        if outcome in ("stop_disk", "stop_xy_bounds", "stop_contact",
                       "stop_artifact", "stop_cleanup"):
            halt = rec["status"]
            break
        if outcome == "launch_fail":
            consec_fail += 1
            if consec_fail >= 2:
                halt = "STOP_TWO_CONSECUTIVE_LAUNCH_FAILURES"
                break
        else:
            consec_fail = 0
    n_ok = sum(1 for r in rows if r.get("status") == "RECORDED_OK")
    if halt:
        print(f"[h6-record] HALTED: {halt} after {len(rows)} episodes "
              f"({n_ok} RECORDED_OK). Ledger: {LEDGER_JSON}", flush=True)
    else:
        print(f"[h6-record] DONE {datetime.now()} {n_ok}/{len(plan)} RECORDED_OK "
              f"-> {LEDGER_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
