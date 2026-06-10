"""
wandb_logger.py — Optional Weights & Biases experiment tracking for FleetSafe.

Designed to be a zero-cost dependency: if wandb is not installed, every public
method is a no-op.  Only raises ImportError when wandb=True is explicitly
requested by the caller.

Typical usage in the benchmark runner script::

    logger = WandbLogger.from_args(args)           # args.wandb / args.wandb_project
    logger.start(run_config)                       # wandb.init()
    for model, fs, metrics_list in runs:
        agg = aggregate_episodes(metrics_list)
        logger.log_run(model, fs, backend, agg, metrics_list)
    logger.log_artifacts(report_dir, run_dir)
    logger.finish()

All public methods are safe to call even when W&B is disabled — they return
None and do nothing, so caller code requires no conditionals.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

# ── W&B availability ──────────────────────────────────────────────────────────

def _check_wandb(required: bool = False) -> bool:
    """Return True if wandb is importable; raise if required and missing."""
    try:
        import wandb  # noqa: F401
        return True
    except ImportError:
        if required:
            raise ImportError(
                "wandb not installed — run: pip install wandb\n"
                "Then: wandb login"
            )
        return False


# ── Metric key sets ───────────────────────────────────────────────────────────

# Run-level aggregate keys logged to wandb.summary / wandb.log
_AGG_METRICS = [
    "n_episodes",
    "success_rate",
    "spl_mean",
    "collision_rate",
    "intervention_rate_mean",
    "near_violation_rate",
    "stuck_rate_mean",
    "smoothness_mean",
    "inference_latency_ms_mean",
    "inference_latency_ms_p95",
    "sim_fps_mean",
    # Social-risk layer
    "crowding_risk_score_mean",
    "occlusion_risk_score_mean",
    "social_margin_violation_rate",
    "rare_event_rate",
    "min_human_distance_m_mean",
    "steps_green_frac",
    "steps_amber_frac",
    "steps_red_frac",
    # Perception
    "perception_latency_ms_mean",
    "depth_fusion_latency_ms_mean",
    "tracked_agent_count_max_mean",
    "detection_count_mean",
]

# Per-episode keys streamed as a time series
_EP_METRICS = [
    "success",
    "spl",
    "path_length_m",
    "time_to_goal_s",
    "collision_count",
    "near_violation_count",
    "intervention_count",
    "intervention_rate",
    "inference_latency_ms_mean",
    "crowding_risk_score_mean",
    "occlusion_risk_score_mean",
    "steps_green",
    "steps_amber",
    "steps_red",
    "perception_latency_ms_mean",
    "tracked_agent_count_max",
    "detection_count_total",
]


# ════════════════════════════════════════════════════════════════════════════════
# Logger
# ════════════════════════════════════════════════════════════════════════════════

class WandbLogger:
    """
    Optional W&B integration for the FleetSafe benchmark.

    Parameters
    ----------
    enabled  : If False, all methods are no-ops.
    project  : W&B project name.
    entity   : W&B entity (username or team). None = default from login.
    mode     : "online" | "offline" | "disabled".
    tags     : list of string tags added to every run.
    """

    def __init__(
        self,
        enabled:  bool = False,
        project:  str  = "fleetsafe-hospitalnav",
        entity:   str | None = None,
        mode:     str  = "online",
        tags:     list[str] | None = None,
    ) -> None:
        self._enabled = enabled and _check_wandb(required=enabled)
        self._project = project
        self._entity  = entity
        self._mode    = mode
        self._tags    = tags or []
        self._run: Any = None   # wandb.Run

    @classmethod
    def from_args(cls, args: Any) -> "WandbLogger":
        """
        Construct from an argparse.Namespace with W&B flags.

        Expected attributes (all optional with safe defaults):
            args.wandb          : bool
            args.wandb_project  : str
            args.wandb_entity   : str | None
            args.wandb_mode     : str
        """
        enabled = getattr(args, "wandb", False)
        return cls(
            enabled = enabled,
            project = getattr(args, "wandb_project", "fleetsafe-hospitalnav"),
            entity  = getattr(args, "wandb_entity",  None),
            mode    = getattr(args, "wandb_mode",    "online"),
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self, run_config: dict[str, Any]) -> None:
        """
        Initialise a W&B run with the benchmark configuration.

        Parameters
        ----------
        run_config : dict passed as wandb.config.  Should include at minimum:
            git_commit, benchmark_version, backend, model, fleetsafe,
            perception, seeds, scenes, claim_scope.
        """
        if not self._enabled:
            return
        import wandb
        self._run = wandb.init(
            project = self._project,
            entity  = self._entity,
            mode    = self._mode,
            config  = run_config,
            tags    = self._tags + [
                run_config.get("backend", ""),
                run_config.get("model", ""),
                "fleetsafe" if run_config.get("fleetsafe") else "baseline",
            ],
            reinit  = True,
        )

    def finish(self) -> None:
        """Finish the current W&B run."""
        if not self._enabled or self._run is None:
            return
        import wandb
        wandb.finish()
        self._run = None

    # ── Metric logging ────────────────────────────────────────────────────────

    def log_run(
        self,
        model:        str,
        fleetsafe:    bool,
        backend:      str,
        agg:          dict[str, Any],
        metrics_list: list[Any],
        perception:   str = "none",
    ) -> None:
        """
        Log aggregate + per-episode metrics for one (model, fleetsafe) combination.

        Parameters
        ----------
        agg          : output of aggregate_episodes(metrics_list)
        metrics_list : list of EpisodeMetrics dataclasses
        """
        if not self._enabled:
            return
        import wandb

        prefix = f"{model}/{'fs' if fleetsafe else 'base'}"

        # Aggregate summary
        agg_payload: dict[str, Any] = {
            f"{prefix}/{k}": agg[k]
            for k in _AGG_METRICS
            if k in agg
        }
        agg_payload[f"{prefix}/model"]     = model
        agg_payload[f"{prefix}/fleetsafe"] = fleetsafe
        agg_payload[f"{prefix}/backend"]   = backend
        agg_payload[f"{prefix}/perception"] = perception
        wandb.log(agg_payload)

        # Per-episode stream
        for ep in metrics_list:
            ep_dict = asdict(ep) if hasattr(ep, "__dataclass_fields__") else vars(ep)
            ep_payload: dict[str, Any] = {
                f"episode/{prefix}/{k}": ep_dict[k]
                for k in _EP_METRICS
                if k in ep_dict
            }
            ep_payload["episode/scene"]     = ep_dict.get("scene", "")
            ep_payload["episode/seed"]      = ep_dict.get("seed", 0)
            ep_payload["episode/model"]     = model
            ep_payload["episode/fleetsafe"] = fleetsafe
            wandb.log(ep_payload)

    def log_per_scene(
        self,
        model:     str,
        fleetsafe: bool,
        by_scene:  dict[str, dict[str, Any]],
    ) -> None:
        """
        Log per-scene aggregate metrics as a W&B Table.

        Parameters
        ----------
        by_scene : output of aggregate_by_scene(metrics_list) —
                   dict[scene_name → aggregate_dict]
        """
        if not self._enabled:
            return
        import wandb

        columns = ["scene", "model", "fleetsafe"] + _AGG_METRICS
        rows: list[list[Any]] = []
        for scene_name, agg in by_scene.items():
            row = [scene_name, model, fleetsafe]
            for k in _AGG_METRICS:
                row.append(agg.get(k, None))
            rows.append(row)

        table = wandb.Table(columns=columns, data=rows)
        prefix = f"{model}/{'fs' if fleetsafe else 'base'}"
        wandb.log({f"{prefix}/per_scene_table": table})

    def log_social_risk(
        self,
        model:     str,
        fleetsafe: bool,
        agg:       dict[str, Any],
    ) -> None:
        """Log social-risk specific metrics as a dedicated W&B section."""
        if not self._enabled:
            return
        import wandb

        prefix = f"social/{model}/{'fs' if fleetsafe else 'base'}"
        social_keys = [
            "crowding_risk_score_mean", "crowding_risk_score_max",
            "occlusion_risk_score_mean", "occlusion_risk_score_max",
            "social_margin_violation_rate", "rare_event_rate",
            "min_human_distance_m_mean",
            "steps_green_frac", "steps_amber_frac", "steps_red_frac",
        ]
        payload = {f"{prefix}/{k}": agg[k] for k in social_keys if k in agg}
        if payload:
            wandb.log(payload)

    def log_latency(
        self,
        model:     str,
        fleetsafe: bool,
        agg:       dict[str, Any],
    ) -> None:
        """Log latency + throughput metrics as a dedicated W&B section."""
        if not self._enabled:
            return
        import wandb

        prefix = f"latency/{model}/{'fs' if fleetsafe else 'base'}"
        latency_keys = [
            "inference_latency_ms_mean", "inference_latency_ms_p95",
            "sim_fps_mean",
            "perception_latency_ms_mean", "perception_latency_ms_p95",
            "depth_fusion_latency_ms_mean",
        ]
        payload = {f"{prefix}/{k}": agg[k] for k in latency_keys if k in agg}
        if payload:
            wandb.log(payload)

    # ── Artifact logging ──────────────────────────────────────────────────────

    def log_artifacts(
        self,
        report_dir:    Path | None = None,
        run_dirs:      list[Path] | None = None,
        html_path:     Path | None = None,
    ) -> None:
        """
        Log benchmark output files as W&B Artifacts for lineage tracking.

        Parameters
        ----------
        report_dir  : directory containing comparison_*.json and comparison_*.html
        run_dirs    : list of per-run output directories (aggregate_metrics.json etc.)
        html_path   : explicit path to the HTML dashboard/report
        """
        if not self._enabled:
            return
        import wandb

        artifact = wandb.Artifact(
            name=f"fleetsafe-results-{wandb.run.id}",
            type="benchmark-results",
            description="FleetSafe VisualNav benchmark outputs",
        )

        # Comparison report
        if report_dir and report_dir.exists():
            for p in sorted(report_dir.glob("comparison_*.json"))[-3:]:
                artifact.add_file(str(p), name=f"reports/{p.name}")
            for p in sorted(report_dir.glob("comparison_*.html"))[-3:]:
                artifact.add_file(str(p), name=f"reports/{p.name}")

        # Per-run dirs
        for run_dir in (run_dirs or []):
            if not run_dir.exists():
                continue
            run_name = run_dir.name
            for fname in [
                "aggregate_metrics.json",
                "aggregate_metrics.csv",
                "aggregate_by_scene.json",
                "metadata.yaml",
            ]:
                p = run_dir / fname
                if p.exists():
                    artifact.add_file(str(p), name=f"runs/{run_name}/{fname}")

            # Episode files (up to 20 per run)
            ep_dir = run_dir / "episodes"
            if ep_dir.exists():
                for ep_path in sorted(ep_dir.rglob("episode.json"))[:20]:
                    rel = ep_path.relative_to(run_dir)
                    artifact.add_file(str(ep_path), name=f"runs/{run_name}/{rel}")

        # Standalone HTML dashboard
        if html_path and html_path.exists():
            artifact.add_file(str(html_path), name="dashboard.html")

        wandb.log_artifact(artifact)

    def log_html_report(self, html_path: Path) -> None:
        """Log an HTML file as a W&B rich media panel (visible in the W&B UI)."""
        if not self._enabled or not html_path.exists():
            return
        import wandb
        wandb.log({"benchmark_report": wandb.Html(str(html_path))})

    # ── Summary update ─────────────────────────────────────────────────────────

    def set_summary(self, key: str, value: Any) -> None:
        """Set a W&B run summary key (appears in the run table)."""
        if not self._enabled or self._run is None:
            return
        import wandb
        wandb.run.summary[key] = value  # type: ignore[index]


# ── Argparse helpers ──────────────────────────────────────────────────────────

def add_wandb_args(parser: Any) -> None:
    """
    Add standard W&B flags to an argparse.ArgumentParser.

    Call this from any benchmark CLI script::

        from fleet_safe_vla.benchmarks.wandb_logger import add_wandb_args
        add_wandb_args(parser)
    """
    g = parser.add_argument_group("Weights & Biases")
    g.add_argument(
        "--wandb", action="store_true", default=False,
        help="Enable Weights & Biases logging (requires: pip install wandb && wandb login)",
    )
    g.add_argument(
        "--wandb-project", dest="wandb_project", default="fleetsafe-hospitalnav",
        metavar="PROJECT",
        help="W&B project name  (default: fleetsafe-hospitalnav)",
    )
    g.add_argument(
        "--wandb-entity", dest="wandb_entity", default=None,
        metavar="ENTITY",
        help="W&B entity (username or team).  Defaults to your logged-in account.",
    )
    g.add_argument(
        "--wandb-mode", dest="wandb_mode", default="online",
        choices=["online", "offline", "disabled"],
        help="W&B sync mode  (default: online)",
    )
