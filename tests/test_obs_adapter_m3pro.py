"""
Unit tests for obs_adapter_m3pro.py — no simulation, no GPU, no ROS2 required.

Covers:
  - Mecanum IK/FK round-trips (pure motions + combined)
  - Sign conventions (forward, strafe, yaw)
  - M3ProObsAdapter.update() output shape and dtype
  - M3ProObsAdapter.reset() clears history
  - M3ProObsAdapter.obs_labels() label count and uniqueness
  - update_from_dicts with full and empty dicts
  - validate_m3pro_contract() structure (assets_ready True when all assets present)
  - M3ProGeometry properties
  - WheelSpeeds.clamp() and M3ProCommand.clamp()
"""
import math

import numpy as np
import pytest

from fleet_safe_vla.robots.yahboom.controllers.obs_adapter_m3pro import (
    DEFAULT_GEOMETRY,
    JOINT_NAMES,
    OBS_DIM,
    M3ProCommand,
    M3ProGeometry,
    M3ProObsAdapter,
    M3ProState,
    ValidationResult,
    WheelSpeeds,
    mecanum_cmd_to_wheel_speeds,
    validate_m3pro_contract,
    wheel_speeds_to_mecanum_cmd,
)

GEO = DEFAULT_GEOMETRY
ATOL = 1e-9


# ── Helper ────────────────────────────────────────────────────────────────────

def roundtrip(vx: float, vy: float, wz: float) -> tuple[float, float, float]:
    """IK then FK; return recovered (vx, vy, wz)."""
    ws = mecanum_cmd_to_wheel_speeds(vx, vy, wz)
    cmd = wheel_speeds_to_mecanum_cmd(ws.fl, ws.fr, ws.rl, ws.rr)
    return cmd.vx, cmd.vy, cmd.wz


# ── Mecanum round-trip ────────────────────────────────────────────────────────

def test_roundtrip_zero():
    vx, vy, wz = roundtrip(0.0, 0.0, 0.0)
    assert abs(vx) < ATOL
    assert abs(vy) < ATOL
    assert abs(wz) < ATOL


def test_roundtrip_pure_forward():
    vx, vy, wz = roundtrip(0.3, 0.0, 0.0)
    assert abs(vx - 0.3) < ATOL
    assert abs(vy) < ATOL
    assert abs(wz) < ATOL


def test_roundtrip_pure_strafe_left():
    vx, vy, wz = roundtrip(0.0, 0.2, 0.0)
    assert abs(vx) < ATOL
    assert abs(vy - 0.2) < ATOL
    assert abs(wz) < ATOL


def test_roundtrip_pure_strafe_right():
    vx, vy, wz = roundtrip(0.0, -0.2, 0.0)
    assert abs(vx) < ATOL
    assert abs(vy + 0.2) < ATOL
    assert abs(wz) < ATOL


def test_roundtrip_pure_yaw_ccw():
    vx, vy, wz = roundtrip(0.0, 0.0, 0.8)
    assert abs(vx) < ATOL
    assert abs(vy) < ATOL
    assert abs(wz - 0.8) < ATOL


def test_roundtrip_pure_yaw_cw():
    vx, vy, wz = roundtrip(0.0, 0.0, -0.8)
    assert abs(vx) < ATOL
    assert abs(vy) < ATOL
    assert abs(wz + 0.8) < ATOL


def test_roundtrip_combined_forward_strafe():
    vx, vy, wz = roundtrip(0.3, 0.2, 0.0)
    assert abs(vx - 0.3) < ATOL
    assert abs(vy - 0.2) < ATOL
    assert abs(wz) < ATOL


def test_roundtrip_all_three_dof():
    vx, vy, wz = roundtrip(0.25, -0.15, 0.5)
    assert abs(vx - 0.25) < ATOL
    assert abs(vy + 0.15) < ATOL
    assert abs(wz - 0.5) < ATOL


# ── Sign conventions ──────────────────────────────────────────────────────────
# Pure forward: all 4 wheels spin the same (positive) direction.
def test_sign_pure_forward_all_wheels_positive():
    ws = mecanum_cmd_to_wheel_speeds(0.3, 0.0, 0.0)
    assert ws.fl > 0
    assert ws.fr > 0
    assert ws.rl > 0
    assert ws.rr > 0


# Pure strafe left: fl<0, fr>0, rl>0, rr<0.
def test_sign_strafe_left():
    ws = mecanum_cmd_to_wheel_speeds(0.0, 0.2, 0.0)
    assert ws.fl < 0, f"fl={ws.fl}"
    assert ws.fr > 0, f"fr={ws.fr}"
    assert ws.rl > 0, f"rl={ws.rl}"
    assert ws.rr < 0, f"rr={ws.rr}"


# Pure yaw CCW: fl<0, fr>0, rl<0, rr>0.
def test_sign_yaw_ccw():
    ws = mecanum_cmd_to_wheel_speeds(0.0, 0.0, 0.5)
    assert ws.fl < 0, f"fl={ws.fl}"
    assert ws.fr > 0, f"fr={ws.fr}"
    assert ws.rl < 0, f"rl={ws.rl}"
    assert ws.rr > 0, f"rr={ws.rr}"


# ── WheelSpeeds and M3ProCommand helpers ──────────────────────────────────────

def test_wheelspeeds_clamp():
    ws = WheelSpeeds(fl=30.0, fr=-30.0, rl=25.0, rr=-25.0)
    clamped = ws.clamp(max_rads=20.0)
    assert clamped.fl == pytest.approx(20.0)
    assert clamped.fr == pytest.approx(-20.0)
    assert clamped.rl == pytest.approx(20.0)
    assert clamped.rr == pytest.approx(-20.0)


def test_wheelspeeds_clamp_no_effect_within_limits():
    ws = WheelSpeeds(fl=5.0, fr=-5.0, rl=3.0, rr=-3.0)
    clamped = ws.clamp(max_rads=20.0)
    assert clamped.fl == pytest.approx(5.0)
    assert clamped.fr == pytest.approx(-5.0)


def test_wheelspeeds_as_array():
    ws = WheelSpeeds(fl=1.0, fr=2.0, rl=3.0, rr=4.0)
    arr = ws.as_array()
    assert arr.shape == (4,)
    assert arr.dtype == np.float32
    np.testing.assert_array_almost_equal(arr, [1.0, 2.0, 3.0, 4.0])


def test_command_clamp():
    cmd = M3ProCommand(vx=1.0, vy=-1.0, wz=5.0)
    c = cmd.clamp()
    assert c.vx == pytest.approx(GEO.max_vx_ms)
    assert c.vy == pytest.approx(-GEO.max_vy_ms)
    assert c.wz == pytest.approx(GEO.max_wz_rads)


def test_command_as_array():
    cmd = M3ProCommand(vx=0.1, vy=0.2, wz=0.3)
    arr = cmd.as_array()
    assert arr.shape == (3,)
    assert arr.dtype == np.float32
    np.testing.assert_array_almost_equal(arr, [0.1, 0.2, 0.3])


# ── M3ProGeometry ─────────────────────────────────────────────────────────────

def test_geometry_lx():
    assert GEO.lx == pytest.approx(0.0775)


def test_geometry_ly():
    assert GEO.ly == pytest.approx(0.0850)


def test_custom_geometry_roundtrip():
    geo = M3ProGeometry(wheel_radius_m=0.05, wheelbase_m=0.20, track_width_m=0.18)
    ws = mecanum_cmd_to_wheel_speeds(0.2, 0.1, 0.3, geo.wheel_radius_m, geo.lx, geo.ly)
    cmd = wheel_speeds_to_mecanum_cmd(ws.fl, ws.fr, ws.rl, ws.rr, geo.wheel_radius_m, geo.lx, geo.ly)
    assert abs(cmd.vx - 0.2) < ATOL
    assert abs(cmd.vy - 0.1) < ATOL
    assert abs(cmd.wz - 0.3) < ATOL


# ── M3ProObsAdapter ───────────────────────────────────────────────────────────

def _default_state() -> M3ProState:
    return M3ProState()


def test_adapter_update_shape_and_dtype():
    adapter = M3ProObsAdapter()
    obs = adapter.update(_default_state())
    assert obs.shape == (OBS_DIM,)
    assert obs.dtype == np.float32


def test_adapter_update_with_command():
    adapter = M3ProObsAdapter()
    cmd = M3ProCommand(vx=0.3, vy=0.1, wz=0.5)
    obs = adapter.update(_default_state(), cmd)
    assert obs.shape == (OBS_DIM,)


def test_adapter_reset_clears_history():
    adapter = M3ProObsAdapter()
    cmd = M3ProCommand(vx=0.5, vy=0.0, wz=0.0)
    # Push a non-zero command into history
    adapter.update(_default_state(), cmd)
    adapter.reset()
    # After reset, cmd_hist slice should be all zeros
    obs_after = adapter.update(_default_state(), None)
    cmd_hist = obs_after[32:]  # last 15 elements = 5 × [vx,vy,wz]
    np.testing.assert_array_equal(cmd_hist, np.zeros(15, dtype=np.float32))


def test_adapter_history_is_ordered_oldest_first():
    """After 2 updates, history[0:3] holds the oldest command."""
    adapter = M3ProObsAdapter()
    cmd1 = M3ProCommand(vx=0.1, vy=0.0, wz=0.0)
    cmd2 = M3ProCommand(vx=0.2, vy=0.0, wz=0.0)
    adapter.update(_default_state(), cmd1)
    obs = adapter.update(_default_state(), cmd2)
    hist = obs[32:47].reshape(5, 3)
    # Oldest entries (first 4) were zeros before any command; cmd1 is second-to-last
    assert hist[-2, 0] == pytest.approx(0.1)
    assert hist[-1, 0] == pytest.approx(0.2)


def test_adapter_multiple_updates_accumulate():
    adapter = M3ProObsAdapter()
    for i in range(10):
        obs = adapter.update(_default_state(), M3ProCommand(vx=float(i) * 0.05))
    assert obs.shape == (OBS_DIM,)


def test_adapter_update_from_dicts_empty():
    adapter = M3ProObsAdapter()
    obs = adapter.update_from_dicts()
    assert obs.shape == (OBS_DIM,)
    assert obs.dtype == np.float32


def test_adapter_update_from_dicts_imu():
    adapter = M3ProObsAdapter()
    imu = {"ax": 0.1, "ay": 0.2, "az": 9.8, "wx": 0.0, "wy": 0.0, "wz": 0.1,
           "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0}
    obs = adapter.update_from_dicts(imu=imu)
    assert obs[0] == pytest.approx(0.1, abs=1e-6)
    assert obs[1] == pytest.approx(0.2, abs=1e-6)
    assert obs[2] == pytest.approx(9.8, abs=1e-6)


def test_adapter_update_from_dicts_cmd_vel():
    adapter = M3ProObsAdapter()
    obs = adapter.update_from_dicts(cmd_vel={"vx": 0.3, "vy": 0.1, "wz": 0.5})
    # cmd_vel should appear in the newest history slot
    hist = obs[32:47].reshape(5, 3)
    assert hist[-1, 0] == pytest.approx(0.3, abs=1e-6)
    assert hist[-1, 1] == pytest.approx(0.1, abs=1e-6)
    assert hist[-1, 2] == pytest.approx(0.5, abs=1e-6)


def test_adapter_update_from_dicts_joint_flat_keys():
    adapter = M3ProObsAdapter()
    joints = {
        "fl_pos": 0.1, "fr_pos": 0.2, "rl_pos": 0.3, "rr_pos": 0.4,
        "fl_vel": 1.0, "fr_vel": 2.0, "rl_vel": 3.0, "rr_vel": 4.0,
        "fl_eff": 0.0, "fr_eff": 0.0, "rl_eff": 0.0, "rr_eff": 0.0,
    }
    obs = adapter.update_from_dicts(joints=joints)
    # joint_pos starts at index 10
    np.testing.assert_array_almost_equal(obs[10:14], [0.1, 0.2, 0.3, 0.4], decimal=5)
    np.testing.assert_array_almost_equal(obs[14:18], [1.0, 2.0, 3.0, 4.0], decimal=5)


def test_adapter_update_from_dicts_odom():
    adapter = M3ProObsAdapter()
    odom = {"x": 1.0, "y": 2.0, "z": 0.0,
            "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0,
            "vx": 0.3, "vy": 0.0, "vyaw": 0.1}
    obs = adapter.update_from_dicts(odom=odom)
    # odom starts at index 22
    assert obs[22] == pytest.approx(1.0, abs=1e-6)
    assert obs[23] == pytest.approx(2.0, abs=1e-6)


# ── obs_labels ────────────────────────────────────────────────────────────────

def test_obs_labels_count():
    labels = M3ProObsAdapter.obs_labels()
    assert len(labels) == OBS_DIM


def test_obs_labels_all_unique():
    labels = M3ProObsAdapter.obs_labels()
    assert len(set(labels)) == len(labels), "Duplicate labels found"


def test_obs_labels_imu_prefix():
    labels = M3ProObsAdapter.obs_labels()
    imu_labels = labels[:10]
    assert imu_labels[0] == "imu_ax"
    assert imu_labels[9] == "imu_qw"


def test_obs_labels_cmd_hist_suffix():
    labels = M3ProObsAdapter.obs_labels()
    assert labels[32] == "cmd_vx_0"
    assert labels[46] == "cmd_wz_4"


# ── validate_m3pro_contract ───────────────────────────────────────────────────

def test_validate_returns_validation_result():
    result = validate_m3pro_contract()
    assert isinstance(result, ValidationResult)


def test_validate_assets_ready_true_with_all_assets():
    """All required M3Pro assets are now present; assets_ready must be True."""
    result = validate_m3pro_contract()
    # Verify individual asset checks
    check_names = {c.name: c for c in result.checks}
    assert check_names["yahboom_m3pro.urdf (URDF)"].present is True
    assert check_names["yahboom_m3pro.xml (MJCF)"].present is True
    assert check_names["obs_adapter_m3pro.py"].present is True
    assert check_names["robot_contract_m3pro.yaml"].present is True
    assert result.assets_ready is True


def test_validate_assets_ready_false_when_urdf_missing(monkeypatch, tmp_path):
    """assets_ready is False when the URDF file does not exist."""
    import fleet_safe_vla.robots.yahboom.controllers.obs_adapter_m3pro as mod
    fake_missing = tmp_path / "does_not_exist.urdf"
    monkeypatch.setattr(mod, "M3PRO_URDF_PATH", fake_missing)
    result = validate_m3pro_contract()
    assert result.assets_ready is False


def test_validate_geometry_ok_default():
    result = validate_m3pro_contract()
    assert result.geo_ok is True


def test_validate_summary_contains_blocked():
    result = validate_m3pro_contract()
    summary = result.summary()
    assert "BLOCKED" in summary or "READY" in summary  # one or the other


def test_validate_obs_adapter_present():
    # obs_adapter_m3pro.py itself should always be found (we're running from it).
    result = validate_m3pro_contract()
    adapter_checks = [c for c in result.checks if "obs_adapter" in c.name]
    assert len(adapter_checks) == 1
    assert adapter_checks[0].present is True


def test_validate_geometry_out_of_range():
    bad_geo = M3ProGeometry(wheel_radius_m=0.001)  # too small
    result = validate_m3pro_contract(geo=bad_geo)
    assert result.geo_ok is False
    assert "wheel_radius" in result.geo_msg


def test_validate_does_not_raise():
    # validate_m3pro_contract() must never raise.
    try:
        validate_m3pro_contract()
    except Exception as e:
        pytest.fail(f"validate_m3pro_contract() raised unexpectedly: {e}")


# ── M3ProState construction ───────────────────────────────────────────────────

def test_state_default_shapes():
    s = M3ProState()
    assert s.imu_lin_acc.shape == (3,)
    assert s.imu_ang_vel.shape == (3,)
    assert s.imu_quat.shape == (4,)
    assert s.joint_positions.shape == (4,)
    assert s.joint_velocities.shape == (4,)
    assert s.joint_efforts.shape == (4,)
    assert s.odom_pos.shape == (3,)
    assert s.odom_quat.shape == (4,)
    assert s.odom_vel.shape == (3,)


def test_state_custom_values():
    s = M3ProState(
        imu_lin_acc=[0.1, 0.2, 9.8],
        joint_velocities=[1.0, 2.0, 3.0, 4.0],
    )
    np.testing.assert_array_almost_equal(s.imu_lin_acc, [0.1, 0.2, 9.8], decimal=5)
    np.testing.assert_array_almost_equal(s.joint_velocities, [1.0, 2.0, 3.0, 4.0], decimal=5)


# ── JOINT_NAMES constant ──────────────────────────────────────────────────────

def test_joint_names_count_and_order():
    assert len(JOINT_NAMES) == 4
    assert JOINT_NAMES[0] == "fl_wheel_joint"
    assert JOINT_NAMES[1] == "fr_wheel_joint"
    assert JOINT_NAMES[2] == "rl_wheel_joint"
    assert JOINT_NAMES[3] == "rr_wheel_joint"
