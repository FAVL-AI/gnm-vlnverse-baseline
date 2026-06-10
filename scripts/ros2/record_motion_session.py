#!/usr/bin/env python3
"""
record_motion_session.py — Publication-grade real-robot motion session recorder.

Flow:
  1. Poll until robot is reachable via Tailscale
  2. SSH → preflight gate checks (7 gates)
  3. SSH → start ros2 bag record on Jetson
  4. SSH → publish motion sequence inside the robot's DDS graph
  5. SSH → stop recording
  6. scp bag to local recordings/
  7. Run analyze_real_robot_session.py → full evidence package
  8. Print git commit instructions

Requirements:
  pip install paramiko
  apt install sshpass
  FLEETSAFE_ROBOT_PASSWORD env var set

Usage:
  export FLEETSAFE_ROBOT_PASSWORD=<password>
  python scripts/ros2/record_motion_session.py [--dry-run] [--no-fetch]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

ROBOT_IP    = "100.91.232.55"
ROBOT_USER  = "jetson"
ROBOT_PORT  = 22
ROS_DOMAIN  = 30
BAG_HOMEDIR = "~/fleetsafe_bags"

BATTERY_MIN_V  = 11.0   # 3S LiPo safe floor
MOTION_CMD_TOPIC = "/cmd_vel"  # direct; switch to /cmd_vel_raw to go via safety layer

RECORD_TOPICS = [
    "/rgb",
    "/odom_raw",
    "/scan0",
    "/scan1",
    "/battery",
    "/cmd_vel",
    "/cmd_vel_raw",
    "/cmd_vel_safe",
    "/fleetsafe/zone",
    "/fleetsafe/social_risk",
    "/fleetsafe/detections",
    "/fleetsafe/tracks",
    "/fleetsafe/latency",
]

# (linear_x m/s, angular_z rad/s, duration_s)
# Straight → rotate 180° → straight back → rotate 180° → stop
MOTION_SEQUENCE = [
    (0.15,  0.0,   5.0),   # forward ~0.75m
    (0.0,   0.5,   6.3),   # CW 180°  (π / 0.5 ≈ 6.28s)
    (0.15,  0.0,   5.0),   # forward back ~0.75m
    (0.0,   0.5,   6.3),   # CW 180°  back to heading
    (0.0,   0.0,   2.0),   # stop
]

# Bench test: wheels lifted, 0.5 s burst only.
# Evidence goal: /cmd_vel nonzero + /odom_raw delta in one clean bag.
BENCH_MOTION_SEQUENCE = [
    (0.15, 0.0, 0.5),   # 0.5 s forward burst — wheels must be lifted
]

PRE_MOTION_SETTLE_S       = 15   # seconds after bag record starts before motion
PRE_MOTION_SETTLE_S_BENCH = 2    # shorter settle for bench runs
POST_MOTION_IDLE_S        = 8    # seconds of recording after motion ends


# ── SSH helpers ───────────────────────────────────────────────────────────────

def _open_ssh(password: str):
    import paramiko
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ROBOT_IP, port=ROBOT_PORT, username=ROBOT_USER,
                password=password, timeout=15)
    return ssh


def _run(ssh, cmd: str, timeout: int = 30) -> tuple[str, str, int]:
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout, get_pty=False)
    out  = stdout.read().decode(errors="replace")
    err  = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    return out, err, code


def _ros2(ssh, inner: str, timeout: int = 25) -> tuple[str, str, int]:
    """Run a ros2 command with sourced environment on the robot.

    Source order matches the manual test that proved connectivity:
      ROS_DOMAIN_ID → ros/humble → M3Pro_ws → yahboomcar_ws → <command>
    Double-quotes wrap the bash -lc argument; inner must not contain double-quotes
    (all current callers use single-quoted awk/grep patterns, which are safe here).
    """
    cmd = (
        f'bash -lc "'
        f'export ROS_DOMAIN_ID={ROS_DOMAIN}; '
        f'source /opt/ros/humble/setup.bash; '
        f'source ~/M3Pro_ws/install/setup.bash; '
        f'source ~/yahboomcar_ws/install/setup.bash; '
        f'{inner}"'
    )
    return _run(ssh, cmd, timeout=timeout)


# ── Preflight gates ───────────────────────────────────────────────────────────

def _topic_sub_count(ssh, topic: str) -> int:
    out, err, _ = _ros2(ssh, f"ros2 topic info -v {topic} 2>/dev/null")
    m = re.search(r'Subscription count:\s*(\d+)', out)
    if m:
        return int(m.group(1))
    print(f"[debug] _topic_sub_count({topic}) parse failed\n"
          f"  stdout: {out!r}\n  stderr: {err!r}")
    return -1


def _topic_pub_count(ssh, topic: str) -> int:
    out, err, _ = _ros2(ssh, f"ros2 topic info -v {topic} 2>/dev/null")
    m = re.search(r'Publisher count:\s*(\d+)', out)
    if m:
        return int(m.group(1))
    print(f"[debug] _topic_pub_count({topic}) parse failed\n"
          f"  stdout: {out!r}\n  stderr: {err!r}")
    return -1


def _node_list(ssh) -> list[str]:
    out, _, _ = _ros2(ssh, "ros2 node list 2>/dev/null")
    return [l.strip() for l in out.splitlines() if l.strip()]


def preflight(ssh, dry_run: bool) -> bool:
    """
    Run 9 preflight gates.  Hard gates abort; soft gates warn.
    Returns True if all hard gates pass.

    Gate summary:
      HARD: cmd_vel_subscriber, no_joy_ctrl, no_autostart_node,
            odom_raw_topic, battery_voltage*
      soft: cmd_vel_safe_publisher, relay_enabled, watchdog_armed,
            scan0_topic, battery_voltage*

    * battery_voltage is soft by default.  Set FLEETSAFE_REQUIRE_BATTERY=true
      to promote it to HARD (e.g. unattended / overnight runs).
      If /battery is unavailable but /cmd_vel subscriber and /YB_Node are
      present, the gate passes as soft with an operator warning.
    """
    require_battery = os.environ.get("FLEETSAFE_REQUIRE_BATTERY", "false").lower() == "true"

    print("\n[preflight] Running gate checks …")
    results: list[tuple[str, bool, bool, str]] = []  # (name, passed, is_hard, detail)

    if dry_run:
        gates = [
            ("cmd_vel_subscriber",     True,  True,  "DRY-RUN skip"),
            ("no_joy_ctrl",            True,  True,  "DRY-RUN skip"),
            ("no_autostart_node",      True,  True,  "DRY-RUN skip"),
            ("odom_raw_topic",         True,  True,  "DRY-RUN skip"),
            ("cmd_vel_safe_publisher", True,  False, "DRY-RUN skip"),
            ("relay_enabled",          True,  False, "DRY-RUN skip"),
            ("watchdog_armed",         True,  False, "DRY-RUN skip"),
            ("scan0_topic",            True,  False, "DRY-RUN skip"),
            ("battery_voltage",        True,  require_battery, "DRY-RUN skip"),
        ]
        for row in gates:
            print(f"  {'✓' if row[1] else '✗'} {row[0]:30s} {row[3]}")
        return True

    nodes = _node_list(ssh)

    # 1. /cmd_vel subscriber exists (motor driver is live) — HARD
    sub_count = _topic_sub_count(ssh, "/cmd_vel")
    ok = sub_count > 0
    results.append(("cmd_vel_subscriber", ok, True,
                    f"subscriber_count={sub_count}"))

    # 2. No joy_ctrl publisher (no conflicting joystick node) — HARD
    joy_nodes = [n for n in nodes if "joy" in n.lower()]
    results.append(("no_joy_ctrl", len(joy_nodes) == 0, True,
                    f"joy_nodes={joy_nodes or 'none'}"))

    # 3. No autostart navigation node — HARD
    auto_nodes = [n for n in nodes if "autostart" in n.lower()]
    results.append(("no_autostart_node", len(auto_nodes) == 0, True,
                    f"autostart_nodes={auto_nodes or 'none'}"))

    # 4. /odom_raw topic has a publisher (wheel odometry live) — HARD
    odom_pubs = _topic_pub_count(ssh, "/odom_raw")
    results.append(("odom_raw_topic", odom_pubs > 0, True,
                    f"publisher_count={odom_pubs}"))

    # 5. /cmd_vel_safe publisher exists (safety node running) — soft
    pub_count = _topic_pub_count(ssh, "/cmd_vel_safe")
    results.append(("cmd_vel_safe_publisher", pub_count > 0, False,
                    f"publisher_count={pub_count}"))

    # 6. Relay enabled: /cmd_vel_safe has ≥1 subscriber — soft
    relay_subs = _topic_sub_count(ssh, "/cmd_vel_safe")
    results.append(("relay_enabled", relay_subs > 0, False,
                    f"cmd_vel_safe subscriber_count={relay_subs}"))

    # 7. Watchdog node present — soft
    wd_nodes = [n for n in nodes if "watchdog" in n.lower()]
    results.append(("watchdog_armed", len(wd_nodes) > 0, False,
                    f"watchdog_nodes={wd_nodes or 'none'}"))

    # 8. /scan0 topic has a publisher (LiDAR live) — soft
    scan_pubs = _topic_pub_count(ssh, "/scan0")
    results.append(("scan0_topic", scan_pubs > 0, False,
                    f"publisher_count={scan_pubs}"))

    # 9. Battery voltage > threshold — soft by default; HARD if FLEETSAFE_REQUIRE_BATTERY=true
    yb_node_present = any("YB_Node" in n for n in nodes)
    cmd_vel_ok      = sub_count > 0   # already fetched in gate 1

    bat_out, bat_err, _ = _ros2(ssh,
        "ros2 topic echo /battery --once --no-daemon 2>/dev/null", timeout=12)
    m = re.search(r'data:\s*([\d.]+)', bat_out)
    if m:
        voltage = float(m.group(1))
        bat_ok  = voltage >= BATTERY_MIN_V
        bat_msg = f"{voltage:.3f} V (min {BATTERY_MIN_V:.1f} V)"
    elif cmd_vel_ok and yb_node_present:
        # /battery unavailable but robot stack is running — warn, don't abort
        bat_ok  = not require_battery   # pass when soft; fail when hard
        bat_msg = "battery topic unavailable — operator must confirm battery OK"
        print("[preflight] ⚠ battery topic unavailable — operator must confirm battery OK")
        print(f"[debug] battery raw stdout: {bat_out!r}\n"
              f"        battery raw stderr: {bat_err!r}")
    else:
        bat_ok  = False
        bat_msg = f"parse failed: {bat_out.strip()!r}"
        print(f"[debug] battery raw stdout: {bat_out!r}\n"
              f"        battery raw stderr: {bat_err!r}")
    results.append(("battery_voltage", bat_ok, require_battery, bat_msg))

    # ── Print and evaluate ───────────────────────────────────────────────────
    hard_fail = False
    for name, passed, is_hard, detail in results:
        icon  = "✓" if passed else ("✗" if is_hard else "⚠")
        label = "HARD" if is_hard else "soft"
        print(f"  {icon} [{label}] {name:30s} {detail}")
        if not passed and is_hard:
            hard_fail = True

    if hard_fail:
        print("[preflight] ✗ Hard gate(s) failed — aborting.")
        return False

    bat_mode = "HARD" if require_battery else "soft"
    print(f"[preflight] ✓ All hard gates passed (battery_voltage={bat_mode}).\n")
    return True


# ── Recording ─────────────────────────────────────────────────────────────────

def start_recording(ssh, bag_name: str, dry_run: bool) -> tuple[str, str]:
    """
    Launch ros2 bag record on the Jetson via nohup.  Returns (bag_path, pid).

    Uses ssh.exec_command directly (not _ros2/_run) so stdout is read once
    for the PID echo and the channel is never left waiting on ros2 output.
    The nohup process continues independently after the SSH channel closes.
    Stop later with: kill -2 <pid>

    Returns pid='' on failure; caller should abort.
    """
    topics   = " ".join(RECORD_TOPICS)
    bag_path = f"{BAG_HOMEDIR}/{bag_name}"
    log_path = f"/tmp/fleetsafe_motion_bag_{bag_name}.log"

    print("[record] Starting ros2 bag record on robot …")
    if dry_run:
        print(f"[record] DRY-RUN: would record to {bag_path}")
        print(f"[record] DRY-RUN: log → {log_path}")
        return bag_path, "DRY-RUN-PID"

    cmd = (
        f'nohup bash -lc "'
        f'export ROS_DOMAIN_ID={ROS_DOMAIN}; '
        f'source /opt/ros/humble/setup.bash; '
        f'source ~/M3Pro_ws/install/setup.bash; '
        f'source ~/yahboomcar_ws/install/setup.bash; '
        f'ros2 bag record {topics} -o {bag_path}'
        f'" > {log_path} 2>&1 & echo $!'
    )
    _, stdout, _ = ssh.exec_command(cmd, timeout=10, get_pty=False)
    pid = stdout.read().decode(errors="replace").strip()

    if not pid.isdigit():
        print(f"[record] ERROR: nohup launch did not return a PID (got {pid!r})")
        return bag_path, ""

    print(f"[record] PID={pid}  bag={bag_path}")
    print(f"[record] log → {log_path}")
    return bag_path, pid


def stop_recording(ssh, pid: str, dry_run: bool) -> None:
    """Send SIGINT to the ros2 bag record process (triggers clean bag close)."""
    print(f"[record] Stopping ros2 bag record (PID={pid}) …")
    if dry_run:
        return
    _run(ssh, f"kill -2 {pid} && sleep 2", timeout=10)


# ── Motion sequence (published from robot's DDS graph) ────────────────────────

_ZERO_MSG = "'{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}'"


def _publish_zero(ssh, dry_run: bool, times: int = 5) -> None:
    """Publish zero cmd_vel N times at 10 Hz to ensure a clean stop."""
    inner = (
        f"ros2 topic pub --rate 10 --times {times} "
        f"{MOTION_CMD_TOPIC} geometry_msgs/msg/Twist {_ZERO_MSG} --no-daemon"
    )
    if dry_run:
        print(f"[motion]  DRY-RUN: zero ×{times}")
        return
    _ros2(ssh, inner, timeout=times + 5)


def _verify_cmd_vel(ssh, dry_run: bool) -> bool:
    """
    Confirm /cmd_vel accepts nonzero commands before running the sequence.

    Starts a background echo (output → temp file), publishes a 0.5 s test
    pulse, then reads the captured message.  Aborts the session if the echo
    shows no nonzero linear.x.
    """
    if dry_run:
        print("[verify] DRY-RUN: skipping /cmd_vel verification")
        return True

    test_msg = "'{linear: {x: 0.100, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}'"
    inner = (
        # Start echo subscriber in background before the publisher
        f"ros2 topic echo {MOTION_CMD_TOPIC} --once --no-daemon 2>/dev/null "
        f"> /tmp/fleetsafe_cv_verify.txt & "
        f"ECHO_PID=$!; "
        f"sleep 0.1; "
        # Publish 5-message test pulse (0.5 s at 10 Hz)
        f"ros2 topic pub --times 5 --rate 10 "
        f"{MOTION_CMD_TOPIC} geometry_msgs/msg/Twist {test_msg} --no-daemon; "
        f"sleep 0.2; "
        f"kill $ECHO_PID 2>/dev/null || true; "
        f"cat /tmp/fleetsafe_cv_verify.txt"
    )
    out, _, _ = _ros2(ssh, inner, timeout=15)

    m = re.search(r'x:\s*([\d.]+)', out)
    if m and float(m.group(1)) > 0.01:
        print(f"[verify] /cmd_vel nonzero ✓  (linear.x={m.group(1)})")
        _publish_zero(ssh, dry_run)   # clean stop after verify pulse
        return True

    print("[verify] /cmd_vel echo did not show nonzero — aborting motion")
    print(f"[verify] raw stdout: {out!r}")
    return False


def _motion_step(ssh, vx: float, wz: float, dur: float, dry_run: bool) -> None:
    n = max(1, int(round(dur * 10)))  # 10 Hz
    msg = (
        f"'{{linear: {{x: {vx:.3f}, y: 0.0, z: 0.0}}, "
        f"angular: {{x: 0.0, y: 0.0, z: {wz:.3f}}}}}'"
    )
    inner = (
        f"ros2 topic pub --rate 10 --times {n} "
        f"{MOTION_CMD_TOPIC} geometry_msgs/msg/Twist {msg} --no-daemon"
    )
    label = f"vx={vx:+.3f} wz={wz:+.3f}  {dur:.1f}s"
    print(f"[motion]  {label}")
    if dry_run:
        print(f"[motion]  DRY-RUN: {inner}")
        time.sleep(0.1)
    else:
        _ros2(ssh, inner, timeout=int(dur) + 20)
    _publish_zero(ssh, dry_run)   # guaranteed stop after every step


def run_motion_sequence(
    ssh,
    dry_run: bool,
    sequence: list | None = None,
    settle_s: int = PRE_MOTION_SETTLE_S,
) -> bool:
    """
    Run a motion sequence.  Returns False if /cmd_vel verification fails.
    Publishes 5 zero messages after every step and after the verify pulse.
    """
    if sequence is None:
        sequence = MOTION_SEQUENCE

    print(f"[motion] Verifying /cmd_vel …")
    if not _verify_cmd_vel(ssh, dry_run):
        return False

    print(f"[motion] Settling {settle_s}s …")
    time.sleep(settle_s if not dry_run else 0.5)
    print("[motion] Motion sequence start")
    for vx, wz, dur in sequence:
        _motion_step(ssh, vx, wz, dur, dry_run)
    print("[motion] Motion sequence complete")
    print(f"[motion] Post-motion idle {POST_MOTION_IDLE_S}s …")
    time.sleep(POST_MOTION_IDLE_S if not dry_run else 0.2)
    return True


# ── Fetch bag ─────────────────────────────────────────────────────────────────

def fetch_bag(remote_bag: str, session_dir: Path, dry_run: bool) -> None:
    print(f"[fetch] scp {ROBOT_USER}@{ROBOT_IP}:{remote_bag} → {session_dir}")
    if dry_run:
        print("[fetch] DRY-RUN: skipping scp")
        return
    password = os.environ["FLEETSAFE_ROBOT_PASSWORD"]
    env = os.environ.copy()
    env["SSHPASS"] = password
    result = subprocess.run(
        [
            "sshpass", "-e",
            "scp", "-r",
            "-o", "StrictHostKeyChecking=no",
            f"{ROBOT_USER}@{ROBOT_IP}:{remote_bag}",
            str(session_dir) + "/",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[fetch] ERROR: {result.stderr.strip()}")
        raise RuntimeError(f"scp failed (exit {result.returncode})")
    print(f"[fetch] Done.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print all steps without executing SSH or motion")
    parser.add_argument("--no-fetch", action="store_true",
                        help="Skip scp — bag stays on robot")
    parser.add_argument("--wait-timeout", type=int, default=300,
                        help="Seconds to wait for robot to come online (default 300)")
    parser.add_argument("--bench", action="store_true",
                        help="Bench test: 0.5 s forward burst only (wheels must be lifted)")
    args = parser.parse_args()

    dry_run: bool = args.dry_run or (
        os.environ.get("FLEETSAFE_ROBOT_DRY_RUN", "false").lower() == "true"
    )
    if dry_run:
        print("[main] *** DRY-RUN MODE ***")

    password = os.environ.get("FLEETSAFE_ROBOT_PASSWORD", "")
    if not password and not dry_run:
        print("ERROR: FLEETSAFE_ROBOT_PASSWORD not set")
        return 1

    # ── 1. Wait for robot ────────────────────────────────────────────────────
    print(f"[main] Waiting for robot at {ROBOT_IP} …")
    deadline = time.monotonic() + (args.wait_timeout if not dry_run else 0)
    online = dry_run
    while not online and time.monotonic() < deadline:
        r = subprocess.run(["ping", "-c", "1", "-W", "2", ROBOT_IP],
                           capture_output=True, timeout=5)
        if r.returncode == 0:
            online = True
            break
        remaining = int(deadline - time.monotonic())
        print(f"  no ping … {remaining}s", end="\r", flush=True)
        time.sleep(5)
    if not online:
        print(f"\n[main] Robot did not come online within {args.wait_timeout}s")
        return 1
    print(f"[main] Robot online ✓")

    # ── 2. SSH ───────────────────────────────────────────────────────────────
    ssh = None
    if not dry_run:
        print(f"[main] SSH {ROBOT_USER}@{ROBOT_IP} …")
        try:
            import paramiko  # noqa: F401
        except ImportError:
            print("ERROR: pip install paramiko")
            return 1
        try:
            ssh = _open_ssh(password)
            print("[main] SSH connected ✓")
        except Exception as e:
            print(f"[main] SSH failed: {e}")
            return 1

    # ── 3. Preflight ─────────────────────────────────────────────────────────
    if not preflight(ssh, dry_run):
        if ssh:
            ssh.close()
        return 1

    # ── 4. Start recording ───────────────────────────────────────────────────
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    session_name = f"session_{ts}"
    bag_name     = f"rosbag2_{ts}"
    remote_bag   = f"{BAG_HOMEDIR}/{bag_name}"
    session_dir  = REPO_ROOT / "recordings" / "real_robot" / session_name
    session_dir.mkdir(parents=True, exist_ok=True)

    _, rec_pid = start_recording(ssh, bag_name, dry_run)
    if not rec_pid and not dry_run:
        print("[main] Bag startup failed — aborting session.")
        if ssh:
            ssh.close()
        return 1

    # ── 5. Motion sequence ───────────────────────────────────────────────────
    if args.bench:
        seq      = BENCH_MOTION_SEQUENCE
        settle_s = PRE_MOTION_SETTLE_S_BENCH
        print("[main] *** BENCH MODE — wheels must be lifted off ground ***")
    else:
        seq      = MOTION_SEQUENCE
        settle_s = PRE_MOTION_SETTLE_S

    motion_ok = run_motion_sequence(ssh, dry_run, sequence=seq, settle_s=settle_s)
    if not motion_ok and not dry_run:
        print("[main] Motion aborted — /cmd_vel verification failed. Stopping bag.")
        stop_recording(ssh, rec_pid, dry_run)
        if ssh:
            ssh.close()
        return 1

    # ── 6. Stop recording ────────────────────────────────────────────────────
    stop_recording(ssh, rec_pid, dry_run)

    # ── 7. Fetch bag ─────────────────────────────────────────────────────────
    if not args.no_fetch:
        fetch_bag(remote_bag, session_dir, dry_run)

    if ssh:
        ssh.close()

    # ── 8. Session manifest ──────────────────────────────────────────────────
    manifest = {
        "session_id":      session_name,
        "robot":           "Yahboom M3Pro",
        "ros_domain_id":   ROS_DOMAIN,
        "recorded_at":     datetime.now(timezone.utc).isoformat(),
        "status":          "DRY_RUN" if dry_run else "RECORDED",
        "motion_topic":    MOTION_CMD_TOPIC,
        "motion_mode":     "bench" if args.bench else "full",
        "motion_sequence": seq,
        "note":            "Motion published from robot via SSH exec_command",
        "topics_requested": RECORD_TOPICS,
    }
    (session_dir / "session_manifest.json").write_text(json.dumps(manifest, indent=2))

    # ── 9. Analysis ──────────────────────────────────────────────────────────
    if not dry_run and not args.no_fetch:
        print("\n[main] Running analysis …")
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "ros2" / "analyze_real_robot_session.py"),
                "--session", str(session_dir),
            ],
        )

    print(f"\n[main] Session: {session_name}")
    print("[main] To commit (not the db3):")
    print(f"  git add recordings/real_robot/{session_name}/*.json "
          f"recordings/real_robot/{session_name}/*.png "
          f"recordings/real_robot/{session_name}/*.csv "
          f"recordings/real_robot/{session_name}/*.md")
    print(f"  git commit -m 'evidence: real robot motion session {session_name}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
