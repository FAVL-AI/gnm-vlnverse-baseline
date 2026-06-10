"""
tests/test_m3pro_mjcf.py — MuJoCo MJCF smoke tests for the M3Pro structural baseline.

Requires MuJoCo 3.x (in the isaac conda env).  Run with:
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \\
    /home/favl/miniforge3/envs/isaac/bin/python \\
    -m pytest tests/test_m3pro_mjcf.py -v --tb=short

All tests skip automatically if mujoco is not importable.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

try:
    import mujoco
    _HAS_MUJOCO = True
except ImportError:
    _HAS_MUJOCO = False

_REPO_ROOT    = Path(__file__).resolve().parents[1]
MJCF_PATH     = _REPO_ROOT / "fleet_safe_vla/robots/yahboom/m3pro/mjcf/yahboom_m3pro.xml"

# Contract constants (literals so tests are self-contained; must match contract YAML)
WHEEL_RADIUS   = 0.048   # m
WHEEL_HALFLEN  = 0.0125  # m  (full width 0.025 m / 2)
LX             = 0.0775  # m  (wheelbase 0.155 / 2)
LY             = 0.0850  # m  (track width 0.170 / 2)
MAX_WHEEL_RADS = 20.0    # rad/s  (ctrlrange upper bound)
_TOL           = 0.005   # 5 mm geometry tolerance

REQUIRED_JOINTS    = ("fl_wheel_joint", "fr_wheel_joint", "rl_wheel_joint", "rr_wheel_joint")
REQUIRED_ACTUATORS = ("fl_drive",       "fr_drive",       "rl_drive",       "rr_drive")
REQUIRED_GEOMS     = ("fl_wheel_geom",  "fr_wheel_geom",  "rl_wheel_geom",  "rr_wheel_geom")

# All tests that need MuJoCo skip cleanly if not available
pytestmark = pytest.mark.skipif(not _HAS_MUJOCO, reason="mujoco not installed")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def model() -> "mujoco.MjModel":
    """Load MJCF once per test module (construction is ~50 ms)."""
    assert MJCF_PATH.exists(), f"MJCF not found: {MJCF_PATH}"
    return mujoco.MjModel.from_xml_path(str(MJCF_PATH))


@pytest.fixture
def data(model: "mujoco.MjModel") -> "mujoco.MjData":
    """Fresh MjData for each test that modifies simulation state."""
    return mujoco.MjData(model)


# ── File and load ─────────────────────────────────────────────────────────────

def test_mjcf_file_exists():
    assert MJCF_PATH.exists(), f"MJCF not found: {MJCF_PATH}"


def test_mjcf_loads(model):
    assert model is not None


def test_mjcf_model_has_6_bodies(model):
    # world(1) + base_link(1) + fl/fr/rl/rr(4) = 6
    assert model.nbody == 6, f"nbody={model.nbody}, expected 6"


# ── Joints ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("jname", REQUIRED_JOINTS)
def test_joint_exists(model, jname):
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, jname)
    assert jid >= 0, f"Joint '{jname}' not found"


@pytest.mark.parametrize("jname", REQUIRED_JOINTS)
def test_joint_is_hinge(model, jname):
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, jname)
    if jid < 0:
        pytest.skip(f"{jname} not found")
    assert model.jnt_type[jid] == mujoco.mjtJoint.mjJNT_HINGE, \
        f"Joint '{jname}' must be hinge (continuous)"


def test_dof_nq(model):
    # freejoint: 7 (pos×3 + quat×4); 4 hinge wheels: 4 → total 11
    assert model.nq == 11, f"nq={model.nq} (expected 11 = 7+4)"


def test_dof_nv(model):
    # freejoint: 6; 4 hinge wheels: 4 → total 10
    assert model.nv == 10, f"nv={model.nv} (expected 10 = 6+4)"


# ── Actuators ─────────────────────────────────────────────────────────────────

def test_actuator_count(model):
    assert model.nu == 4, f"nu={model.nu}, expected 4 (one per wheel)"


@pytest.mark.parametrize("aname", REQUIRED_ACTUATORS)
def test_actuator_exists(model, aname):
    aid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, aname)
    assert aid >= 0, f"Actuator '{aname}' not found"


@pytest.mark.parametrize("aname", REQUIRED_ACTUATORS)
def test_actuator_ctrlrange(model, aname):
    """ctrlrange upper bound must match max_wheel_rads from contract."""
    aid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, aname)
    if aid < 0:
        pytest.skip(f"{aname} not found")
    upper = model.actuator_ctrlrange[aid, 1]
    assert abs(upper - MAX_WHEEL_RADS) <= 1.0, \
        f"Actuator '{aname}' ctrlrange upper={upper}, expected {MAX_WHEEL_RADS}"


# ── Geoms ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("gname", REQUIRED_GEOMS)
def test_wheel_geom_exists(model, gname):
    gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, gname)
    assert gid >= 0, f"Geom '{gname}' not found"


@pytest.mark.parametrize("gname", REQUIRED_GEOMS)
def test_wheel_geom_radius(model, gname):
    gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, gname)
    if gid < 0:
        pytest.skip(f"{gname} not found")
    r = model.geom_size[gid, 0]
    assert abs(r - WHEEL_RADIUS) <= _TOL, \
        f"Geom '{gname}' radius={r:.4f} m, expected {WHEEL_RADIUS:.4f} m"


@pytest.mark.parametrize("gname", REQUIRED_GEOMS)
def test_wheel_geom_is_cylinder(model, gname):
    gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, gname)
    if gid < 0:
        pytest.skip(f"{gname} not found")
    assert model.geom_type[gid] == mujoco.mjtGeom.mjGEOM_CYLINDER, \
        f"Geom '{gname}' should be cylinder"


# ── Body positions ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bname,ex,ey", [
    ("fl_wheel",  LX,  LY),
    ("fr_wheel",  LX, -LY),
    ("rl_wheel", -LX,  LY),
    ("rr_wheel", -LX, -LY),
])
def test_wheel_body_position(model, bname, ex, ey):
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, bname)
    assert bid >= 0, f"Body '{bname}' not found"
    bx, by, bz = model.body_pos[bid]
    assert abs(bx - ex) <= _TOL, f"{bname}.x = {bx:.4f}, expected {ex:.4f}"
    assert abs(by - ey) <= _TOL, f"{bname}.y = {by:.4f}, expected {ey:.4f}"
    assert abs(bz)       <= _TOL, f"{bname}.z = {bz:.4f}, expected 0"


# ── Simulation stability ──────────────────────────────────────────────────────

def test_zero_control_100_steps_no_nan(model, data):
    for _ in range(100):
        mujoco.mj_step(model, data)
    assert not np.any(np.isnan(data.qpos)), "NaN in qpos (zero control)"
    assert not np.any(np.isnan(data.qvel)), "NaN in qvel (zero control)"


def test_max_forward_100_steps_no_nan(model, data):
    """All wheels at max forward speed (pure translation forward)."""
    data.ctrl[:] = MAX_WHEEL_RADS
    for _ in range(100):
        mujoco.mj_step(model, data)
    assert not np.any(np.isnan(data.qpos)), "NaN in qpos (max forward)"
    assert not np.any(np.isnan(data.qvel)), "NaN in qvel (max forward)"


def test_max_reverse_100_steps_no_nan(model, data):
    data.ctrl[:] = -MAX_WHEEL_RADS
    for _ in range(100):
        mujoco.mj_step(model, data)
    assert not np.any(np.isnan(data.qpos)), "NaN in qpos (max reverse)"
    assert not np.any(np.isnan(data.qvel)), "NaN in qvel (max reverse)"


def test_strafe_left_pattern_no_nan(model, data):
    """Mecanum strafe-left: fl<0, fr>0, rl>0, rr<0."""
    speed = MAX_WHEEL_RADS / 2
    fl = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "fl_drive")
    fr = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "fr_drive")
    rl = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "rl_drive")
    rr = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "rr_drive")
    data.ctrl[fl] = -speed
    data.ctrl[fr] =  speed
    data.ctrl[rl] =  speed
    data.ctrl[rr] = -speed
    for _ in range(100):
        mujoco.mj_step(model, data)
    assert not np.any(np.isnan(data.qpos)), "NaN in qpos (strafe left)"
    assert not np.any(np.isnan(data.qvel)), "NaN in qvel (strafe left)"


def test_yaw_ccw_pattern_no_nan(model, data):
    """Mecanum CCW yaw: fl<0, fr>0, rl<0, rr>0."""
    speed = MAX_WHEEL_RADS / 2
    fl = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "fl_drive")
    fr = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "fr_drive")
    rl = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "rl_drive")
    rr = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "rr_drive")
    data.ctrl[fl] = -speed
    data.ctrl[fr] =  speed
    data.ctrl[rl] = -speed
    data.ctrl[rr] =  speed
    for _ in range(100):
        mujoco.mj_step(model, data)
    assert not np.any(np.isnan(data.qpos)), "NaN in qpos (yaw CCW)"
    assert not np.any(np.isnan(data.qvel)), "NaN in qvel (yaw CCW)"


def test_mixed_holonomic_100_steps_no_nan(model, data):
    """Combined forward + strafe + yaw command for 100 steps."""
    from fleet_safe_vla.robots.yahboom.controllers.obs_adapter_m3pro import (
        mecanum_cmd_to_wheel_speeds,
    )
    ws = mecanum_cmd_to_wheel_speeds(vx=0.3, vy=0.1, wz=0.5)
    fl = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "fl_drive")
    fr = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "fr_drive")
    rl = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "rl_drive")
    rr = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "rr_drive")
    data.ctrl[fl] = np.clip(ws.fl, -MAX_WHEEL_RADS, MAX_WHEEL_RADS)
    data.ctrl[fr] = np.clip(ws.fr, -MAX_WHEEL_RADS, MAX_WHEEL_RADS)
    data.ctrl[rl] = np.clip(ws.rl, -MAX_WHEEL_RADS, MAX_WHEEL_RADS)
    data.ctrl[rr] = np.clip(ws.rr, -MAX_WHEEL_RADS, MAX_WHEEL_RADS)
    for _ in range(100):
        mujoco.mj_step(model, data)
    assert not np.any(np.isnan(data.qpos)), "NaN in qpos (mixed holonomic)"
    assert not np.any(np.isnan(data.qvel)), "NaN in qvel (mixed holonomic)"
