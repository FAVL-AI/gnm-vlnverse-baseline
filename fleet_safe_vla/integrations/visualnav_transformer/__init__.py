"""
fleet_safe_vla.integrations.visualnav_transformer
==================================================

FleetSafe adapters for GNM / ViNT / NoMaD from the upstream
visualnav-transformer repo (https://github.com/robodhruv/visualnav-transformer).

Upstream model code is NOT modified.  All FleetSafe-specific logic lives here.

Quickstart
----------
    bash scripts/visualnav/setup_visualnav.sh   # clone + install upstream
    python -c "from fleet_safe_vla.integrations.visualnav_transformer.validate_gates import run_all_gates; run_all_gates()"
"""
from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
    ActionOutput,
    BaseVisualNavAdapter,
    CheckpointNotFoundError,
    CmdVel,
    UpstreamNotFoundError,
)

__all__ = [
    "ActionOutput",
    "BaseVisualNavAdapter",
    "CheckpointNotFoundError",
    "CmdVel",
    "UpstreamNotFoundError",
]
