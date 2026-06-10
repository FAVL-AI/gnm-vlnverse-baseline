"""
fleet_safe_vla/envs/isaaclab/yahboom/m3pro_nav_env.py

Isaac Lab navigation benchmark environment for the Yahboom M3Pro.

Provides the same Gym-compatible interface as YahboomObstacleEnv (MuJoCo):
  reset(seed) -> (obs: np.ndarray[47], info: dict)
  step(action: np.ndarray[2]) -> (obs, reward, terminated, truncated, info)
  teleport_to(x, y, yaw=0.0) -> None
  close() -> None
  ._last_obs  (cache updated at reset / step / teleport_to)

Physics:   Isaac Lab rigid body simulation via SimulationContext.
Robot:     Kinematic integration of cmd_vel — identical algorithm to
           YahboomMuJoCoBase.step().  Robot appears as a kinematic USD prim
           in Isaac space (box placeholder).  Upgradeable to full articulation
           when M3Pro URDF/USD is ready.
Obstacles: Spawned as kinematic rigid cylinders at exact SceneSpec (x, y)
           coordinates.  Isaac physics handles their rigid-body presence.
Collision: Distance-based (same formula as MuJoCo) for metric comparability.

Fail policy:
  - Module is importable without Isaac (CI safe).
  - Class instantiation raises IsaacNotAvailableError immediately if
    called outside an AppLauncher process or if isaaclab is not installed.
  - Never falls back to mock.

PREREQUISITE: AppLauncher must be initialised before instantiating this
class.  See scripts/visualnav/run_visualnav_benchmark_isaac.py.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

# ── Isaac availability guard ──────────────────────────────────────────────────
# Only stdlib + numpy imported at module level.  All isaaclab imports deferred.

try:
    import isaaclab  # noqa: F401
    _ISAACLAB_AVAILABLE = True
except ImportError:
    _ISAACLAB_AVAILABLE = False

# ── Physical constants (match YahboomObstacleEnv) ────────────────────────────

OBS_RADIUS_M     = 0.10    # cylinder radius — same as MuJoCo obstacle_env
CHASSIS_SIZE_XYZ = (0.28, 0.22, 0.08)   # robot placeholder box (L, W, H) m
ROBOT_Z_OFFSET   = CHASSIS_SIZE_XYZ[2] / 2.0   # bottom of chassis at z=0
MAX_LINEAR_MS    = 0.5
MAX_ANGULAR_RS   = 1.0
SIM_DT           = 0.01    # Isaac physics timestep (100 Hz fixed)
_NEAR_MISS_M     = 0.30    # safety cost threshold (reward)

_REPO_ROOT = Path(__file__).resolve().parents[5]


# ── Public exception ──────────────────────────────────────────────────────────

class IsaacNotAvailableError(RuntimeError):
    """
    Raised when IsaacNavBenchmarkEnv is instantiated outside an active
    AppLauncher process, or when isaaclab is not installed in this Python env.

    CI note: this module and exception class are always importable.

    Remedy:
      conda activate isaac
      python scripts/visualnav/run_visualnav_benchmark_isaac.py --model gnm ...
    """


# ── Isaac physics benchmark env ───────────────────────────────────────────────

class IsaacNavBenchmarkEnv:
    """
    Isaac Lab navigation benchmark environment for the Yahboom M3Pro.

    Matches the YahboomObstacleEnv (MuJoCo) API exactly so that
    VisualNavBenchmarkRunner._run_isaaclab_episode() mirrors
    _run_mujoco_episode() with minimal changes.

    Parameters
    ----------
    fixed_positions : list[(x, y)]
        World positions of static cylinder obstacles. Spawned as kinematic
        rigid cylinders in Isaac space.
    n_obstacles : int
        Used when fixed_positions is None (random placement is disabled for
        benchmark use; pass fixed_positions from SceneSpec).
    max_episode_steps : int
    control_hz : float
        Control frequency. Isaac steps at SIM_DT=0.01 s; decimation is
        round(1 / (control_hz * SIM_DT)) sim steps per control step.
    seed : int | None
    """

    _EXPECTED_OBS_DIM: int = 47

    def __init__(
        self,
        fixed_positions:    list[tuple[float, float]] | None = None,
        obstacle_radii:     list[float] | None = None,
        n_obstacles:        int   = 0,
        max_episode_steps:  int   = 500,
        control_hz:         float = 4.0,
        seed:               int | None = None,
        scene_name:         str   = "",
        dynamic_agent_specs: list | None = None,
    ) -> None:
        if not _ISAACLAB_AVAILABLE:
            raise IsaacNotAvailableError(
                "isaaclab package not found in this Python environment.\n"
                "  conda activate isaac\n"
                "  python scripts/visualnav/run_visualnav_benchmark_isaac.py"
            )

        # Verify AppLauncher is active by probing a submodule that requires it.
        try:
            from isaaclab.sim import SimulationContext, SimulationCfg  # noqa: F401
        except Exception as exc:
            raise IsaacNotAvailableError(
                "AppLauncher not initialised.  Must call AppLauncher before "
                "constructing IsaacNavBenchmarkEnv.\n"
                f"  Original error: {exc}\n"
                "  Entry point: scripts/visualnav/run_visualnav_benchmark_isaac.py"
            ) from exc

        self._fixed_positions: list[tuple[float, float]] = fixed_positions or []
        self._n_obstacles = max(n_obstacles, len(self._fixed_positions))
        self.max_episode_steps = max_episode_steps
        self.control_hz = control_hz
        self._decimation = max(1, round(1.0 / (control_hz * SIM_DT)))
        self._rng = np.random.default_rng(seed)
        self._scene_name = scene_name
        self._dynamic_agent_specs = dynamic_agent_specs or []
        self.hospital_zone_map = None  # set by _maybe_spawn_hospital_scene()

        # Per-obstacle radii — used for both physics cylinders and distance queries.
        # Falls back to OBS_RADIUS_M if not supplied.
        _n = len(self._fixed_positions)
        self._obstacle_radii: list[float] = (
            list(obstacle_radii) if obstacle_radii and len(obstacle_radii) == _n
            else [OBS_RADIUS_M] * _n
        )
        self._obstacle_radii_arr = np.array(self._obstacle_radii, dtype=np.float64)

        # Internal kinematic state (mirrors YahboomMuJoCoBase exactly)
        self._x:         float = 0.0
        self._y:         float = 0.0
        self._yaw:       float = 0.0
        self._step_count: int  = 0
        self._last_cmd = np.zeros(2, dtype=np.float32)

        # 47-dim obs adapter (M3Pro contract)
        from fleet_safe_vla.robots.yahboom.controllers.obs_adapter_m3pro import (
            M3ProObsAdapter,
        )
        self._obs_adapter = M3ProObsAdapter()

        # Obstacle positions for distance queries
        self._obs_xy = (
            np.array(self._fixed_positions, dtype=np.float64).reshape(-1, 2)
            if self._fixed_positions
            else np.empty((0, 2), dtype=np.float64)
        )

        # Bring up Isaac simulation.
        # Reuse the singleton SimulationContext if one already exists (Isaac Lab 4/5.x
        # enforces a singleton — creating a second one resets the first).
        from isaaclab.sim import SimulationContext, SimulationCfg
        existing = SimulationContext.instance()
        if existing is not None:
            self._sim = existing
        else:
            self._sim = SimulationContext(SimulationCfg(dt=SIM_DT))

        # Track prim paths we create so close() can delete them cleanly.
        self._owned_prim_paths: list[str] = []

        # Spawn scene objects into /World
        # Hospital scenes replace the flat ground + lights with room geometry.
        if not self._maybe_spawn_hospital_scene():
            self._spawn_ground_and_lights()
        self._spawn_obstacles()
        self._robot_prim_path = self._spawn_robot_placeholder()

        # Initialise physics.
        # reset() stops the timeline; play() must be called before step().
        self._sim.reset()
        self._sim.play()
        self._flush_app(n=4)

        # Build initial obs cache
        obs = self._build_obs()
        self._last_obs = obs

    # ── Gym-compatible API ────────────────────────────────────────────────────

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict | None = None,
    ) -> tuple[np.ndarray, dict]:
        if seed is not None:
            self._rng = np.random.default_rng(seed)

        # Small random jitter around origin (same as MuJoCo base_env)
        self._x   = float(self._rng.uniform(-0.1,  0.1))
        self._y   = float(self._rng.uniform(-0.1,  0.1))
        self._yaw = float(self._rng.uniform(-0.2,  0.2))
        self._step_count = 0
        self._last_cmd   = np.zeros(2, dtype=np.float32)
        self._obs_adapter.reset()

        self._write_robot_pose()
        if not self._sim.is_playing():
            self._sim.play()
        self._sim.step()
        self._flush_app(n=2)

        obs = self._build_obs()
        self._last_obs = obs
        return obs, self._task_info()

    def step(
        self,
        action: np.ndarray,
    ) -> tuple[np.ndarray, float, bool, bool, dict]:
        action = np.clip(
            action,
            np.array([-MAX_LINEAR_MS, -MAX_ANGULAR_RS], dtype=np.float32),
            np.array([ MAX_LINEAR_MS,  MAX_ANGULAR_RS], dtype=np.float32),
        )
        vx = float(action[0])
        wz = float(action[1])
        self._last_cmd = action.astype(np.float32)

        dt = 1.0 / self.control_hz

        # Kinematic integration — identical to YahboomMuJoCoBase.step()
        self._x   += vx * math.cos(self._yaw) * dt
        self._y   += vx * math.sin(self._yaw) * dt
        self._yaw += wz * dt

        self._write_robot_pose()

        # Advance Isaac physics
        if not self._sim.is_playing():
            self._sim.play()
        for _ in range(self._decimation):
            self._sim.step()

        obs = self._build_obs()
        self._last_obs = obs
        self._step_count += 1

        info      = self._task_info()
        reward    = self._compute_reward(vx, info["min_obstacle_dist_m"])
        terminated = info["collision"]
        truncated  = self._step_count >= self.max_episode_steps

        return obs, float(reward), terminated, truncated, info

    def teleport_to(self, x: float, y: float, yaw: float = 0.0) -> None:
        """Move robot to world (x, y, yaw) — used for start-position init."""
        self._x   = x
        self._y   = y
        self._yaw = yaw
        self._write_robot_pose()
        if not self._sim.is_playing():
            self._sim.play()
        self._sim.step()
        self._flush_app(n=2)
        self._last_obs = self._build_obs()

    def close(self) -> None:
        # Clean up camera render product before removing prims.
        if getattr(self, "_has_camera", False):
            try:
                self._rgb_annotator.detach()
                self._render_product.destroy()
            except Exception:
                pass
            self._has_camera = False
        # Delete scene prims we spawned so the next episode can re-use the same paths.
        # sim.stop() deadlocks in Isaac Sim 5.x outside the app update loop, so we
        # clean up via USD stage removal instead.
        try:
            import omni.usd
            stage = omni.usd.get_context().get_stage()
            for path in getattr(self, "_owned_prim_paths", []):
                stage.RemovePrim(path)
            # Also remove the Obstacles parent prim if it exists
            stage.RemovePrim("/World/Obstacles")
        except Exception:
            pass
        self._flush_app(n=4)

    # ── Photoreal camera ──────────────────────────────────────────────────────

    def setup_camera(self, img_w: int = 85, img_h: int = 64) -> bool:
        """
        Mount a forward-facing camera on the robot matching the M3Pro URDF camera_link.

        The camera prim is a child of /World/Robot so it automatically inherits
        the robot's world transform at every step.

        URDF camera_joint: xyz="0.100 0.0 0.082" from base_link.
        base_link is at wheel-axle height (0.048 m from floor).
        Camera world height ≈ 0.048 + 0.082 = 0.130 m from floor.
        Relative to the robot box centre (z=0.04 m): z_offset = +0.09 m.

        Rotation: RotateY(90°) makes the USD camera's -Z look direction point
        along the robot's +X (forward).  No tilt — URDF rpy is 0 0 0.

        Returns True on success; False if omni.replicator is unavailable
        (the caller falls back to zero-frame images).
        """
        try:
            import omni.replicator.core as rep
            import omni.usd
            from pxr import Gf, UsdGeom

            stage = omni.usd.get_context().get_stage()
            cam_path = f"{self._robot_prim_path}/Camera"

            cam = UsdGeom.Camera.Define(stage, cam_path)
            # Horizontal aperture + focal length → ≈ 62° HFOV (matching USB cam)
            cam.GetHorizontalApertureAttr().Set(20.955)
            cam.GetFocalLengthAttr().Set(17.5)
            cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.01, 50.0))

            # Local offset relative to /World/Robot box centre:
            # +0.10 m forward (X), 0 lateral (Y), +0.09 m up (Z = 0.13 m from floor)
            # RotateY(90°): rotates -Z look direction → +X (robot forward).
            xform = UsdGeom.Xformable(cam.GetPrim())
            xform.ClearXformOpOrder()
            t_op = xform.AddTranslateOp()
            t_op.Set(Gf.Vec3d(0.10, 0.0, 0.09))
            r_op = xform.AddRotateXYZOp()
            r_op.Set(Gf.Vec3f(0.0, 90.0, 0.0))

            rp = rep.create.render_product(cam_path, resolution=(img_w, img_h))
            annotator = rep.AnnotatorRegistry.get_annotator("rgb")
            annotator.attach([rp])

            self._cam_prim_path  = cam_path
            self._render_product = rp
            self._rgb_annotator  = annotator
            self._cam_img_shape  = (img_h, img_w)
            self._has_camera     = True
            self._frame_log_count = 0

            # Warm up the RTX renderer — Isaac Sim 5.x needs multiple passes
            # before the async pipeline produces non-black frames.
            import sys as _sys
            for _wi in range(30):
                self._sim.render()
                self._flush_app(n=2)
                _d = annotator.get_data()
                if _d is not None and _d.size > 0:
                    _mean = float(np.mean(_d[:, :, :3]))
                    if _mean > 2.0:
                        print(
                            f"[IsaacNavBenchmarkEnv] Camera ready after {_wi + 1} "
                            f"warm-up renders (mean={_mean:.1f})",
                            file=_sys.stderr, flush=True,
                        )
                        break
            else:
                print(
                    "[IsaacNavBenchmarkEnv] Camera still blank after 30 warm-up renders",
                    file=_sys.stderr, flush=True,
                )
            return True
        except Exception as exc:
            print(f"[IsaacNavBenchmarkEnv] Camera setup failed: {exc} — using random obs")
            self._has_camera = False
            return False

    def get_rgb_frame(self) -> np.ndarray:
        """
        Render one frame and return (H, W, 3) uint8 RGB from the robot camera.

        Falls back to random noise when camera is not set up (so callers don't
        need to guard — they just get a less-informative observation).
        """
        if not getattr(self, "_has_camera", False):
            h, w = getattr(self, "_cam_img_shape", (64, 85))
            return np.zeros((h, w, 3), dtype=np.uint8)
        try:
            self._sim.render()
            data = self._rgb_annotator.get_data()   # (H, W, 4) RGBA uint8
            if data is None or data.size == 0:
                h, w = self._cam_img_shape
                return np.zeros((h, w, 3), dtype=np.uint8)
            rgb = np.asarray(data[:, :, :3], dtype=np.uint8).copy()
            # Log shape/stats for the first 5 frames to aid debugging blank-camera issues
            if getattr(self, "_frame_log_count", 0) < 5:
                import sys as _sys
                print(
                    f"[IsaacNavBenchmarkEnv] frame[{self._frame_log_count}] "
                    f"shape={rgb.shape} dtype={rgb.dtype} "
                    f"min={int(rgb.min())} max={int(rgb.max())} mean={float(np.mean(rgb)):.1f}",
                    file=_sys.stderr, flush=True,
                )
                self._frame_log_count += 1
            return rgb
        except Exception:
            h, w = self._cam_img_shape
            return np.zeros((h, w, 3), dtype=np.uint8)

    def get_robot_pose(self) -> tuple[float, float, float]:
        return self._x, self._y, self._yaw

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _flush_app(self, n: int = 4) -> None:
        """Flush the omni kit event loop n times.

        Required in Isaac Sim 5.x after reset() so that the physics engine
        completes its async initialisation handshake before any step() calls.
        """
        try:
            import omni.kit.app
            app = omni.kit.app.get_app()
            for _ in range(n):
                app.update()
        except Exception:
            pass

    # ── Scene construction ────────────────────────────────────────────────────

    _HOSPITAL_SCENE_NAMES = frozenset({
        "hospital_corridor",
        "hospital_icu_approach",
        "hospital_elevator_lobby",
    })

    def _maybe_spawn_hospital_scene(self) -> bool:
        """
        If scene_name is a hospital scene, spawn the procedural hospital world.

        Returns True when the hospital scene was spawned (caller should skip
        the default _spawn_ground_and_lights).  Returns False otherwise.

        On success, self.hospital_zone_map is populated with the ZoneMap.
        Agent capsules are spawned for any dynamic_agent_specs provided.
        """
        if self._scene_name not in self._HOSPITAL_SCENE_NAMES:
            return False
        try:
            from fleet_safe_vla.envs.isaaclab.hospital.hospital_world_loader import (
                HospitalWorldLoader,
            )
            agent_specs = [
                {
                    "agent_id": f"agent_{i}",
                    "position_xy": spec.position_at(0.0),
                    "semantic_role": getattr(spec, "semantic_role", "unknown"),
                }
                for i, spec in enumerate(self._dynamic_agent_specs)
            ]
            loader = HospitalWorldLoader(verbose=True)
            zone_map, prim_paths = loader.build_procedural_scene(
                base_prim="/World/Hospital",
                spawn_lights=True,
                agent_specs=agent_specs or None,
            )
            self._owned_prim_paths.extend(prim_paths)
            self.hospital_zone_map = zone_map
            return True
        except Exception as exc:
            print(f"[IsaacNavBenchmarkEnv] Hospital scene build failed: {exc}; "
                  f"falling back to flat ground.")
            return False

    def _spawn_ground_and_lights(self) -> None:
        import isaaclab.sim as sim_utils
        # GroundPlaneCfg loads a USD from the Isaac Assets nucleus server.
        # Fall back to a plain procedural plane if that asset is unavailable
        # (pip-only install without a local nucleus server).
        try:
            ground_cfg = sim_utils.GroundPlaneCfg()
            ground_cfg.func("/World/Ground", ground_cfg)
        except Exception:
            try:
                from pxr import UsdGeom, Gf
                stage = self._sim.stage
                mesh = UsdGeom.Mesh.Define(stage, "/World/Ground")
                mesh.CreatePointsAttr([
                    Gf.Vec3f(-50, -50, 0), Gf.Vec3f(50, -50, 0),
                    Gf.Vec3f(50,  50, 0), Gf.Vec3f(-50,  50, 0),
                ])
                mesh.CreateFaceVertexCountsAttr([4])
                mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
            except Exception:
                pass  # headless benchmark run — ground plane is cosmetic only
        try:
            light_cfg = sim_utils.DomeLightCfg(intensity=2000.0, color=(0.9, 0.9, 1.0))
            light_cfg.func("/World/DomeLight", light_cfg)
        except Exception:
            pass  # lighting is cosmetic only

    def _spawn_obstacles(self) -> None:
        import isaaclab.sim as sim_utils
        for i, (ox, oy) in enumerate(self._fixed_positions):
            prim_path = f"/World/Obstacles/obs_{i}"
            # No visual_material: obstacles are invisible to the VLA camera.
            # The CBF uses known obstacle positions from the scene map — this
            # models map-based hazards that vision may not detect (glass, zones, etc.)
            obs_cfg = sim_utils.CylinderCfg(
                radius=self._obstacle_radii[i],
                height=0.50,
                rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
                mass_props=sim_utils.MassPropertiesCfg(mass=10.0),
                collision_props=sim_utils.CollisionPropertiesCfg(),
            )
            obs_cfg.func(prim_path, obs_cfg, translation=(float(ox), float(oy), 0.25))
            self._owned_prim_paths.append(prim_path)

    def _spawn_robot_placeholder(self) -> str:
        """Spawn a kinematic box prim as the robot placeholder. Returns prim path."""
        import isaaclab.sim as sim_utils
        prim_path = "/World/Robot"
        lx, ly, lz = CHASSIS_SIZE_XYZ
        box_cfg = sim_utils.CuboidCfg(
            size=(lx, ly, lz),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=2.1),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.15, 0.45, 0.80)),
        )
        box_cfg.func(prim_path, box_cfg, translation=(0.0, 0.0, ROBOT_Z_OFFSET))
        self._owned_prim_paths.append(prim_path)
        return prim_path

    # ── Robot pose write-back ─────────────────────────────────────────────────

    def _write_robot_pose(self) -> None:
        """Set the robot prim's world transform from kinematic state."""
        try:
            from pxr import Gf, UsdGeom
            import omni.usd
            stage = omni.usd.get_context().get_stage()
            prim  = stage.GetPrimAtPath(self._robot_prim_path)
            if not prim.IsValid():
                return
            xform = UsdGeom.Xformable(prim)
            xform.ClearXformOpOrder()
            # Translation
            t_op = xform.AddTranslateOp()
            t_op.Set(Gf.Vec3d(self._x, self._y, ROBOT_Z_OFFSET))
            # Rotation about Z (yaw)
            r_op = xform.AddRotateZOp()
            r_op.Set(math.degrees(self._yaw))
        except Exception:
            # Fail silently — pose tracking still works via Python state
            pass

    # ── Observation / info ────────────────────────────────────────────────────

    def _nearest_dist(self) -> float:
        if self._obs_xy.shape[0] == 0:
            return 99.0
        dists = np.linalg.norm(
            self._obs_xy - np.array([self._x, self._y], dtype=np.float64),
            axis=1,
        )
        return float(np.min(dists - self._obstacle_radii_arr))

    def _compute_reward(self, vx: float, min_d: float) -> float:
        safety_cost = 1.0 if min_d < _NEAR_MISS_M else 0.0
        return 0.1 + 1.0 * vx - 5.0 * safety_cost

    def _task_info(self) -> dict:
        min_d = self._nearest_dist()
        return {
            "step":                self._step_count,
            "robot_xy":            [self._x, self._y],
            "min_obstacle_dist_m": min_d,
            "collision":           min_d < 0.0,
            "success":             False,
            "isaac_contact_count": 0,   # wired in Stage 3 (LiDAR/contact)
        }

    def _build_obs(self) -> np.ndarray:
        """Build 47-dim M3ProObsAdapter obs from current kinematic state."""
        from fleet_safe_vla.robots.yahboom.controllers.obs_adapter_m3pro import (
            M3ProCommand,
            M3ProGeometry,
            M3ProState,
        )
        vx  = float(self._last_cmd[0])
        wz  = float(self._last_cmd[1])
        geo = M3ProGeometry()

        # Estimate wheel angular speed from kinematic cmd_vel
        w_l = (vx - wz * (geo.lx + geo.ly)) / geo.wheel_radius_m
        w_r = (vx + wz * (geo.lx + geo.ly)) / geo.wheel_radius_m

        # Quaternion (xyzw) for current yaw
        qz = math.sin(self._yaw / 2.0)
        qw = math.cos(self._yaw / 2.0)

        state = M3ProState(
            imu_lin_acc=np.array([0.0, 0.0, -9.81],  dtype=np.float32),
            imu_ang_vel=np.array([0.0, 0.0, wz],      dtype=np.float32),
            imu_quat=np.array([0.0, 0.0, qz, qw],     dtype=np.float32),
            joint_positions=np.zeros(4,  dtype=np.float32),
            joint_velocities=np.array([w_l, w_r, w_l, w_r], dtype=np.float32),
            joint_efforts=np.zeros(4, dtype=np.float32),
            odom_pos=np.array([self._x, self._y, 0.0], dtype=np.float32),
            odom_quat=np.array([0.0, 0.0, qz, qw],    dtype=np.float32),
            odom_vel=np.array([vx, 0.0, wz],           dtype=np.float32),
        )
        cmd = M3ProCommand(vx=vx, vy=0.0, wz=wz)
        return self._obs_adapter.update(state, cmd)
