"""BackboneRouter — select and run GNM / ViNT / NoMaD as nominal VLN backbones.

The router treats the learned model as a *nominal intent generator*, NOT as a
safety-critical controller. Its output is u_nom, which FleetSafe CBF-QP converts
to u_safe before any robot actuation.

Architecture:
    GroundedGoal + camera obs
        → BackboneRouter.choose_backbone()
        → BackboneRouter.run_nominal_policy()
        → u_nom (CmdVel-compatible list [vx, wz])
        → FleetSafe CBF-QP
        → u_safe
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fleet_safe_vla.vln.instruction_schema import (
    BackboneChoice,
    GroundedGoal,
    ActionType,
    VLNInstruction,
)


# ---------------------------------------------------------------------------
# Nominal action output
# ---------------------------------------------------------------------------

@dataclass
class NominalAction:
    """Raw nominal command from any backbone."""
    backbone:         str   = BackboneChoice.MOCK.value
    vx:               float = 0.0    # forward velocity (m/s)
    wz:               float = 0.0    # yaw rate (rad/s)
    inference_ms:     float = 0.0
    confidence:       float = 1.0
    explanation:      str   = ""
    waypoints:        List[Dict[str, Any]] = field(default_factory=list)

    def as_list(self) -> List[float]:
        return [self.vx, self.wz]


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class BackboneRouter:
    """Choose and invoke a nominal visual navigation backbone.

    Usage:
        router = BackboneRouter(preferred=BackboneChoice.GNM, max_vx=0.12, max_wz=0.35)
        action = router.run_nominal_policy(grounded_goal, camera_context)
        u_nom = action.as_list()
    """

    def __init__(
        self,
        preferred: BackboneChoice = BackboneChoice.AUTO,
        max_vx: float = 0.12,
        max_wz: float = 0.35,
        ckpt_dir: Optional[str] = None,
    ):
        self._preferred   = preferred
        self._max_vx      = max_vx
        self._max_wz      = max_wz
        self._ckpt_dir    = ckpt_dir
        self._adapters: Dict[str, Any] = {}
        self._attempted:  set[str]  = set()

    # ── Public API ────────────────────────────────────────────────────────────

    def choose_backbone(
        self,
        goal: GroundedGoal,
        instruction: Optional[VLNInstruction] = None,
    ) -> BackboneChoice:
        """Select the best backbone for this goal.

        Selection logic:
          1. If instruction.preferred_backbone is set, use it.
          2. If an image goal is available, prefer ViNT (image-goal conditioned).
          3. If a semantic search goal, try GNM.
          4. For directional/stop, fall back to mock.
        """
        if instruction and instruction.preferred_backbone:
            try:
                return BackboneChoice(instruction.preferred_backbone)
            except ValueError:
                pass

        if self._preferred != BackboneChoice.AUTO:
            return self._preferred

        if goal.target_image_path:
            return BackboneChoice.VINT

        if goal.action_type in (ActionType.STOP.value,):
            return BackboneChoice.MOCK

        # Try GNM as default general-purpose backbone
        return BackboneChoice.GNM

    def run_nominal_policy(
        self,
        goal: GroundedGoal,
        camera_context: Optional[Any] = None,
        instruction: Optional[VLNInstruction] = None,
    ) -> NominalAction:
        """Run the chosen backbone and return a nominal action.

        Falls back to rule-based mock if real adapter is unavailable.
        Never bypasses the safety layer.
        """
        backbone = self.choose_backbone(goal, instruction)
        t0 = time.perf_counter()

        # Try to use real adapter if available
        if backbone not in (BackboneChoice.MOCK,):
            action = self._try_real_adapter(backbone, goal, camera_context)
            if action is not None:
                action.inference_ms = (time.perf_counter() - t0) * 1000
                return self._clip(action)

        # Rule-based mock: derive from grounded goal directly
        action = self._mock_action(backbone, goal)
        action.inference_ms = (time.perf_counter() - t0) * 1000
        return self._clip(action)

    # ── Real adapter integration ──────────────────────────────────────────────

    def _try_real_adapter(
        self,
        backbone: BackboneChoice,
        goal: GroundedGoal,
        camera_context: Optional[Any],
    ) -> Optional[NominalAction]:
        """Attempt to call the real GNM/ViNT/NoMaD adapter.

        Returns None on any import/checkpoint error so we fall back to mock.
        """
        if backbone.value in self._attempted:
            return None
        self._attempted.add(backbone.value)
        try:
            if backbone == BackboneChoice.GNM:
                from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter import GNMAdapter
                if BackboneChoice.GNM.value not in self._adapters:
                    self._adapters[BackboneChoice.GNM.value] = GNMAdapter()
                return self._call_adapter(self._adapters[BackboneChoice.GNM.value], goal, camera_context)

            if backbone == BackboneChoice.VINT:
                from fleet_safe_vla.integrations.visualnav_transformer.vint_adapter import ViNTAdapter
                if BackboneChoice.VINT.value not in self._adapters:
                    self._adapters[BackboneChoice.VINT.value] = ViNTAdapter()
                return self._call_adapter(self._adapters[BackboneChoice.VINT.value], goal, camera_context)

            if backbone == BackboneChoice.NOMAD:
                from fleet_safe_vla.integrations.visualnav_transformer.nomad_adapter import NoMaDAdapter
                if BackboneChoice.NOMAD.value not in self._adapters:
                    self._adapters[BackboneChoice.NOMAD.value] = NoMaDAdapter()
                return self._call_adapter(self._adapters[BackboneChoice.NOMAD.value], goal, camera_context)

        except Exception as exc:
            print(f"[BackboneRouter] {backbone.value} unavailable ({type(exc).__name__}), using mock.")
        return None

    def _call_adapter(self, adapter: Any, goal: GroundedGoal, camera_context: Any) -> Optional[NominalAction]:
        """Convert an adapter's output to NominalAction.

        Adapter interface is compatible with base_adapter.BaseVisualNavAdapter.
        """
        try:
            # Adapters expose action_to_cmd_vel(); use goal as dummy observation
            raw_cmd = adapter.action_to_cmd_vel(
                waypoint=getattr(goal, "waypoint_dx", 0.0),
            )
            vx = float(getattr(raw_cmd, "vx", goal.nominal_vx))
            wz = float(getattr(raw_cmd, "wz", goal.nominal_wz))
            return NominalAction(
                backbone=type(adapter).__name__.lower().replace("adapter", ""),
                vx=vx, wz=wz,
                explanation=f"real {type(adapter).__name__}",
            )
        except Exception:
            return None

    # ── Mock rule-based policy ────────────────────────────────────────────────

    def _mock_action(self, backbone: BackboneChoice, goal: GroundedGoal) -> NominalAction:
        """Deterministic rule-based nominal action derived from grounded goal."""
        return NominalAction(
            backbone=backbone.value,
            vx=goal.nominal_vx,
            wz=goal.nominal_wz,
            confidence=goal.confidence,
            explanation=(
                f"mock rule-based: action={goal.action_type} "
                f"label={goal.label!r} conf={goal.confidence:.2f}"
            ),
            waypoints=[{"dx": goal.waypoint_dx, "dy": goal.waypoint_dy}],
        )

    # ── Clipping ──────────────────────────────────────────────────────────────

    def _clip(self, action: NominalAction) -> NominalAction:
        """Apply actuator limits to nominal action."""
        import math
        action.vx = max(-self._max_vx, min(self._max_vx, action.vx))
        action.wz = max(-self._max_wz, min(self._max_wz, action.wz))
        if not math.isfinite(action.vx):
            action.vx = 0.0
        if not math.isfinite(action.wz):
            action.wz = 0.0
        return action
