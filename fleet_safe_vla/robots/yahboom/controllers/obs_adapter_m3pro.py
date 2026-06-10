"""
obs_adapter_m3pro.py — Observation adapter for the Yahboom RosMaster M3Pro

Provides:
  M3ProGeometry           physical constants (wheel radius, wheelbase, track)
  M3ProState              typed sensor state container
  M3ProCommand            typed 3-DoF holonomic velocity command
  WheelSpeeds             typed 4-wheel (fl/fr/rl/rr) velocity container
  mecanum_cmd_to_wheel_speeds()   inverse kinematics: [vx,vy,wz] → wheel rad/s
  wheel_speeds_to_mecanum_cmd()   forward kinematics: wheel rad/s → [vx,vy,wz]
  M3ProObsAdapter         stateful 47-dim obs vector builder (matches contract)
  validate_m3pro_contract()       asset existence + geometry sanity check

All kinematics functions are pure Python/NumPy — no simulation engine required.

Contract reference: fleet_safe_vla/robots/yahboom/config/robot_contract_m3pro.yaml

Observation vector layout (47 dims):
  [0:10]   imu        ax,ay,az,wx,wy,wz,qx,qy,qz,qw
  [10:22]  joints     fl_pos,fr_pos,rl_pos,rr_pos, fl_vel,fr_vel,rl_vel,rr_vel,
                      fl_eff,fr_eff,rl_eff,rr_eff
  [22:32]  odom       x,y,z,qx,qy,qz,qw,vx,vy,vyaw
  [32:47]  cmd_hist   5 × [vx,vy,wz]  (oldest first)
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

import numpy as np


# ── Canonical asset paths ─────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[4]
_M3PRO_DIR = _REPO_ROOT / "fleet_safe_vla/robots/yahboom/m3pro"

M3PRO_URDF_PATH = _M3PRO_DIR / "urdf" / "yahboom_m3pro.urdf"
M3PRO_MJCF_PATH = _M3PRO_DIR / "mjcf" / "yahboom_m3pro.xml"
M3PRO_USD_DIR   = _M3PRO_DIR / "usd"
CONTRACT_PATH   = _REPO_ROOT / "fleet_safe_vla/robots/yahboom/config/robot_contract_m3pro.yaml"

JOINT_NAMES = ("fl_wheel_joint", "fr_wheel_joint", "rl_wheel_joint", "rr_wheel_joint")
OBS_DIM       = 47   # from robot_contract_m3pro.yaml §obs_vector_dim
CMD_HIST_LEN  = 5    # 5-step history × 3 dims = 15


# ── Physical geometry ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class M3ProGeometry:
    """
    Physical constants for the M3Pro mecanum drivetrain.

    Default values are from robot_contract_m3pro.yaml.  Override with
    measured values once the physical robot is characterised.

    All values in SI units (metres, radians).
    """
    wheel_radius_m: float = 0.048    # verify with calipers
    wheelbase_m:    float = 0.155    # front-rear axle centre distance
    track_width_m:  float = 0.170    # left-right wheel centre distance
    max_wheel_rads: float = 20.0     # rad/s — motor max speed
    max_vx_ms:      float = 0.5      # m/s
    max_vy_ms:      float = 0.5      # m/s
    max_wz_rads:    float = 1.0      # rad/s

    @property
    def lx(self) -> float:
        """Half wheelbase (front-rear half-distance)."""
        return self.wheelbase_m / 2.0   # = 0.0775 m

    @property
    def ly(self) -> float:
        """Half track width (left-right half-distance)."""
        return self.track_width_m / 2.0  # = 0.0850 m


# Singleton default geometry — used by all functions when not overridden
DEFAULT_GEOMETRY = M3ProGeometry()


# ── Typed containers ──────────────────────────────────────────────────────────

@dataclass
class M3ProCommand:
    """
    3-DoF holonomic velocity command for the M3Pro.

    Units: m/s (vx, vy), rad/s (wz).
    vx > 0 = forward, vy > 0 = left strafe, wz > 0 = counter-clockwise.
    """
    vx: float = 0.0   # forward/backward  [−0.5, 0.5] m/s
    vy: float = 0.0   # strafe left/right [−0.5, 0.5] m/s
    wz: float = 0.0   # yaw rate          [−1.0, 1.0] rad/s

    def clamp(self, geo: M3ProGeometry = DEFAULT_GEOMETRY) -> "M3ProCommand":
        """Return a new command clamped to the geometry's velocity limits."""
        return M3ProCommand(
            vx=float(np.clip(self.vx, -geo.max_vx_ms,  geo.max_vx_ms)),
            vy=float(np.clip(self.vy, -geo.max_vy_ms,  geo.max_vy_ms)),
            wz=float(np.clip(self.wz, -geo.max_wz_rads, geo.max_wz_rads)),
        )

    def as_array(self) -> np.ndarray:
        return np.array([self.vx, self.vy, self.wz], dtype=np.float32)


@dataclass
class WheelSpeeds:
    """
    4-wheel velocity targets in rad/s.

    Layout matches joint_names:
      fl = front-left   fr = front-right
      rl = rear-left    rr = rear-right

    Sign convention: positive = forward rotation.
    """
    fl: float = 0.0
    fr: float = 0.0
    rl: float = 0.0
    rr: float = 0.0

    def clamp(self, max_rads: float = DEFAULT_GEOMETRY.max_wheel_rads) -> "WheelSpeeds":
        """Return a new WheelSpeeds with all values clamped to ±max_rads."""
        return WheelSpeeds(
            fl=float(np.clip(self.fl, -max_rads, max_rads)),
            fr=float(np.clip(self.fr, -max_rads, max_rads)),
            rl=float(np.clip(self.rl, -max_rads, max_rads)),
            rr=float(np.clip(self.rr, -max_rads, max_rads)),
        )

    def as_array(self) -> np.ndarray:
        return np.array([self.fl, self.fr, self.rl, self.rr], dtype=np.float32)


@dataclass
class M3ProState:
    """
    Full sensor state snapshot from the physical M3Pro or simulation.

    Each field mirrors a ROS2 topic payload.  Fill from the appropriate
    source (real robot: ROS2 callbacks; sim: Isaac Lab robot.data).
    """
    # /imu/data — sensor_msgs/Imu
    imu_lin_acc: np.ndarray = field(default_factory=lambda: np.zeros(3, np.float32))
    imu_ang_vel: np.ndarray = field(default_factory=lambda: np.zeros(3, np.float32))
    imu_quat:    np.ndarray = field(default_factory=lambda: np.array([0., 0., 0., 1.], np.float32))

    # /joint_states — sensor_msgs/JointState (fl/fr/rl/rr order)
    joint_positions:  np.ndarray = field(default_factory=lambda: np.zeros(4, np.float32))
    joint_velocities: np.ndarray = field(default_factory=lambda: np.zeros(4, np.float32))
    joint_efforts:    np.ndarray = field(default_factory=lambda: np.zeros(4, np.float32))

    # /odom — nav_msgs/Odometry
    odom_pos:  np.ndarray = field(default_factory=lambda: np.zeros(3, np.float32))
    odom_quat: np.ndarray = field(default_factory=lambda: np.array([0., 0., 0., 1.], np.float32))
    odom_vel:  np.ndarray = field(default_factory=lambda: np.zeros(3, np.float32))  # [vx, vy, vyaw]

    def __post_init__(self):
        self.imu_lin_acc  = np.asarray(self.imu_lin_acc,  dtype=np.float32).flatten()[:3]
        self.imu_ang_vel  = np.asarray(self.imu_ang_vel,  dtype=np.float32).flatten()[:3]
        self.imu_quat     = np.asarray(self.imu_quat,     dtype=np.float32).flatten()[:4]
        self.joint_positions  = np.asarray(self.joint_positions,  dtype=np.float32).flatten()[:4]
        self.joint_velocities = np.asarray(self.joint_velocities, dtype=np.float32).flatten()[:4]
        self.joint_efforts    = np.asarray(self.joint_efforts,    dtype=np.float32).flatten()[:4]
        self.odom_pos  = np.asarray(self.odom_pos,  dtype=np.float32).flatten()[:3]
        self.odom_quat = np.asarray(self.odom_quat, dtype=np.float32).flatten()[:4]
        self.odom_vel  = np.asarray(self.odom_vel,  dtype=np.float32).flatten()[:3]


# ── Mecanum kinematics ────────────────────────────────────────────────────────

def mecanum_cmd_to_wheel_speeds(
    vx: float,
    vy: float,
    wz: float,
    wheel_radius: float = DEFAULT_GEOMETRY.wheel_radius_m,
    lx: float = DEFAULT_GEOMETRY.lx,
    ly: float = DEFAULT_GEOMETRY.ly,
) -> WheelSpeeds:
    """
    Inverse mecanum kinematics: body velocity command → wheel angular speeds.

    From robot_contract_m3pro.yaml:
      fl = (vx - vy - (lx + ly) * wz) / r
      fr = (vx + vy + (lx + ly) * wz) / r
      rl = (vx + vy - (lx + ly) * wz) / r
      rr = (vx - vy + (lx + ly) * wz) / r

    Where:
      vx, vy  — body-frame linear velocities [m/s]
      wz      — yaw rate [rad/s]
      lx      — half wheelbase  (axle-to-axle / 2)   [m]
      ly      — half track width (left-to-right / 2)  [m]
      r       — wheel radius                           [m]

    Derivation of sign conventions (verified by round-trip test):
      Pure forward (vx>0, vy=0, wz=0):  all wheels positive → robot moves fwd
      Pure strafe  (vx=0, vy>0, wz=0):  fl<0, fr>0, rl>0, rr<0  → moves left
      Pure yaw     (vx=0, vy=0, wz>0):  fl<0, fr>0, rl<0, rr>0  → turns CCW

    Args:
      vx, vy:       linear body velocity [m/s]
      wz:           yaw angular velocity [rad/s]
      wheel_radius: r [m]
      lx:           half wheelbase [m]
      ly:           half track width [m]

    Returns:
      WheelSpeeds with fl/fr/rl/rr in rad/s.
    """
    L = lx + ly
    r = wheel_radius
    return WheelSpeeds(
        fl=(vx - vy - L * wz) / r,
        fr=(vx + vy + L * wz) / r,
        rl=(vx + vy - L * wz) / r,
        rr=(vx - vy + L * wz) / r,
    )


def wheel_speeds_to_mecanum_cmd(
    fl: float,
    fr: float,
    rl: float,
    rr: float,
    wheel_radius: float = DEFAULT_GEOMETRY.wheel_radius_m,
    lx: float = DEFAULT_GEOMETRY.lx,
    ly: float = DEFAULT_GEOMETRY.ly,
) -> M3ProCommand:
    """
    Forward mecanum kinematics: wheel angular speeds → body velocity command.

    Inverse of mecanum_cmd_to_wheel_speeds.  Derived by solving the 4×3 system:

      [ fl ]   [ 1/r  -1/r  -(lx+ly)/r ] [ vx ]
      [ fr ] = [ 1/r   1/r   (lx+ly)/r ] [ vy ]
      [ rl ]   [ 1/r   1/r  -(lx+ly)/r ] [ wz ]
      [ rr ]   [ 1/r  -1/r   (lx+ly)/r ]

    Least-squares solution (Moore–Penrose pseudoinverse of the 4×3 matrix):
      vx  =  r * (fl + fr + rl + rr) / 4
      vy  = -r * (fl - fr - rl + rr) / 4
      wz  =  r * (-fl + fr - rl + rr) / (4 * (lx + ly))

    Verified: round-trip error < 1e-10 for all pure and mixed motions.

    Args:
      fl, fr, rl, rr: wheel angular velocities [rad/s]
      wheel_radius:   r [m]
      lx:             half wheelbase [m]
      ly:             half track width [m]

    Returns:
      M3ProCommand (vx [m/s], vy [m/s], wz [rad/s]).
    """
    L = lx + ly
    r = wheel_radius
    vx = r * (fl + fr + rl + rr) / 4.0
    vy = -r * (fl - fr - rl + rr) / 4.0
    wz = r * (-fl + fr - rl + rr) / (4.0 * L)
    return M3ProCommand(vx=vx, vy=vy, wz=wz)


# ── Stateful obs adapter ──────────────────────────────────────────────────────

class M3ProObsAdapter:
    """
    Converts sensor data from any source (ROS2, Isaac Lab, MuJoCo) into
    the standardised 47-dim flat observation vector defined in
    robot_contract_m3pro.yaml §obs_vector_dim.

    Observation layout:
      [0:10]  imu:      ax,ay,az,wx,wy,wz,qx,qy,qz,qw
      [10:22] joints:   fl_pos,fr_pos,rl_pos,rr_pos,
                        fl_vel,fr_vel,rl_vel,rr_vel,
                        fl_eff,fr_eff,rl_eff,rr_eff
      [22:32] odom:     x,y,z,qx,qy,qz,qw,vx,vy,vyaw
      [32:47] cmd_hist: 5 × [vx,vy,wz]  (oldest first)
      TOTAL:  47

    Usage:
        adapter = M3ProObsAdapter()
        obs = adapter.update(state, command)
        # or with dicts (for ROS2 bridge compatibility):
        obs = adapter.update_from_dicts(imu={...}, joints={...}, odom={...}, cmd_vel={...})
    """

    def __init__(self):
        self._cmd_history: deque[np.ndarray] = deque(
            [np.zeros(3, dtype=np.float32)] * CMD_HIST_LEN,
            maxlen=CMD_HIST_LEN,
        )

    def update(self, state: M3ProState, command: M3ProCommand | None = None) -> np.ndarray:
        """
        Build 47-dim obs from a typed M3ProState + optional M3ProCommand.

        Args:
            state:   Full sensor snapshot.
            command: Last issued velocity command (recorded in history).
                     Pass None to append a zero command.

        Returns:
            obs: (47,) float32
        """
        cmd_vec = command.as_array() if command is not None else np.zeros(3, dtype=np.float32)
        self._cmd_history.append(cmd_vec.astype(np.float32))

        imu_vec = np.concatenate([
            state.imu_lin_acc,   # [3]
            state.imu_ang_vel,   # [3]
            state.imu_quat,      # [4]
        ])                       # total: [10]

        joint_vec = np.concatenate([
            state.joint_positions,   # [4]
            state.joint_velocities,  # [4]
            state.joint_efforts,     # [4]
        ])                           # total: [12]

        odom_vec = np.concatenate([
            state.odom_pos,    # [3]
            state.odom_quat,   # [4]
            state.odom_vel,    # [3]
        ])                     # total: [10]

        history_vec = np.array(list(self._cmd_history), dtype=np.float32).flatten()  # [15]

        obs = np.concatenate([imu_vec, joint_vec, odom_vec, history_vec]).astype(np.float32)
        assert obs.shape == (OBS_DIM,), f"obs shape mismatch: {obs.shape} != ({OBS_DIM},)"
        return obs

    def update_from_dicts(
        self,
        imu: dict | None = None,
        joints: dict | None = None,
        odom: dict | None = None,
        cmd_vel: dict | None = None,
    ) -> np.ndarray:
        """
        Dict-based update for ROS2 bridge compatibility.

        Dict keys match the ROS2 bridge _state payload format:
          imu:    {ax, ay, az, wx, wy, wz, qx, qy, qz, qw}
          joints: {fl_pos, fr_pos, rl_pos, rr_pos,
                   fl_vel, fr_vel, rl_vel, rr_vel,
                   fl_eff, fr_eff, rl_eff, rr_eff}  — or
                  JointState dict {names: [...], positions: [...], velocities: [...]}
          odom:   {x, y, z, qx, qy, qz, qw, vx, vy, vyaw}
          cmd_vel:{vx, vy, wz}
        """
        state = M3ProState(
            imu_lin_acc=_parse_imu_acc(imu),
            imu_ang_vel=_parse_imu_gyr(imu),
            imu_quat=_parse_imu_quat(imu),
            joint_positions=_parse_joint_field(joints, "pos"),
            joint_velocities=_parse_joint_field(joints, "vel"),
            joint_efforts=_parse_joint_field(joints, "eff"),
            odom_pos=_parse_odom_pos(odom),
            odom_quat=_parse_odom_quat(odom),
            odom_vel=_parse_odom_vel(odom),
        )
        cmd = None
        if cmd_vel is not None:
            cmd = M3ProCommand(
                vx=float(cmd_vel.get("vx", 0.0)),
                vy=float(cmd_vel.get("vy", 0.0)),
                wz=float(cmd_vel.get("wz", 0.0)),
            )
        return self.update(state, cmd)

    def reset(self) -> None:
        """Clear cmd_vel history (call at episode reset)."""
        self._cmd_history = deque(
            [np.zeros(3, dtype=np.float32)] * CMD_HIST_LEN,
            maxlen=CMD_HIST_LEN,
        )

    @staticmethod
    def obs_labels() -> list[str]:
        """Human-readable name for each obs dimension (for TensorBoard logging)."""
        labels = (
            ["imu_ax", "imu_ay", "imu_az", "imu_wx", "imu_wy", "imu_wz",
             "imu_qx", "imu_qy", "imu_qz", "imu_qw"]
            + [f"{j}_{f}" for f in ("pos", "vel", "eff")
               for j in ("fl", "fr", "rl", "rr")]
            + ["od_x", "od_y", "od_z", "od_qx", "od_qy", "od_qz", "od_qw",
               "od_vx", "od_vy", "od_vyaw"]
        )
        for i in range(CMD_HIST_LEN):
            labels += [f"cmd_vx_{i}", f"cmd_vy_{i}", f"cmd_wz_{i}"]
        assert len(labels) == OBS_DIM, f"label count mismatch: {len(labels)}"
        return labels


# ── Dict parsers (shared between update_from_dicts and ROS2 bridge) ──────────

def _parse_imu_acc(d: dict | None) -> np.ndarray:
    if not d:
        return np.zeros(3, np.float32)
    return np.array([d.get("ax", 0), d.get("ay", 0), d.get("az", 0)], np.float32)

def _parse_imu_gyr(d: dict | None) -> np.ndarray:
    if not d:
        return np.zeros(3, np.float32)
    return np.array([d.get("wx", 0), d.get("wy", 0), d.get("wz", 0)], np.float32)

def _parse_imu_quat(d: dict | None) -> np.ndarray:
    if not d:
        return np.array([0., 0., 0., 1.], np.float32)
    return np.array([d.get("qx", 0), d.get("qy", 0), d.get("qz", 0), d.get("qw", 1)], np.float32)

def _parse_joint_field(d: dict | None, field: str) -> np.ndarray:
    """Parse joint field from ROS2 bridge dict or JointState-style dict."""
    if not d:
        return np.zeros(4, np.float32)
    # Flat keys: fl_pos, fr_pos, etc.
    flat_keys = [f"{j}_{field}" for j in ("fl", "fr", "rl", "rr")]
    if flat_keys[0] in d:
        return np.array([d.get(k, 0) for k in flat_keys], np.float32)
    # Isaac bridge joint dict: {names: [...], positions: [...], velocities: [...]}
    field_map = {"pos": "positions", "vel": "velocities", "eff": "efforts"}
    arr_key = field_map.get(field, field)
    names = d.get("names", JOINT_NAMES)
    vals  = d.get(arr_key, [0.0] * len(names))
    n2i   = {n: i for i, n in enumerate(names)}
    return np.array(
        [vals[n2i[j]] if j in n2i and n2i[j] < len(vals) else 0.0 for j in JOINT_NAMES],
        np.float32,
    )

def _parse_odom_pos(d: dict | None) -> np.ndarray:
    if not d:
        return np.zeros(3, np.float32)
    return np.array([d.get("x", 0), d.get("y", 0), d.get("z", 0)], np.float32)

def _parse_odom_quat(d: dict | None) -> np.ndarray:
    if not d:
        return np.array([0., 0., 0., 1.], np.float32)
    return np.array([d.get("qx", 0), d.get("qy", 0), d.get("qz", 0), d.get("qw", 1)], np.float32)

def _parse_odom_vel(d: dict | None) -> np.ndarray:
    if not d:
        return np.zeros(3, np.float32)
    return np.array([d.get("vx", 0), d.get("vy", 0), d.get("vyaw", 0)], np.float32)


# ── Contract validation ───────────────────────────────────────────────────────

@dataclass
class AssetCheck:
    name:     str
    path:     Path
    required: bool    # True = blocks Stage 1+; False = needed for later stages
    present:  bool = False
    note:     str = ""

    def status(self) -> str:
        if self.present:
            return "✓"
        return "✗" if self.required else "?"

    def __str__(self) -> str:
        return f"  {self.status()}  {self.name:<44} {self.note}"


@dataclass
class ValidationResult:
    checks:  list[AssetCheck] = field(default_factory=list)
    geo_ok:  bool = True
    geo_msg: str = ""

    @property
    def assets_ready(self) -> bool:
        """True only if all *required* assets exist."""
        return all(c.present for c in self.checks if c.required)

    @property
    def all_present(self) -> bool:
        return all(c.present for c in self.checks)

    def summary(self) -> str:
        lines = ["M3Pro Asset Validation", "=" * 44]
        for c in self.checks:
            lines.append(str(c))
        lines.append("")
        if self.geo_ok:
            lines.append("  Geometry constants: OK")
        else:
            lines.append(f"  Geometry constants: WARN — {self.geo_msg}")
        lines.append("")
        if self.assets_ready:
            lines.append("  READY — Stage 1 training can proceed.")
        else:
            missing = [c.name for c in self.checks if c.required and not c.present]
            lines.append(f"  BLOCKED — missing required assets: {', '.join(missing)}")
            lines.append(f"  See: {_M3PRO_DIR / 'ASSET_REQUIREMENTS.md'}")
        return "\n".join(lines)


def validate_m3pro_contract(geo: M3ProGeometry = DEFAULT_GEOMETRY) -> ValidationResult:
    """
    Check that required M3Pro simulation assets exist and geometry is sane.

    Does NOT raise — returns a ValidationResult so callers can handle
    failures in a structured way (CLI table, JSON report, CI assertion).

    To block training on failure:
        result = validate_m3pro_contract()
        if not result.assets_ready:
            raise RuntimeError(result.summary())

    Args:
        geo: Geometry to validate against contract bounds.

    Returns:
        ValidationResult with per-asset checks and geometry validation.
    """
    checks = [
        AssetCheck(
            name="yahboom_m3pro.urdf (URDF)",
            path=M3PRO_URDF_PATH,
            required=True,
            note="→ m3pro/urdf/PLACEHOLDER.md",
        ),
        AssetCheck(
            name="yahboom_m3pro.xml (MJCF)",
            path=M3PRO_MJCF_PATH,
            required=False,
            note="needed for MuJoCo validation",
        ),
        AssetCheck(
            name="obs_adapter_m3pro.py",
            path=Path(__file__),
            required=True,
            note="",
        ),
        AssetCheck(
            name="robot_contract_m3pro.yaml",
            path=CONTRACT_PATH,
            required=True,
            note="",
        ),
    ]

    for c in checks:
        c.present = c.path.exists()

    # ── Geometry sanity check ─────────────────────────────────────────────
    geo_warnings = []
    if not (0.03 <= geo.wheel_radius_m <= 0.08):
        geo_warnings.append(f"wheel_radius={geo.wheel_radius_m:.3f} m out of range [0.03, 0.08]")
    if not (0.08 <= geo.wheelbase_m <= 0.25):
        geo_warnings.append(f"wheelbase={geo.wheelbase_m:.3f} m out of range [0.08, 0.25]")
    if not (0.08 <= geo.track_width_m <= 0.25):
        geo_warnings.append(f"track_width={geo.track_width_m:.3f} m out of range [0.08, 0.25]")

    geo_ok  = len(geo_warnings) == 0
    geo_msg = "; ".join(geo_warnings)

    return ValidationResult(checks=checks, geo_ok=geo_ok, geo_msg=geo_msg)
