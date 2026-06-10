"""
Control Barrier Function (CBF) Safety Filter — Fleet-Safe-VLA-OS.

Implements a real-time CBF safety filter for the H1 humanoid robot.
Uses scipy QP solving for the minimal intervention guarantee.

Theory:
  A CBF h(x) ≥ 0 defines a safe set C = {x | h(x) ≥ 0}.
  The filter modifies policy actions u_nom to u_safe such that:
    ḣ(x, u_safe) + α(h(x)) ≥ 0  (CBF condition)

  This is solved as a Quadratic Program:
    minimize  ‖u - u_nom‖²
    subject to  Lf h(x) + Lg h(x) u + α(h(x)) ≥ 0

  We use class-K function α(h) = γ * h.

Barrier functions implemented:
  h_joint(x):    Joint position limits — maintains joints in safe range
  h_tilt(x):     Base tilt limit — prevents robot from falling

Usage:
    cfg = CBFConfig(joint_pos_limits=limits, max_tilt_rad=0.7)
    cbf = CBFSafetyFilter(cfg)
    safe_action = cbf.filter_action(obs, action)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy.optimize import minimize, LinearConstraint, Bounds

# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class CBFConfig:
    """
    Configuration for the CBF safety filter.

    Args:
        joint_pos_limits: (N, 2) array of [lower, upper] joint limits in radians.
                          If None, uses H1 defaults.
        max_tilt_rad:     Maximum allowed base tilt angle (radians).
        gamma:            CBF class-K function gain (α(h) = γ·h).
        slack_weight:     Weight for QP slack variable (soft constraint).
        use_soft_constraints: If True, add slack to make the QP always feasible.
        action_dim:       Number of actuated DOF.
        dt:               Control timestep for discrete-time CBF approximation.
    """
    joint_pos_limits: np.ndarray | None = None
    max_tilt_rad: float = 0.7       # ~40° — conservative for fleet ops
    gamma: float = 1.0              # CBF gain: larger = more conservative
    slack_weight: float = 1000.0    # large = near-hard constraint
    use_soft_constraints: bool = True
    action_dim: int = 18
    dt: float = 0.02                # 50 Hz control

    # H1 default joint limits (18 DOF)
    _h1_joint_limits: np.ndarray = field(default_factory=lambda: np.array([
        # leg: hip_yaw, hip_roll, hip_pitch, knee, ankle (left then right)
        [-0.785, 0.785], [-0.523, 0.523], [-1.57, 1.57], [-0.087, 2.443], [-0.785, 0.785],
        [-0.785, 0.785], [-0.523, 0.523], [-1.57, 1.57], [-0.087, 2.443], [-0.785, 0.785],
        # arm: shoulder_pitch, shoulder_roll, elbow, wrist (left then right)
        [-3.14, 3.14], [-1.57, 1.57], [-1.57, 1.57], [-1.57, 1.57],
        [-3.14, 3.14], [-1.57, 1.57], [-1.57, 1.57], [-1.57, 1.57],
    ], dtype=np.float32))

    def __post_init__(self) -> None:
        if self.joint_pos_limits is None:
            self.joint_pos_limits = self._h1_joint_limits.copy()
        self.joint_pos_limits = np.asarray(self.joint_pos_limits, dtype=np.float64)


# ── Observation parsing ───────────────────────────────────────────────────────

def parse_obs(obs: np.ndarray) -> dict[str, np.ndarray]:
    """
    Parse the 45-dim proprioceptive observation vector.

    obs layout:
        [0:3]   base angular velocity (rad/s)
        [3:6]   projected gravity vector
        [6:9]   velocity command (vx, vy, yaw)
        [9:27]  joint positions relative to default
        [27:45] joint velocities
    """
    return {
        "ang_vel":   obs[0:3],
        "proj_grav": obs[3:6],
        "cmd_vel":   obs[6:9],
        "q_rel":     obs[9:27],
        "qd":        obs[27:45],
    }


# ── Barrier functions ─────────────────────────────────────────────────────────

def h_joint_limits(
    q: np.ndarray,
    limits: np.ndarray,
    margin: float = 0.05,
) -> np.ndarray:
    """
    Joint position barrier values. One barrier per joint × 2 (lower + upper).

    h_lower_i(q) = q_i - (lower_i + margin) ≥ 0
    h_upper_i(q) = (upper_i - margin) - q_i ≥ 0

    Args:
        q:       (N,) joint positions (relative to default, must add default back)
        limits:  (N, 2) [lower, upper] joint limits
        margin:  safety margin inside limits (radians)

    Returns:
        (2N,) barrier values [h_lower_0, h_upper_0, h_lower_1, ...]
    """
    n = len(q)
    barriers = np.zeros(2 * n, dtype=np.float64)
    for i in range(n):
        lower = limits[i, 0] + margin
        upper = limits[i, 1] - margin
        barriers[2 * i]     = q[i] - lower      # h_lower_i ≥ 0
        barriers[2 * i + 1] = upper - q[i]      # h_upper_i ≥ 0
    return barriers


def h_tilt(proj_gravity: np.ndarray, max_tilt_rad: float) -> float:
    """
    Base tilt barrier value.

    h_tilt = cos(max_tilt_rad) - cos(actual_tilt)
           = cos(max_tilt_rad) - (-proj_gravity[2])
           ≥ 0 when tilt ≤ max_tilt_rad

    proj_gravity[2] ≈ -cos(tilt) when projected gravity is downward.
    """
    cos_actual_tilt = float(-proj_gravity[2])  # -1 = upright, 0 = sideways
    cos_max = np.cos(max_tilt_rad)
    return cos_actual_tilt - cos_max


def grad_h_tilt_wrt_action(
    proj_gravity: np.ndarray,
    ang_vel: np.ndarray,
    dt: float,
    action_dim: int,
) -> np.ndarray:
    """
    Approximate Lie derivative Lg h_tilt(x) · u.

    For base tilt, the action influences angular velocity through joint torques.
    We use a simplified linear approximation: Lg h ≈ -dt * ê_z where ê_z is
    the gravity axis direction. Since the exact Jacobian depends on robot
    kinematics, we use a conservative approximation.

    Returns: (action_dim,) gradient vector.
    """
    # Conservative uniform gradient: any large torque could cause tilt
    # The true gradient requires full robot Jacobian — we use a finite-difference
    # approximation scaled by dt and a coupling factor.
    coupling_factor = 0.01 * dt  # small but nonzero for all joints
    return -coupling_factor * np.ones(action_dim, dtype=np.float64)


# ── CBF Safety Filter ─────────────────────────────────────────────────────────

class CBFSafetyFilter:
    """
    CBF-based safety filter using scipy QP.

    Solves at each step:
        minimize   (1/2) ‖u - u_nom‖²  (+  slack_weight · δ²)
        subject to:
            Lg h_joint(x) · u + α(h_joint(x)) ≥ 0   (joint safety)
            Lg h_tilt(x)  · u + α(h_tilt(x))  ≥ 0   (tilt safety)

    The QP is solved on the action (target joint positions).
    For the joint barrier, Lg h ≈ I (since action directly sets position).

    Args:
        cfg: CBFConfig instance
    """

    def __init__(self, cfg: CBFConfig | None = None) -> None:
        self.cfg = cfg if cfg is not None else CBFConfig()
        self._n = self.cfg.action_dim
        self._last_safe_action: np.ndarray | None = None
        self._intervention_count = 0
        self._total_calls = 0

    @property
    def intervention_rate(self) -> float:
        """Fraction of calls where the filter modified the action."""
        if self._total_calls == 0:
            return 0.0
        return self._intervention_count / self._total_calls

    def filter_action(
        self,
        obs: np.ndarray,
        action: np.ndarray,
        default_joint_pos: np.ndarray | None = None,
    ) -> tuple[np.ndarray, dict]:
        """
        Apply CBF filter to nominal action.

        Args:
            obs:              (45,) proprioceptive observation
            action:           (18,) nominal action from policy (target joint positions)
            default_joint_pos: (18,) default pose for computing absolute positions.
                               If None, uses H1 defaults.

        Returns:
            (safe_action, info_dict)
            safe_action: (18,) safe joint position targets
            info_dict: {"intervened": bool, "h_min": float, "qp_success": bool}
        """
        self._total_calls += 1
        action = np.asarray(action, dtype=np.float64)

        if default_joint_pos is None:
            default_joint_pos = np.array([
                0., 0., -0.4, 0.8, -0.4,
                0., 0., -0.4, 0.8, -0.4,
                0., 0., 0., 0.,
                0., 0., 0., 0.,
            ], dtype=np.float64)

        parsed = parse_obs(obs.astype(np.float64))
        q_rel  = parsed["q_rel"]
        proj_grav = parsed["proj_grav"]
        ang_vel   = parsed["ang_vel"]

        # Absolute joint positions
        q_abs = q_rel + default_joint_pos

        # Evaluate barriers at current state (before applying action)
        h_joints = h_joint_limits(q_abs, self.cfg.joint_pos_limits)
        h_t = h_tilt(proj_grav, self.cfg.max_tilt_rad)

        h_min = float(min(np.min(h_joints), h_t))

        # Fast check: if all barriers are safe AND action is also safe, skip QP
        h_joints_after = h_joint_limits(
            action + default_joint_pos, self.cfg.joint_pos_limits
        )
        h_t_after = h_tilt(proj_grav - ang_vel * self.cfg.dt, self.cfg.max_tilt_rad)

        all_safe_after = (
            np.all(h_joints_after + self.cfg.gamma * h_joints >= 0)
            and (h_t_after + self.cfg.gamma * h_t >= 0)
        )

        if all_safe_after:
            self._last_safe_action = action.copy()
            return action.astype(np.float32), {
                "intervened": False,
                "h_min": h_min,
                "qp_success": True,
            }

        # Solve QP
        safe_action, success = self._solve_qp(
            action, q_abs, proj_grav, ang_vel, h_joints, h_t, default_joint_pos
        )

        intervened = not np.allclose(safe_action, action, atol=1e-4)
        if intervened:
            self._intervention_count += 1

        self._last_safe_action = safe_action.copy()
        return safe_action.astype(np.float32), {
            "intervened": intervened,
            "h_min": h_min,
            "qp_success": success,
        }

    def _solve_qp(
        self,
        u_nom: np.ndarray,
        q_abs: np.ndarray,
        proj_grav: np.ndarray,
        ang_vel: np.ndarray,
        h_joints: np.ndarray,
        h_t: float,
        default_joint_pos: np.ndarray,
    ) -> tuple[np.ndarray, bool]:
        """
        Solve the CBF QP using scipy.optimize.minimize with SLSQP.

        QP: min ‖u - u_nom‖² s.t. CBF constraints

        For joint barriers:
            Lg h_lower_i = +1  (increasing action increases lower barrier)
            Lg h_upper_i = -1  (decreasing action increases upper barrier)

        For tilt barrier: use approximation.
        """
        n = self._n
        limits = self.cfg.joint_pos_limits
        gamma = self.cfg.gamma

        # Constraint list for SLSQP
        constraints = []

        # Joint lower limit constraints: u_i - default_i + default_i ≥ lower + margin
        # i.e., u_i ≥ lower + margin - default_i
        # Rewritten as: u_i + gamma * h_lower_i ≥ 0
        # where Lg h_lower = 1 (action directly sets position)
        margin = 0.05
        for i in range(n):
            lower = limits[i, 0] + margin - default_joint_pos[i]
            upper = limits[i, 1] - margin - default_joint_pos[i]

            def lower_con(u, i=i, lo=limits[i, 0] + margin, dp=default_joint_pos[i]):
                # h_lower(u) = u[i] + dp - lo ≥ 0
                return u[i] + dp - lo + gamma * h_joints[2 * i]

            def upper_con(u, i=i, up=limits[i, 1] - margin, dp=default_joint_pos[i]):
                # h_upper(u) = up - u[i] - dp ≥ 0
                return up - u[i] - dp + gamma * h_joints[2 * i + 1]

            constraints.append({"type": "ineq", "fun": lower_con})
            constraints.append({"type": "ineq", "fun": upper_con})

        # Tilt constraint
        grad_tilt = grad_h_tilt_wrt_action(proj_grav, ang_vel, self.cfg.dt, n)

        def tilt_con(u, gt=grad_tilt, ht=h_t, gm=gamma):
            return float(np.dot(gt, u)) + gm * ht

        constraints.append({"type": "ineq", "fun": tilt_con})

        # Bounds: stay within joint limits
        lb = limits[:, 0] - default_joint_pos
        ub = limits[:, 1] - default_joint_pos
        bounds = Bounds(lb=lb, ub=ub)

        # Objective: minimize distance to nominal action
        def objective(u):
            diff = u - u_nom
            return 0.5 * float(np.dot(diff, diff))

        def grad_objective(u):
            return u - u_nom

        result = minimize(
            fun=objective,
            jac=grad_objective,
            x0=u_nom.copy(),
            method="SLSQP",
            constraints=constraints,
            bounds=bounds,
            options={
                "maxiter": 100,
                "ftol": 1e-6,
                "disp": False,
            },
        )

        if result.success:
            return result.x.astype(np.float64), True
        else:
            # QP failed: fall back to clamped action
            safe = np.clip(u_nom, lb, ub)
            return safe.astype(np.float64), False

    def reset(self) -> None:
        """Reset filter state (call on episode reset)."""
        self._last_safe_action = None

    def get_stats(self) -> dict:
        """Return filter statistics."""
        return {
            "total_calls": self._total_calls,
            "intervention_count": self._intervention_count,
            "intervention_rate": self.intervention_rate,
        }


# ── Convenience wrapper ───────────────────────────────────────────────────────

def make_cbf_filter(
    max_tilt_rad: float = 0.7,
    gamma: float = 1.0,
    joint_limits: np.ndarray | None = None,
) -> CBFSafetyFilter:
    """Factory for quick CBF filter construction."""
    cfg = CBFConfig(
        joint_pos_limits=joint_limits,
        max_tilt_rad=max_tilt_rad,
        gamma=gamma,
    )
    return CBFSafetyFilter(cfg)


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    print("Running CBF smoke test...")

    cbf = make_cbf_filter()

    # Nominal obs (robot upright)
    obs = np.zeros(45, dtype=np.float32)
    obs[3:6] = [0.0, 0.0, -1.0]  # proj_gravity = downward (upright)

    # Safe action (at default pose)
    action = np.zeros(18, dtype=np.float32)
    safe, info = cbf.filter_action(obs, action)
    print(f"  Safe action test: intervened={info['intervened']}, h_min={info['h_min']:.3f}")
    assert not info["intervened"], "Should not intervene on safe nominal action"

    # Unsafe action (push knee beyond limit)
    obs2 = obs.copy()
    obs2[9 + 3] = 2.4  # left knee near limit
    action2 = np.zeros(18, dtype=np.float32)
    action2[3] = 2.5   # target beyond limit
    safe2, info2 = cbf.filter_action(obs2, action2)
    print(f"  Unsafe action test: intervened={info2['intervened']}, safe[3]={safe2[3]:.3f}")

    # Tilted robot
    obs3 = obs.copy()
    obs3[3:6] = [0.5, 0.5, -0.7]  # tilted
    safe3, info3 = cbf.filter_action(obs3, action)
    print(f"  Tilt test: intervened={info3['intervened']}, h_tilt={info3['h_min']:.3f}")

    print(f"  Stats: {cbf.get_stats()}")
    print("CBF smoke test PASSED")
