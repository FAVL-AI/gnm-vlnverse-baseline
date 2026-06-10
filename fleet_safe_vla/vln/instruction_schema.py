"""VLN instruction data schemas — no external dependencies.

These dataclasses are the shared data contract between every VLN module:
the intake layer, the grounding layer, the backbone router, and the trace logger.
All fields are JSON-serialisable via dataclasses.asdict().
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Dict, Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class InstructionSource(str, Enum):
    TEXT        = "text"
    VOICE       = "voice"
    IMAGE       = "image"
    VOICE_TEXT  = "voice_text"
    IMAGE_TEXT  = "image_text"
    MULTIMODAL  = "multimodal"
    STDIN       = "stdin"


class ActionType(str, Enum):
    NAVIGATE     = "navigate"
    STOP         = "stop"
    RETURN_HOME  = "return_home"
    SEARCH       = "search"
    FOLLOW       = "follow"
    TURN_LEFT    = "turn_left"
    TURN_RIGHT   = "turn_right"
    MOVE_FORWARD = "move_forward"
    MOVE_BACK    = "move_back"
    UNKNOWN      = "unknown"


class GoalType(str, Enum):
    SEMANTIC_REGION = "semantic_region"
    LANDMARK        = "landmark"
    WAYPOINT        = "waypoint"
    IMAGE_GOAL      = "image_goal"
    DIRECTIONAL     = "directional"
    STOP            = "stop"
    UNKNOWN         = "unknown"


class BackboneChoice(str, Enum):
    GNM   = "gnm"
    VINT  = "vint"
    NOMAD = "nomad"
    AUTO  = "auto"
    MOCK  = "mock"


# ---------------------------------------------------------------------------
# Core instruction schemas
# ---------------------------------------------------------------------------

@dataclass
class VLNInstruction:
    """Normalised language instruction from any source modality."""

    instruction_id:         str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp_ns:           int   = field(default_factory=lambda: int(time.time() * 1e9))
    source:                 str   = InstructionSource.TEXT.value
    raw_text:               str   = ""
    transcript:             str   = ""
    transcript_confidence:  Optional[float] = None
    audio_path:             Optional[str]   = None
    image_path:             Optional[str]   = None
    goal_text:              str   = ""
    goal_type:              str   = GoalType.UNKNOWN.value
    constraints:            List[str] = field(default_factory=list)
    preferred_backbone:     Optional[str] = None
    confidence:             float = 1.0
    metadata:               Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> "VLNInstruction":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_text(cls, text: str, source: InstructionSource = InstructionSource.TEXT) -> "VLNInstruction":
        return cls(raw_text=text, transcript=text, source=source.value, goal_text=text)


@dataclass
class SafetyConstraint:
    """A safety constraint extracted from a natural-language instruction."""

    constraint_type:  str   = "avoid"    # "avoid" | "max_speed" | "stop_at" | "no_enter"
    target:           str   = ""         # "people" | "obstacles" | "chair" | "zone:ICU"
    distance_m:       float = 0.5        # minimum clearance in metres
    mandatory:        bool  = True       # if True, robot stops if violated
    source_text:      str   = ""         # the substring that triggered this constraint

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GroundedGoal:
    """The result of grounding a VLNInstruction against the environment."""

    label:                str   = ""
    confidence:           float = 0.0
    source:               str   = "rule_based"   # "rule_based" | "topomap" | "goal_image" | "llm"
    goal_type:            str   = GoalType.UNKNOWN.value
    action_type:          str   = ActionType.UNKNOWN.value
    target_node_id:       Optional[str] = None
    target_image_path:    Optional[str] = None
    relative_hint:        Optional[str] = None
    waypoint_dx:          float = 0.0   # desired motion in robot x-frame (forward)
    waypoint_dy:          float = 0.0   # desired motion in robot y-frame (lateral)
    nominal_vx:           float = 0.0   # suggested forward speed
    nominal_wz:           float = 0.0   # suggested yaw rate
    safety_constraints:   List[SafetyConstraint] = field(default_factory=list)
    clarification_needed: bool  = False
    stop_reason:          Optional[str] = None
    grounding_candidates: List[Dict[str, Any]] = field(default_factory=list)

    def is_actionable(self) -> bool:
        """Return True if the robot should attempt motion."""
        return (
            not self.clarification_needed
            and self.confidence >= 0.3
            and self.action_type != ActionType.UNKNOWN.value
            and self.stop_reason is None
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["safety_constraints"] = [c.to_dict() for c in self.safety_constraints]
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class VLNPlan:
    """A VLN plan: instruction → grounded goal → chosen backbone."""

    instruction_id:     str  = ""
    policy_name:        str  = BackboneChoice.MOCK.value
    grounded_goal:      Optional[GroundedGoal] = None
    selected_goal_image: Optional[str] = None
    status:             str  = "pending"   # "pending" | "executing" | "succeeded" | "failed" | "stopped"
    explanation:        str  = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.grounded_goal is not None:
            d["grounded_goal"] = self.grounded_goal.to_dict()
        return d


@dataclass
class VLNTrace:
    """One timestep of VLN execution — the primary audit record."""

    timestamp_ns:           int   = field(default_factory=lambda: int(time.time() * 1e9))
    instruction_source:     str   = ""
    raw_instruction:        str   = ""
    parsed_instruction:     Dict[str, Any] = field(default_factory=dict)
    grounding_candidates:   List[Dict[str, Any]] = field(default_factory=list)
    chosen_subgoal:         Dict[str, Any] = field(default_factory=dict)
    current_camera_frame_id: str  = ""
    model_name:             str   = ""
    u_nom:                  List[float] = field(default_factory=lambda: [0.0, 0.0])
    u_safe:                 List[float] = field(default_factory=lambda: [0.0, 0.0])
    cbf_active:             bool  = False
    qp_status:              str   = "not_available"
    min_dist_m:             float = 0.0
    h_min:                  float = 0.0
    latency_ms:             float = 0.0
    stop_reason:            Optional[str] = None
    certificate_id:         str   = ""
    notes:                  str   = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, line: str) -> "VLNTrace":
        d = json.loads(line)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
