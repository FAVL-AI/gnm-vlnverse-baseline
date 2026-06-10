#!/usr/bin/env python3
"""
run_visualnav_benchmark_isaac.py — Isaac Lab benchmark entry point.

Runs GNM / ViNT / NoMaD + FleetSafe against canonical scenes using the
Isaac Lab physics backend.  AppLauncher is initialised BEFORE any fleet_safe_vla
or isaaclab import, as required by Isaac's Python runtime.

Usage
-----
Smoke test (1 seed, 1 scene, Isaac physics):
  conda activate isaac
  python scripts/visualnav/run_visualnav_benchmark_isaac.py \\
      --model gnm --seeds smoke --scenes cluttered_static \\
      --fleetsafe both --headless

Development run (3 seeds, all scenes):
  python scripts/visualnav/run_visualnav_benchmark_isaac.py \\
      --model gnm --seeds dev --scenes all --fleetsafe both --headless

Full matrix (all models, both modes, dev seeds):
  python scripts/visualnav/run_visualnav_benchmark_isaac.py \\
      --model all --seeds dev --scenes all --fleetsafe both --headless

⚠ BACKEND NOTE:
  Isaac physics results carry claim_scope: simulation_isaaclab.
  They are publication-quality ONLY after the sim-to-sim validation gate passes
  (see docs/architecture/PPO_DDS_SIM2SIM_DEPLOYMENT.md §sim-to-sim validation).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ── AppLauncher MUST be called before ANY isaaclab or fleet_safe_vla import ──
# Parse our args first with parse_known_args so Isaac's own argparse flags
# are forwarded to AppLauncher unchanged.

def _parse_our_args() -> tuple[argparse.Namespace, list[str]]:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,   # let Isaac add its own help flags
    )
    p.add_argument("--model",      default="gnm",
                   help="gnm | vint | nomad | mock | all")
    p.add_argument("--seeds",      default="smoke",
                   help="smoke | dev | paper | N | '0,1,2'")
    p.add_argument("--scenes",     default="all",
                   help="all | scene_name | 's1,s2'")
    p.add_argument("--fleetsafe",  default="both",
                   choices=["true", "false", "both"])
    p.add_argument("--checkpoint", default=None)
    p.add_argument("--output-dir", default="benchmarks/visualnav/results")
    p.add_argument("--max-steps",  type=int,   default=500)
    p.add_argument("--control-hz", type=float, default=4.0)
    p.add_argument("--v-max",      type=float, default=0.3)
    p.add_argument("--vy-max",     type=float, default=0.3)
    p.add_argument("--w-max",      type=float, default=0.7)
    p.add_argument("--near-miss",  type=float, default=0.45)
    # AppLauncher flags (parsed here for clarity; forwarded to launcher below)
    p.add_argument("--headless",   action="store_true", default=False)
    p.add_argument("--device",     default="cuda:0")
    return p.parse_known_args()


def main() -> int:
    args, extra_isaac_args = _parse_our_args()

    # ── Step 1: AppLauncher — must be the FIRST real import ──────────────────
    try:
        from isaaclab.app import AppLauncher
    except ImportError:
        print(
            "[ERROR] isaaclab not found.  Activate the isaac conda environment:\n"
            "  conda activate isaac\n"
            "  python scripts/visualnav/run_visualnav_benchmark_isaac.py ..."
        )
        return 1

    launcher_cfg = {
        "headless": args.headless,
    }
    # Build sys.argv that AppLauncher sees (extra Isaac flags only)
    _orig_argv = sys.argv[:]
    sys.argv = [sys.argv[0]] + extra_isaac_args
    launcher = AppLauncher(launcher_cfg)
    app      = launcher.app
    sys.argv = _orig_argv

    # ── Step 2: All downstream imports AFTER app boots ───────────────────────
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_REPO_ROOT))

    from fleet_safe_vla.benchmarks.visualnav_runner import (
        BACKEND_ISAACLAB,
        VisualNavBenchmarkRunner,
    )
    from fleet_safe_vla.benchmarks.visualnav_metrics import aggregate_episodes
    from fleet_safe_vla.benchmarks.visualnav_scenarios import get_scenes, get_seeds

    _VNT_WEIGHTS = _REPO_ROOT / "third_party" / "visualnav-transformer" / "model_weights"
    _DEFAULT_CKPT = {
        "gnm":   _VNT_WEIGHTS / "gnm"   / "gnm.pth",
        "vint":  _VNT_WEIGHTS / "vint"  / "vint.pth",
        "nomad": _VNT_WEIGHTS / "nomad" / "nomad.pth",
    }
    _ALL_MODELS = ["gnm", "vint", "nomad", "mock"]

    # ── Step 3: Build adapter(s) ─────────────────────────────────────────────
    def _build_adapter(model: str, checkpoint: Path | None):
        if model == "mock":
            from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
                BaseVisualNavAdapter, ActionOutput,
            )
            import numpy as np

            class _MockAdapter(BaseVisualNavAdapter):
                """Deterministic straight-line adapter for CI/smoke testing."""
                def load_checkpoint(self, path):
                    pass
                def preprocess_observation(self, obs_imgs, goal_img):
                    return {}
                def predict_action(self, preprocessed):
                    return ActionOutput(
                        waypoints=np.array([[0.05, 0.0]]),
                        goal_reached=False,
                        raw_output={},
                    )

            print("[isaac-bench] mock adapter (no checkpoint needed)")
            return _MockAdapter()

        if model == "gnm":
            from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter import GNMAdapter
            adapter = GNMAdapter()
        elif model == "vint":
            from fleet_safe_vla.integrations.visualnav_transformer.vint_adapter import ViNTAdapter
            adapter = ViNTAdapter()
        elif model == "nomad":
            from fleet_safe_vla.integrations.visualnav_transformer.nomad_adapter import NoMaDAdapter
            adapter = NoMaDAdapter()
        else:
            raise ValueError(f"Unknown model: {model!r}. Choose from: gnm, vint, nomad, mock")

        ckpt = checkpoint or _DEFAULT_CKPT.get(model)
        if ckpt is None or not Path(ckpt).exists():
            print(f"[ERROR] Checkpoint not found: {ckpt}")
            print("  bash scripts/visualnav/setup_visualnav.sh --download-weights")
            sys.exit(1)

        from fleet_safe_vla.integrations.visualnav_transformer import (
            CheckpointNotFoundError, UpstreamNotFoundError,
        )
        try:
            adapter.load_checkpoint(Path(ckpt))
        except (CheckpointNotFoundError, UpstreamNotFoundError, Exception) as exc:
            print(f"[ERROR] Could not load checkpoint: {exc}")
            sys.exit(1)

        print(f"[isaac-bench] {model} loaded on {adapter._device}")
        return adapter

    models = _ALL_MODELS if args.model == "all" else [args.model]
    seeds  = get_seeds(args.seeds)
    scenes = get_scenes(args.scenes)

    if args.fleetsafe == "both":
        fleetsafe_modes = [False, True]
    else:
        fleetsafe_modes = [args.fleetsafe.lower() == "true"]

    out_dir = _REPO_ROOT / args.output_dir

    print(f"\n[isaac-bench] backend=isaaclab  models={models}  "
          f"seeds={len(seeds)}  scenes={[s.name for s in scenes]}")
    print(f"[isaac-bench] output → {out_dir}\n")

    # ── Step 4: Run benchmark matrix ─────────────────────────────────────────
    run_summaries: list[dict] = []
    exit_code = 0

    for model_name in models:
        adapter = _build_adapter(
            model_name,
            Path(args.checkpoint) if args.checkpoint else None,
        )
        for fs in fleetsafe_modes:
            runner = VisualNavBenchmarkRunner(
                adapter     = adapter,
                fleetsafe   = fs,
                backend     = BACKEND_ISAACLAB,
                output_dir  = out_dir,
                control_hz  = args.control_hz,
                v_max       = args.v_max,
                vy_max      = args.vy_max,
                w_max       = args.w_max,
                near_miss_m = args.near_miss,
                max_steps   = args.max_steps,
            )
            try:
                metrics_list = runner.run(scenes, seeds)
                agg = aggregate_episodes(metrics_list)
                run_summaries.append({
                    "model": model_name, "fleetsafe": fs, "backend": BACKEND_ISAACLAB, **agg
                })
            except Exception as exc:
                print(f"[ERROR] {model_name} fleetsafe={fs}: {exc}")
                exit_code = 1
                continue

    # ── Step 5: Print terminal summary ───────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  {'Model':<8} {'FS':<5} {'N':>4} {'SPL':>6} "
          f"{'Succ%':>6} {'Coll%':>6} {'Interv%':>8}")
    print(f"  {'-'*56}")
    for s in run_summaries:
        fs_tag = "✓" if s["fleetsafe"] else "—"
        print(
            f"  {s['model']:<8} {fs_tag:<5} {s.get('n_episodes',0):>4} "
            f"{s.get('spl_mean',0):>6.3f} "
            f"{100*s.get('success_rate',0):>5.1f}% "
            f"{100*s.get('collision_rate',0):>5.1f}% "
            f"{100*s.get('intervention_rate_mean',0):>7.1f}%"
        )
    print(f"{'='*72}\n")

    # ── Step 6: Close Isaac ───────────────────────────────────────────────────
    app.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
