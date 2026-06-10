#!/usr/bin/env python3
"""
run_visualnav_benchmark.py — Publishable FleetSafe VisualNav benchmark entry point.

Runs GNM / ViNT / NoMaD with and without the FleetSafe safety layer across
canonical scenes and seeds, writing per-episode JSON/CSV logs and an aggregate
comparison report.

Usage
-----
Smoke test (1 seed, 1 scene, mock backend — no checkpoints needed):
  python scripts/visualnav/run_visualnav_benchmark.py \\
      --model gnm --seeds smoke --scenes straight_corridor \\
      --backend mock --fleetsafe both

Dev run (10 seeds, all scenes, mock backend):
  python scripts/visualnav/run_visualnav_benchmark.py \\
      --model gnm --seeds dev --scenes all --backend mock --fleetsafe both

Publication run (50 seeds, all scenes, mujoco backend, real checkpoint):
  python scripts/visualnav/run_visualnav_benchmark.py \\
      --model gnm --seeds paper --scenes all --backend mujoco --fleetsafe both \\
      --checkpoint third_party/visualnav-transformer/model_weights/gnm/gnm.pth

Full matrix (all models, both modes, 10 seeds):
  python scripts/visualnav/run_visualnav_benchmark.py \\
      --model all --seeds dev --scenes all --backend mock --fleetsafe both

⚠ MOCK BACKEND: results from --backend mock are NOT valid for publication.
  Use --backend mujoco or --backend isaaclab (not yet implemented).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from fleet_safe_vla.benchmarks.visualnav_metrics import (
    aggregate_episodes,
    aggregate_by_scene,
    build_comparison_table,
)
from fleet_safe_vla.benchmarks.visualnav_runner import (
    BACKEND_ISAACLAB,
    BACKEND_MOCK,
    BACKEND_MUJOCO,
    PERCEPTION_NONE,
    PERCEPTION_MOCK,
    PERCEPTION_YOLO,
    VisualNavBenchmarkRunner,
)
from fleet_safe_vla.benchmarks.visualnav_scenarios import get_scenes, get_seeds
from fleet_safe_vla.benchmarks.wandb_logger import WandbLogger, add_wandb_args


# ── Default checkpoint paths ──────────────────────────────────────────────────

_VNT_WEIGHTS = _REPO_ROOT / "third_party" / "visualnav-transformer" / "model_weights"
_DEFAULT_CKPT = {
    "gnm":   _VNT_WEIGHTS / "gnm"   / "gnm.pth",
    "vint":  _VNT_WEIGHTS / "vint"  / "vint.pth",
    "nomad": _VNT_WEIGHTS / "nomad" / "nomad.pth",
}

_ALL_MODELS = ["gnm", "vint", "nomad"]


# ── Mock adapter (no checkpoint needed, for smoke testing) ────────────────────

class _MockAdapter:
    """
    Stand-in adapter for smoke testing the benchmark pipeline.

    Returns deterministic random waypoints — never loads real checkpoints.
    ⚠ Results produced with this adapter are meaningless as navigation metrics.
    """
    model_name  = "mock"
    image_size  = (85, 64)
    context_size = 5

    def __init__(self) -> None:
        self._loaded = True
        self._device = None

    def is_loaded(self) -> bool:
        return True

    def load_checkpoint(self, path: Path) -> None:
        pass

    def preprocess_observation(self, obs_imgs, goal_img) -> dict:
        import numpy as np
        return {"obs": obs_imgs[0] if obs_imgs else None, "goal": goal_img}

    def predict_action(self, preprocessed):
        import numpy as np
        from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import ActionOutput
        return ActionOutput(
            waypoints    = np.random.default_rng().standard_normal((5, 2)) * 0.05,
            goal_distance = 2.0,
            goal_reached  = False,
            model_name    = self.model_name,
            inference_ms  = 1.0,
        )

    def action_to_cmd_vel(self, action, *, v_max=0.3, vy_max=0.3, w_max=0.7, control_hz=4.0):
        from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
            CmdVel, waypoints_to_cmd_vel,
        )
        return waypoints_to_cmd_vel(
            action.waypoints,
            v_max=v_max, vy_max=vy_max, w_max=w_max, control_hz=control_hz,
        )


def _build_adapter(model: str, checkpoint: Path | None, backend: str):
    """Instantiate and load the appropriate adapter."""
    if model == "mock":
        return _MockAdapter()

    from fleet_safe_vla.integrations.visualnav_transformer import (
        CheckpointNotFoundError, UpstreamNotFoundError,
    )

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
        raise ValueError(f"Unknown model: {model!r}")

    ckpt = checkpoint or _DEFAULT_CKPT.get(model)
    if ckpt is None or not Path(ckpt).exists():
        if backend == BACKEND_MOCK:
            print(
                f"[WARN] Checkpoint not found for {model!r} — using mock adapter "
                f"(pipeline test only, results are NOT meaningful)."
            )
            return _MockAdapter()
        raise FileNotFoundError(
            f"Checkpoint not found: {ckpt}\n"
            "Download checkpoints:\n"
            "  bash scripts/visualnav/setup_visualnav.sh --download-weights\n"
            "Or use --backend mock for pipeline testing (no checkpoint needed)."
        )

    try:
        adapter.load_checkpoint(Path(ckpt))
    except (UpstreamNotFoundError, CheckpointNotFoundError) as exc:
        if backend == BACKEND_MOCK:
            print(f"[WARN] {exc}\nFalling back to mock adapter.")
            return _MockAdapter()
        print(f"[ERROR] {exc}")
        sys.exit(1)
    except Exception as exc:
        # On mock backend any load failure (e.g. missing training deps such as
        # warmup_scheduler) falls back gracefully — the mock sim doesn't need weights.
        if backend == BACKEND_MOCK:
            print(
                f"[WARN] Could not load checkpoint for {model!r} "
                f"({type(exc).__name__}: {exc})\n"
                f"  Falling back to mock adapter (pipeline test only, NOT meaningful)."
            )
            return _MockAdapter()
        print(f"[ERROR] {exc}")
        sys.exit(1)

    return adapter


# ── HTML comparison report ─────────────────────────────────────────────────────

def _write_html_comparison(
    run_summaries: list[dict],
    out_path: Path,
    title: str,
) -> None:
    from fleet_safe_vla.benchmarks.visualnav_metrics import build_comparison_table
    rows = build_comparison_table(run_summaries)
    if not rows:
        return

    headers = list(rows[0].keys())
    thead = "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
    tbody_rows = []
    for r in rows:
        fs_cls = " class='fs'" if r.get("FleetSafe") == "✓" else ""
        cells  = "".join(f"<td>{r[h]}</td>" for h in headers)
        tbody_rows.append(f"<tr{fs_cls}>{cells}</tr>")
    tbody = "\n".join(tbody_rows)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"/><title>{title}</title>
<style>
  body{{font-family:monospace;background:#1a1a2e;color:#eee;padding:24px;}}
  h1{{color:#00d4ff;}} h2{{color:#6bcfff;margin-top:28px;}}
  table{{border-collapse:collapse;width:100%;margin:10px 0;}}
  th{{background:#0f3460;color:#00d4ff;padding:6px 10px;text-align:left;}}
  td{{padding:5px 10px;border-bottom:1px solid #0f3460;}}
  tr.fs td{{background:rgba(0,212,255,.07);}}
  .warn{{color:#ff6b6b;}} .note{{color:#888;font-size:.9em;margin:10px 0;}}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="note">
  FleetSafe × VisualNav benchmark.
  Baseline and FleetSafe variants use identical seeds and scenes —
  any difference is caused only by the CBF-QP safety layer.<br>
  <span class="warn">⚠ MOCK BACKEND rows are NOT valid for publication claims.</span>
</p>
<h2>Aggregate Comparison</h2>
<table><thead>{thead}</thead><tbody>{tbody}</tbody></table>
<p class="note">
  SPL = Success weighted by Path Length (Anderson et al. 2018).<br>
  NearMiss = mean steps within near_miss threshold (0.45 m).<br>
  Interv. Rate = CBF interventions / total steps (FleetSafe only).
</p>
</body></html>"""

    out_path.write_text(html)
    print(f"  HTML → {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--model",      default="gnm",
                   help="gnm | vint | nomad | all  (default: gnm)")
    p.add_argument("--seeds",      default="smoke",
                   help="smoke | dev | paper | N | '0,1,2'  (default: smoke)")
    p.add_argument("--scenes",     default="all",
                   help="all | scene_name | 'scene1,scene2'  (default: all)")
    p.add_argument("--backend",    default=BACKEND_MOCK,
                   choices=[BACKEND_MOCK, BACKEND_MUJOCO, BACKEND_ISAACLAB],
                   help=(
                       "mock (pipeline test) | mujoco (publication) | "
                       "isaaclab (use run_visualnav_benchmark_isaac.py instead)  "
                       "(default: mock)"
                   ))
    p.add_argument("--fleetsafe",  default="both",
                   choices=["true", "false", "both"],
                   help="true | false | both  (default: both)")
    p.add_argument("--checkpoint", default=None,
                   help="Path to checkpoint (overrides default path per model)")
    p.add_argument("--output-dir", default="benchmarks/visualnav/results",
                   help="Root output directory")
    p.add_argument("--max-steps",  type=int, default=500)
    p.add_argument("--control-hz", type=float, default=4.0)
    p.add_argument("--v-max",      type=float, default=0.3)
    p.add_argument("--vy-max",     type=float, default=0.3)
    p.add_argument("--w-max",      type=float, default=0.7)
    p.add_argument("--near-miss",  type=float, default=0.45)
    p.add_argument("--cmd-delay-ms", type=int, default=0,
                   help="Inject N ms of cmd_vel delay (0 = no delay)")
    p.add_argument(
        "--perception", default=PERCEPTION_NONE,
        choices=[PERCEPTION_NONE, PERCEPTION_MOCK, PERCEPTION_YOLO],
        help="none | mock | yolo  (default: none)",
    )
    add_wandb_args(p)
    args = p.parse_args()

    if args.backend == BACKEND_ISAACLAB:
        print(
            "\n[ERROR] --backend isaaclab requires the Isaac AppLauncher entry point:\n"
            "  conda activate isaac\n"
            "  python scripts/visualnav/run_visualnav_benchmark_isaac.py "
            "--model <gnm|vint|nomad> ...\n\n"
            "  This script cannot initialise Isaac Sim (AppLauncher must be\n"
            "  the first import — see docs/visualnav_reproduction/ISAAC_PHYSICS_BACKEND.md).\n"
        )
        return 1

    models = _ALL_MODELS if args.model == "all" else [args.model]
    seeds  = get_seeds(args.seeds)
    scenes = get_scenes(args.scenes)
    fleetsafe_modes: list[bool]
    if args.fleetsafe == "both":
        fleetsafe_modes = [False, True]
    else:
        fleetsafe_modes = [args.fleetsafe.lower() == "true"]

    out_dir = _REPO_ROOT / args.output_dir
    report_dir = _REPO_ROOT / "benchmarks" / "visualnav" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    perception = getattr(args, "perception", PERCEPTION_NONE)

    print(f"\n[benchmark] models={models}  seeds={len(seeds)}  "
          f"scenes={[s.name for s in scenes]}  "
          f"fleetsafe={fleetsafe_modes}  backend={args.backend}  "
          f"perception={perception}")
    print(f"[benchmark] output → {out_dir}\n")

    # ── W&B logger ────────────────────────────────────────────────────────────
    logger = WandbLogger.from_args(args)
    from fleet_safe_vla.benchmark_version import GIT_COMMIT, version_block
    base_config = {
        "git_commit":   GIT_COMMIT,
        "backend":      args.backend,
        "seeds":        args.seeds,
        "scenes":       args.scenes,
        "perception":   perception,
        "claim_scope":  (
            "engineering_only_not_publication_evidence"
            if args.backend == BACKEND_MOCK
            else f"simulation_{args.backend}"
        ),
        **version_block(),
    }

    run_summaries: list[dict] = []
    run_dirs:      list[Path] = []
    t_start = time.time()

    for model_name in models:
        adapter = _build_adapter(
            model_name,
            Path(args.checkpoint) if args.checkpoint else None,
            args.backend,
        )

        for fs in fleetsafe_modes:
            run_config = {
                **base_config,
                "model":     model_name,
                "fleetsafe": fs,
            }
            logger.start(run_config)

            runner = VisualNavBenchmarkRunner(
                adapter       = adapter,
                fleetsafe     = fs,
                backend       = args.backend,
                output_dir    = out_dir,
                control_hz    = args.control_hz,
                v_max         = args.v_max,
                vy_max        = args.vy_max,
                w_max         = args.w_max,
                near_miss_m   = args.near_miss,
                max_steps     = args.max_steps,
                perception    = perception,
                cmd_delay_ms  = getattr(args, "cmd_delay_ms", 0),
            )
            metrics_list = runner.run(scenes, seeds)

            agg      = aggregate_episodes(metrics_list)
            by_scene = aggregate_by_scene(metrics_list)
            summary  = {
                "model":     model_name,
                "fleetsafe": fs,
                "backend":   args.backend,
                "perception": perception,
                **agg,
            }
            run_summaries.append(summary)

            # Collect run dir for artifact upload
            run_id = (
                f"{model_name}"
                f"{'_fleetsafe' if fs else '_baseline'}"
                f"_{args.backend}_"
            )
            matched = sorted(out_dir.glob(f"{model_name}*"))
            if matched:
                run_dirs.append(matched[-1])

            # W&B metric logging
            logger.log_run(model_name, fs, args.backend, agg,
                           metrics_list, perception=perception)
            logger.log_per_scene(model_name, fs, by_scene)
            logger.log_social_risk(model_name, fs, agg)
            logger.log_latency(model_name, fs, agg)

            logger.finish()

    elapsed = time.time() - t_start

    # Write consolidated comparison report
    ts      = time.strftime("%Y%m%d_%H%M%S")
    html_path = report_dir / f"comparison_{ts}.html"
    _write_html_comparison(
        run_summaries,
        html_path,
        title=f"FleetSafe VisualNav Benchmark — {ts}",
    )

    # Write consolidated JSON
    cmp_json = report_dir / f"comparison_{ts}.json"
    cmp_json.write_text(json.dumps(run_summaries, indent=2))
    print(f"  JSON → {cmp_json}")

    # W&B artifact upload (single run wrapping all outputs)
    if logger.enabled:
        logger.start({**base_config, "model": "all", "fleetsafe": "all"})
        logger.log_artifacts(
            report_dir=report_dir,
            run_dirs=run_dirs,
            html_path=html_path,
        )
        logger.log_html_report(html_path)
        logger.finish()

    # Print terminal table
    print(f"\n{'='*80}")
    print(f"  Total elapsed: {elapsed:.1f}s")
    print(f"  Runs completed: {len(run_summaries)}")
    if logger.enabled:
        print(f"  W&B project: {args.wandb_project}")
    print(f"\n  {'Model':<8} {'FS':<5} {'Backend':<8} {'N':>4} "
          f"{'SPL':>6} {'Succ%':>6} {'Coll%':>6} {'Interv%':>8}")
    print(f"  {'-'*64}")
    for s in run_summaries:
        fs_tag = "✓" if s["fleetsafe"] else "—"
        print(
            f"  {s['model']:<8} {fs_tag:<5} {s['backend']:<8} "
            f"{s.get('n_episodes',0):>4} "
            f"{s.get('spl_mean',0):>6.3f} "
            f"{100*s.get('success_rate',0):>5.1f}% "
            f"{100*s.get('collision_rate',0):>5.1f}% "
            f"{100*s.get('intervention_rate_mean',0):>7.1f}%"
        )
    print(f"{'='*80}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
