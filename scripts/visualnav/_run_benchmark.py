#!/usr/bin/env python3
"""
_run_benchmark.py — Python entry-point called by run_baseline_isaac.sh and
run_fleetsafe_isaac.sh.  Not intended to be run directly by users.

Parses CLI arguments, instantiates the correct adapter, runs BenchmarkRunner,
and saves results JSON.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

import numpy as np


def _load_yaml_simple(path: Path) -> dict:
    """Minimal YAML loader (key: value only — avoids PyYAML dep)."""
    result: dict = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line and not line.startswith("-"):
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model",       required=True, choices=["gnm", "vint", "nomad"])
    p.add_argument("--checkpoint",  required=True)
    p.add_argument("--config",      required=True)
    p.add_argument("--output",      required=True)
    p.add_argument("--fleetsafe",   default="false")
    p.add_argument("--cbf-d-safe",  type=float, default=0.30)
    p.add_argument("--cbf-estop",   type=float, default=0.15)
    p.add_argument("--max-steps",   type=int,   default=500)
    p.add_argument("--seeds",       default="")   # "0,1,2" or empty
    p.add_argument("--scenes",      default="")   # "open_corridor,sparse_obstacles"
    p.add_argument("--smoke-test",  action="store_true")
    args = p.parse_args()

    fleetsafe = args.fleetsafe.lower() in ("true", "1", "yes")
    ckpt_path = Path(args.checkpoint)
    out_path  = Path(args.output)

    # ── Load adapter ──────────────────────────────────────────────────────────
    print(f"\n[run_benchmark] model={args.model}  fleetsafe={fleetsafe}")
    print(f"  checkpoint: {ckpt_path}")

    from fleet_safe_vla.integrations.visualnav_transformer import (
        CheckpointNotFoundError, UpstreamNotFoundError,
    )

    if args.model == "gnm":
        from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter import GNMAdapter
        adapter = GNMAdapter()
    elif args.model == "vint":
        from fleet_safe_vla.integrations.visualnav_transformer.vint_adapter import ViNTAdapter
        adapter = ViNTAdapter()
    else:
        from fleet_safe_vla.integrations.visualnav_transformer.nomad_adapter import NoMaDAdapter
        adapter = NoMaDAdapter()

    try:
        adapter.load_checkpoint(ckpt_path)
    except (UpstreamNotFoundError, CheckpointNotFoundError) as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(f"  checkpoint loaded on {adapter._device}")

    # ── Build benchmark config ────────────────────────────────────────────────
    from fleet_safe_vla.integrations.visualnav_transformer.benchmark_runner import (
        BenchmarkConfig, BenchmarkRunner, SceneConfig, StartGoalPair,
    )

    _scene_defaults = {
        "open_corridor":    SceneConfig("open_corridor",    "none",   0,  8.0),
        "sparse_obstacles": SceneConfig("sparse_obstacles", "sparse", 6,  8.0),
        "dense_obstacles":  SceneConfig("dense_obstacles",  "dense",  16, 8.0),
    }
    _sg_defaults = [
        StartGoalPair((0.0, 0.0), (2.0, 0.0), "forward_short"),
        StartGoalPair((0.0, 0.0), (4.0, 0.0), "forward_long"),
        StartGoalPair((0.0, 0.0), (2.5, 2.0), "diagonal"),
        StartGoalPair((0.0, 0.0), (0.0, 3.0), "lateral"),
        StartGoalPair((0.0, 0.0), (-1.5, 2.0), "reverse_diagonal"),
    ]

    if args.smoke_test:
        seeds  = [0]
        scenes = [_scene_defaults["open_corridor"]]
        pairs  = [_sg_defaults[0]]
    else:
        seeds  = [int(s) for s in args.seeds.split(",")] if args.seeds else [0, 1, 2, 3, 4]
        scene_keys = args.scenes.split(",") if args.scenes else list(_scene_defaults.keys())
        scenes = [_scene_defaults[k] for k in scene_keys if k in _scene_defaults]
        pairs  = _sg_defaults

    cfg = BenchmarkConfig(
        scenes           = scenes,
        start_goal_pairs = pairs,
        seeds            = seeds,
        max_steps        = args.max_steps,
        control_hz       = 4.0,
        v_max            = 0.3,
        vy_max           = 0.3,
        w_max            = 0.7,
        use_camera       = False,   # synthetic frames for now
    )

    # ── FleetSafe CBF config ──────────────────────────────────────────────────
    if fleetsafe:
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFConfig
        cbf_cfg = YahboomCBFConfig(
            d_safe_m    = args.cbf_d_safe,
            estop_dist_m = args.cbf_estop,
        )
    else:
        cbf_cfg = None

    # ── Run ───────────────────────────────────────────────────────────────────
    runner = BenchmarkRunner(
        adapter      = adapter,
        benchmark_cfg = cfg,
        fleetsafe    = fleetsafe,
    )
    if fleetsafe and cbf_cfg is not None:
        runner._wrapper.cbf.cfg = cbf_cfg

    results = runner.run_all()
    runner.save_results(out_path, results)

    agg = runner._aggregate(results)
    print(f"\n[run_benchmark] Aggregate results:")
    print(f"  episodes        : {agg.get('n_episodes', 0)}")
    print(f"  success_rate    : {agg.get('success_rate', 0):.3f}")
    print(f"  collision_rate  : {agg.get('collision_rate', 0):.3f}")
    print(f"  mean_latency_ms : {agg.get('mean_latency_ms', 0):.1f}")
    if fleetsafe:
        print(f"  mean_interventions: {agg.get('mean_intervention_count', 0):.1f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
