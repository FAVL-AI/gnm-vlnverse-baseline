"""TaskConfig — YAML-driven task definition for FleetSafe-VLN episodes."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False


@dataclass
class RobotProfile:
    name: str = "yahboom_m3_pro"
    max_vx: float = 0.30
    max_wz: float = 0.70
    wheel_base_m: float = 0.23
    lidar_range_m: float = 8.0
    camera_fov_deg: float = 87.0
    ros2_namespace: str = "/m3pro"


@dataclass
class SafetyConstraints:
    d_safe_m: float = 0.50
    estop_dist_m: float = 0.30
    min_human_distance_m: float = 0.80
    max_speed_near_humans: float = 0.15
    cbf_alpha: float = 1.0


@dataclass
class TaskInstruction:
    text: str = ""
    voice_file: Optional[str] = None
    image_goal: Optional[str] = None
    semantic_goal: str = ""
    constraints: List[str] = field(default_factory=list)


@dataclass
class TaskConfig:
    task_id: str = ""
    scene: str = ""
    platform: str = "mock"
    description: str = ""
    instruction: TaskInstruction = field(default_factory=TaskInstruction)
    start_pose: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    goal_xy: List[float] = field(default_factory=lambda: [3.0, 0.0])
    optimal_path_m: float = 3.0
    success_radius_m: float = 0.5
    max_steps: int = 500
    control_hz: float = 4.0
    safety: SafetyConstraints = field(default_factory=SafetyConstraints)
    robot: RobotProfile = field(default_factory=RobotProfile)
    metrics: List[str] = field(default_factory=lambda: [
        "success_rate", "spl", "navigation_error",
        "collision_rate", "min_obstacle_distance",
        "min_human_distance", "cbf_intervention_count",
        "cbf_intervention_magnitude", "certificate_validity_rate",
        "near_miss_count",
    ])
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_yaml(self) -> str:
        if not _YAML_OK:
            raise ImportError("pyyaml not installed: pip install pyyaml")
        return yaml.dump(self.to_dict(), default_flow_style=False)


def load_task(path: str | Path) -> TaskConfig:
    """Load a TaskConfig from a YAML or JSON file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Task file not found: {p}")

    raw = p.read_text(encoding="utf-8")

    if p.suffix in (".yaml", ".yml"):
        if not _YAML_OK:
            raise ImportError("pyyaml not installed: pip install pyyaml")
        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)

    instruction_data = data.pop("instruction", {})
    safety_data = data.pop("safety", {})
    robot_data = data.pop("robot", {})

    return TaskConfig(
        **{k: v for k, v in data.items() if k in TaskConfig.__dataclass_fields__},
        instruction=TaskInstruction(**{
            k: v for k, v in instruction_data.items()
            if k in TaskInstruction.__dataclass_fields__
        }),
        safety=SafetyConstraints(**{
            k: v for k, v in safety_data.items()
            if k in SafetyConstraints.__dataclass_fields__
        }),
        robot=RobotProfile(**{
            k: v for k, v in robot_data.items()
            if k in RobotProfile.__dataclass_fields__
        }),
    )
