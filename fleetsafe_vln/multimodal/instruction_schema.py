"""Multimodal instruction schema — normalizes text/voice/image/click into NormalizedGoal."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class MultimodalInstruction:
    """Raw multimodal instruction from any input source."""
    text: str = ""
    voice_file: Optional[str] = None
    image_goal: Optional[str] = None
    clicked_region: Optional[Dict[str, Any]] = None
    semantic_goal: str = ""
    constraints: List[str] = field(default_factory=list)
    safety_profile: str = "standard"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MultimodalInstruction":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_text(cls, text: str) -> "MultimodalInstruction":
        return cls(text=text, semantic_goal=text)


@dataclass
class NormalizedGoal:
    """Unified goal representation after normalizing all input modalities."""
    goal_type: str = "semantic_object"   # semantic_object | image | waypoint | directional
    goal_label: str = ""
    goal_image_path: Optional[str] = None
    route_constraints: List[str] = field(default_factory=list)
    safety_profile: str = "standard"    # standard | human_aware | conservative
    nominal_vx: float = 0.20
    nominal_wz: float = 0.0
    confidence: float = 1.0
    source_modality: str = "text"
    raw_instruction: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def is_human_aware(self) -> bool:
        return self.safety_profile in ("human_aware", "conservative")

    def max_speed(self) -> float:
        profile_speeds = {
            "standard": 0.30,
            "human_aware": 0.15,
            "conservative": 0.10,
        }
        return profile_speeds.get(self.safety_profile, 0.30)
