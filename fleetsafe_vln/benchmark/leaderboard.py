"""Leaderboard — aggregate suite results into a ranked comparison table."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from fleetsafe_vln.benchmark.metrics import EpisodeResult, leaderboard_row


def aggregate_by_model(results: List[EpisodeResult]) -> Dict[str, dict]:
    """Average metrics across tasks per (model, platform) pair."""
    groups: Dict[str, List[EpisodeResult]] = {}
    for r in results:
        key = f"{r.model}/{r.platform}"
        groups.setdefault(key, []).append(r)

    agg = {}
    for key, group in groups.items():
        n = len(group)
        agg[key] = {
            "model": group[0].model,
            "platform": group[0].platform,
            "n_episodes": n,
            "success_rate": sum(r.success for r in group) / n,
            "spl": sum(r.spl for r in group) / n,
            "navigation_error_m": sum(r.navigation_error_m for r in group) / n,
            "collision_rate": sum(r.collision_rate for r in group) / n,
            "cbf_intervention_rate": sum(r.cbf_intervention_rate for r in group) / n,
            "certificate_validity_rate": sum(r.certificate_validity_rate for r in group) / n,
            "min_human_distance_m": min(
                (r.min_human_distance_m for r in group if r.min_human_distance_m is not None),
                default=None,
            ),
        }
    return agg


def save_leaderboard(results: List[EpisodeResult], path: str | Path) -> None:
    agg = aggregate_by_model(results)
    rows = sorted(agg.values(), key=lambda r: -r["success_rate"])
    Path(path).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Leaderboard saved to {path}")


def print_leaderboard_from_file(path: str | Path) -> None:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not rows:
        print("No results.")
        return

    cols = ["model", "platform", "n_episodes", "success_rate", "spl",
            "navigation_error_m", "collision_rate", "certificate_validity_rate"]
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    print(header)
    print("  ".join("-" * widths[c] for c in cols))
    for row in rows:
        def _fmt(v):
            if isinstance(v, float):
                return f"{v:.3f}"
            return str(v) if v is not None else "—"
        print("  ".join(_fmt(row.get(c, "")).ljust(widths[c]) for c in cols))
