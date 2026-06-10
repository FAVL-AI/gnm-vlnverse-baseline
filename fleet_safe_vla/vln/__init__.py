"""FleetSafe-VLN: voice/text/image-conditioned visual-language navigation.

Pipeline:
    Instruction (voice | text | image)
        → instruction_schema  → VLNInstruction
        → instruction_intake  → normalised text + goal
        → grounding           → GroundedGoal + safety constraints
        → backbone_router     → GNM / ViNT / NoMaD → u_nom
        → FleetSafe CBF-QP   → u_safe + SafetyCertificate
        → /cmd_vel + JSONL trace log
"""
from fleet_safe_vla.vln.instruction_schema import (
    VLNInstruction,
    GroundedGoal,
    SafetyConstraint,
    BackboneChoice,
    VLNTrace,
    InstructionSource,
)
from fleet_safe_vla.vln.instruction_intake import InstructionIntake
from fleet_safe_vla.vln.grounding import InstructionGrounder
from fleet_safe_vla.vln.backbone_router import BackboneRouter
from fleet_safe_vla.vln.vln_trace_logger import VLNTraceLogger

__all__ = [
    "VLNInstruction",
    "GroundedGoal",
    "SafetyConstraint",
    "BackboneChoice",
    "VLNTrace",
    "InstructionSource",
    "InstructionIntake",
    "InstructionGrounder",
    "BackboneRouter",
    "VLNTraceLogger",
]
