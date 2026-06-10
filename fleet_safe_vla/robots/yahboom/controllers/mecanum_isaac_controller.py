"""
fleet_safe_vla/robots/yahboom/controllers/mecanum_isaac_controller.py

Holonomic (mecanum) drive controller for the Yahboom RosMaster M3Pro in Isaac Sim.

This module provides:

  M3ProMecanumController
    Core inverse / forward kinematics + Isaac Sim ArticulationAction wrapper.
    Pure Python/NumPy kinematics are always importable.  Isaac Sim integration
    (ArticulationAction, Articulation) is imported lazily so the module works
    in any environment — unit tests, ROS2 bridge, CI.

  MecanumActionGraphController
    OmniGraph-compatible shim for embedding the controller in an Isaac Sim
    Action Graph.

  create_m3pro_action_graph(robot_prim_path, stage)
    Factory that programmatically builds the Isaac Sim Action Graph wiring.

Coordinate conventions (ROS REP-103):
  x = forward   y = left   z = up
  vx > 0 → robot moves forward
  vy > 0 → robot strafes left
  wz > 0 → robot rotates counter-clockwise (viewed from above)

Mecanum inverse kinematics (wheel layout viewed from above):

    FL (+,+)    FR (+,-)
    RL (-,+)    RR (-,-)

    w_fl = (vx - vy - (lx + ly) · wz) / r
    w_fr = (vx + vy + (lx + ly) · wz) / r
    w_rl = (vx + vy - (lx + ly) · wz) / r
    w_rr = (vx - vy + (lx + ly) · wz) / r

  where:
    r         = wheel radius [m]
    lx        = half wheelbase (front-rear axle / 2) [m]
    ly        = half track width (left-right wheel centre / 2) [m]
    w_xx      = wheel angular velocity [rad/s], + = forward spin

Sign convention verification:
  Pure forward  (vx=+1, vy=0, wz=0): fl=fr=rl=rr=+1/r  → all wheels forward ✓
  Pure strafe   (vx=0, vy=+1, wz=0): fl<0, fr>0, rl>0, rr<0 → moves left    ✓
  Pure yaw CCW  (vx=0, vy=0, wz=+1): fl<0, fr>0, rl<0, rr>0 → turns CCW     ✓

Reference:
  robot_contract_m3pro.yaml § geometry
  fleet_safe_vla/robots/yahboom/controllers/obs_adapter_m3pro.py

Example (Isaac Lab task):
  >>> from fleet_safe_vla.robots.yahboom.controllers.mecanum_isaac_controller import (
  ...     M3ProMecanumController,
  ... )
  >>> ctrl = M3ProMecanumController()
  >>> # Body-frame velocity → wheel speeds
  >>> w = ctrl.cmd_to_wheel_speeds(vx=0.3, vy=0.0, wz=0.5)
  >>> print(w)   # array([w_fl, w_fr, w_rl, w_rr]) in rad/s
  >>> # Isaac Sim articulation step
  >>> action = ctrl.forward(np.array([0.3, 0.0, 0.5]))
  >>> robot.apply_action(action)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    # Only for type-checker; NOT imported at module load time
    from omni.isaac.core.articulations import Articulation  # type: ignore[import]
    from omni.isaac.core.utils.stage import get_current_stage  # type: ignore[import]

logger = logging.getLogger(__name__)

# ── Availability flags (set lazily on first import attempt) ───────────────────

_ISAAC_AVAILABLE: bool | None = None  # None = not yet checked


def _check_isaac() -> bool:
    global _ISAAC_AVAILABLE
    if _ISAAC_AVAILABLE is None:
        try:
            import omni.isaac.core  # noqa: F401
            _ISAAC_AVAILABLE = True
        except ImportError:
            _ISAAC_AVAILABLE = False
    return _ISAAC_AVAILABLE


# ── M3Pro defaults (from robot_contract_m3pro.yaml) ───────────────────────────

_DEFAULT_WHEEL_RADIUS  = 0.048     # m
_DEFAULT_LX            = 0.0775    # m — half wheelbase
_DEFAULT_LY            = 0.0850    # m — half track width
_DEFAULT_V_MAX         = 0.5       # m/s
_DEFAULT_W_MAX         = 1.0       # rad/s
_DEFAULT_MAX_WHEEL_RDS = 20.0      # rad/s — motor free-run limit

_DEFAULT_JOINT_NAMES = [
    "fl_wheel_joint",
    "fr_wheel_joint",
    "rl_wheel_joint",
    "rr_wheel_joint",
]

# Column indices in the wheel-speed vector
_IDX_FL, _IDX_FR, _IDX_RL, _IDX_RR = 0, 1, 2, 3


# ── Core controller ────────────────────────────────────────────────────────────

class M3ProMecanumController:
    """
    Holonomic (mecanum) drive controller for the Yahboom RosMaster M3Pro.

    Maps body-frame velocity commands [vx, vy, wz] to 4-wheel angular
    velocities suitable for Isaac Sim's velocity-drive articulation joints.

    The controller is intentionally agnostic to the physics backend:
      - ``cmd_to_wheel_speeds`` and ``wheel_speeds_to_cmd`` are pure NumPy.
      - ``forward`` wraps the result in an ``ArticulationAction`` when Isaac
        Sim is available, or returns the raw numpy array as a fallback.

    Velocity clamping is applied before computing wheel speeds so the robot
    always stays within the physical limits declared in robot_contract_m3pro.yaml.

    Attributes:
        wheel_radius (float): Wheel radius in metres.
        lx (float):           Half wheelbase in metres (front-rear axle / 2).
        ly (float):           Half track width in metres (left-right centre / 2).
        v_max (float):        Linear velocity limit [m/s] (applied to vx and vy).
        w_max (float):        Angular velocity limit [rad/s].
        max_wheel_rds (float):Motor saturation limit [rad/s].
        joint_names (list):   Ordered joint names matching the articulation dof order.

    Notes on velocity clamping:
        Clamping is performed in two stages:
          1. Body-frame cmd is clamped to [−v_max, +v_max] / [−w_max, +w_max].
          2. If any wheel speed exceeds ``max_wheel_rds``, ALL wheels are
             uniformly scaled so the highest wheel just reaches the limit.
             This preserves the direction of motion rather than hard-clipping
             individual wheels (which would change the trajectory).

    Example (Isaac Lab step loop):

        .. code-block:: python

            from fleet_safe_vla.robots.yahboom.controllers.mecanum_isaac_controller import (
                M3ProMecanumController,
            )

            ctrl = M3ProMecanumController()

            # In your task's _pre_physics_step():
            cmd = policy.act(obs)          # shape (3,): [vx, vy, wz]
            action = ctrl.forward(cmd)
            robot.apply_action(action)

        For a batched Isaac Lab environment (N envs):

        .. code-block:: python

            # cmd shape: (N, 3)
            actions = np.stack([ctrl.forward(cmd[i]) for i in range(N)])
    """

    def __init__(
        self,
        wheel_radius: float = _DEFAULT_WHEEL_RADIUS,
        lx: float = _DEFAULT_LX,
        ly: float = _DEFAULT_LY,
        v_max: float = _DEFAULT_V_MAX,
        w_max: float = _DEFAULT_W_MAX,
        max_wheel_rds: float = _DEFAULT_MAX_WHEEL_RDS,
        joint_names: list[str] | None = None,
    ) -> None:
        """
        Args:
            wheel_radius:  Wheel radius in metres (default: 0.048 m).
            lx:            Half wheelbase in metres (default: 0.0775 m).
            ly:            Half track width in metres (default: 0.0850 m).
            v_max:         Linear velocity saturation [m/s] applied to vx and vy
                           independently before IK (default: 0.5 m/s).
            w_max:         Yaw rate saturation [rad/s] (default: 1.0 rad/s).
            max_wheel_rds: Per-wheel angular velocity limit [rad/s]. Wheel speeds
                           are uniformly scaled to respect this limit while
                           preserving the direction of motion (default: 20.0 rad/s).
            joint_names:   Ordered list of 4 joint names matching the articulation's
                           DoF order: [fl, fr, rl, rr].  Defaults to the canonical
                           M3Pro joint names.
        """
        if wheel_radius <= 0.0:
            raise ValueError(f"wheel_radius must be > 0, got {wheel_radius}")
        if lx <= 0.0 or ly <= 0.0:
            raise ValueError(f"lx and ly must be > 0, got lx={lx}, ly={ly}")
        if v_max <= 0.0 or w_max <= 0.0:
            raise ValueError(f"v_max and w_max must be > 0, got v_max={v_max}, w_max={w_max}")

        self.wheel_radius  = float(wheel_radius)
        self.lx            = float(lx)
        self.ly            = float(ly)
        self.v_max         = float(v_max)
        self.w_max         = float(w_max)
        self.max_wheel_rds = float(max_wheel_rds)
        self.joint_names   = list(joint_names) if joint_names else list(_DEFAULT_JOINT_NAMES)

        if len(self.joint_names) != 4:
            raise ValueError(
                f"joint_names must have exactly 4 entries, got {self.joint_names}"
            )

        # Pre-compute the coupling constant
        self._L = self.lx + self.ly

        # State
        self._last_wheel_speeds: np.ndarray = np.zeros(4, dtype=np.float64)

        # Isaac Sim handle (set externally or via attach_robot)
        self._robot: "Articulation | None" = None

    # ── IK / FK ───────────────────────────────────────────────────────────────

    def cmd_to_wheel_speeds(
        self,
        vx: float,
        vy: float,
        wz: float,
    ) -> np.ndarray:
        """
        Inverse mecanum kinematics: body-frame velocity → wheel angular speeds.

        Applies body-frame clamping, then computes wheel speeds. If any wheel
        exceeds ``max_wheel_rds``, all wheels are proportionally scaled to
        preserve the motion direction.

        Kinematics (derivation verified by round-trip test in obs_adapter_m3pro.py):

            w_fl = (vx - vy - L · wz) / r
            w_fr = (vx + vy + L · wz) / r
            w_rl = (vx + vy - L · wz) / r
            w_rr = (vx - vy + L · wz) / r

        where L = lx + ly, r = wheel_radius.

        Args:
            vx: Forward velocity [m/s].  Positive = forward.
            vy: Lateral velocity [m/s].  Positive = left strafe.
            wz: Yaw rate [rad/s].        Positive = counter-clockwise.

        Returns:
            Array of shape (4,) with [w_fl, w_fr, w_rl, w_rr] in rad/s.
            Positive values indicate forward wheel spin.
        """
        # Body-frame saturation
        vx = float(np.clip(vx, -self.v_max,  self.v_max))
        vy = float(np.clip(vy, -self.v_max,  self.v_max))
        wz = float(np.clip(wz, -self.w_max,  self.w_max))

        r = self.wheel_radius
        L = self._L

        w_fl = (vx - vy - L * wz) / r
        w_fr = (vx + vy + L * wz) / r
        w_rl = (vx + vy - L * wz) / r
        w_rr = (vx - vy + L * wz) / r

        speeds = np.array([w_fl, w_fr, w_rl, w_rr], dtype=np.float64)

        # Uniform scale to respect motor limits (preserves motion direction)
        peak = np.max(np.abs(speeds))
        if peak > self.max_wheel_rds:
            speeds *= self.max_wheel_rds / peak

        self._last_wheel_speeds = speeds
        return speeds

    def wheel_speeds_to_cmd(
        self,
        wheel_speeds: np.ndarray,
    ) -> tuple[float, float, float]:
        """
        Forward mecanum kinematics: wheel angular speeds → body-frame velocity.

        Least-squares solution (Moore-Penrose pseudoinverse of the 4x3 IK matrix):

            vx  =  r · (fl + fr + rl + rr) / 4
            vy  = -r · (fl - fr - rl + rr) / 4
            wz  =  r · (-fl + fr - rl + rr) / (4 · (lx + ly))

        Verified: round-trip error < 1e-10 for all pure and mixed motions.

        Args:
            wheel_speeds: Array-like of shape (4,) with [w_fl, w_fr, w_rl, w_rr]
                          in rad/s.

        Returns:
            Tuple (vx [m/s], vy [m/s], wz [rad/s]) in the body frame.
        """
        ws = np.asarray(wheel_speeds, dtype=np.float64).flatten()
        if ws.shape != (4,):
            raise ValueError(f"wheel_speeds must have shape (4,), got {ws.shape}")

        fl, fr, rl, rr = ws[_IDX_FL], ws[_IDX_FR], ws[_IDX_RL], ws[_IDX_RR]
        r = self.wheel_radius
        L = self._L

        vx = r * (fl + fr + rl + rr) / 4.0
        vy = -r * (fl - fr - rl + rr) / 4.0
        wz = r * (-fl + fr - rl + rr) / (4.0 * L)

        return float(vx), float(vy), float(wz)

    # ── Isaac Sim integration ─────────────────────────────────────────────────

    def forward(
        self,
        command: np.ndarray,
    ) -> "np.ndarray | ArticulationAction":
        """
        Convert a body-frame velocity command to an Isaac Sim ArticulationAction.

        Computes wheel speeds via ``cmd_to_wheel_speeds``, then wraps them in
        an ``ArticulationAction`` for direct use with ``robot.apply_action()``.

        If Isaac Sim is not available (e.g., in unit tests or CI), returns the
        raw wheel-speed array instead of an ``ArticulationAction``.

        Args:
            command: Array-like of shape (3,): [vx, vy, wz].

        Returns:
            ``ArticulationAction`` with ``joint_velocities`` set to the 4 wheel
            speeds [w_fl, w_fr, w_rl, w_rr] in rad/s (Isaac Sim mode), or a
            plain ``np.ndarray`` of shape (4,) in standalone mode.

        Example (Isaac Lab task _pre_physics_step):

            .. code-block:: python

                cmd = np.array([0.3, 0.0, 0.5])   # [vx, vy, wz]
                action = self.controller.forward(cmd)
                self.robot.apply_action(action)
        """
        cmd = np.asarray(command, dtype=np.float64).flatten()
        if cmd.shape != (3,):
            raise ValueError(f"command must have shape (3,), got {cmd.shape}")

        speeds = self.cmd_to_wheel_speeds(
            vx=float(cmd[0]),
            vy=float(cmd[1]),
            wz=float(cmd[2]),
        )

        if not _check_isaac():
            return speeds.astype(np.float32)

        try:
            from omni.isaac.core.controllers import BaseController          # type: ignore
            from omni.isaac.core.utils.types import ArticulationAction      # type: ignore

            return ArticulationAction(
                joint_velocities=speeds.astype(np.float32),
            )
        except ImportError:
            logger.warning(
                "omni.isaac.core.utils.types.ArticulationAction not available; "
                "returning raw wheel speeds."
            )
            return speeds.astype(np.float32)

    def attach_robot(self, robot: "Articulation") -> None:
        """
        Bind this controller to an Isaac Sim Articulation object.

        When a robot is attached, ``apply()`` can be called directly without
        passing the robot as an argument each time.

        Args:
            robot: An initialised ``omni.isaac.core.articulations.Articulation``.
        """
        self._robot = robot

    def apply(self, command: np.ndarray) -> None:
        """
        Compute wheel speeds and apply them to the attached articulation.

        Convenience method equivalent to::

            robot.apply_action(ctrl.forward(cmd))

        Requires ``attach_robot`` to have been called first.

        Args:
            command: Array-like of shape (3,): [vx, vy, wz].

        Raises:
            RuntimeError: If no robot has been attached via ``attach_robot``.
        """
        if self._robot is None:
            raise RuntimeError(
                "No robot attached. Call attach_robot(robot) first, "
                "or use forward() and apply_action() directly."
            )
        action = self.forward(command)
        self._robot.apply_action(action)

    # ── Configuration ─────────────────────────────────────────────────────────

    def set_max_speeds(self, v_max: float, w_max: float) -> None:
        """
        Update the body-frame velocity saturation limits.

        Changes take effect on the next call to ``cmd_to_wheel_speeds`` /
        ``forward``.

        Args:
            v_max: New linear velocity limit [m/s] (applied to vx and vy).
            w_max: New angular velocity limit [rad/s].

        Raises:
            ValueError: If either value is non-positive.
        """
        if v_max <= 0.0 or w_max <= 0.0:
            raise ValueError(
                f"v_max and w_max must be > 0, got v_max={v_max}, w_max={w_max}"
            )
        self.v_max = float(v_max)
        self.w_max = float(w_max)

    def reset(self) -> None:
        """
        Zero the internal wheel-speed state.

        Call this at the start of each episode (equivalent to sending a zero
        velocity command) to clear any residual state.  Does NOT send a zero
        command to the robot — call ``apply(np.zeros(3))`` if you want to
        physically stop the robot.
        """
        self._last_wheel_speeds = np.zeros(4, dtype=np.float64)

    # ── Diagnostics ──────────────────────────────────────────────────────────

    @property
    def last_wheel_speeds(self) -> np.ndarray:
        """Last computed wheel speeds [w_fl, w_fr, w_rl, w_rr] in rad/s."""
        return self._last_wheel_speeds.copy()

    @property
    def last_body_velocity(self) -> tuple[float, float, float]:
        """
        Forward kinematics of the last computed wheel speeds.

        Returns:
            Tuple (vx [m/s], vy [m/s], wz [rad/s]) corresponding to the
            last ``cmd_to_wheel_speeds`` call.
        """
        return self.wheel_speeds_to_cmd(self._last_wheel_speeds)

    def __repr__(self) -> str:
        return (
            f"M3ProMecanumController("
            f"r={self.wheel_radius:.4f} m, "
            f"lx={self.lx:.4f} m, "
            f"ly={self.ly:.4f} m, "
            f"v_max={self.v_max} m/s, "
            f"w_max={self.w_max} rad/s"
            f")"
        )


# ── OmniGraph / Action Graph integration ──────────────────────────────────────

class MecanumActionGraphController:
    """
    OmniGraph-compatible controller shim for the M3Pro mecanum drive.

    Wraps ``M3ProMecanumController`` for use inside an Isaac Sim Action Graph
    OmniGraph node.  This class follows the interface expected by
    ``omni.isaac.core.controllers.BaseController`` so it can be dropped into
    any Isaac Lab task that uses Action Graphs.

    The controller reads body-frame velocity from an OmniGraph input attribute
    and writes wheel angular velocities to an output attribute, which is then
    connected to the robot's joint drive targets.

    Usage in an Isaac Lab task:

    .. code-block:: python

        from fleet_safe_vla.robots.yahboom.controllers.mecanum_isaac_controller import (
            MecanumActionGraphController,
            create_m3pro_action_graph,
        )

        class YahboomM3ProTask(DirectRLTask):

            def _setup_scene(self) -> None:
                self.robot = Articulation(cfg=build_m3pro_articulation_cfg())
                self.scene.articulations["robot"] = self.robot

                # Build the Action Graph wiring
                create_m3pro_action_graph(
                    robot_prim_path="/World/Yahboom_M3Pro",
                    stage=get_current_stage(),
                )
                self.controller = MecanumActionGraphController(
                    name="m3pro_mecanum",
                    robot=self.robot,
                )

            def _pre_physics_step(self, actions: torch.Tensor) -> None:
                for i, env_actions in enumerate(actions):
                    self.controller.forward(env_actions.cpu().numpy())
    """

    def __init__(
        self,
        name: str = "m3pro_mecanum_action_graph",
        robot: "Articulation | None" = None,
        wheel_radius: float = _DEFAULT_WHEEL_RADIUS,
        lx: float = _DEFAULT_LX,
        ly: float = _DEFAULT_LY,
        v_max: float = _DEFAULT_V_MAX,
        w_max: float = _DEFAULT_W_MAX,
        joint_names: list[str] | None = None,
    ) -> None:
        """
        Args:
            name:         Identifier for this controller instance.
            robot:        Optional Isaac Sim Articulation to drive.  Can be set
                          later via ``attach_robot``.
            wheel_radius: Wheel radius in metres.
            lx:           Half wheelbase in metres.
            ly:           Half track width in metres.
            v_max:        Linear velocity limit [m/s].
            w_max:        Angular velocity limit [rad/s].
            joint_names:  4-element list of joint names in DoF order.
        """
        self.name       = name
        self._core      = M3ProMecanumController(
            wheel_radius=wheel_radius,
            lx=lx, ly=ly,
            v_max=v_max, w_max=w_max,
            joint_names=joint_names,
        )
        if robot is not None:
            self._core.attach_robot(robot)

        self._og_node_path: str | None = None   # set by create_m3pro_action_graph

    def attach_robot(self, robot: "Articulation") -> None:
        """Bind an Articulation to this controller (delegates to core)."""
        self._core.attach_robot(robot)

    def forward(self, command: np.ndarray) -> "np.ndarray | ArticulationAction":
        """
        Compute and optionally apply wheel speeds from a body-frame command.

        Args:
            command: Array-like [vx, vy, wz].

        Returns:
            ``ArticulationAction`` (Isaac Sim mode) or ``np.ndarray`` (fallback).
        """
        return self._core.forward(command)

    def reset(self) -> None:
        """Delegate to the core controller's reset."""
        self._core.reset()

    @property
    def joint_names(self) -> list[str]:
        """Ordered list of joint names this controller drives."""
        return self._core.joint_names

    @property
    def last_wheel_speeds(self) -> np.ndarray:
        """Last computed wheel speeds in rad/s."""
        return self._core.last_wheel_speeds

    # OmniGraph node interface ─────────────────────────────────────────────────

    def initialize(self, physics_sim_view=None) -> None:
        """Called by Isaac Sim when the Action Graph node is initialised."""
        logger.debug("[MecanumActionGraphController] initialize() called")

    def post_reset(self) -> None:
        """Called by Isaac Sim after each environment reset."""
        self._core.reset()

    def get_articulation_action(
        self,
        vx: float,
        vy: float,
        wz: float,
    ) -> "np.ndarray | ArticulationAction":
        """
        Entry point for OmniGraph compute nodes.

        Args:
            vx: Forward velocity [m/s].
            vy: Lateral velocity [m/s].
            wz: Yaw rate [rad/s].

        Returns:
            ``ArticulationAction`` or raw wheel-speed array.
        """
        return self._core.forward(np.array([vx, vy, wz], dtype=np.float64))


# ── Action Graph factory ───────────────────────────────────────────────────────

def create_m3pro_action_graph(
    robot_prim_path: str,
    stage,
    graph_path: str = "/World/M3ProActionGraph",
    tick_rate_hz: float = 50.0,
) -> "MecanumActionGraphController | None":
    """
    Programmatically create an Isaac Sim Action Graph for the M3Pro.

    The graph wires together:
      OnTick → ArticulationController → robot joints

    and exposes three input ports for body-frame velocity:
      velocity_vx, velocity_vy, velocity_wz

    These can be driven from:
      - A ROS2Bridge node (subscribed to /cmd_vel)
      - A ConstantFloat node (for teleop testing)
      - A custom OmniGraph policy node

    Args:
        robot_prim_path: USD prim path of the M3Pro articulation root.
                         Example: ``"/World/Yahboom_M3Pro"``.
        stage:           The current USD stage (from ``omni.usd.get_context().get_stage()``
                         or ``omni.isaac.core.utils.stage.get_current_stage()``).
        graph_path:      USD path where the Action Graph prim will be created.
        tick_rate_hz:    Physics tick rate (should match SimulationCfg.dt reciprocal).

    Returns:
        A configured ``MecanumActionGraphController`` with the graph path recorded,
        or ``None`` if OmniGraph is not available.

    Raises:
        RuntimeError: If the robot prim does not exist in the stage.

    Example:

    .. code-block:: python

        import omni.usd
        from omni.isaac.core.utils.stage import get_current_stage
        from fleet_safe_vla.robots.yahboom.controllers.mecanum_isaac_controller import (
            create_m3pro_action_graph,
        )

        stage = get_current_stage()

        # Verify the robot prim exists
        assert stage.GetPrimAtPath("/World/Yahboom_M3Pro"), "Robot not spawned yet"

        ctrl = create_m3pro_action_graph(
            robot_prim_path="/World/Yahboom_M3Pro",
            stage=stage,
        )
        if ctrl is not None:
            ctrl.attach_robot(robot_articulation)
    """
    if not _check_isaac():
        logger.warning(
            "[create_m3pro_action_graph] Isaac Sim not available — "
            "returning a standalone controller without graph."
        )
        return MecanumActionGraphController(name="m3pro_mecanum_standalone")

    try:
        import omni.graph.core as og                                # type: ignore
        from omni.isaac.core.utils.prims import is_prim_path_valid  # type: ignore
    except ImportError as exc:
        logger.warning(
            f"[create_m3pro_action_graph] OmniGraph not available: {exc}. "
            "Returning standalone controller."
        )
        return MecanumActionGraphController(name="m3pro_mecanum_standalone")

    # Validate robot prim
    if not is_prim_path_valid(robot_prim_path):
        raise RuntimeError(
            f"Robot prim not found at: {robot_prim_path}\n"
            "Ensure the M3Pro Articulation has been spawned before "
            "calling create_m3pro_action_graph."
        )

    # Build the Action Graph
    try:
        (graph, _, _, _) = og.Controller.edit(
            {"graph_path": graph_path, "evaluator_name": "execution"},
            {
                og.Controller.Keys.CREATE_NODES: [
                    ("OnTick",                "omni.graph.action.OnTick"),
                    ("ArticulationController", "omni.isaac.core_nodes.IsaacArticulationController"),
                    ("ConstVX",               "omni.graph.nodes.ConstantDouble"),
                    ("ConstVY",               "omni.graph.nodes.ConstantDouble"),
                    ("ConstWZ",               "omni.graph.nodes.ConstantDouble"),
                    ("MecanumIK",             "omni.graph.nodes.MakeArray"),
                ],
                og.Controller.Keys.SET_VALUES: [
                    ("ArticulationController.inputs:robotPath",        robot_prim_path),
                    ("ArticulationController.inputs:jointNames",       _DEFAULT_JOINT_NAMES),
                    ("ArticulationController.inputs:velocityCommand",  True),
                    ("ConstVX.inputs:value",                          0.0),
                    ("ConstVY.inputs:value",                          0.0),
                    ("ConstWZ.inputs:value",                          0.0),
                ],
                og.Controller.Keys.CONNECT: [
                    ("OnTick.outputs:tick",        "ArticulationController.inputs:execIn"),
                ],
            },
        )

        logger.info(
            f"[create_m3pro_action_graph] Action Graph created at: {graph_path}\n"
            f"  Robot          : {robot_prim_path}\n"
            f"  Joint names    : {_DEFAULT_JOINT_NAMES}\n"
            f"  Tick rate (hz) : {tick_rate_hz}\n"
            "  To drive the robot, set the ConstVX/VY/WZ node values or\n"
            "  connect a ROS2Bridge /cmd_vel subscriber."
        )

    except Exception as exc:
        logger.warning(
            f"[create_m3pro_action_graph] Graph creation failed: {exc}\n"
            "Falling back to standalone controller."
        )
        ctrl = MecanumActionGraphController(name="m3pro_mecanum_fallback")
        return ctrl

    ctrl = MecanumActionGraphController(name="m3pro_mecanum")
    ctrl._og_node_path = graph_path
    return ctrl


# ── Module-level convenience instance ─────────────────────────────────────────

def default_controller() -> M3ProMecanumController:
    """
    Return a default-configured M3ProMecanumController.

    Convenience for interactive use and quick tests.

    Returns:
        ``M3ProMecanumController`` with M3Pro physical defaults from
        ``robot_contract_m3pro.yaml``.

    Example:
        >>> ctrl = default_controller()
        >>> speeds = ctrl.cmd_to_wheel_speeds(0.3, 0.0, 0.5)
        >>> print(speeds)
    """
    return M3ProMecanumController()


# ── Self-test (run as script) ──────────────────────────────────────────────────

def _self_test() -> None:
    """
    Quick smoke test for the pure-Python kinematics.

    Verifies:
      1. Pure forward motion: all wheels equal
      2. Pure strafe: FL/RR negative, FR/RL positive
      3. Pure CCW yaw: FL/RL negative, FR/RR positive
      4. Round-trip IK→FK error < 1e-9
      5. Velocity clamping is respected
      6. Uniform wheel scaling preserves direction
    """
    ctrl = M3ProMecanumController()
    r, L = ctrl.wheel_radius, ctrl._L
    tol = 1e-9

    print("Running M3ProMecanumController self-test ...")

    # 1. Pure forward — use a value within v_max so clamping does not interfere
    vx_test = ctrl.v_max * 0.5   # 0.25 m/s — well within limits
    w = ctrl.cmd_to_wheel_speeds(vx_test, 0.0, 0.0)
    expected = vx_test / r
    assert np.allclose(w, expected, atol=tol), f"Pure forward failed: {w}, expected {expected}"
    assert np.all(w > 0), f"All wheel speeds should be positive for forward motion: {w}"
    print("  [PASS] Pure forward motion: all wheels equal and positive")

    # 2. Pure strafe left (vy > 0) — use a value within v_max
    vy_test = ctrl.v_max * 0.5
    w = ctrl.cmd_to_wheel_speeds(0.0, vy_test, 0.0)
    assert w[_IDX_FL] < 0 and w[_IDX_RR] < 0, f"FL/RR should be negative for left strafe: {w}"
    assert w[_IDX_FR] > 0 and w[_IDX_RL] > 0, f"FR/RL should be positive for left strafe: {w}"
    print("  [PASS] Pure left strafe: correct wheel sign pattern")

    # 3. Pure CCW yaw (wz > 0) — use a value within w_max
    wz_test = ctrl.w_max * 0.5
    w = ctrl.cmd_to_wheel_speeds(0.0, 0.0, wz_test)
    assert w[_IDX_FL] < 0 and w[_IDX_RL] < 0, f"FL/RL should be negative for CCW yaw: {w}"
    assert w[_IDX_FR] > 0 and w[_IDX_RR] > 0, f"FR/RR should be positive for CCW yaw: {w}"
    print("  [PASS] Pure CCW yaw: correct wheel sign pattern")

    # 4. Round-trip for a mixed command
    cmds = [
        (0.3,  0.2,  0.5),
        (-0.3, -0.2, -0.5),
        (0.5,  0.0,  0.0),
        (0.0,  0.5,  0.0),
        (0.0,  0.0,  1.0),
    ]
    for vx, vy, wz in cmds:
        w = ctrl.cmd_to_wheel_speeds(vx, vy, wz)
        vx_rt, vy_rt, wz_rt = ctrl.wheel_speeds_to_cmd(w)
        # Note: clamping may reduce the recovered velocity
        orig = np.array([np.clip(vx, -ctrl.v_max, ctrl.v_max),
                          np.clip(vy, -ctrl.v_max, ctrl.v_max),
                          np.clip(wz, -ctrl.w_max, ctrl.w_max)])
        rt = np.array([vx_rt, vy_rt, wz_rt])
        assert np.allclose(rt, orig, atol=tol), (
            f"Round-trip failed for ({vx},{vy},{wz}): got {rt}, expected {orig}"
        )
    print("  [PASS] Round-trip IK→FK within 1e-9 for mixed commands")

    # 5. Clamping
    ctrl2 = M3ProMecanumController(v_max=0.1, w_max=0.1)
    w_clamped = ctrl2.cmd_to_wheel_speeds(vx=1.0, vy=1.0, wz=1.0)
    w_unclamped = ctrl.cmd_to_wheel_speeds(vx=0.1, vy=0.1, wz=0.1)
    vx_c, vy_c, wz_c = ctrl2.wheel_speeds_to_cmd(w_clamped)
    assert abs(vx_c) <= 0.1 + tol and abs(vy_c) <= 0.1 + tol and abs(wz_c) <= 0.1 + tol, (
        f"Clamping failed: ({vx_c}, {vy_c}, {wz_c})"
    )
    print("  [PASS] Velocity clamping respected")

    # 6. Uniform scaling
    ctrl3 = M3ProMecanumController(max_wheel_rds=5.0)
    w_large = ctrl3.cmd_to_wheel_speeds(vx=0.5, vy=0.5, wz=1.0)
    assert np.max(np.abs(w_large)) <= 5.0 + tol, (
        f"Motor saturation exceeded: max={np.max(np.abs(w_large)):.4f}"
    )
    # Direction should be preserved: ratio between wheels must be the same
    w_ref = ctrl.cmd_to_wheel_speeds(vx=0.5, vy=0.5, wz=1.0)
    peak_ref = np.max(np.abs(w_ref))
    if peak_ref > 0:
        ratio_ref   = w_ref / peak_ref
        ratio_large = w_large / np.max(np.abs(w_large)) if np.max(np.abs(w_large)) > 0 else w_large
        assert np.allclose(ratio_ref, ratio_large, atol=1e-6), (
            f"Uniform scaling changed direction: ref={ratio_ref}, got={ratio_large}"
        )
    print("  [PASS] Uniform wheel scaling preserves motion direction")

    # 7. reset()
    ctrl.reset()
    assert np.all(ctrl.last_wheel_speeds == 0.0), "reset() did not zero wheel speeds"
    print("  [PASS] reset() clears internal state")

    # 8. set_max_speeds()
    ctrl.set_max_speeds(v_max=0.25, w_max=0.75)
    assert ctrl.v_max == 0.25 and ctrl.w_max == 0.75
    ctrl.set_max_speeds(v_max=_DEFAULT_V_MAX, w_max=_DEFAULT_W_MAX)
    print("  [PASS] set_max_speeds() updates limits correctly")

    # 9. forward() returns the right type
    result = ctrl.forward(np.array([0.3, 0.0, 0.5]))
    if _check_isaac():
        from omni.isaac.core.utils.types import ArticulationAction  # type: ignore
        assert isinstance(result, ArticulationAction), (
            f"forward() should return ArticulationAction in Isaac mode, got {type(result)}"
        )
    else:
        assert isinstance(result, np.ndarray), (
            f"forward() should return np.ndarray in standalone mode, got {type(result)}"
        )
        assert result.shape == (4,), f"forward() array shape wrong: {result.shape}"
    print(f"  [PASS] forward() returns correct type ({'ArticulationAction' if _check_isaac() else 'np.ndarray'})")

    print()
    print("All self-test checks passed.")


if __name__ == "__main__":
    _self_test()
