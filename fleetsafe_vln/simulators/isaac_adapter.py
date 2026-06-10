"""Isaac Sim adapter — wraps the existing run_supervisor_demo_isaac environment.

Fails gracefully if Isaac is not installed.
"""
from __future__ import annotations

from typing import Any, List

from fleetsafe_vln.simulators.base import SimulatorAdapter, SimulatorObs


class IsaacSimAdapter(SimulatorAdapter):
    """Thin wrapper around Isaac Lab FleetSafe environment."""

    platform_name = "isaac"

    def __init__(self, scene: str = "hospital_corridor", headless: bool = False,
                 stream: bool = True, **kwargs):
        self._scene = scene
        self._headless = headless
        self._stream = stream
        self._env = None
        self._step_count = 0
        self._check_available()

    def _check_available(self) -> None:
        try:
            import omni  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "Isaac Sim (omni) is not installed or not activated. "
                "Activate the 'isaac' conda environment and retry. "
                f"Original error: {e}"
            ) from e

    def reset(self, task: Any) -> SimulatorObs:
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro import FleetSafeHospitalEnv  # type: ignore
        if self._env is not None:
            self._env.close()
        self._env = FleetSafeHospitalEnv(
            scene=self._scene,
            headless=self._headless,
            stream=self._stream,
        )
        obs = self._env.reset()
        self._step_count = 0
        return self._convert(obs)

    def step(self, u_safe: List[float]) -> SimulatorObs:
        assert self._env is not None, "Call reset() first"
        obs, _, done, info = self._env.step(u_safe)
        self._step_count += 1
        return self._convert(obs, done=done, info=info)

    def close(self) -> None:
        if self._env is not None:
            self._env.close()
            self._env = None

    def _convert(self, raw: Any, done: bool = False, info: dict = None) -> SimulatorObs:
        import numpy as np
        info = info or {}
        return SimulatorObs(
            rgb=getattr(raw, "rgb", None),
            depth=getattr(raw, "depth", None),
            lidar=getattr(raw, "lidar", None),
            robot_pose=tuple(getattr(raw, "pose", (0.0, 0.0, 0.0))),
            obstacle_positions=list(getattr(raw, "obstacle_xy", [])),
            human_positions=list(getattr(raw, "human_xy", [])),
            goal_reached=bool(info.get("goal_reached", done)),
            collision=bool(info.get("collision", False)),
            step=self._step_count,
            metadata=info,
        )

    def is_available(self) -> bool:
        try:
            import omni  # noqa: F401
            return True
        except ImportError:
            return False
