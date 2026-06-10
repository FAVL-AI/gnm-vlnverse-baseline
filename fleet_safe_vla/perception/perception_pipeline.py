"""
perception_pipeline.py — end-to-end frame → Detection list pipeline.

PerceptionPipeline is the single entry point for the live perception stack.
It wires SemanticDetector → DepthFusion → list[Detection] in one call.

    pipeline = PerceptionPipeline.from_config(config)
    detections = pipeline.process(rgb_frame, depth_image, robot_xy, timestamp)
    tracker.update(detections, timestamp)

Graceful degradation
--------------------
- No ultralytics installed → SemanticDetector returns [] → no detections.
- No depth image → positions stay at (0, 0) relative to robot.
- Either case is silent: the rest of the stack handles empty detection lists.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from fleet_safe_vla.perception.semantic_detector import (
    DetectionResult,
    RoleClassifier,
    SemanticDetector,
)
from fleet_safe_vla.perception.depth_fusion import CameraIntrinsics, DepthFusion
from fleet_safe_vla.social_awareness.dynamic_agent_tracker import AgentType, Detection


@dataclass
class PerceptionConfig:
    """
    Configuration for PerceptionPipeline.

    Fields
    ------
    model_path      : YOLO model path or name ("yolov8n.pt", "yolov8s.pt", …).
                      None disables the detector.
    conf_threshold  : minimum detection confidence.
    iou_threshold   : NMS IoU threshold.
    device          : "cpu", "cuda", etc.  None = auto.
    enable_tracker  : use YOLO byte-track for persistent IDs.
    depth_scale     : raw depth → metres (0.001 for uint16 mm).
    max_depth_m     : discard detections beyond this distance.
    camera          : CameraIntrinsics instance.
    median_kernel   : depth patch radius for robust median.
    min_confidence  : post-fusion minimum confidence (applied after depth fill).
    """
    model_path:     str | None = "yolov8n.pt"
    conf_threshold: float = 0.40
    iou_threshold:  float = 0.45
    device:         str | None = None
    enable_tracker: bool = False
    depth_scale:    float = 0.001
    max_depth_m:    float = 8.0
    camera:         CameraIntrinsics = field(default_factory=CameraIntrinsics)
    median_kernel:  int = 5
    min_confidence: float = 0.30


class PerceptionPipeline:
    """
    Frame-level perception: RGB-D → list[Detection].

    Parameters
    ----------
    detector : SemanticDetector instance.
    depth_fusion : DepthFusion instance.
    min_confidence : detections below this are dropped after depth fusion.
    """

    def __init__(
        self,
        detector: SemanticDetector,
        depth_fusion: DepthFusion,
        min_confidence: float = 0.30,
    ) -> None:
        self._detector = detector
        self._depth    = depth_fusion
        self._min_conf = min_confidence
        self._frame_count = 0
        self._total_detections = 0

    @classmethod
    def from_config(cls, config: PerceptionConfig | None = None) -> "PerceptionPipeline":
        """Construct a fully-wired pipeline from a PerceptionConfig."""
        cfg = config or PerceptionConfig()
        detector = SemanticDetector(
            model_path=cfg.model_path,
            conf_threshold=cfg.conf_threshold,
            iou_threshold=cfg.iou_threshold,
            device=cfg.device,
            enable_tracker=cfg.enable_tracker,
        )
        fusion = DepthFusion(
            intrinsics=cfg.camera,
            depth_scale=cfg.depth_scale,
            max_depth_m=cfg.max_depth_m,
            median_kernel=cfg.median_kernel,
        )
        return cls(detector=detector, depth_fusion=fusion, min_confidence=cfg.min_confidence)

    @property
    def detector_enabled(self) -> bool:
        return self._detector.enabled

    @property
    def stats(self) -> dict[str, int]:
        return {
            "frames_processed": self._frame_count,
            "total_detections": self._total_detections,
        }

    def process(
        self,
        rgb_frame: Any,
        depth_image: Any = None,
        robot_xy: tuple[float, float] = (0.0, 0.0),
        timestamp: float | None = None,
    ) -> list[Detection]:
        """
        Process one RGB-D frame and return Detection objects.

        Parameters
        ----------
        rgb_frame   : numpy HxWx3 uint8, or None (returns []).
        depth_image : numpy HxW depth, or None (positions default to (0, 0)).
        robot_xy    : robot global position; added as offset to local positions.
        timestamp   : sensor time; defaults to time.monotonic().

        Returns
        -------
        list[Detection] — ready for DynamicAgentTracker.update().
        """
        if timestamp is None:
            timestamp = time.monotonic()

        self._frame_count += 1

        raw: list[DetectionResult] = self._detector.detect(rgb_frame, timestamp)

        if depth_image is not None:
            self._depth.fill_positions(raw, depth_image, robot_xy)

        detections: list[Detection] = []
        for det in raw:
            if det.confidence < self._min_conf:
                continue
            detections.append(det.to_detection())

        self._total_detections += len(detections)
        return detections

    def process_raw(
        self,
        rgb_frame: Any,
        depth_image: Any = None,
        robot_xy: tuple[float, float] = (0.0, 0.0),
        timestamp: float | None = None,
    ) -> list[DetectionResult]:
        """
        Like process() but returns DetectionResult objects (with bbox info).

        Useful for visualisation overlays.
        """
        if timestamp is None:
            timestamp = time.monotonic()

        raw: list[DetectionResult] = self._detector.detect(rgb_frame, timestamp)
        if depth_image is not None:
            self._depth.fill_positions(raw, depth_image, robot_xy)
        return [d for d in raw if d.confidence >= self._min_conf]
