#!/usr/bin/env python3
"""
check_visualnav_checkpoints.py — Validate GNM, ViNT, NoMaD checkpoints.

For each model:
  1. Check checkpoint file exists and has non-zero size.
  2. Load the checkpoint (weights_only=False; upstream checkpoints are trusted).
  3. Run one forward pass on a synthetic input image.
  4. Verify output shape and record inference latency.
  5. Print PASS / WARN / FAIL per model.

Exit codes:
  0  all three models passed (or warned with fallback).
  1  one or more models failed hard (checkpoint missing or wrong shape).
  2  one or more models warned (dependency missing, action taken per --strict).

Usage:
  python scripts/visualnav/check_visualnav_checkpoints.py
  python scripts/visualnav/check_visualnav_checkpoints.py --strict   # WARN → FAIL
  python scripts/visualnav/check_visualnav_checkpoints.py --model gnm
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

_VNT_ROOT    = _REPO_ROOT / "third_party" / "visualnav-transformer"
_WEIGHTS_DIR = _VNT_ROOT  / "model_weights"


# ── Per-model spec ─────────────────────────────────────────────────────────────

_MODEL_SPECS = {
    "gnm": {
        "ckpt":             _WEIGHTS_DIR / "gnm"   / "gnm.pth",
        "expected_min_mb":  80,
        "context_size":     5,
        "action_horizon":   5,
        "image_size":       (85, 64),
        "expected_waypoints_shape": (5, 2),
    },
    "vint": {
        "ckpt":             _WEIGHTS_DIR / "vint"  / "vint.pth",
        "expected_min_mb":  300,
        "context_size":     5,
        "action_horizon":   5,
        "image_size":       (85, 64),
        "expected_waypoints_shape": (5, 2),
    },
    "nomad": {
        "ckpt":             _WEIGHTS_DIR / "nomad" / "nomad.pth",
        "expected_min_mb":  50,
        "context_size":     3,
        "action_horizon":   8,
        "image_size":       (96, 96),
        "expected_waypoints_shape": (8, 2),
    },
}


# ── Result ─────────────────────────────────────────────────────────────────────

class _Result:
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"

    def __init__(self, model: str) -> None:
        self.model    = model
        self.status   = self.PASS
        self.messages: list[str] = []
        self.latency_ms: float   = 0.0
        self.output_shape: tuple = ()

    def warn(self, msg: str) -> None:
        if self.status == self.PASS:
            self.status = self.WARN
        self.messages.append(f"[WARN] {msg}")

    def fail(self, msg: str) -> None:
        self.status = self.FAIL
        self.messages.append(f"[FAIL] {msg}")

    def ok(self, msg: str) -> None:
        self.messages.append(f"  ✓  {msg}")

    def print_summary(self) -> None:
        icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}[self.status]
        colour = {"PASS": "\033[92m", "WARN": "\033[93m", "FAIL": "\033[91m"}[self.status]
        reset  = "\033[0m"
        print(f"\n{colour}{icon} {self.model.upper()} — {self.status}{reset}")
        for m in self.messages:
            print(f"    {m}")
        if self.latency_ms > 0:
            print(f"    latency: {self.latency_ms:.1f} ms")
        if self.output_shape:
            print(f"    waypoints shape: {self.output_shape}")


# ── Checker ────────────────────────────────────────────────────────────────────

def _check_model(model_name: str, spec: dict) -> _Result:
    r = _Result(model_name)

    # Step 1: checkpoint file
    ckpt_path = spec["ckpt"]
    if not ckpt_path.exists():
        r.fail(f"Checkpoint missing: {ckpt_path}")
        r.fail("Download: bash scripts/visualnav/setup_visualnav.sh --download-weights")
        return r

    size_mb = ckpt_path.stat().st_size / 1e6
    if size_mb < spec["expected_min_mb"]:
        r.fail(f"Checkpoint too small: {size_mb:.0f} MB (expected ≥ {spec['expected_min_mb']} MB) — truncated?")
        return r
    r.ok(f"Checkpoint: {ckpt_path.name} ({size_mb:.0f} MB)")

    # Step 2: upstream importable
    if not _VNT_ROOT.exists():
        r.fail("Upstream not cloned. Run: bash scripts/visualnav/setup_visualnav.sh")
        return r
    r.ok("Upstream repo present")

    # Step 3: load adapter and checkpoint
    try:
        if model_name == "gnm":
            from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter import GNMAdapter
            adapter = GNMAdapter(
                context_size   = spec["context_size"],
                action_horizon = spec["action_horizon"],
                image_size     = spec["image_size"],
            )
        elif model_name == "vint":
            from fleet_safe_vla.integrations.visualnav_transformer.vint_adapter import ViNTAdapter
            adapter = ViNTAdapter(
                context_size   = spec["context_size"],
                action_horizon = spec["action_horizon"],
                image_size     = spec["image_size"],
            )
        else:
            from fleet_safe_vla.integrations.visualnav_transformer.nomad_adapter import NoMaDAdapter
            adapter = NoMaDAdapter(
                context_size        = spec["context_size"],
                action_horizon      = spec["action_horizon"],
                num_diffusion_steps = 5,   # fast for validation
                image_size          = spec["image_size"],
            )

        adapter.load_checkpoint(ckpt_path)
        r.ok("Checkpoint loaded")

    except ModuleNotFoundError as exc:
        r.warn(f"Missing dependency: {exc}")
        if "warmup_scheduler" in str(exc):
            r.warn("Fix: pip install warmup_scheduler")
        elif "diffusers" in str(exc) or "cached_download" in str(exc):
            r.warn("Fix: pip install 'diffusers==0.11.1' 'huggingface_hub==0.12.0'")
        elif "diffusion_policy" in str(exc):
            r.warn("Fix: git clone https://github.com/real-stanford/diffusion_policy && pip install -e diffusion_policy/")
        r.warn("Cannot validate inference — dependency install required")
        return r

    except Exception as exc:
        r.fail(f"Checkpoint load failed: {exc}")
        return r

    # Step 4: synthetic forward pass
    try:
        import numpy as np
        W, H = spec["image_size"]
        ctx  = spec["context_size"]
        rng  = np.random.default_rng(0)
        obs_imgs = [rng.integers(0, 256, (H, W, 3), dtype=np.uint8) for _ in range(ctx + 1)]
        goal_img = rng.integers(0, 256, (H, W, 3), dtype=np.uint8)

        preprocessed = adapter.preprocess_observation(obs_imgs, goal_img)

        t0     = time.perf_counter()
        action = adapter.predict_action(preprocessed)
        ms     = (time.perf_counter() - t0) * 1000.0

        r.latency_ms   = ms
        r.output_shape = tuple(action.waypoints.shape)

        expected = spec["expected_waypoints_shape"]
        if r.output_shape != expected:
            r.fail(f"Unexpected waypoints shape: {r.output_shape} (expected {expected})")
        else:
            r.ok(f"Inference OK — waypoints {r.output_shape}, {ms:.1f} ms")

    except Exception as exc:
        r.fail(f"Inference failed: {exc}")

    return r


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model",  default="all",
                   help="gnm | vint | nomad | all  (default: all)")
    p.add_argument("--strict", action="store_true",
                   help="Treat WARN as FAIL (for CI)")
    args = p.parse_args()

    models = list(_MODEL_SPECS.keys()) if args.model == "all" else [args.model]

    print(f"\n[check_checkpoints] Validating {models}")
    print(f"  Weights dir: {_WEIGHTS_DIR}")

    results: list[_Result] = []
    for model_name in models:
        spec = _MODEL_SPECS.get(model_name)
        if spec is None:
            print(f"  Unknown model: {model_name!r}")
            return 1
        r = _check_model(model_name, spec)
        r.print_summary()
        results.append(r)

    # Summary line
    print(f"\n{'─'*60}")
    n_pass = sum(1 for r in results if r.status == _Result.PASS)
    n_warn = sum(1 for r in results if r.status == _Result.WARN)
    n_fail = sum(1 for r in results if r.status == _Result.FAIL)
    print(f"  PASS: {n_pass}   WARN: {n_warn}   FAIL: {n_fail}")

    if n_fail > 0:
        return 1
    if n_warn > 0 and args.strict:
        print("  --strict: WARN treated as FAIL")
        return 2
    if n_warn > 0:
        print("  WARN: dependency issues present. Install missing packages to enable full inference validation.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
