"""
semantic_detector.py — YOLOv8 object detector with hospital role classification.

Wraps ultralytics.YOLO with graceful degradation when ultralytics is not installed
(returns empty detection lists so the rest of the pipeline stays testable without GPU).

Semantic role mapping
---------------------
YOLO detects generic COCO classes.  RoleClassifier maps those class names, plus
optional domain-specific fine-tuned names, to FleetSafe semantic roles:

    nurse / doctor / staff → "staff"
    patient / person       → "patient"  (context-dependent; see _role_rules)
    wheelchair_user        → "wheelchair_user"
    gurney / stretcher     → "gurney"
    robot / vehicle        → "robot"
    *                      → "unknown"
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from fleet_safe_vla.social_awareness.dynamic_agent_tracker import AgentType, Detection

# ── Role classification ────────────────────────────────────────────────────────

# Maps lower-cased YOLO class name fragment → (semantic_role, AgentType)
_ROLE_RULES: list[tuple[str, str, AgentType]] = [
    # Fine-tuned domain names (take priority — checked first)
    ("nurse",           "staff",            AgentType.HUMAN),
    ("doctor",          "staff",            AgentType.HUMAN),
    ("staff",           "staff",            AgentType.HUMAN),
    ("medic",           "staff",            AgentType.HUMAN),
    ("wheelchair_user", "wheelchair_user",  AgentType.HUMAN),
    ("wheelchair",      "wheelchair_user",  AgentType.HUMAN),
    ("patient",         "patient",          AgentType.HUMAN),
    ("visitor",         "visitor",          AgentType.HUMAN),
    ("gurney",          "gurney",           AgentType.HUMAN),
    ("stretcher",       "gurney",           AgentType.HUMAN),
    # COCO generic classes
    ("person",          "patient",          AgentType.HUMAN),   # default person → patient
    ("bicycle",         "robot",            AgentType.ROBOT),
    ("car",             "robot",            AgentType.ROBOT),
    ("robot",           "robot",            AgentType.ROBOT),
]


class RoleClassifier:
    """
    Map a YOLO class name to a (semantic_role, AgentType) pair.

    Parameters
    ----------
    extra_rules : list of (fragment, role, AgentType)
        Prepended before the built-in rules so domain-specific entries take priority.
    """

    def __init__(
        self,
        extra_rules: list[tuple[str, str, AgentType]] | None = None,
    ) -> None:
        self._rules: list[tuple[str, str, AgentType]] = list(extra_rules or []) + _ROLE_RULES

    def classify(self, class_name: str) -> tuple[str, AgentType]:
        """Return (semantic_role, AgentType) for a YOLO class name."""
        name = class_name.lower().strip()
        for fragment, role, atype in self._rules:
            if fragment in name:
                return role, atype
        return "unknown", AgentType.UNKNOWN


# ── Detection result ───────────────────────────────────────────────────────────

@dataclass
class DetectionResult:
    """
    One raw detection from SemanticDetector, before depth fusion.

    Fields
    ------
    bbox_xyxy       : bounding box in pixel coords (x1, y1, x2, y2)
    class_name      : YOLO class name string
    confidence      : detector confidence [0, 1]
    semantic_role   : classified role string
    agent_type      : AgentType enum value
    position_xy     : 2-D world position (m) — (0, 0) until DepthFusion fills it
    timestamp       : sensor timestamp (s)
    track_id        : optional YOLO tracker ID
    """
    bbox_xyxy:    tuple[float, float, float, float]
    class_name:   str
    confidence:   float
    semantic_role: str
    agent_type:   AgentType
    position_xy:  tuple[float, float] = (0.0, 0.0)
    timestamp:    float = 0.0
    track_id:     int | None = None

    def to_detection(self) -> Detection:
        """Convert to the Detection interface consumed by DynamicAgentTracker."""
        return Detection(
            position_xy=self.position_xy,
            agent_type=self.agent_type,
            timestamp=self.timestamp,
            confidence=self.confidence,
            semantic_role=self.semantic_role,
        )

    @property
    def center_xy_px(self) -> tuple[float, float]:
        """Pixel-space bounding-box centre."""
        x1, y1, x2, y2 = self.bbox_xyxy
        return (x1 + x2) / 2.0, (y1 + y2) / 2.0


# ── Detector ──────────────────────────────────────────────────────────────────

class SemanticDetector:
    """
    YOLOv8 detector with hospital role classification.

    Gracefully degrades to empty-list output when ultralytics is not installed
    or model loading fails — useful for dry-run / mock testing.

    Parameters
    ----------
    model_path : path or model name passed to YOLO(), e.g. "yolov8n.pt" or
                 "path/to/hospital_yolov8s.pt".  If None, detector is disabled.
    conf_threshold : minimum confidence to keep a detection.
    iou_threshold  : NMS IoU threshold.
    device         : "cpu", "cuda", "cuda:0", etc.  None = auto-select.
    role_classifier : RoleClassifier instance; default built-in rules used if None.
    enable_tracker  : if True, use YOLO byte-track to assign persistent track IDs.
    """

    def __init__(
        self,
        model_path: str | None = "yolov8n.pt",
        conf_threshold: float = 0.40,
        iou_threshold: float = 0.45,
        device: str | None = None,
        role_classifier: RoleClassifier | None = None,
        enable_tracker: bool = False,
    ) -> None:
        self._conf = conf_threshold
        self._iou  = iou_threshold
        self._device = device
        self._tracker = enable_tracker
        self._classifier = role_classifier or RoleClassifier()
        self._model: Any = None
        self._enabled = False

        if model_path is not None:
            self._load_model(model_path)

    def _load_model(self, model_path: str) -> None:
        try:
            from ultralytics import YOLO  # type: ignore[import]
            kwargs: dict[str, Any] = {}
            if self._device is not None:
                kwargs["device"] = self._device
            self._model = YOLO(model_path)
            self._enabled = True
        except ImportError:
            # ultralytics not installed — run in stub mode
            self._enabled = False
        except Exception:
            self._enabled = False

    @property
    def enabled(self) -> bool:
        """True when a YOLO model is loaded and ready."""
        return self._enabled

    def detect(
        self,
        frame: Any,
        timestamp: float | None = None,
    ) -> list[DetectionResult]:
        """
        Run detection on a single RGB frame (numpy HxWx3 uint8).

        Parameters
        ----------
        frame     : numpy array HxWx3 uint8, or None (returns []).
        timestamp : sensor timestamp; defaults to time.monotonic().

        Returns
        -------
        list[DetectionResult] sorted by confidence descending.
        """
        if timestamp is None:
            timestamp = time.monotonic()

        if not self._enabled or frame is None:
            return []

        try:
            if self._tracker:
                results = self._model.track(
                    frame,
                    conf=self._conf,
                    iou=self._iou,
                    persist=True,
                    verbose=False,
                )
            else:
                results = self._model.predict(
                    frame,
                    conf=self._conf,
                    iou=self._iou,
                    verbose=False,
                )
        except Exception:
            return []

        detections: list[DetectionResult] = []
        for r in results:
            boxes = r.boxes
            if boxes is None:
                continue
            for i in range(len(boxes)):
                conf  = float(boxes.conf[i])
                cls   = int(boxes.cls[i])
                name  = r.names.get(cls, str(cls))
                xyxy  = tuple(float(v) for v in boxes.xyxy[i])  # type: ignore[arg-type]
                tid   = int(boxes.id[i]) if (self._tracker and boxes.id is not None) else None
                role, atype = self._classifier.classify(name)
                detections.append(DetectionResult(
                    bbox_xyxy=xyxy,  # type: ignore[arg-type]
                    class_name=name,
                    confidence=conf,
                    semantic_role=role,
                    agent_type=atype,
                    timestamp=timestamp,
                    track_id=tid,
                ))

        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections
