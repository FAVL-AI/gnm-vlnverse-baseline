"""
Canonical observation adapter for the Yahboom RosMaster X3.

Converts raw sensor data from ANY source (Isaac Lab, MuJoCo, Gazebo, real robot)
into the standardised flat observation vector defined in robot_contract.yaml.

obs_vector (36-dim):
  [0:10]  imu:   ax,ay,az,wx,wy,wz,qx,qy,qz,qw
  [10:16] joints: lpos,rpos,lvel,rvel,leffort,reffort
  [16:26] odom:  x,y,z,qx,qy,qz,qw,vx,vy,vyaw
  [26:36] cmd_vel_history: 5 × [vx, wz]  (oldest first)

The adapter is stateful — call update() at each control step.
"""
from __future__ import annotations

from collections import deque

import numpy as np


class YahboomObsAdapter:
    """
    Converts heterogeneous sensor dicts → 36-dim obs vector.

    Usage:
        adapter = YahboomObsAdapter()
        obs = adapter.update(imu=..., joints=..., odom=..., cmd_vel=...)
    """

    OBS_DIM = 36
    CMD_HISTORY_LEN = 5

    def __init__(self):
        self._cmd_history: deque[np.ndarray] = deque(
            [np.zeros(2)] * self.CMD_HISTORY_LEN,
            maxlen=self.CMD_HISTORY_LEN,
        )

    def update(
        self,
        imu: np.ndarray | dict,
        joints: np.ndarray | dict,
        odom: np.ndarray | dict,
        cmd_vel: np.ndarray | dict | None = None,
    ) -> np.ndarray:
        """
        Build 36-dim observation vector.

        Args:
            imu:    (10,) [ax,ay,az,wx,wy,wz,qx,qy,qz,qw]  OR dict
            joints: (6,)  [lpos,rpos,lvel,rvel,leff,reff]   OR dict
            odom:   (10,) [x,y,z,qx,qy,qz,qw,vx,vy,vyaw]   OR dict
            cmd_vel: (2,) [vx, wz] — last command sent       OR dict

        Returns:
            obs: (36,) float32
        """
        imu_vec    = self._parse_imu(imu)
        joint_vec  = self._parse_joints(joints)
        odom_vec   = self._parse_odom(odom)

        if cmd_vel is not None:
            cmd = self._parse_cmd(cmd_vel)
        else:
            cmd = np.zeros(2, dtype=np.float32)
        self._cmd_history.append(cmd)

        history_vec = np.array(list(self._cmd_history), dtype=np.float32).flatten()

        obs = np.concatenate([imu_vec, joint_vec, odom_vec, history_vec]).astype(np.float32)
        assert obs.shape == (self.OBS_DIM,), f"Bad obs shape: {obs.shape}"
        return obs

    # ── parsers ────────────────────────────────────────────────────────────── #

    @staticmethod
    def _parse_imu(imu) -> np.ndarray:
        if isinstance(imu, np.ndarray):
            return imu.astype(np.float32).flatten()[:10]
        if isinstance(imu, dict):
            return np.array([
                imu.get("ax", 0), imu.get("ay", 0), imu.get("az", 0),
                imu.get("wx", 0), imu.get("wy", 0), imu.get("wz", 0),
                imu.get("qx", 0), imu.get("qy", 0), imu.get("qz", 0), imu.get("qw", 1),
            ], dtype=np.float32)
        return np.zeros(10, dtype=np.float32)

    @staticmethod
    def _parse_joints(joints) -> np.ndarray:
        if isinstance(joints, np.ndarray):
            v = joints.astype(np.float32).flatten()
            return np.pad(v, (0, max(0, 6 - len(v))))[:6]
        if isinstance(joints, dict):
            return np.array([
                joints.get("left_pos", 0),   joints.get("right_pos", 0),
                joints.get("left_vel", 0),   joints.get("right_vel", 0),
                joints.get("left_eff", 0),   joints.get("right_eff", 0),
            ], dtype=np.float32)
        return np.zeros(6, dtype=np.float32)

    @staticmethod
    def _parse_odom(odom) -> np.ndarray:
        if isinstance(odom, np.ndarray):
            v = odom.astype(np.float32).flatten()
            return np.pad(v, (0, max(0, 10 - len(v))))[:10]
        if isinstance(odom, dict):
            return np.array([
                odom.get("x", 0),  odom.get("y", 0),  odom.get("z", 0),
                odom.get("qx", 0), odom.get("qy", 0), odom.get("qz", 0), odom.get("qw", 1),
                odom.get("vx", 0), odom.get("vy", 0), odom.get("vyaw", 0),
            ], dtype=np.float32)
        return np.zeros(10, dtype=np.float32)

    @staticmethod
    def _parse_cmd(cmd) -> np.ndarray:
        if isinstance(cmd, np.ndarray):
            return cmd.astype(np.float32).flatten()[:2]
        if isinstance(cmd, dict):
            return np.array([cmd.get("vx", 0), cmd.get("wz", 0)], dtype=np.float32)
        return np.zeros(2, dtype=np.float32)

    def reset(self) -> None:
        self._cmd_history = deque(
            [np.zeros(2)] * self.CMD_HISTORY_LEN,
            maxlen=self.CMD_HISTORY_LEN,
        )

    @staticmethod
    def obs_labels() -> list[str]:
        labels = (
            ["ax", "ay", "az", "wx", "wy", "wz", "qx", "qy", "qz", "qw"]
            + ["l_pos", "r_pos", "l_vel", "r_vel", "l_eff", "r_eff"]
            + ["od_x", "od_y", "od_z", "od_qx", "od_qy", "od_qz", "od_qw",
               "od_vx", "od_vy", "od_vyaw"]
        )
        for i in range(5):
            labels += [f"cmd_vx_{i}", f"cmd_wz_{i}"]
        return labels


def cmd_vel_to_wheel_speeds(
    vx: float, wz: float,
    wheelbase: float = 0.245,
    wheel_radius: float = 0.048,
) -> tuple[float, float]:
    """
    Convert (vx, wz) → (left_rad_s, right_rad_s) for diff-drive kinematics.

    v_left  = (vx - wz * L/2) / r
    v_right = (vx + wz * L/2) / r
    """
    L = wheelbase
    r = wheel_radius
    v_left  = (vx - wz * L / 2.0) / r
    v_right = (vx + wz * L / 2.0) / r
    return float(v_left), float(v_right)


def wheel_speeds_to_cmd_vel(
    left_rad_s: float, right_rad_s: float,
    wheelbase: float = 0.245,
    wheel_radius: float = 0.048,
) -> tuple[float, float]:
    """Inverse kinematics: wheel speeds → (vx, wz)."""
    L = wheelbase
    r = wheel_radius
    vx = r * (left_rad_s + right_rad_s) / 2.0
    wz = r * (right_rad_s - left_rad_s) / L
    return float(vx), float(wz)
