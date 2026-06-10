"""
intervention_evidence.py — Structured, replayable evidence record for every FleetSafe intervention.

Each intervention event is logged as a single evidence record containing:
  - what the policy wanted (raw_action)
  - what FleetSafe executed (safe_action)
  - why it changed the action (intervention_reason + causal_explanation)
  - what changed in the scene graph (scene_graph_delta)
  - what would have happened without intervention (counterfactual_rollout_id)
  - a reproducibility hash linking to the source run artifact

Written to: intervention_evidence.jsonl (one JSON object per line, additive).
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class InterventionEvidence:
    """Full evidence record for one episode step."""
    episode_id:                  str
    step_idx:                    int
    timestamp:                   float
    scene_id:                    str
    model_name:                  str
    backend:                     str
    benchmark_version:           str
    protocol_version:            str
    raw_action:                  tuple[float, float, float]   # (vx, vy, wz)
    safe_action:                 tuple[float, float, float]
    action_delta:                tuple[float, float, float]   # safe - raw, per component
    intervention_applied:        bool
    intervention_reason:         str
    safety_margin_before:        float                         # nearest obstacle dist before step
    safety_margin_after:         float                         # nearest obstacle dist after step
    nearest_obstacle_id:         str
    nearest_obstacle_distance_m: float
    active_constraints:          list[str]
    scene_graph_before:          dict[str, Any]
    scene_graph_after:           dict[str, Any]
    scene_graph_delta:           dict[str, Any]
    causal_explanation:          str
    counterfactual_explanation:  str
    counterfactual_rollout_id:   str
    rgb_frame_ref:               str
    depth_frame_ref:             str
    lidar_ref:                   str
    trajectory_ref:              str
    reproducibility_hash:        str = field(default="", init=True)
    # Social-risk zone (populated by social_awareness layer; default=GREEN/safe)
    active_safety_zone:          str   = "GREEN"
    safety_zone_reason:          str   = ""
    crowding_risk_score:         float = 0.0
    occlusion_risk_score:        float = 0.0
    rare_event_count:            int   = 0
    environment_profile:         str   = "default"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "episode_id":                  self.episode_id,
            "step_idx":                    self.step_idx,
            "timestamp":                   self.timestamp,
            "scene_id":                    self.scene_id,
            "model_name":                  self.model_name,
            "backend":                     self.backend,
            "benchmark_version":           self.benchmark_version,
            "protocol_version":            self.protocol_version,
            "raw_action":                  list(self.raw_action),
            "safe_action":                 list(self.safe_action),
            "action_delta":                list(self.action_delta),
            "intervention_applied":        self.intervention_applied,
            "intervention_reason":         self.intervention_reason,
            "safety_margin_before":        self.safety_margin_before,
            "safety_margin_after":         self.safety_margin_after,
            "nearest_obstacle_id":         self.nearest_obstacle_id,
            "nearest_obstacle_distance_m": self.nearest_obstacle_distance_m,
            "active_constraints":          self.active_constraints,
            "scene_graph_before":          self.scene_graph_before,
            "scene_graph_after":           self.scene_graph_after,
            "scene_graph_delta":           self.scene_graph_delta,
            "causal_explanation":          self.causal_explanation,
            "counterfactual_explanation":  self.counterfactual_explanation,
            "counterfactual_rollout_id":   self.counterfactual_rollout_id,
            "rgb_frame_ref":               self.rgb_frame_ref,
            "depth_frame_ref":             self.depth_frame_ref,
            "lidar_ref":                   self.lidar_ref,
            "trajectory_ref":              self.trajectory_ref,
            "reproducibility_hash":        self.reproducibility_hash,
            # Social-risk zone fields (replay viewer reads these)
            "active_safety_zone":          self.active_safety_zone,
            "safety_zone_reason":          self.safety_zone_reason,
            "crowding_risk_score":         self.crowding_risk_score,
            "occlusion_risk_score":        self.occlusion_risk_score,
            "rare_event_count":            self.rare_event_count,
            "environment_profile":         self.environment_profile,
        }
        return d

    @staticmethod
    def compute_hash(d: dict[str, Any]) -> str:
        """SHA256 (first 16 hex chars) of a stable JSON snapshot, excluding the hash field."""
        d_stable = {k: v for k, v in d.items() if k != "reproducibility_hash"}
        blob = json.dumps(d_stable, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()[:16]

    @classmethod
    def build(
        cls,
        episode_id:                  str,
        step_idx:                    int,
        timestamp:                   float,
        scene_id:                    str,
        model_name:                  str,
        backend:                     str,
        benchmark_version:           str,
        protocol_version:            str,
        raw_action:                  tuple[float, float, float],
        safe_action:                 tuple[float, float, float],
        intervention_applied:        bool,
        intervention_reason:         str,
        safety_margin_before:        float,
        safety_margin_after:         float,
        nearest_obstacle_id:         str,
        nearest_obstacle_distance_m: float,
        active_constraints:          list[str],
        scene_graph_before:          dict[str, Any],
        scene_graph_after:           dict[str, Any],
        scene_graph_delta:           dict[str, Any],
        causal_explanation:          str,
        counterfactual_explanation:  str,
        counterfactual_rollout_id:   str,
        rgb_frame_ref:               str = "",
        depth_frame_ref:             str = "",
        lidar_ref:                   str = "",
        trajectory_ref:              str = "",
        active_safety_zone:          str   = "GREEN",
        safety_zone_reason:          str   = "",
        crowding_risk_score:         float = 0.0,
        occlusion_risk_score:        float = 0.0,
        rare_event_count:            int   = 0,
        environment_profile:         str   = "default",
    ) -> "InterventionEvidence":
        action_delta = (
            safe_action[0] - raw_action[0],
            safe_action[1] - raw_action[1],
            safe_action[2] - raw_action[2],
        )
        ev = cls(
            episode_id=episode_id,
            step_idx=step_idx,
            timestamp=timestamp,
            scene_id=scene_id,
            model_name=model_name,
            backend=backend,
            benchmark_version=benchmark_version,
            protocol_version=protocol_version,
            raw_action=raw_action,
            safe_action=safe_action,
            action_delta=action_delta,
            intervention_applied=intervention_applied,
            intervention_reason=intervention_reason,
            safety_margin_before=safety_margin_before,
            safety_margin_after=safety_margin_after,
            nearest_obstacle_id=nearest_obstacle_id,
            nearest_obstacle_distance_m=nearest_obstacle_distance_m,
            active_constraints=active_constraints,
            scene_graph_before=scene_graph_before,
            scene_graph_after=scene_graph_after,
            scene_graph_delta=scene_graph_delta,
            causal_explanation=causal_explanation,
            counterfactual_explanation=counterfactual_explanation,
            counterfactual_rollout_id=counterfactual_rollout_id,
            rgb_frame_ref=rgb_frame_ref,
            depth_frame_ref=depth_frame_ref,
            lidar_ref=lidar_ref,
            trajectory_ref=trajectory_ref,
            active_safety_zone=active_safety_zone,
            safety_zone_reason=safety_zone_reason,
            crowding_risk_score=crowding_risk_score,
            occlusion_risk_score=occlusion_risk_score,
            rare_event_count=rare_event_count,
            environment_profile=environment_profile,
        )
        d = ev.to_dict()
        ev.reproducibility_hash = cls.compute_hash(d)
        return ev


class InterventionEvidenceRecorder:
    """
    Accumulates InterventionEvidence records and writes intervention_evidence.jsonl.

    Writes are additive: if the target file already exists the new records are
    appended, not overwritten.  This preserves multi-run aggregation.
    """

    def __init__(self) -> None:
        self._records: list[InterventionEvidence] = []

    def record(self, ev: InterventionEvidence) -> None:
        self._records.append(ev)

    def __len__(self) -> int:
        return len(self._records)

    def intervention_count(self) -> int:
        return sum(1 for ev in self._records if ev.intervention_applied)

    def write(self, path: Path) -> None:
        """Append all records to path (creates file if not present)."""
        path = Path(path)
        with path.open("a") as fh:
            for ev in self._records:
                fh.write(json.dumps(ev.to_dict()) + "\n")
