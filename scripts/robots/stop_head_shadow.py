"""Shadow-mode Temporal Stop Head for live GNM closed-loop episodes.

Runs the REAL trained temporal stop head (the Track A checkpoint
results/bo_reviewer_packet/temporal_stop_head/22_temporal_stop_head_model.pt)
online, fed by the same live GNM signals it was trained on: the history of
GNM's predicted goal distance and predicted-waypoint norm (window means and
trends, seq_len feature sequences, saved normalisation).

SHADOW ONLY: it observes and logs stop probabilities/decisions; it has no
authority and never touches /cmd_vel or the wheels. The decision rule
mirrors the offline evaluation: probability >= best_threshold for stable_k
consecutive inference steps.

The tiny MLP is re-declared here verbatim (Flatten -> Linear -> ReLU ->
Linear -> ReLU -> Linear) so loading stays free of the offline evaluator's
heavy import chain; weights come solely from the committed checkpoint.
"""

import hashlib
import math
import time
from collections import deque
from pathlib import Path

STOP_FIELDS = [
    "stop_head_enabled", "stop_head_mode", "stop_head_model_path",
    "stop_head_latency_ms", "stop_probability", "stop_decision_shadow",
    "stop_threshold", "stop_reason_shadow",
    "distance_to_goal_at_stop_signal", "nearest_goal_distance_so_far",
    "overshoot_detected", "would_have_stopped_step",
    "would_have_stopped_sim_time", "stop_authority_enabled",
]

OVERSHOOT_MARGIN_M = 0.10


class StopHeadShadow:
    def __init__(self, repo_root, device="cpu"):
        import numpy as np
        import torch
        import torch.nn as nn

        self._np = np
        self._torch = torch
        self.repo = Path(repo_root)
        self.model_path = (self.repo / "results/bo_reviewer_packet"
                           / "temporal_stop_head"
                           / "22_temporal_stop_head_model.pt")
        ckpt = torch.load(self.model_path, map_location=device,
                          weights_only=False)
        self.seq_len = int(ckpt["seq_len"])
        self.window = int(ckpt["window"])
        self.feature_dim = int(ckpt["feature_dim"])
        self.threshold = float(ckpt["best_threshold"])
        self.stable_k = int(ckpt["stable_k"])
        self.mean = np.asarray(ckpt["mean"], dtype=np.float32)
        self.std = np.asarray(ckpt["std"], dtype=np.float32)

        self.model = nn.Sequential(
            nn.Flatten(),
            nn.Linear(self.seq_len * self.feature_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )
        state = ckpt["model_state"]
        state = {k.replace("net.", "", 1): v for k, v in state.items()}
        self.model.load_state_dict(state)
        self.model.eval()
        self.device = device
        self.sha256 = hashlib.sha256(
            self.model_path.read_bytes()).hexdigest()

        self.dist_hist = []
        self.wp_hist = []
        self.seq = deque(maxlen=self.seq_len)
        self.consecutive = 0
        self.decided = False
        self.would_step = None
        self.would_sim_time = None
        self.d2g_at_signal = None
        self.nearest_d2g = math.inf
        self.latencies_ms = []
        self.evaluations = 0
        self.latest = self._row(status_prob=None)

    def _row(self, status_prob, latency=None, decision=False, reason=None,
             overshoot=False):
        return {
            "stop_head_enabled": True,
            "stop_head_mode": "shadow",
            "stop_head_model_path": str(
                self.model_path.relative_to(self.repo)),
            "stop_head_latency_ms": latency,
            "stop_probability": status_prob,
            "stop_decision_shadow": decision,
            "stop_threshold": self.threshold,
            "stop_reason_shadow": reason,
            "distance_to_goal_at_stop_signal": self.d2g_at_signal,
            "nearest_goal_distance_so_far":
                None if math.isinf(self.nearest_d2g)
                else round(self.nearest_d2g, 4),
            "overshoot_detected": overshoot,
            "would_have_stopped_step": self.would_step,
            "would_have_stopped_sim_time": self.would_sim_time,
            "stop_authority_enabled": False,
        }

    def _features(self):
        np = self._np
        d = np.asarray(self.dist_hist, dtype=np.float32)
        w = np.asarray(self.wp_hist, dtype=np.float32)
        k = min(self.window, len(d))
        dist_trend = float(d[-1] - d[max(0, len(d) - k)]) if len(d) >= 2 else 0.0
        wp_trend = float(w[-1] - w[max(0, len(w) - k)]) if len(w) >= 2 else 0.0
        return np.array([float(d[-1]), float(w[-1]),
                         float(d[-k:].mean()), float(w[-k:].mean()),
                         dist_trend, wp_trend], dtype=np.float32)

    def update(self, step_idx, sim_time, gnm_goal_dist, waypoint_xy,
               d2g_actual):
        """One shadow evaluation on fresh GNM outputs. No authority."""
        np, torch = self._np, self._torch
        if d2g_actual is not None:
            self.nearest_d2g = min(self.nearest_d2g, d2g_actual)
        overshoot = (d2g_actual is not None
                     and not math.isinf(self.nearest_d2g)
                     and d2g_actual - self.nearest_d2g > OVERSHOOT_MARGIN_M)

        if gnm_goal_dist is None or waypoint_xy is None:
            self.latest = self._row(None, overshoot=overshoot,
                                    decision=self.decided,
                                    reason="waiting_for_gnm")
            return self.latest

        self.dist_hist.append(float(gnm_goal_dist))
        self.wp_hist.append(float(math.hypot(waypoint_xy[0],
                                             waypoint_xy[1])))
        self.seq.append(self._features())
        if len(self.seq) < self.seq_len:
            self.latest = self._row(None, overshoot=overshoot,
                                    decision=self.decided,
                                    reason="sequence_warmup")
            return self.latest

        t0 = time.perf_counter()
        x = (np.stack(self.seq) - self.mean) / self.std
        with torch.no_grad():
            logit = self.model(torch.from_numpy(x).unsqueeze(0))
            prob = float(torch.sigmoid(logit))
        latency = (time.perf_counter() - t0) * 1000.0
        self.latencies_ms.append(latency)
        self.evaluations += 1

        reason = None
        if prob >= self.threshold:
            self.consecutive += 1
        else:
            self.consecutive = 0
        if not self.decided and self.consecutive >= self.stable_k:
            self.decided = True
            self.would_step = step_idx
            self.would_sim_time = round(float(sim_time), 3)
            self.d2g_at_signal = (round(d2g_actual, 4)
                                  if d2g_actual is not None else None)
            reason = (f"prob>={self.threshold} for {self.stable_k} "
                      "consecutive evaluations")
        self.latest = self._row(
            round(prob, 4), latency=round(latency, 3),
            decision=self.decided, reason=reason, overshoot=overshoot)
        return self.latest

    def summary(self, final_d2g=None):
        lats = self.latencies_ms
        overshoot_after_stop = None
        if self.decided and final_d2g is not None \
                and self.d2g_at_signal is not None:
            overshoot_after_stop = round(final_d2g - self.d2g_at_signal, 4)
        return {
            "stop_head_mode": "shadow",
            "stop_head_model_path": str(
                self.model_path.relative_to(self.repo)),
            "stop_head_model_sha256": self.sha256,
            "stop_head_threshold": self.threshold,
            "stop_head_stable_k": self.stable_k,
            "stop_head_evaluations": self.evaluations,
            "stop_head_mean_latency_ms": round(sum(lats) / len(lats), 3)
            if lats else None,
            "stop_head_would_have_stopped_step": self.would_step,
            "stop_head_would_have_stopped_sim_time": self.would_sim_time,
            "stop_head_distance_at_stop_signal": self.d2g_at_signal,
            "stop_head_nearest_d2g": None if math.isinf(self.nearest_d2g)
            else round(self.nearest_d2g, 4),
            "stop_head_overshoot_after_predicted_stop_m":
                overshoot_after_stop,
            "stop_head_authority": False,
            "stop_head_scope_note": (
                "learned temporal stop head running in SHADOW only: stop "
                "signal measured against actual distance-to-goal; no "
                "authority, no improvement claim"),
        }
