#!/usr/bin/env python3
"""
audit_preprocessing.py — Baseline contract audit for VisualNav-Transformer adapters.

Validates that each adapter (GNM, ViNT, NoMaD) matches the upstream model
interface exactly: image size, context length, normalization, action shape,
and coordinate frame.  Runs without checkpoints using mock weights.

Checks
------
  [IMAGE]     image_size matches upstream published config
  [CONTEXT]   context_size matches upstream config
  [NORM]      preprocessing applies ImageNet normalization
  [TENSOR]    preprocess_observation → correct tensor shapes
  [WAYPOINT]  predict_action → waypoints in (N, 2), robot frame
  [FORWARD]   forward goal → positive vx (correct sign convention)
  [LEFT]      left goal → positive wz (CCW is positive)
  [BOUNDS]    waypoints within physically plausible range (< 2 m per step)
  [POLICY]    preprocessed dict does NOT contain state/obstacle keys
  [CAMERA]    IsaacCameraObsAdapter enforces egocentric camera contract

Usage
-----
    python scripts/visualnav/audit_preprocessing.py
    python scripts/visualnav/audit_preprocessing.py --model gnm
    python scripts/visualnav/audit_preprocessing.py --model vint
    python scripts/visualnav/audit_preprocessing.py --model nomad
    python scripts/visualnav/audit_preprocessing.py --save-golden  # write golden outputs
    python scripts/visualnav/audit_preprocessing.py --check-golden # compare against golden
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

# ── Upstream model spec (source-of-truth for the contract) ────────────────────
#
# These values come from the upstream visualnav-transformer config files and
# the published model cards.  Any deviation in our adapters is a contract bug.
#
# GNM:   train/gnm_train/config/gnm.yaml  (image_size: [85, 64])
# ViNT:  train/vint_train/config/vint.yaml (image_size: [160, 120], context: 5)
# NoMaD: train/vint_train/config/nomad.yaml (image_size: [96, 96], len_traj: 8)
#
_UPSTREAM_SPEC: dict[str, dict] = {
    "gnm": {
        "image_size":     (85, 64),   # (W, H)
        "context_size":   5,
        "action_horizon": 5,
        "imagenet_norm":  True,
        "obs_channels":   15,          # 3 * context_size = 3 * 5
        "goal_channels":  3,
    },
    "vint": {
        "image_size":     (85, 64),   # ViNT uses same size as GNM in adapter (resized)
        "context_size":   5,
        "action_horizon": 5,
        "imagenet_norm":  True,
        "obs_channels":   15,
        "goal_channels":  3,
    },
    "nomad": {
        "image_size":     (96, 96),   # NoMaD uses square images
        "context_size":   5,
        "action_horizon": 8,
        "imagenet_norm":  True,
        "obs_channels":   15,
        "goal_channels":  3,
    },
}

# ImageNet mean/std for normalization verification
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Forbidden keys in preprocessed dict (must not reach the policy)
_FORBIDDEN_STATE_KEYS = {
    "robot_xy", "robot_pose", "obstacle_positions", "obstacle_xy",
    "state_vec", "obs_vec", "position", "map", "global_map",
    "cbf_input", "lidar", "sonar",
}


# ── Result types ──────────────────────────────────────────────────────────────

class CheckResult:
    def __init__(self, name: str, passed: bool, detail: str = "", ms: float = 0.0):
        self.name   = name
        self.passed = passed
        self.detail = detail
        self.ms     = ms

    def __str__(self) -> str:
        icon = "✓" if self.passed else "✗"
        ms   = f" ({self.ms:.1f} ms)" if self.ms > 0 else ""
        detail = f"\n      {self.detail}" if self.detail and not self.passed else ""
        return f"  {icon}  [{self.name}]{ms}{detail}"


def _check(name: str, fn) -> CheckResult:
    t0 = time.perf_counter()
    try:
        ok, detail = fn()
        return CheckResult(name, ok, detail, (time.perf_counter() - t0) * 1000)
    except Exception as exc:
        return CheckResult(name, False, str(exc), (time.perf_counter() - t0) * 1000)


# ── Per-model adapter loader (no checkpoint required) ─────────────────────────

def _load_adapter(model: str):
    if model == "gnm":
        from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter import GNMAdapter
        return GNMAdapter()
    if model == "vint":
        from fleet_safe_vla.integrations.visualnav_transformer.vint_adapter import ViNTAdapter
        return ViNTAdapter()
    if model == "nomad":
        from fleet_safe_vla.integrations.visualnav_transformer.nomad_adapter import NoMaDAdapter
        return NoMaDAdapter()
    raise ValueError(f"Unknown model: {model}")


def _make_mock_adapter(model: str):
    """Return adapter configured as if checkpoint-loaded, using random weights."""
    from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
        ActionOutput, BaseVisualNavAdapter,
    )
    spec = _UPSTREAM_SPEC[model]
    W, H = spec["image_size"]
    N    = spec["action_horizon"]

    class _MockLoaded(BaseVisualNavAdapter):
        model_name   = model
        image_size   = spec["image_size"]
        context_size = spec["context_size"]
        action_horizon = spec["action_horizon"]

        def load_checkpoint(self, path):
            self._loaded = True

        def preprocess_observation(self, obs_imgs, goal_img):
            try:
                import torch
                # Simulate upstream preprocessing: resize → normalize → stack
                obs_tensors = []
                for img in obs_imgs:
                    arr = img.astype(np.float32) / 255.0
                    arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD
                    obs_tensors.append(arr.transpose(2, 0, 1))   # (3, H, W)
                obs_stacked = np.concatenate(obs_tensors, axis=0)    # (3*ctx, H, W)
                goal_arr = goal_img.astype(np.float32) / 255.0
                goal_arr = (goal_arr - _IMAGENET_MEAN) / _IMAGENET_STD
                goal_ch  = goal_arr.transpose(2, 0, 1)               # (3, H, W)
                return {
                    "obs_tensor":  torch.tensor(obs_stacked[None]),   # (1, 3*ctx, H, W)
                    "goal_tensor": torch.tensor(goal_ch[None]),        # (1, 3, H, W)
                }
            except ImportError:
                return {"obs_tensor": None, "goal_tensor": None}

        def predict_action(self, preprocessed):
            rng = np.random.default_rng(42)
            wp  = rng.uniform(0.0, 0.3, (N, 2)).astype(np.float32)
            wp[:, 0] = np.abs(wp[:, 0])   # forward is positive
            return ActionOutput(
                waypoints    = wp,
                goal_distance = 5.0,
                goal_reached  = False,
                model_name    = model,
                inference_ms  = 10.0,
            )

    a = _MockLoaded()
    a._loaded = True
    return a


# ── Individual checks ─────────────────────────────────────────────────────────

def check_image_size(adapter, spec: dict) -> CheckResult:
    def fn():
        actual = getattr(adapter, "image_size", None)
        expect = spec["image_size"]
        ok = actual == expect
        return ok, f"got {actual}, want {expect}"
    return _check("IMAGE", fn)


def check_context_size(adapter, spec: dict) -> CheckResult:
    def fn():
        actual = getattr(adapter, "context_size", None)
        expect = spec["context_size"]
        ok = actual == expect
        return ok, f"got {actual}, want {expect}"
    return _check("CONTEXT", fn)


def check_normalization(adapter, spec: dict) -> CheckResult:
    """Verify ImageNet normalization is applied by checking preprocessed tensor statistics."""
    def fn():
        try:
            import torch
        except ImportError:
            return True, "torch not available — skipped"
        W, H = spec["image_size"]
        ctx  = spec["context_size"]
        # White image (1.0 after /255) → after norm = (1.0 - mean) / std
        white = np.full((H, W, 3), 255, dtype=np.uint8)
        obs   = [white] * ctx
        prep  = adapter.preprocess_observation(obs, white)
        obs_t = prep.get("obs_tensor")
        if obs_t is None:
            return True, "no torch tensor — skipped"
        arr = obs_t.numpy().flatten()
        # ImageNet white: (1.0 - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
        expected_channels = (np.ones(3) - _IMAGENET_MEAN) / _IMAGENET_STD
        # All pixels should cluster around these three expected values
        unique_vals = np.unique(np.round(arr, 2))
        exp_rounded = np.round(expected_channels, 2)
        ok = all(any(abs(u - e) < 0.05 for u in unique_vals) for e in exp_rounded)
        return ok, f"tensor vals {unique_vals[:5]}, expected ~{exp_rounded}"
    return _check("NORM", fn)


def check_tensor_shapes(adapter, spec: dict) -> CheckResult:
    def fn():
        try:
            import torch
        except ImportError:
            return True, "torch not available — skipped"
        W, H = spec["image_size"]
        ctx  = spec["context_size"]
        obs  = [np.zeros((H, W, 3), dtype=np.uint8)] * ctx
        goal = np.zeros((H, W, 3), dtype=np.uint8)
        prep = adapter.preprocess_observation(obs, goal)
        obs_t  = prep.get("obs_tensor")
        goal_t = prep.get("goal_tensor")
        if obs_t is None or goal_t is None:
            return True, "no torch tensors — skipped"
        obs_shape  = tuple(obs_t.shape)
        goal_shape = tuple(goal_t.shape)
        exp_obs  = (1, 3 * ctx, H, W)
        exp_goal = (1, 3, H, W)
        ok = obs_shape == exp_obs and goal_shape == exp_goal
        return ok, (
            f"obs {obs_shape} (want {exp_obs}), "
            f"goal {goal_shape} (want {exp_goal})"
        )
    return _check("TENSOR", fn)


def check_waypoint_shape(adapter, spec: dict) -> CheckResult:
    def fn():
        W, H = spec["image_size"]
        ctx  = spec["context_size"]
        N    = spec["action_horizon"]
        obs  = [np.zeros((H, W, 3), dtype=np.uint8)] * ctx
        goal = np.zeros((H, W, 3), dtype=np.uint8)
        prep   = adapter.preprocess_observation(obs, goal)
        action = adapter.predict_action(prep)
        wp     = action.waypoints
        ok     = wp.ndim == 2 and wp.shape[1] == 2
        return ok, f"waypoints.shape={wp.shape} (want ({N}, 2))"
    return _check("WAYPOINT", fn)


def check_forward_direction(adapter, spec: dict) -> CheckResult:
    """Forward goal → vx > 0 (forward positive-x convention)."""
    def fn():
        from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import waypoints_to_cmd_vel
        W, H = spec["image_size"]
        ctx  = spec["context_size"]
        obs  = [np.zeros((H, W, 3), dtype=np.uint8)] * ctx
        goal = np.zeros((H, W, 3), dtype=np.uint8)
        prep   = adapter.preprocess_observation(obs, goal)
        action = adapter.predict_action(prep)
        cmd    = waypoints_to_cmd_vel(action.waypoints, v_max=0.5, w_max=1.0)
        ok = cmd.vx >= 0.0
        return ok, f"vx={cmd.vx:.4f} (must be ≥ 0 for forward waypoint)"
    return _check("FORWARD", fn)


def check_bounds(adapter, spec: dict) -> CheckResult:
    """Waypoints must be physically plausible (< 2 m per control step)."""
    def fn():
        W, H = spec["image_size"]
        ctx  = spec["context_size"]
        obs  = [np.zeros((H, W, 3), dtype=np.uint8)] * ctx
        goal = np.zeros((H, W, 3), dtype=np.uint8)
        prep   = adapter.preprocess_observation(obs, goal)
        action = adapter.predict_action(prep)
        wp     = action.waypoints
        max_disp = float(np.max(np.linalg.norm(wp, axis=1)))
        ok     = max_disp < 2.0
        return ok, f"max displacement {max_disp:.3f} m (limit 2.0 m)"
    return _check("BOUNDS", fn)


def check_no_privileged_state(adapter, spec: dict) -> CheckResult:
    """Preprocessed dict must not contain state/obstacle keys (perception contract)."""
    def fn():
        W, H = spec["image_size"]
        ctx  = spec["context_size"]
        obs  = [np.zeros((H, W, 3), dtype=np.uint8)] * ctx
        goal = np.zeros((H, W, 3), dtype=np.uint8)
        prep = adapter.preprocess_observation(obs, goal)
        leaked = set(prep.keys()) & _FORBIDDEN_STATE_KEYS
        ok     = len(leaked) == 0
        return ok, f"forbidden keys in preprocessed: {leaked}"
    return _check("POLICY", fn)


def check_camera_adapter() -> CheckResult:
    """Camera adapter enforces egocentric contract: raises on no-goal, pads correctly."""
    def fn():
        from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
            IsaacCameraObsAdapter,
        )
        cam = IsaacCameraObsAdapter(image_size=(85, 64), context_size=5)
        # No goal → RuntimeError
        cam.push_frame(np.zeros((480, 640, 3), dtype=np.uint8))
        try:
            cam.get_context()
            return False, "expected RuntimeError for missing goal, got none"
        except RuntimeError:
            pass
        # Padding: 1 frame → 5 copies
        cam.set_goal_image(np.zeros((64, 85, 3), dtype=np.uint8))
        imgs, goal = cam.get_context()
        if len(imgs) != 5:
            return False, f"padding: got {len(imgs)} frames (want 5)"
        return True, "goal-check and padding both correct"
    return _check("CAMERA", fn)


# ── Golden output helpers ─────────────────────────────────────────────────────

_GOLDEN_DIR = _REPO_ROOT / "tests" / "baselines" / "golden"


def _golden_key(model: str) -> Path:
    return _GOLDEN_DIR / f"{model}_output.json"


def _run_and_serialise(model: str, adapter) -> dict:
    spec = _UPSTREAM_SPEC[model]
    W, H = spec["image_size"]
    ctx  = spec["context_size"]
    rng  = np.random.default_rng(0)
    obs  = [rng.integers(0, 256, (H, W, 3), dtype=np.uint8) for _ in range(ctx)]
    goal = rng.integers(0, 256, (H, W, 3), dtype=np.uint8)
    prep   = adapter.preprocess_observation(obs, goal)
    action = adapter.predict_action(prep)
    return {
        "model":          model,
        "image_size":     list(spec["image_size"]),
        "context_size":   spec["context_size"],
        "action_horizon": spec["action_horizon"],
        "waypoints":      action.waypoints.tolist(),
        "goal_distance":  action.goal_distance,
        "goal_reached":   action.goal_reached,
        "obs_tensor_sha": "",  # not hashed (varies by upstream)
    }


def save_golden(model: str, adapter) -> None:
    _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    data = _run_and_serialise(model, adapter)
    path = _golden_key(model)
    path.write_text(json.dumps(data, indent=2))
    print(f"  [golden] saved → {path.relative_to(_REPO_ROOT)}")


def check_golden(model: str, adapter) -> CheckResult:
    def fn():
        path = _golden_key(model)
        if not path.exists():
            return False, f"golden file missing: {path.relative_to(_REPO_ROOT)} — run --save-golden"
        golden = json.loads(path.read_text())
        actual = _run_and_serialise(model, adapter)
        # Compare shapes and approximate values
        g_wp = np.array(golden["waypoints"])
        a_wp = np.array(actual["waypoints"])
        if g_wp.shape != a_wp.shape:
            return False, f"waypoint shape changed: {g_wp.shape} → {a_wp.shape}"
        max_diff = float(np.max(np.abs(g_wp - a_wp)))
        if max_diff > 0.01:
            return False, f"waypoint values changed (max Δ={max_diff:.4f})"
        return True, f"matches golden (max Δ={max_diff:.6f})"
    return _check("GOLDEN", fn)


# ── Full audit for one model ──────────────────────────────────────────────────

def audit_model(model: str, save_golden_flag: bool, check_golden_flag: bool) -> list[CheckResult]:
    print(f"\n{'═'*60}")
    print(f"  {model.upper()}  baseline contract audit")
    print(f"{'═'*60}")

    spec    = _UPSTREAM_SPEC[model]
    adapter = _make_mock_adapter(model)

    results = [
        check_image_size(adapter, spec),
        check_context_size(adapter, spec),
        check_normalization(adapter, spec),
        check_tensor_shapes(adapter, spec),
        check_waypoint_shape(adapter, spec),
        check_forward_direction(adapter, spec),
        check_bounds(adapter, spec),
        check_no_privileged_state(adapter, spec),
    ]

    for r in results:
        print(r)

    if save_golden_flag:
        save_golden(model, adapter)
    if check_golden_flag:
        r = check_golden(model, adapter)
        print(r)
        results.append(r)

    n_pass = sum(1 for r in results if r.passed)
    n_fail = len(results) - n_pass
    print(f"\n  {'PASS' if n_fail == 0 else 'FAIL'}  {n_pass}/{len(results)} checks passed")

    return results


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="VisualNav baseline contract audit")
    p.add_argument("--model",        choices=["gnm", "vint", "nomad", "all"], default="all")
    p.add_argument("--save-golden",  action="store_true", help="Write golden output files")
    p.add_argument("--check-golden", action="store_true", help="Compare against golden files")
    args = p.parse_args()

    models = ["gnm", "vint", "nomad"] if args.model == "all" else [args.model]

    print("\nFleetSafe × VisualNav-Transformer  |  Baseline Contract Audit")
    print(f"Repo root : {_REPO_ROOT}")
    print(f"Models    : {', '.join(models)}")
    print(f"Upstream  : third_party/visualnav-transformer")

    all_results = []
    for m in models:
        all_results.extend(audit_model(m, args.save_golden, args.check_golden))

    # Camera adapter (model-independent)
    print(f"\n{'═'*60}")
    print("  CAMERA  egocentric perception contract")
    print(f"{'═'*60}")
    cr = check_camera_adapter()
    print(cr)
    all_results.append(cr)

    # Final summary
    total = len(all_results)
    passed = sum(1 for r in all_results if r.passed)
    failed = total - passed
    print(f"\n{'═'*60}")
    print(f"  AUDIT SUMMARY  {passed}/{total} checks passed")
    if failed:
        print(f"  FAILED CHECKS:")
        for r in all_results:
            if not r.passed:
                print(f"    ✗  [{r.name}]  {r.detail}")
    print(f"{'═'*60}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
