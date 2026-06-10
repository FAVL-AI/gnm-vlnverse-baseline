"""
fleet_safe_vla.perception
=========================
Live semantic perception pipeline for FleetSafe.

Converts raw camera frames into semantically-labelled Detection objects
compatible with DynamicAgentTracker and the social-risk layer.

Public API
----------
    SemanticDetector      — YOLOv8 detector with role classification
    DepthFusion           — RGB-D 2-D position estimation from depth
    PerceptionPipeline    — end-to-end: frame → Detection list
    MockPerceptionSource  — deterministic stub for testing without hardware
"""
from fleet_safe_vla.perception.semantic_detector import (
    SemanticDetector,
    DetectionResult,
    RoleClassifier,
)
from fleet_safe_vla.perception.depth_fusion import DepthFusion
from fleet_safe_vla.perception.perception_pipeline import (
    PerceptionPipeline,
    PerceptionConfig,
)
from fleet_safe_vla.perception.mock_source import MockPerceptionSource

__all__ = [
    "SemanticDetector",
    "DetectionResult",
    "RoleClassifier",
    "DepthFusion",
    "PerceptionPipeline",
    "PerceptionConfig",
    "MockPerceptionSource",
]
