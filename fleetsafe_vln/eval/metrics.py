"""Evaluation metrics and comparison table for the GNM evaluation matrix.

Re-exports EpisodeResult from fleetsafe_vln.benchmark.metrics and adds:
  EvaluationMatrix   — aggregate results across configs and tasks
  format_comparison_table() — ASCII table comparing configs (Manual section 8)
  load_results_from_dir()   — load all metrics.json files from a run directory

Evaluation matrix columns (Manual section 8)
---------------------------------------------
  config         system label (e.g. gnm_cbf_qp)
  task           task ID
  SR             success rate (✓/✗ for single run)
  SPL            success weighted by path length
  Nav Err (m)    final distance to goal
  Collisions     simulator collision count
  CBF            CBF intervention count
  Cert           certificate validity rate
  Min Obs (m)    closest obstacle distance
  Latency (ms)   mean inference latency
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Re-export everything from benchmark.metrics
from fleetsafe_vln.benchmark.metrics import (  # noqa: F401
    EpisodeResult,
    compute_certificate_validity_rate,
    leaderboard_row,
    print_leaderboard,
)


# ── EvaluationMatrix ──────────────────────────────────────────────────────────

@dataclass
class EvaluationMatrix:
    """Aggregate results across multiple configs and tasks.

    Stores one or more EpisodeResult per (config, task) combination and
    computes aggregate statistics.
    """

    results: List[EpisodeResult] = field(default_factory=list)

    def add(self, result: EpisodeResult) -> None:
        self.results.append(result)

    def add_all(self, results: List[EpisodeResult]) -> None:
        self.results.extend(results)

    def configs(self) -> List[str]:
        seen = []
        for r in self.results:
            key = f"{r.model}_{r.safety}"
            if key not in seen:
                seen.append(key)
        return seen

    def tasks(self) -> List[str]:
        seen = []
        for r in self.results:
            if r.task_id not in seen:
                seen.append(r.task_id)
        return seen

    def aggregate(self, config: str, task: Optional[str] = None) -> Dict:
        """Compute mean statistics for one config (and optionally one task)."""
        subset = [
            r for r in self.results
            if f"{r.model}_{r.safety}" == config
            and (task is None or r.task_id == task)
        ]
        if not subset:
            return {}

        n = len(subset)
        return {
            "config": config,
            "task": task or "all",
            "n": n,
            "success_rate": sum(r.success for r in subset) / n,
            "spl_mean": sum(r.spl for r in subset) / n,
            "nav_error_m_mean": sum(r.navigation_error_m for r in subset) / n,
            "collision_rate_mean": sum(r.collision_rate for r in subset) / n,
            "cbf_intervention_count_mean": (
                sum(r.cbf_intervention_count for r in subset) / n
            ),
            "certificate_validity_rate_mean": (
                sum(r.certificate_validity_rate for r in subset) / n
            ),
            "min_obstacle_m_mean": sum(
                r.min_obstacle_distance_m for r in subset
                if not math.isinf(r.min_obstacle_distance_m)
            ) / max(1, sum(1 for r in subset if not math.isinf(r.min_obstacle_distance_m))),
            "inference_latency_ms_mean": (
                sum(r.inference_latency_ms_mean for r in subset) / n
            ),
        }

    def to_rows(self) -> List[Dict[str, str]]:
        """Return one row per (config, task) for table formatting."""
        rows = []
        for r in self.results:
            config = f"{r.model}_{r.safety}"
            obs_m = (
                f"{r.min_obstacle_distance_m:.2f}"
                if not math.isinf(r.min_obstacle_distance_m) else "—"
            )
            rows.append({
                "config":    config,
                "task":      r.task_id,
                "SR":        "✓" if r.success else "✗",
                "SPL":       f"{r.spl:.3f}",
                "Nav Err":   f"{r.navigation_error_m:.2f}m",
                "Collisions":str(r.collision_count),
                "CBF":       str(r.cbf_intervention_count),
                "Cert":      f"{r.certificate_validity_rate:.3f}",
                "Min Obs":   obs_m,
                "Lat ms":    f"{r.inference_latency_ms_mean:.1f}",
            })
        return rows


# ── Comparison table ──────────────────────────────────────────────────────────

def format_comparison_table(matrix: EvaluationMatrix) -> str:
    """Return a formatted ASCII comparison table (Manual section 8)."""
    rows = matrix.to_rows()
    if not rows:
        return "No results."

    cols = list(rows[0].keys())
    widths = {
        c: max(len(c), max(len(r[c]) for r in rows))
        for c in cols
    }
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    sep    = "  ".join("-" * widths[c] for c in cols)
    lines  = [header, sep]
    for row in rows:
        lines.append("  ".join(row[c].ljust(widths[c]) for c in cols))

    return "\n".join(lines)


# ── Load results from eval_gnm.sh output ─────────────────────────────────────

def load_results_from_dir(log_dir: str | Path) -> EvaluationMatrix:
    """Load all metrics.json files under a run directory into an EvaluationMatrix.

    Expects the directory layout produced by scripts/gnm/eval_gnm.sh:
        <log_dir>/<config_name>/<task_id>/metrics.json

    Parameters
    ----------
    log_dir : root directory of an eval_gnm.sh run

    Returns
    -------
    EvaluationMatrix populated with one EpisodeResult per metrics.json found.
    """
    matrix = EvaluationMatrix()
    log_dir = Path(log_dir)

    for metrics_path in sorted(log_dir.rglob("metrics.json")):
        try:
            d = json.loads(metrics_path.read_text(encoding="utf-8"))
            r = EpisodeResult(
                task_id=d.get("task_id", metrics_path.parent.name),
                scene=d.get("scene", ""),
                platform=d.get("platform", ""),
                model=d.get("model", ""),
                safety=d.get("safety", ""),
                seed=d.get("seed", 0),
                run_id=d.get("run_id", ""),
                log_dir=str(metrics_path.parent),
                success=bool(d.get("success", False)),
                navigation_error_m=float(d.get("navigation_error_m", 0.0)),
                path_length_m=float(d.get("path_length_m", 0.0)),
                optimal_path_m=float(d.get("optimal_path_m", 0.0)),
                spl=float(d.get("spl", 0.0)),
                episode_steps=int(d.get("episode_steps", 0)),
                time_s=float(d.get("time_s", 0.0)),
                collision_count=int(d.get("collision_count", 0)),
                collision_rate=float(d.get("collision_rate", 0.0)),
                min_obstacle_distance_m=float(
                    d.get("min_obstacle_distance_m") or math.inf
                ),
                min_human_distance_m=float(
                    d.get("min_human_distance_m") or math.inf
                ),
                near_miss_count=int(d.get("near_miss_count", 0)),
                cbf_intervention_count=int(d.get("cbf_intervention_count", 0)),
                cbf_intervention_rate=float(d.get("cbf_intervention_rate", 0.0)),
                cbf_intervention_magnitude_mean=float(
                    d.get("cbf_intervention_magnitude_mean", 0.0)
                ),
                unsafe_nominal_action_count=int(
                    d.get("unsafe_nominal_action_count", 0)
                ),
                unsafe_nominal_action_rate=float(
                    d.get("unsafe_nominal_action_rate", 0.0)
                ),
                certificate_validity_rate=float(
                    d.get("certificate_validity_rate", 0.0)
                ),
                invalid_certificate_count=int(
                    d.get("invalid_certificate_count", 0)
                ),
                social_margin_violation_count=int(
                    d.get("social_margin_violation_count", 0)
                ),
                inference_latency_ms_mean=float(
                    d.get("inference_latency_ms_mean", 0.0)
                ),
            )
            matrix.add(r)
        except Exception as exc:
            print(f"[eval.metrics] Skipping {metrics_path}: {exc}")

    return matrix


# ── CLI: print a table from an existing run directory ─────────────────────────

if __name__ == "__main__":
    import argparse, sys

    p = argparse.ArgumentParser(
        description="Print comparison table from eval_gnm.sh run directory"
    )
    p.add_argument("log_dir", help="Path to eval_gnm.sh output directory")
    args = p.parse_args()

    m = load_results_from_dir(args.log_dir)
    if not m.results:
        print("No results found.")
        sys.exit(1)

    print(format_comparison_table(m))
    print(f"\n{len(m.results)} episodes loaded from {args.log_dir}")
