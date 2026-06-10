"""Backbone adapter interface — re-exports and extends fleet_safe_vla types."""
from __future__ import annotations

from typing import Any, List, Optional

try:
    from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
        BaseVisualNavAdapter,
    )
    from fleet_safe_vla.vln.backbone_router import BackboneRouter, NominalAction
    from fleet_safe_vla.vln.instruction_schema import BackboneChoice
    _BASE_OK = True
except ImportError:
    _BASE_OK = False
    BaseVisualNavAdapter = object
    BackboneChoice = None


def make_backbone(model: str, **kwargs) -> Any:
    """Return a BackboneRouter configured for the requested model.

    Fails gracefully — if the checkpoint is missing, returns mock backbone.
    """
    if not _BASE_OK:
        raise ImportError("fleet_safe_vla is not installed.")

    model = model.lower()
    choice_map = {
        "gnm": BackboneChoice.GNM,
        "vint": BackboneChoice.VINT,
        "nomad": BackboneChoice.NOMAD,
        "mock": BackboneChoice.MOCK,
        "auto": BackboneChoice.AUTO,
    }
    choice = choice_map.get(model, BackboneChoice.AUTO)
    return BackboneRouter(preferred=choice, **kwargs)


if not _BASE_OK:
    class NominalAction:  # type: ignore[no-redef]
        def __init__(self, vx=0.0, wz=0.0, backbone="mock"):
            self.vx = vx
            self.wz = wz
            self.backbone = backbone

        def as_list(self) -> List[float]:
            return [self.vx, self.wz]

    class BackboneAdapter:
        def run_nominal_policy(self, goal, camera_context=None, instruction=None):
            return NominalAction()
else:
    BackboneAdapter = BackboneRouter  # type: ignore[misc]
