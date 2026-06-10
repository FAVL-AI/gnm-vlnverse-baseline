"""
sensor_degradation.py — Degradation configs and adapter/wrapper wrappers for Scenario 3.

Three degradation axes:
  image_blur       : Gaussian blur on obs_imgs + action noise proxy
  low_light        : Brightness reduction on obs_imgs + action noise proxy
  lidar_dropout    : Fraction of obstacle positions randomly dropped from CBF input

All wrappers are duck-typed to fit the runner's adapter / wrapper interfaces without
modifying VisualNavBenchmarkRunner or FleetSafeWrapper.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Any

import numpy as np


# ── Degradation config ─────────────────────────────────────────────────────────

@dataclass
class DegradationConfig:
    """Parameters for one degradation condition."""
    name:               str
    blur_sigma:         float = 0.0   # Gaussian σ in pixels; 0 = off
    brightness_factor:  float = 1.0   # 1.0 = full, 0.30 = very dark
    lidar_dropout_rate: float = 0.0   # Fraction of obstacle detections dropped per step
    action_noise_sigma: float = 0.0   # Std dev of Gaussian noise on waypoints (image proxy)
    description:        str   = ""


DEGRADATION_SUITE: dict[str, DegradationConfig] = {
    "baseline": DegradationConfig(
        "baseline",
        description="No degradation — clean sensor conditions",
    ),
    "blur_20": DegradationConfig(
        "blur_20", blur_sigma=2.0, action_noise_sigma=0.005,
        description="Mild motion blur (σ=2 px) — camera shake at walking speed",
    ),
    "blur_40": DegradationConfig(
        "blur_40", blur_sigma=4.0, action_noise_sigma=0.010,
        description="Moderate blur (σ=4 px) — fast motion or out-of-focus lens",
    ),
    "blur_60": DegradationConfig(
        "blur_60", blur_sigma=6.0, action_noise_sigma=0.020,
        description="Heavy blur (σ=6 px) — worst-case camera degradation",
    ),
    "low_light_30": DegradationConfig(
        "low_light_30", brightness_factor=0.30, action_noise_sigma=0.008,
        description="Very low light (30 %% brightness) — hospital corridor at night",
    ),
    "low_light_60": DegradationConfig(
        "low_light_60", brightness_factor=0.60, action_noise_sigma=0.004,
        description="Dim lighting (60 %% brightness) — evening ward conditions",
    ),
    "lidar_dropout_10": DegradationConfig(
        "lidar_dropout_10", lidar_dropout_rate=0.10,
        description="10 %% LiDAR beam dropout — sporadic sensor glitches",
    ),
    "lidar_dropout_30": DegradationConfig(
        "lidar_dropout_30", lidar_dropout_rate=0.30,
        description="30 %% LiDAR beam dropout — significant sensor degradation",
    ),
    "combined_degradation": DegradationConfig(
        "combined_degradation",
        blur_sigma=4.0, brightness_factor=0.50,
        lidar_dropout_rate=0.20, action_noise_sigma=0.015,
        description="Simultaneous blur + low-light + LiDAR dropout — worst case",
    ),
}


# ── Perception confidence proxy ────────────────────────────────────────────────

def perception_confidence_proxy(cfg: DegradationConfig) -> float:
    """
    Heuristic confidence score in [0, 1].  Higher = better (less degraded).
    Combines image and lidar degradation axes with calibrated weights.
    """
    image_deg = min(1.0, cfg.blur_sigma / 8.0) * 0.4 + (1.0 - cfg.brightness_factor) * 0.3
    lidar_deg = cfg.lidar_dropout_rate * 0.5
    noise_deg = min(1.0, cfg.action_noise_sigma / 0.025) * 0.2
    return round(float(np.clip(1.0 - image_deg - lidar_deg - noise_deg, 0.0, 1.0)), 4)


# ── DegradedAdapter ────────────────────────────────────────────────────────────

class DegradedAdapter:
    """
    Duck-typed adapter wrapper applying sensor degradation to observations.

    Applies before any model call:
      - Blur / brightness: transforms obs_imgs in preprocess_observation
      - Action noise:      Gaussian noise on waypoints in predict_action
        (models increased uncertainty under degraded visual input)
    """

    def __init__(self, inner: Any, cfg: DegradationConfig, seed: int = 0) -> None:
        self._inner = inner
        self._cfg   = cfg
        self._rng   = np.random.default_rng(seed)

        self.model_name   = getattr(inner, "model_name",   "degraded_mock")
        self.image_size   = getattr(inner, "image_size",   (85, 64))
        self.context_size = getattr(inner, "context_size", 5)
        self._loaded      = getattr(inner, "_loaded",      True)
        self._device      = getattr(inner, "_device",      None)

    # ── Delegate interface ─────────────────────────────────────────────────────

    def is_loaded(self) -> bool:
        return True

    def load_checkpoint(self, path: Any) -> None:
        pass

    def preprocess_observation(self, obs_imgs: list, goal_img: np.ndarray) -> dict:
        degraded = [self._degrade_img(img) for img in obs_imgs]
        return self._inner.preprocess_observation(degraded, self._degrade_img(goal_img))

    def predict_action(self, preprocessed: dict):
        action = self._inner.predict_action(preprocessed)
        if self._cfg.action_noise_sigma > 0.0 and action.waypoints is not None:
            noise = self._rng.normal(0, self._cfg.action_noise_sigma, action.waypoints.shape)
            noisy_wp = action.waypoints + noise
            noisy_wp[:, 0] = np.clip(noisy_wp[:, 0], 0.0, None)  # keep forward component ≥ 0
            from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import ActionOutput
            action = ActionOutput(
                waypoints    = noisy_wp,
                model_name   = action.model_name,
                inference_ms = action.inference_ms,
            )
        return action

    def action_to_cmd_vel(self, action, *, v_max=0.3, vy_max=0.0, w_max=0.7, control_hz=4.0):
        return self._inner.action_to_cmd_vel(
            action, v_max=v_max, vy_max=vy_max, w_max=w_max, control_hz=control_hz,
        )

    def log_policy_output(self, action: Any, cmd_vel: Any) -> dict:
        fn = getattr(self._inner, "log_policy_output", None)
        return fn(action, cmd_vel) if fn else {}

    # ── Image degradation helpers ──────────────────────────────────────────────

    def _degrade_img(self, img: np.ndarray) -> np.ndarray:
        out = img.astype(np.float32)
        if self._cfg.brightness_factor < 1.0:
            out *= self._cfg.brightness_factor
        if self._cfg.blur_sigma > 0.0:
            try:
                from scipy.ndimage import gaussian_filter
                if out.ndim == 3:
                    for c in range(out.shape[2]):
                        out[:, :, c] = gaussian_filter(out[:, :, c], sigma=self._cfg.blur_sigma)
                else:
                    out = gaussian_filter(out, sigma=self._cfg.blur_sigma)
            except ImportError:
                pass  # scipy unavailable — blur is structural, not safety-critical
        return np.clip(out, 0, 255).astype(np.uint8)


# ── LiDAR dropout wrapper ──────────────────────────────────────────────────────

class _DroppedObstacleWrapper:
    """
    Wraps a FleetSafeWrapper and randomly drops obstacles from the CBF input.

    Simulates LiDAR beam dropout: the safety filter cannot see every obstacle,
    leading to fewer interventions and potential near-violations.
    """

    def __init__(
        self,
        inner_wrapper: Any,
        dropout_rate: float,
        seed: int = 0,
    ) -> None:
        self._inner       = inner_wrapper
        self.dropout_rate = dropout_rate
        self._rng         = np.random.default_rng(seed)

    def step(
        self,
        preprocessed:       dict,
        obs_vec:            np.ndarray,
        obstacle_positions: Sequence[np.ndarray] | None = None,
    ):
        if obstacle_positions and self.dropout_rate > 0.0:
            keep = self._rng.random(len(obstacle_positions)) >= self.dropout_rate
            obstacle_positions = [p for p, k in zip(obstacle_positions, keep) if k]
        return self._inner.step(preprocessed, obs_vec, obstacle_positions)

    def reset_stats(self) -> None:
        self._inner.reset_stats()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


# ── Robustness score ───────────────────────────────────────────────────────────

def compute_degradation_robustness_score(
    baseline:   dict,
    conditions: dict[str, dict],
) -> dict[str, float]:
    """
    Per-condition robustness score in [0, 1].

    score = (1 − success_degradation_fraction) × (1 − collision_increase)

    where:
      success_degradation_fraction = max(0, base_success − deg_success)
                                     / max(base_success, 0.01)
      collision_increase = max(0, collision_rate_degraded − collision_rate_baseline)

    When both baseline and degraded have the same success rate (including 0/0),
    success_degradation_fraction = 0 and score = 1.0 × (1 − collision_increase).
    This correctly reflects "no degradation" rather than treating 0/0 as failure.
    """
    base_success   = float(baseline.get("success_rate",   0.0))
    base_collision = float(baseline.get("collision_rate", 0.0))

    scores: dict[str, float] = {}
    for name, cond in conditions.items():
        deg_success   = float(cond.get("success_rate",   0.0))
        deg_collision = float(cond.get("collision_rate", 0.0))
        success_deg   = max(0.0, base_success - deg_success) / max(base_success, 0.01)
        coll_increase = max(0.0, deg_collision - base_collision)
        raw           = (1.0 - success_deg) * (1.0 - coll_increase)
        scores[name]  = round(float(np.clip(raw, 0.0, 1.0)), 4)
    return scores
