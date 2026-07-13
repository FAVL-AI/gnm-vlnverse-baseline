#!/usr/bin/env python3
"""H6 controller-feasibility precheck harness (LIGHT mode: runner + verdicts).

Runs ONE bounded feasibility episode per H6 route family using the proven
smoke recipe (scripted RouteFollower, holonomic base, PhysX contact report,
--steps 6000) in LIGHT mode: NO --episode => NO rosbag; trajectory +
collision tally + metadata only (bag machinery is None-guarded in the runner,
so the --gnm-control finalize path still writes episode_metadata.json).

Per-episode hygiene: disk guard, bounded timeout with return-code capture,
clean_dds, process + DDS-shm cleanup checks, free-disk logging.
Emits h6_precheck_verdict_table.{json,csv}.

SCOPE GUARD: prechecks only. No 16-episode recording, no training, no
promotion. Full rosbags are deferred to the real collection phase.
"""
import csv, glob, json, os, subprocess, sys, time
from pathlib import Path
from datetime import datetime

REPO       = Path(__file__).resolve().parents[2]
ROUTES_DIR = REPO / "assets/experiments/hospital_h6_routes"
TRAJ_DIR   = REPO / "assets/experiments/trajectories"
LOGS_DIR   = REPO / "logs"
OUT_DIR    = REPO / "assets/experiments/hospital_h2_collection_20260709"
ISAAC_PY   = str(Path.home() / "miniforge3/envs/isaac/bin/python")
BRINGUP    = str(REPO / "scripts/robots/m3pro_ros2_bringup.py")
ROS_SETUP  = "/opt/ros/humble/setup.bash"
GOAL_ID    = "h2_weave_J"   # fixed reference goal image (feasibility only; no nav-quality claim)

# ---- predeclared thresholds ----
DISK_GUARD_GB          = 100    # standing recording gate: abort if free < this
EPISODE_TIMEOUT_S      = 1500   # bounded per-episode wrapper (~25 min; proven full run ~13.5 min)
STEPS                  = 6000   # ~100 s control authority @60 Hz (H4-equivalent)
MAX_TOTAL_CONTACTS     = 20
MAX_CONTACT_STREAK     = 10
SPAWN_CONTACT_MIN_STEP = 20

FAMILIES = [
    ("h6_uturn_01",      "uturn",               "train"),
    ("h6_chain_01",      "chain",               "train"),
    ("h6_ftL_01",        "ftL_sharp",           "train"),
    ("h6_sharpmulti_01", "sharp_multi_turn",    "train"),
    ("h6_tightcorr_01",  "tight_corridor_turn", "train"),
    ("h6_compound_01",   "compound_turn",       "validation"),
    ("h6_uturn_02",      "uturn",               "fresh_heldout"),
    ("h6_chain_02",      "chain",               "fresh_heldout"),
]


def free_gb(path="/"):
    st = os.statvfs(path)
    return round(st.f_bavail * st.f_frsize / 1e9, 1)


def sh(cmd, timeout=60):
    return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)


def clean_dds():
    """Stop the ROS2 daemon and remove DDS-specific /dev/shm segments only."""
    try:
        sh(f"source {ROS_SETUP} 2>/dev/null; ros2 daemon stop >/dev/null 2>&1 || true", timeout=30)
    except Exception:
        pass
    for pat in ("fastrtps_*", "fast_datasharing_*", "fastdds_*", "sem.fastrtps_*", "sem.fast_*", "iox_*"):
        for f in glob.glob(f"/dev/shm/{pat}"):
            try:
                os.remove(f)
            except OSError:
                pass


def stale_isaac_ros_procs():
    r = sh("pgrep -af -i 'isaac-sim|isaac_sim|omni\\.isaac|/kit |ros2 bag|rosbag2|_ros2_daemon' | grep -v pgrep || true")
    return [l for l in r.stdout.splitlines() if l.strip()]


def dds_shm_debris():
    r = sh("ls -1 /dev/shm 2>/dev/null | grep -iE 'fast|dds|rtps|cyclone|iox' || true")
    return [l for l in r.stdout.splitlines() if l.strip()]


def newest_new_dir(prefix, since_ts):
    cands = [p for p in TRAJ_DIR.glob(prefix + "_*")
             if p.is_dir() and p.stat().st_mtime >= since_ts - 2]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def contact_streak(traj_jsonl):
    """Longest run of consecutive collision_detected rows (== sustained contact)."""
    best = streak = 0
    try:
        with open(traj_jsonl) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("collision_detected"):
                    streak += 1
                    best = max(best, streak)
                else:
                    streak = 0
    except OSError:
        return None
    return best


def run_family(rid, rtype, split):
    rec = {"route_id": rid, "route_type": rtype, "split_target": split,
           "disk_before_gb": free_gb()}
    route_file = ROUTES_DIR / f"{rid}.json"

    if rec["disk_before_gb"] < DISK_GUARD_GB:
        rec.update(cleanup_status="not_run", disk_after_gb=free_gb(),
                   precheck_verdict="ABORT_DISK_GUARD", failure_stage="disk_guard")
        return rec, "abort_disk"
    if not route_file.exists():
        rec.update(route_infeasible_reason="route_file_missing", cleanup_status="not_run",
                   disk_after_gb=free_gb(), precheck_verdict="REJECT", failure_stage="missing_route")
        return rec, "ran"

    clean_dds()  # clean start
    name = f"h6pre_{rid}"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log = LOGS_DIR / f"{name}_{ts}.log"
    rec["log_path"] = str(log.relative_to(REPO))
    inner = (f"source {ROS_SETUP} 2>/dev/null; "
             f"'{ISAAC_PY}' -u '{BRINGUP}' --gnm-control "
             f"--route-follow '{route_file}' --holonomic-base --collision-report "
             f"--episode-name {name} --goal-id {GOAL_ID} --steps {STEPS}")
    t0 = time.time()
    with open(log, "w") as lf:
        p = subprocess.run(
            ["timeout", "--signal=INT", "--kill-after=60", str(EPISODE_TIMEOUT_S), "bash", "-c", inner],
            stdout=lf, stderr=subprocess.STDOUT)
    rc = p.returncode
    timed_out = (rc == 124)
    rec["return_code"] = rc
    rec["timeout"] = timed_out

    ed = newest_new_dir(name, t0)
    launch_ok = ed is not None
    if launch_ok:
        rec["episode_dir"] = str(ed.relative_to(REPO))
        meta = {}
        try:
            meta = json.loads((ed / "episode_metadata.json").read_text())
        except Exception:
            pass
        rec["route_completed"]        = meta.get("route_completed")
        rec["route_infeasible_reason"] = meta.get("route_infeasible_reason")
        rec["total_collision_count"]  = meta.get("total_collision_count")
        rec["first_collision_step"]   = meta.get("first_collision_step")
        rec["steps"]                  = meta.get("steps_logged")
        rec["distance_m"]             = meta.get("total_distance_m")
        rec["max_contact_streak"]     = contact_streak(ed / "trajectory.jsonl")

    clean_dds()
    stale = stale_isaac_ros_procs()
    shm = dds_shm_debris()
    rec["stale_procs_after"] = stale
    rec["dds_shm_after"] = shm
    rec["cleanup_status"] = "clean" if (not stale and not shm) else "DIRTY"
    rec["disk_after_gb"] = free_gb()

    fc, tot = rec.get("first_collision_step"), rec.get("total_collision_count")
    streak = rec.get("max_contact_streak")
    if not launch_ok:
        verdict, stage = "REJECT", "launch_failure"
    elif timed_out:
        verdict, stage = "REJECT", "timeout"
    elif rc != 0:
        verdict, stage = "REJECT", f"nonzero_rc_{rc}"
    elif not bool(rec.get("route_completed")):
        verdict = "REJECT"
        stage = "route_incomplete" + (f":{rec['route_infeasible_reason']}" if rec.get("route_infeasible_reason") else "")
    elif tot is not None and tot > MAX_TOTAL_CONTACTS:
        verdict, stage = "REJECT", "mid_route_grind"
    elif streak is not None and streak > MAX_CONTACT_STREAK:
        verdict, stage = "REJECT", "sustained_contact"
    elif fc is not None and fc < SPAWN_CONTACT_MIN_STEP:
        verdict, stage = "REJECT", "spawn_contact"
    else:
        verdict, stage = "PASS", ""
    rec["failure_stage"] = stage
    rec["precheck_verdict"] = verdict
    return rec, ("launch_fail" if not launch_ok else "ran")


CSV_COLS = ["route_id", "route_type", "split_target", "return_code", "timeout",
            "route_completed", "route_infeasible_reason", "total_collision_count",
            "max_contact_streak", "first_collision_step", "steps", "distance_m",
            "episode_dir", "log_path", "disk_before_gb", "disk_after_gb",
            "cleanup_status", "failure_stage", "precheck_verdict"]


def write_tables(rows):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "h6_precheck_verdict_table.json").write_text(json.dumps(rows, indent=2))
    with open(OUT_DIR / "h6_precheck_verdict_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _load_existing_rows():
    p = OUT_DIR / "h6_precheck_verdict_table.json"
    if p.exists():
        try:
            return {r["route_id"]: r for r in json.loads(p.read_text())}
        except Exception:
            return {}
    return {}


def main():
    LOGS_DIR.mkdir(exist_ok=True)
    # optional CLI: one or more route_ids to run a targeted subset; results are
    # merged into the existing verdict table (other families preserved).
    selected = [a for a in sys.argv[1:] if not a.startswith("-")]
    todo = [f for f in FAMILIES if not selected or f[0] in selected]
    merged = _load_existing_rows() if selected else {}
    subset_note = f" [subset: {','.join(selected)}]" if selected else ""
    print(f"[h6-precheck] start {datetime.now()} free={free_gb()}GB "
          f"thresholds: disk>={DISK_GUARD_GB}G steps={STEPS} "
          f"max_total={MAX_TOTAL_CONTACTS} max_streak={MAX_CONTACT_STREAK} "
          f"(LIGHT mode, no bags){subset_note}", flush=True)
    consec_launch_fail = 0
    for rid, rtype, split in todo:
        print(f"[h6-precheck] === {rid} ({rtype}, {split}) free={free_gb()}GB ===", flush=True)
        rec, outcome = run_family(rid, rtype, split)
        merged[rid] = rec
        write_tables([merged[f[0]] for f in FAMILIES if f[0] in merged])  # FAMILIES order, incremental
        print(f"[h6-precheck] {rid}: {rec['precheck_verdict']} "
              f"completed={rec.get('route_completed')} contacts={rec.get('total_collision_count')} "
              f"streak={rec.get('max_contact_streak')} rc={rec.get('return_code')} "
              f"cleanup={rec.get('cleanup_status')} stage={rec.get('failure_stage')}", flush=True)
        if outcome == "abort_disk":
            print("[h6-precheck] ABORT: disk guard tripped; stopping run.", flush=True)
            break
        if outcome == "launch_fail":
            consec_launch_fail += 1
            if consec_launch_fail >= 2:
                print("[h6-precheck] ABORT: 2 consecutive launch failures (env likely broken); stopping.", flush=True)
                break
        else:
            consec_launch_fail = 0
    final_rows = [merged[f[0]] for f in FAMILIES if f[0] in merged]
    n_pass = sum(1 for r in final_rows if r.get("precheck_verdict") == "PASS")
    print(f"[h6-precheck] DONE {datetime.now()} {n_pass}/{len(final_rows)} PASS "
          f"-> {OUT_DIR / 'h6_precheck_verdict_table.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
