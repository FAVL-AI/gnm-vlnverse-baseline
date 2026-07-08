"""Drive live Isaac episodes with an ablation-trained MobileNetV2-GNM.

Loads a checkpoint produced by scripts/gnm/04_train_gnm.py and exposes the
same interface the closed-loop episode runner uses for the published-GNM
shadow (add_frame / infer / raw_cmd / latest / summary), so Stage 2 Isaac
physics evaluation reuses the identical control loop, safety envelope and
logging. Weight selection follows the offline evaluator's rule: EMA shadow
weights are used automatically when ema_state is present (logged), live
weights otherwise.

Inference preprocessing/unnormalisation is the repo's own GNMEvaluator, so
offline Stage 1 and Isaac Stage 2 share one inference path.
"""

import hashlib
import math
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


class AblationPolicyShadow:
    """GNMShadow-compatible wrapper around a trained ablation checkpoint."""

    def __init__(self, ckpt_path, goal_image_path, device="cuda"):
        import torch
        from PIL import Image
        from gnm_vlnverse.models.gnm import build_gnm
        from gnm_vlnverse.evaluation.evaluator import GNMEvaluator

        self.repo = REPO
        self.ckpt_path = Path(ckpt_path).resolve()
        ckpt = torch.load(self.ckpt_path, map_location="cpu",
                          weights_only=False)
        cfg = ckpt["cfg"]
        model = build_gnm(cfg["model"])
        has_ema = ckpt.get("ema_state") is not None
        state = ckpt["ema_state"] if has_ema else ckpt["model_state"]
        model.load_state_dict(state)
        self.weight_source = "EMA shadow" if has_ema else "live model"
        self.sha256 = hashlib.sha256(
            self.ckpt_path.read_bytes()).hexdigest()

        self.evaluator = GNMEvaluator(
            model=model,
            action_std=tuple(cfg["data"]["action_std"]),
            context_size=cfg["model"]["context_size"],
            image_size=tuple(cfg["data"]["image_size"]),
            stop_threshold=cfg["evaluation"].get("stop_threshold", 0.15),
            max_steps=cfg["evaluation"].get("max_steps", 500),
            device=device,
            track=cfg["evaluation"].get("track", "A"),
        )
        self.goal_image_path = Path(goal_image_path)
        self.goal = np.array(Image.open(self.goal_image_path).convert("RGB"))
        self._context_ready = False
        self.model_path = self.ckpt_path  # GNMShadow-compatible name

        self.last_waypoints = None
        self.frames_received = 0
        self.attempts = 0
        self.successes = 0
        self.failures = 0
        self.latencies_ms = []
        self.latest = self._row("warmup")
        print(f"[policy] ablation checkpoint loaded: {self.ckpt_path} "
              f"(weights: {self.weight_source})")

    def _row(self, status, latency=None, lin=None, ang=None, wx=None,
             wy=None, goal_dist=None, error=None):
        return {
            "shadow_gnm_enabled": True,
            "shadow_gnm_status": status,
            "shadow_gnm_model_path": str(self.ckpt_path.relative_to(self.repo)),
            "shadow_gnm_latency_ms": latency,
            "shadow_gnm_candidate_linear_velocity": lin,
            "shadow_gnm_candidate_angular_velocity": ang,
            "shadow_gnm_candidate_waypoint_x": wx,
            "shadow_gnm_candidate_waypoint_y": wy,
            "shadow_gnm_goal_distance": goal_dist,
            "shadow_gnm_confidence": None,
            "shadow_gnm_error": error,
        }

    def add_frame(self, rgb):
        self.frames_received += 1
        if not self._context_ready:
            self.evaluator.reset_context(rgb)
            self._context_ready = True
        else:
            self.evaluator.push_frame(rgb)
        self._last_frame = rgb

    def infer(self):
        if not self._context_ready:
            self.latest = self._row("warmup")
            return self.latest
        self.attempts += 1
        try:
            t0 = time.perf_counter()
            dist_pred, action = self.evaluator.predict(
                self._last_frame, self.goal)
            latency = (time.perf_counter() - t0) * 1000.0
            dx, dy = float(action[0]), float(action[1])
            self.last_waypoints = np.array([[dx, dy]], dtype=np.float32)
            # waypoint -> (vx, wz) at the model's control horizon; the
            # closed-loop clamps enforce the safety limits downstream.
            control_hz = 4.0
            vx = dx * control_hz
            wz = math.atan2(dy, max(dx, 1e-3)) * control_hz
            self.successes += 1
            self.latencies_ms.append(latency)
            self.latest = self._row(
                "ok", latency=round(latency, 2), lin=round(vx, 4),
                ang=round(wz, 4), wx=round(dx, 4), wy=round(dy, 4),
                goal_dist=round(float(dist_pred), 4))
        except Exception as e:
            self.failures += 1
            self.latest = self._row("error", error=str(e)[:200])
        return self.latest

    def raw_cmd(self):
        if self.latest.get("shadow_gnm_status") != "ok":
            return None
        return (self.latest["shadow_gnm_candidate_linear_velocity"],
                self.latest["shadow_gnm_candidate_angular_velocity"])

    def summary(self):
        lats = self.latencies_ms
        return {
            "policy_checkpoint": str(self.ckpt_path.relative_to(self.repo)),
            "policy_checkpoint_sha256": self.sha256,
            "policy_weight_source": self.weight_source,
            "shadow_gnm_goal_image": str(self.goal_image_path),
            "shadow_gnm_frames_received": self.frames_received,
            "shadow_gnm_inference_attempts": self.attempts,
            "shadow_gnm_inference_successes": self.successes,
            "shadow_gnm_inference_failures": self.failures,
            "shadow_gnm_mean_latency_ms": round(sum(lats) / len(lats), 2)
            if lats else None,
            "shadow_gnm_max_latency_ms": round(max(lats), 2) if lats else None,
            "shadow_gnm_scope_note": (
                "ablation-trained MobileNetV2-GNM driving live Isaac; "
                "goal_distance is the model's NORMALISED dist_pred (not "
                "published-GNM step units); Isaac physics smoke evaluation, "
                "not full benchmark"),
        }
