"""Shadow-mode GNM inference for live Isaac episodes.

GNM reads real camera frames (the same render product that publishes
/camera/image_raw), runs a real forward pass on the published Shah et al.
CoRL 2022 checkpoint, and produces CANDIDATE actions that are logged but
never applied: the scripted/manual controller keeps exclusive control of
/cmd_vel. This module has no ROS publisher by construction.

Honest scope: the smoke goal image is a fixed real dataset frame from a
kujiale interior, which does not exist in the bring-up scene — candidate
actions therefore validate the inference path (real image in, real forward
pass, real action out), not navigation quality. No policy-navigation claim.

Shadow fields contributed to trajectory.jsonl:
    shadow_gnm_enabled, shadow_gnm_status, shadow_gnm_model_path,
    shadow_gnm_latency_ms, shadow_gnm_candidate_linear_velocity,
    shadow_gnm_candidate_angular_velocity, shadow_gnm_candidate_waypoint_x,
    shadow_gnm_candidate_waypoint_y, shadow_gnm_goal_distance,
    shadow_gnm_confidence, shadow_gnm_error,
    actual_controller, actual_linear_velocity_cmd, actual_angular_velocity_cmd
"""

import sys
import time
from collections import deque
from pathlib import Path

import numpy as np

SHADOW_FIELDS = [
    "shadow_gnm_enabled", "shadow_gnm_status", "shadow_gnm_model_path",
    "shadow_gnm_latency_ms", "shadow_gnm_candidate_linear_velocity",
    "shadow_gnm_candidate_angular_velocity",
    "shadow_gnm_candidate_waypoint_x", "shadow_gnm_candidate_waypoint_y",
    "shadow_gnm_goal_distance", "shadow_gnm_confidence", "shadow_gnm_error",
    "actual_controller", "actual_linear_velocity_cmd",
    "actual_angular_velocity_cmd",
]


class GNMShadow:
    def __init__(self, repo_root, goal_image_path, device="cuda"):
        self.repo = Path(repo_root)
        sys.path.insert(0, str(self.repo))
        from PIL import Image
        from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter \
            import GNMAdapter
        from fleet_safe_vla.integrations.visualnav_transformer.base_adapter \
            import waypoints_to_cmd_vel

        self._waypoints_to_cmd_vel = waypoints_to_cmd_vel
        self.model_path = (self.repo / "third_party/visualnav-transformer"
                           / "model_weights/gnm/gnm.pth")
        self.adapter = GNMAdapter(device=device)
        self.adapter.load_checkpoint(self.model_path)
        self.goal_image_path = Path(goal_image_path)
        self.goal = np.array(Image.open(self.goal_image_path).convert("RGB"))
        self.context = deque(maxlen=self.adapter.context_size + 1)

        self.frames_received = 0
        self.attempts = 0
        self.successes = 0
        self.failures = 0
        self.latencies_ms = []
        self.latest = self._row(status="warmup")

    def _row(self, status, latency_ms=None, lin=None, ang=None,
             wx=None, wy=None, goal_dist=None, error=None):
        return {
            "shadow_gnm_enabled": True,
            "shadow_gnm_status": status,
            "shadow_gnm_model_path": str(
                self.model_path.relative_to(self.repo)),
            "shadow_gnm_latency_ms": latency_ms,
            "shadow_gnm_candidate_linear_velocity": lin,
            "shadow_gnm_candidate_angular_velocity": ang,
            "shadow_gnm_candidate_waypoint_x": wx,
            "shadow_gnm_candidate_waypoint_y": wy,
            "shadow_gnm_goal_distance": goal_dist,
            "shadow_gnm_confidence": None,  # GNM does not output confidence
            "shadow_gnm_error": error,
        }

    def add_frame(self, rgb):
        self.frames_received += 1
        self.context.append(rgb)

    def infer(self):
        """Run one shadow forward pass; returns and caches the shadow row."""
        if len(self.context) < self.context.maxlen:
            self.latest = self._row(status="warmup")
            return self.latest
        self.attempts += 1
        try:
            t0 = time.perf_counter()
            pre = self.adapter.preprocess_observation(
                list(self.context), self.goal)
            out = self.adapter.predict_action(pre)
            latency = (time.perf_counter() - t0) * 1000.0
            cmd = self._waypoints_to_cmd_vel(
                out.waypoints, v_max=0.3, vy_max=0.0, w_max=0.7,
                control_hz=4.0)
            self.successes += 1
            self.latencies_ms.append(latency)
            self.latest = self._row(
                status="ok", latency_ms=round(latency, 2),
                lin=round(float(cmd.vx), 4), ang=round(float(cmd.wz), 4),
                wx=round(float(out.waypoints[0][0]), 4),
                wy=round(float(out.waypoints[0][1]), 4),
                goal_dist=round(float(out.goal_distance), 2)
                if out.goal_distance is not None else None)
        except Exception as e:
            self.failures += 1
            self.latest = self._row(status="error", error=str(e)[:200])
        return self.latest

    def summary(self):
        lats = self.latencies_ms
        return {
            "shadow_gnm_model_path": str(
                self.model_path.relative_to(self.repo)),
            "shadow_gnm_goal_image": str(self.goal_image_path),
            "shadow_gnm_frames_received": self.frames_received,
            "shadow_gnm_inference_attempts": self.attempts,
            "shadow_gnm_inference_successes": self.successes,
            "shadow_gnm_inference_failures": self.failures,
            "shadow_gnm_mean_latency_ms": round(sum(lats) / len(lats), 2)
            if lats else None,
            "shadow_gnm_max_latency_ms": round(max(lats), 2) if lats else None,
            "shadow_gnm_scope_note": (
                "fixed dataset goal image; candidate actions validate the "
                "inference path only — no navigation-quality claim"),
        }
