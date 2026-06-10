"""Isaac Sim GNM inference environment.

This is the top-level entry point for running GNM episodes inside Isaac Sim.
It ties together the camera sensor, robot controller, and GNM evaluator.

How a live Isaac episode works
────────────────────────────────
  1. world.reset()   — teleport robot to episode start position
  2. Load goal image — final frame from reference trajectory
  3. Control loop (5 Hz, max 500 steps):
       a. camera.capture()         → RGB frame
       b. evaluator.predict()      → dist_pred, action_pred
       c. controller.compute_vel() → linear_vel, angular_vel
       d. controller.apply_vel()   → drive robot
       e. world.step()             → advance physics
       f. check collision          → log to episode
  4. evaluator.predict dist_pred < stop_threshold → stop
  5. compute_all_metrics()         → NavigationMetrics

This file runs inside Isaac Sim's bundled Python.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    from omni.isaac.core.world import World
    _ISAAC_AVAILABLE = True
except ImportError:
    _ISAAC_AVAILABLE = False


class GNMIsaacEnv:
    """Live Isaac Sim evaluation environment for GNM.

    Parameters
    ----------
    evaluator : GNMEvaluator
        Trained GNM evaluator (from gnm_vlnverse.evaluation.evaluator)
    robot_prim_path : str
    camera_prim_path : str
    max_steps : int
    physics_hz : float
        Isaac simulation frequency.  Camera captured every (physics_hz / control_hz) steps.
    control_hz : float
        GNM control frequency (typically 5 Hz).
    """

    def __init__(
        self,
        evaluator,
        robot_prim_path:  str   = "/World/YahboomM3Pro",
        camera_prim_path: str   = "/World/YahboomM3Pro/Camera",
        max_steps:        int   = 500,
        physics_hz:       float = 60.0,
        control_hz:       float = 5.0,
    ) -> None:
        if not _ISAAC_AVAILABLE:
            raise ImportError(
                "GNMIsaacEnv requires Isaac Sim. "
                "For offline evaluation, use GNMEvaluator.evaluate_from_files()."
            )
        self.evaluator        = evaluator
        self.robot_prim_path  = robot_prim_path
        self.camera_prim_path = camera_prim_path
        self.max_steps        = max_steps
        self.physics_hz       = physics_hz
        self.control_hz       = control_hz
        self.decimation       = int(physics_hz / control_hz)  # steps per control

        from .sensor import GNMCamera, GNMPoseSensor
        from .robot  import GNMRobotController

        self.camera     = GNMCamera(prim_path=camera_prim_path)
        self.pose_sensor = GNMPoseSensor(robot_prim_path=robot_prim_path)
        self.controller  = GNMRobotController(robot_prim_path=robot_prim_path)

        self._world: Optional[object] = None

    def setup(self) -> None:
        """Create USD prims and initialize sensors.  Call once before running episodes."""
        self._world = World.instance()
        self.camera.create()
        self.camera.attach_render_product()
        self.controller.initialize()
        logger.info("GNMIsaacEnv setup complete")

    def run_episode(
        self,
        goal_image:  np.ndarray,
        start_pos:   tuple[float, float, float],
    ) -> dict:
        """Run one GNM navigation episode.

        Parameters
        ----------
        goal_image : (H, W, 3) uint8 RGB
        start_pos  : (x, y, yaw_degrees) start pose

        Returns
        -------
        dict with actual_path, collisions, n_steps, stopped
        """
        from gnm_vlnverse.evaluation.metrics import Episode

        # Teleport robot to start
        self._teleport(start_pos)
        self._world.step(render=True)

        # Capture first frame and initialise context
        first_frame = self.camera.capture()
        self.evaluator.reset_context(first_frame)

        actual_path: list[tuple[float, float]] = []
        collisions:  list[bool] = []
        stopped = False

        x, y, yaw = self.pose_sensor.get_pose()
        actual_path.append((x, y))

        for step in range(self.max_steps):
            frame = self.camera.capture()
            dist_pred, action_pred = self.evaluator.predict(frame, goal_image)

            lin_vel, ang_vel = self.controller.compute_velocity(action_pred, yaw)
            self.controller.apply_velocity(lin_vel, ang_vel)

            # Step physics (decimation steps)
            for _ in range(self.decimation):
                self._world.step(render=False)

            # Record pose
            x, y, yaw = self.pose_sensor.get_pose()
            actual_path.append((x, y))

            # Check collision (PhysX contact reports)
            collision = self._check_collision()
            collisions.append(collision)

            if dist_pred < self.evaluator.stop_threshold:
                stopped = True
                logger.debug(f"Episode stopped at step {step} (dist_pred={dist_pred:.3f})")
                break

        self.controller.stop()

        return {
            "actual_path": actual_path,
            "collisions":  collisions,
            "n_steps":     step + 1,
            "stopped":     stopped,
        }

    def _teleport(self, pos: tuple[float, float, float]) -> None:
        """Teleport robot to (x, y, yaw_degrees)."""
        import math
        from pxr import Gf
        import omni.usd

        stage = omni.usd.get_context().get_stage()
        from pxr import UsdGeom
        prim  = stage.GetPrimAtPath(self.robot_prim_path)
        if not prim.IsValid():
            return

        x, y, yaw_deg = pos
        xf = UsdGeom.Xformable(prim)
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(x, y, 0.0))
        xf.AddRotateZOp().Set(float(yaw_deg))

    def _check_collision(self) -> bool:
        """Return True if robot is currently in contact with an obstacle."""
        try:
            import omni.physx
            contact_report = omni.physx.get_physx_interface().get_contact_report(
                self.robot_prim_path
            )
            return len(contact_report) > 0
        except Exception:
            return False
