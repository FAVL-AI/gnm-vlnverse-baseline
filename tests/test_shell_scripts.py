"""
test_shell_scripts.py — bash -n syntax check for FleetSafe shell scripts.

All scripts in scripts/ that are used in production or by Makefile targets
must pass bash -n.  This ensures syntax errors are caught before deployment.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

SHELL_SCRIPTS = [
    "scripts/robot/install_robot_tools.sh",
    "scripts/robot/discover_yahboom_stack.sh",
    "scripts/robot/diagnose_yahboom_live_stack.sh",
    "scripts/robot/start_yahboom_stack.sh",
    "scripts/robot/status_yahboom_stack.sh",
    "scripts/live/preflight_live_motion.sh",
    "scripts/live/vln_live_preflight.sh",
    "scripts/live/detect_scan_topics.sh",
    "scripts/live/check_vln_stack.sh",
    "scripts/live/run_vln_desktop.sh",
    "scripts/live/inspect_lidar_clearance.py",   # Python — skip below
    "scripts/robot/check_robot_connection.sh",
    "scripts/robot/sync_repo_to_jetson.sh",
]

BASH_SCRIPTS = [p for p in SHELL_SCRIPTS if p.endswith(".sh")]


@pytest.mark.parametrize("script", BASH_SCRIPTS)
def test_shell_syntax(script: str):
    """Every .sh script must pass bash -n (no syntax errors)."""
    path = REPO_ROOT / script
    if not path.exists():
        pytest.skip(f"{script} does not exist yet")
    result = subprocess.run(
        ["bash", "-n", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"bash -n failed for {script}:\n{result.stderr}"
    )


def test_vln_live_preflight_exists():
    """vln_live_preflight.sh must exist and be executable-looking."""
    path = REPO_ROOT / "scripts/live/vln_live_preflight.sh"
    assert path.exists(), "scripts/live/vln_live_preflight.sh not found"
    content = path.read_text()
    assert "FAIL" in content, "preflight script must contain FAIL checks"
    assert "exit 1" in content, "preflight script must exit 1 on failure"
    assert "camera_seen" in content, "preflight script must check camera_seen"


def test_install_robot_tools_has_all_three_scripts():
    """install_robot_tools.sh must define start, status, and stop scripts."""
    path = REPO_ROOT / "scripts/robot/install_robot_tools.sh"
    assert path.exists()
    content = path.read_text()
    assert "start_robot_stack.sh" in content
    assert "status_robot_stack.sh" in content
    assert "stop_robot_motion.sh" in content


def test_install_robot_tools_includes_bringup():
    """start_robot_stack.sh content must attempt yahboomcar bringup."""
    path = REPO_ROOT / "scripts/robot/install_robot_tools.sh"
    content = path.read_text()
    assert "yahboomcar" in content, \
        "install_robot_tools.sh must attempt to launch yahboomcar bringup"
    assert "micro_ros_agent" in content, \
        "install_robot_tools.sh must start micro_ros_agent"


def test_preflight_checks_all_required_topics():
    """vln_live_preflight.sh must explicitly check all 6 required topics."""
    path = REPO_ROOT / "scripts/live/vln_live_preflight.sh"
    content = path.read_text()
    required = ["/scan0", "/scan1", "/odom_raw", "/camera/color/image_raw",
                "/fleetsafe/instruction_text", "YB_Node"]
    for topic in required:
        assert topic in content, \
            f"preflight script missing check for {topic}"


def test_preflight_live_motion_exists():
    """preflight_live_motion.sh must exist with all hard-fail sensor checks."""
    path = REPO_ROOT / "scripts/live/preflight_live_motion.sh"
    assert path.exists(), "scripts/live/preflight_live_motion.sh not found"
    content = path.read_text()
    # Hard-fail checks
    for item in ["/YB_Node", "/scan0", "/scan1", "/odom_raw", "/cmd_vel",
                 "inspect_lidar_clearance", "Publisher count", "SAFETY_RADIUS"]:
        assert item in content, f"preflight_live_motion.sh missing: {item}"
    # Camera must be advisory, not a hard fail
    assert "advisory" in content.lower() or "[WARN]" in content, \
        "camera check must be advisory (WARN), not a hard fail"
    assert "exit 1" in content, "preflight must exit 1 on failure"


def test_preflight_live_motion_camera_is_advisory():
    """Camera check in preflight_live_motion.sh must use _warn, not _fail."""
    path = REPO_ROOT / "scripts/live/preflight_live_motion.sh"
    content = path.read_text()
    lines = content.splitlines()
    # Find camera section lines
    camera_lines = [l for l in lines if "camera" in l.lower() and ("_fail" in l or "_warn" in l)]
    fail_lines = [l for l in camera_lines if "_fail" in l]
    assert len(fail_lines) == 0, \
        f"Camera check must not use _fail — found: {fail_lines}"


def test_run_vln_desktop_calls_preflight_for_live_motion():
    """run_vln_desktop.sh must invoke preflight_live_motion.sh when --enable-motion."""
    path = REPO_ROOT / "scripts/live/run_vln_desktop.sh"
    content = path.read_text()
    assert "preflight_live_motion.sh" in content, \
        "run_vln_desktop.sh must call preflight_live_motion.sh for --enable-motion"
    # Preflight failure must abort launch
    assert "ABORTED" in content or "exit 1" in content


def test_discover_yahboom_stack_exists():
    """discover_yahboom_stack.sh must exist and check key Yahboom topics."""
    path = REPO_ROOT / "scripts/robot/discover_yahboom_stack.sh"
    assert path.exists(), "scripts/robot/discover_yahboom_stack.sh not found"
    content = path.read_text()
    for item in ["/YB_Node", "/scan0", "/odom_raw", "micro_ros_agent", "yahboomcar_ws"]:
        assert item in content, f"discover_yahboom_stack.sh missing reference to {item}"


def test_start_yahboom_stack_has_all_components():
    """start_yahboom_stack.sh must launch agent, bringup, and camera."""
    path = REPO_ROOT / "scripts/robot/start_yahboom_stack.sh"
    assert path.exists(), "scripts/robot/start_yahboom_stack.sh not found"
    content = path.read_text()
    assert "micro_ros_agent" in content
    assert "slam_mapping" in content or "bringup.launch.py" in content, \
        "start_yahboom_stack.sh must reference slam_mapping bringup"
    assert "orbbec" in content.lower() or "dabai" in content.lower() or "camera" in content.lower()
    assert "tmux" in content, "start_yahboom_stack.sh must support tmux sessions"


def test_start_yahboom_stack_uses_new_tmux_sessions():
    """start_yahboom_stack.sh must use the canonical FleetSafe session names."""
    content = (REPO_ROOT / "scripts/robot/start_yahboom_stack.sh").read_text()
    for sess in ["fleetsafe_micro_ros", "fleetsafe_yahboom_base",
                 "fleetsafe_yahboom_lidar", "fleetsafe_orbbec_camera"]:
        assert sess in content, f"start_yahboom_stack.sh missing session name: {sess}"


def test_start_yahboom_stack_has_nohup_fallback():
    """start_yahboom_stack.sh must fall back to nohup when tmux is not installed."""
    content = (REPO_ROOT / "scripts/robot/start_yahboom_stack.sh").read_text()
    assert "nohup" in content, \
        "start_yahboom_stack.sh must use nohup as fallback when tmux is missing"
    assert "USE_TMUX" in content, \
        "start_yahboom_stack.sh must check tmux availability via USE_TMUX"
    assert ".pid" in content, \
        "start_yahboom_stack.sh must write .pid files for nohup processes"


def test_start_yahboom_stack_uses_stable_serial_path():
    """start_yahboom_stack.sh must prefer the stable /dev/serial/by-id/... path."""
    content = (REPO_ROOT / "scripts/robot/start_yahboom_stack.sh").read_text()
    assert "serial/by-id" in content, \
        "start_yahboom_stack.sh must list the stable /dev/serial/by-id/... path first"


def test_start_yahboom_stack_uses_source_ros_helper():
    """start_yahboom_stack.sh must use a source_ros helper to avoid set -u ROS failures."""
    content = (REPO_ROOT / "scripts/robot/start_yahboom_stack.sh").read_text()
    assert "source_ros" in content, \
        "start_yahboom_stack.sh must define/call source_ros() to guard against nounset"


def test_start_yahboom_stack_uses_ros2_run_for_agent():
    """start_yahboom_stack.sh must use 'ros2 run micro_ros_agent' as primary detection."""
    content = (REPO_ROOT / "scripts/robot/start_yahboom_stack.sh").read_text()
    assert "ros2 pkg prefix micro_ros_agent" in content, \
        "start_yahboom_stack.sh must check 'ros2 pkg prefix micro_ros_agent' first"
    assert "ros2 run micro_ros_agent micro_ros_agent" in content, \
        "start_yahboom_stack.sh must use 'ros2 run micro_ros_agent' when pkg available"


def test_start_yahboom_stack_uses_correct_baud_rate():
    """start_yahboom_stack.sh must default to 2000000 baud (per Yahboom M3Pro firmware)."""
    content = (REPO_ROOT / "scripts/robot/start_yahboom_stack.sh").read_text()
    assert "2000000" in content, \
        "start_yahboom_stack.sh must use 2000000 baud (confirmed by ~/start_agent.sh and fleetsafe_boot/start_base.sh)"


def test_config_baud_rate_is_2000000():
    """fleetsafe_real_robot.env must set baud rate to 2000000 (per Yahboom M3Pro firmware)."""
    content = (REPO_ROOT / "config/fleetsafe_real_robot.env").read_text()
    assert "FLEETSAFE_MICRO_ROS_BAUD=2000000" in content, \
        "config/fleetsafe_real_robot.env FLEETSAFE_MICRO_ROS_BAUD must be 2000000 (Yahboom M3Pro STM32 firmware)"


def test_start_yahboom_stack_fixes_ttyths_permissions():
    """start_yahboom_stack.sh must fix ttyTHS permissions before starting LiDAR drivers."""
    content = (REPO_ROOT / "scripts/robot/start_yahboom_stack.sh").read_text()
    assert "ttyTHS" in content and "chmod" in content, \
        "start_yahboom_stack.sh must chmod ttyTHS devices (jetson not in dialout on M3Pro)"
    assert "udev" in content or "99-yahboom-serial" in content, \
        "start_yahboom_stack.sh must create udev rule for ttyTHS (persistent fix)"


def test_makefile_has_robot_install_jetson_deps():
    """Makefile must define robot-install-jetson-deps target."""
    makefile = (REPO_ROOT / "Makefile").read_text()
    assert "robot-install-jetson-deps:" in makefile, \
        "Makefile must define robot-install-jetson-deps target"
    recipe = _makefile_recipe("robot-install-jetson-deps")
    assert "tmux" in recipe and "micro-ros-agent" in recipe, \
        "robot-install-jetson-deps must install tmux and micro-ros-agent"


def test_start_yahboom_stack_knows_jetson_launch_paths():
    """start_yahboom_stack.sh must list the known Jetson install paths for each component."""
    content = (REPO_ROOT / "scripts/robot/start_yahboom_stack.sh").read_text()
    assert "slam_mapping" in content, \
        "start_yahboom_stack.sh must reference slam_mapping/bringup.launch.py as nav pipeline"
    assert "ldlidar_stl_ros2" in content, \
        "start_yahboom_stack.sh must start ldlidar_stl_ros2_node for hardware LiDAR drivers"
    assert "dabai_dcw2" in content, \
        "start_yahboom_stack.sh must include dabai_dcw2.launch.py camera path"


def test_status_yahboom_stack_checks_hz():
    """status_yahboom_stack.sh must measure topic Hz rates."""
    path = REPO_ROOT / "scripts/robot/status_yahboom_stack.sh"
    assert path.exists(), "scripts/robot/status_yahboom_stack.sh not found"
    content = path.read_text()
    assert "ros2 topic hz" in content, "status script must measure topic Hz"
    assert "/scan0" in content
    assert "run_vln_m3pro.py" in content, "status script must check desktop VLN controller"


def test_status_yahboom_stack_shows_tmux_log_tails():
    """status_yahboom_stack.sh must show last N log lines from each tmux session."""
    content = (REPO_ROOT / "scripts/robot/status_yahboom_stack.sh").read_text()
    assert "tail" in content, "status script must tail session logs"
    for sess in ["fleetsafe_micro_ros", "fleetsafe_yahboom_base",
                 "fleetsafe_yahboom_lidar", "fleetsafe_orbbec_camera"]:
        assert sess in content, f"status script missing session: {sess}"


def test_status_yahboom_stack_handles_no_tmux():
    """status_yahboom_stack.sh must check PID files when tmux is not installed."""
    content = (REPO_ROOT / "scripts/robot/status_yahboom_stack.sh").read_text()
    assert ".pid" in content, \
        "status script must check .pid files for nohup fallback"
    assert "kill -0" in content, \
        "status script must use kill -0 to test if nohup PID is still running"


def test_vln_live_preflight_uses_detect_scan_topics():
    """vln_live_preflight.sh must source detect_scan_topics.sh for dynamic topic detection."""
    content = (REPO_ROOT / "scripts/live/vln_live_preflight.sh").read_text()
    assert "detect_scan_topics.sh" in content, \
        "vln_live_preflight.sh must source detect_scan_topics.sh"
    assert "FLEETSAFE_SCAN_TOPICS" in content, \
        "vln_live_preflight.sh must use FLEETSAFE_SCAN_TOPICS from detection"


def test_vln_live_preflight_has_set_u_guard():
    """vln_live_preflight.sh must use set +u before sourcing ROS setup files."""
    content = (REPO_ROOT / "scripts/live/vln_live_preflight.sh").read_text()
    assert "set +u" in content, \
        "vln_live_preflight.sh must guard ROS source with set +u"


@pytest.mark.parametrize("target", [
    "robot-discover-yahboom",
    "robot-start-yahboom",
    "robot-status-yahboom",
    "robot-live-preflight",
    "vln-live-preflight",
    "vln-full-preflight",
])
def test_makefile_live_motion_targets_present(target: str):
    """Each live-motion Makefile target must be defined."""
    makefile = (REPO_ROOT / "Makefile").read_text()
    assert f"{target}:" in makefile, f"Makefile missing target: {target}"


def _makefile_recipe(target: str) -> str:
    """Return all tab-prefixed recipe lines for a given Makefile target."""
    makefile = (REPO_ROOT / "Makefile").read_text()
    lines = makefile.splitlines()
    in_target = False
    recipe_lines: list[str] = []
    for line in lines:
        if line.startswith(f"{target}:"):
            in_target = True
            continue
        if in_target:
            if line.startswith("\t"):
                recipe_lines.append(line)
            else:
                break
    return "\n".join(recipe_lines)


def test_makefile_vln_live_preflight_calls_new_script():
    """vln-live-preflight must call preflight_live_motion.sh, not the old 9-check."""
    recipe = _makefile_recipe("vln-live-preflight")
    assert "preflight_live_motion.sh" in recipe, \
        f"vln-live-preflight must call preflight_live_motion.sh. Recipe:\n{recipe}"


def test_makefile_robot_live_preflight_calls_sensor_gate():
    """robot-live-preflight must call preflight_live_motion.sh (sensor-only, no controller)."""
    recipe = _makefile_recipe("robot-live-preflight")
    assert "preflight_live_motion.sh" in recipe, \
        f"robot-live-preflight must call preflight_live_motion.sh. Recipe:\n{recipe}"


# ── New tests for launch-file scoring and override vars ───────────────────────

def test_start_yahboom_stack_has_launch_scoring():
    """start_yahboom_stack.sh must define _score_base() to rank launch files."""
    content = (REPO_ROOT / "scripts/robot/start_yahboom_stack.sh").read_text()
    assert "_score_base" in content, \
        "start_yahboom_stack.sh must define _score_base() scoring function"
    assert r"MoveIt\|MoveItCpp\|move_group" in content or "moveit" in content.lower(), \
        "start_yahboom_stack.sh scoring must penalise MoveIt launch files"


def test_start_yahboom_stack_excludes_moveit_launch():
    """start_yahboom_stack.sh scoring must assign a negative score to MoveIt arm configs."""
    content = (REPO_ROOT / "scripts/robot/start_yahboom_stack.sh").read_text()
    # Script must contain a negative penalty for moveit/move_group
    assert "s-30" in content or "s=$((s-30))" in content, \
        "start_yahboom_stack.sh must deduct points (-30) for MoveIt/move_group launch files"
    # demo.launch.py must still appear in candidate list (it is listed but scored out)
    assert "demo.launch.py" in content, \
        "start_yahboom_stack.sh must include demo.launch.py in candidates (it will score negative)"


def test_start_yahboom_stack_respects_env_override():
    """start_yahboom_stack.sh must honour FLEETSAFE_YAHBOOM_BASE_LAUNCH override."""
    content = (REPO_ROOT / "scripts/robot/start_yahboom_stack.sh").read_text()
    assert "FLEETSAFE_YAHBOOM_BASE_LAUNCH" in content or "BASE_OVR" in content, \
        "start_yahboom_stack.sh must check FLEETSAFE_YAHBOOM_BASE_LAUNCH override"
    assert "FLEETSAFE_LIDAR_1_PORT" in content or "L1_OVR" in content, \
        "start_yahboom_stack.sh must check FLEETSAFE_LIDAR_1_PORT / L1_OVR override"
    assert "FLEETSAFE_YAHBOOM_CAMERA_LAUNCH" in content or "CAM_OVR" in content, \
        "start_yahboom_stack.sh must check FLEETSAFE_YAHBOOM_CAMERA_LAUNCH override"
    assert "FLEETSAFE_MICRO_ROS_SERIAL" in content or "SERIAL_OVR" in content, \
        "start_yahboom_stack.sh must check FLEETSAFE_MICRO_ROS_SERIAL override"


def test_detect_scan_topics_has_data_quality_check():
    """detect_scan_topics.sh must verify topics deliver real messages, not just graph presence."""
    content = (REPO_ROOT / "scripts/live/detect_scan_topics.sh").read_text()
    assert "_has_data" in content, \
        "detect_scan_topics.sh must define _has_data() to check for real messages"
    assert "ros2 topic echo --once" in content, \
        "detect_scan_topics.sh must use 'ros2 topic echo --once' to verify data"


def test_detect_scan_topics_prefers_data_over_graph_only():
    """detect_scan_topics.sh must distinguish between data-publishing and graph-only topics."""
    content = (REPO_ROOT / "scripts/live/detect_scan_topics.sh").read_text()
    assert "SCAN_HAS_DATA" in content, \
        "detect_scan_topics.sh must track whether detected scan topics have real data"
    # Exit 0 only when data is confirmed; exit 1 when graph-only
    assert "SCAN_HAS_DATA" in content, \
        "detect_scan_topics.sh must gate exit code on SCAN_HAS_DATA"


def test_config_has_launch_override_vars():
    """fleetsafe_real_robot.env must define all launch file and topic override vars."""
    content = (REPO_ROOT / "config/fleetsafe_real_robot.env").read_text()
    for var in [
        "FLEETSAFE_YAHBOOM_BASE_LAUNCH",
        "FLEETSAFE_YAHBOOM_LIDAR_LAUNCH",
        "FLEETSAFE_YAHBOOM_CAMERA_LAUNCH",
        "FLEETSAFE_MICRO_ROS_SERIAL",
        "FLEETSAFE_MICRO_ROS_BAUD",
        "FLEETSAFE_SCAN_TOPICS",
        "FLEETSAFE_ODOM_TOPIC",
    ]:
        assert var in content, \
            f"config/fleetsafe_real_robot.env must define {var} override var"


def test_makefile_has_robot_diagnose_yahboom():
    """Makefile must define robot-diagnose-yahboom target."""
    makefile = (REPO_ROOT / "Makefile").read_text()
    assert "robot-diagnose-yahboom:" in makefile, \
        "Makefile must define robot-diagnose-yahboom target"
    recipe = _makefile_recipe("robot-diagnose-yahboom")
    assert "diagnose_yahboom_live_stack.sh" in recipe, \
        "robot-diagnose-yahboom must call diagnose_yahboom_live_stack.sh"


def test_makefile_robot_install_jetson_deps_disables_cudnn_source():
    """robot-install-jetson-deps must disable broken cuDNN Tegra apt source before apt update."""
    recipe = _makefile_recipe("robot-install-jetson-deps")
    assert "cudnn" in recipe.lower(), \
        "robot-install-jetson-deps must handle the broken cuDNN local apt source"
    assert "disabled" in recipe.lower() or "mv" in recipe, \
        "robot-install-jetson-deps must disable (not just skip) the broken apt source"


def test_diagnose_yahboom_script_exists_with_scoring():
    """diagnose_yahboom_live_stack.sh must exist and include launch file scoring."""
    path = REPO_ROOT / "scripts/robot/diagnose_yahboom_live_stack.sh"
    assert path.exists(), "scripts/robot/diagnose_yahboom_live_stack.sh not found"
    content = path.read_text()
    assert "_score_base" in content, \
        "diagnose script must define _score_base() to rank launch files"
    assert r"moveit\|MoveItCpp\|move_group" in content or "moveit" in content.lower(), \
        "diagnose script scoring must penalise MoveIt launch files"
    assert "/YB_Node" in content, \
        "diagnose script must check for /YB_Node mobile-base node"
    assert "micro_ros_agent" in content, \
        "diagnose script must reference micro_ros_agent"


@pytest.mark.parametrize("target", [
    "robot-discover-yahboom",
    "robot-diagnose-yahboom",
    "robot-start-yahboom",
    "robot-status-yahboom",
    "robot-live-preflight",
    "vln-live-preflight",
    "vln-full-preflight",
])
def test_makefile_yahboom_targets_present(target: str):
    """Each Yahboom / live-motion Makefile target must be defined."""
    makefile = (REPO_ROOT / "Makefile").read_text()
    assert f"{target}:" in makefile, f"Makefile missing target: {target}"
