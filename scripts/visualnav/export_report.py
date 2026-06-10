#!/usr/bin/env python3
"""
export_report.py — Export FleetSafe VisualNav benchmark results to HTML and CSV.

Reads one or more JSON result files (or a directory of them) and produces:
  - A comparative HTML report with metric tables and basic charts.
  - A flat CSV suitable for further analysis in pandas / spreadsheets.

Handles both single-run files and multi-run comparison across models and modes.

Usage
-----
    python scripts/visualnav/export_report.py \
        --input  benchmarks/visualnav/results/gnm_baseline_20260514.json \
        --output-dir benchmarks/visualnav/reports/

    # Compare all JSON files in a directory
    python scripts/visualnav/export_report.py \
        --input  benchmarks/visualnav/results/ \
        --output-dir benchmarks/visualnav/reports/

Exit codes: 0 success, 1 error.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


# ── JSON loading ───────────────────────────────────────────────────────────────

def _load_results(input_path: Path) -> list[dict]:
    """Load one JSON file or all JSON files in a directory."""
    if input_path.is_dir():
        files = sorted(input_path.glob("*.json"))
        if not files:
            print(f"[ERROR] No JSON files found in {input_path}")
            sys.exit(1)
        return [json.loads(f.read_text()) for f in files]
    elif input_path.suffix == ".json":
        return [json.loads(input_path.read_text())]
    else:
        print(f"[ERROR] Expected .json file or directory, got: {input_path}")
        sys.exit(1)


# ── CSV export ────────────────────────────────────────────────────────────────

def _export_csv(results: list[dict], out_path: Path) -> None:
    """Flatten aggregate metrics from all result files to CSV."""
    rows: list[dict[str, Any]] = []
    for run in results:
        agg = run.get("aggregate", {})
        row = {
            "model":               run.get("model", "?"),
            "fleetsafe":           run.get("fleetsafe", False),
            "timestamp":           run.get("timestamp", 0),
            "n_episodes":          agg.get("n_episodes", 0),
            "success_rate":        agg.get("success_rate", None),
            "collision_rate":      agg.get("collision_rate", None),
            "mean_path_length_m":  agg.get("mean_path_length_m", None),
            "mean_smoothness":     agg.get("mean_smoothness", None),
            "mean_stuck_count":    agg.get("mean_stuck_count", None),
            "mean_near_violation_count": agg.get("mean_near_violation_count", None),
            "mean_min_obs_dist_m": agg.get("mean_min_obstacle_dist_m", None),
            "mean_intervention_count": agg.get("mean_intervention_count", None),
            "mean_latency_ms":     agg.get("mean_latency_ms", None),
            "mean_fps":            agg.get("mean_fps", None),
        }
        rows.append(row)

    if not rows:
        return

    fieldnames = list(rows[0].keys())
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  CSV  → {out_path}")


# ── HTML export ───────────────────────────────────────────────────────────────

def _fmt(v: Any, digits: int = 3) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def _build_metric_rows(results: list[dict]) -> list[dict]:
    rows = []
    for run in results:
        agg = run.get("aggregate", {})
        rows.append({
            "Model":     run.get("model", "?").upper(),
            "FleetSafe": "✓" if run.get("fleetsafe") else "—",
            "Episodes":  agg.get("n_episodes", 0),
            "Success %": _fmt(100 * agg.get("success_rate", 0), 1),
            "Collision %": _fmt(100 * agg.get("collision_rate", 0), 1),
            "Path (m)":  _fmt(agg.get("mean_path_length_m"), 2),
            "Smoothness": _fmt(agg.get("mean_smoothness"), 4),
            "Stuck":     _fmt(agg.get("mean_stuck_count"), 1),
            "NearMiss":  _fmt(agg.get("mean_near_violation_count"), 1),
            "MinDist (m)": _fmt(agg.get("mean_min_obstacle_dist_m"), 3),
            "Interv.":   _fmt(agg.get("mean_intervention_count"), 1),
            "Latency (ms)": _fmt(agg.get("mean_latency_ms"), 1),
            "FPS":       _fmt(agg.get("mean_fps"), 1),
        })
    return rows


def _export_html(results: list[dict], out_path: Path, title: str) -> None:
    rows = _build_metric_rows(results)
    if not rows:
        return

    headers = list(rows[0].keys())

    def _row_html(r: dict) -> str:
        cells = "".join(f"<td>{r[h]}</td>" for h in headers)
        fleetsafe_class = " class='fleetsafe'" if r["FleetSafe"] == "✓" else ""
        return f"<tr{fleetsafe_class}>{cells}</tr>"

    thead = "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
    tbody = "\n".join(_row_html(r) for r in rows)

    # Per-episode detail tables
    detail_html = ""
    for run in results:
        model_tag  = run.get("model", "?").upper()
        fs_tag     = "FleetSafe" if run.get("fleetsafe") else "Baseline"
        episodes   = run.get("episodes", [])[:20]   # show up to 20

        ep_headers = [
            "Scene", "Seed", "Success", "Collision",
            "Path (m)", "Interv.", "NearMiss", "Latency (ms)",
        ]
        ep_rows = []
        for ep in episodes:
            ep_rows.append([
                ep.get("scene", "?"),
                ep.get("seed", 0),
                "✓" if ep.get("success") else "✗",
                "✓" if ep.get("collision") else "—",
                _fmt(ep.get("path_length_m"), 2),
                ep.get("intervention_count", 0),
                ep.get("near_violation_count", 0),
                _fmt(ep.get("mean_latency_ms"), 1),
            ])

        ep_thead = "<tr>" + "".join(f"<th>{h}</th>" for h in ep_headers) + "</tr>"
        ep_tbody = "\n".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
            for row in ep_rows
        )
        detail_html += f"""
        <h3>{model_tag} — {fs_tag}</h3>
        <table>
          <thead>{ep_thead}</thead>
          <tbody>{ep_tbody}</tbody>
        </table>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{title}</title>
<style>
  body {{ font-family: monospace; background: #1a1a2e; color: #eee; padding: 20px; }}
  h1   {{ color: #00d4ff; }}
  h2   {{ color: #6bcfff; margin-top: 30px; }}
  h3   {{ color: #aaa; margin-top: 20px; }}
  table {{ border-collapse: collapse; margin: 10px 0; width: 100%; }}
  th   {{ background: #0f3460; color: #00d4ff; padding: 6px 10px; text-align: left; }}
  td   {{ padding: 5px 10px; border-bottom: 1px solid #0f3460; }}
  tr.fleetsafe td {{ background: rgba(0, 212, 255, 0.06); }}
  .warn  {{ color: #ff6b6b; }}
  .ok    {{ color: #06d6a0; }}
  .note  {{ color: #888; font-size: 0.9em; margin: 10px 0; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="note">
  Generated by FleetSafe benchmark pipeline.
  Upstream models: GNM / ViNT / NoMaD (robodhruv/visualnav-transformer).
  FleetSafe safety layer: CBF-QP (YahboomCBFFilter).
  Do not report final numbers until baseline reproduction and FleetSafe comparison both complete.
</p>

<h2>Aggregate Metrics — All Runs</h2>
<table>
  <thead>{thead}</thead>
  <tbody>{tbody}</tbody>
</table>

<p class="note">
  FleetSafe rows (✓) used the same seeds as their baseline counterparts.
  Differences in success rate and collision rate are caused only by the safety layer.
  "Interv." = mean CBF interventions per episode.
  "NearMiss" = mean steps within {0.45} m of an obstacle.
</p>

<h2>Per-Episode Detail (first 20 episodes per run)</h2>
{detail_html}

<h2>Metric Definitions</h2>
<ul>
  <li><b>Success %</b>: fraction of episodes reaching the goal within MAX_STEPS.</li>
  <li><b>Collision %</b>: fraction of episodes ending in collision.</li>
  <li><b>Path (m)</b>: total distance travelled per episode.</li>
  <li><b>Smoothness</b>: mean |Δcmd_vel| per step (lower = smoother).</li>
  <li><b>Stuck</b>: mean count of stuck streaks per episode.</li>
  <li><b>NearMiss</b>: mean steps within near_miss_dist_m of an obstacle.</li>
  <li><b>MinDist (m)</b>: mean minimum obstacle distance over the episode.</li>
  <li><b>Interv.</b>: mean CBF-QP interventions per episode (FleetSafe only).</li>
  <li><b>Latency (ms)</b>: mean wall-clock time per inference+safety step.</li>
  <li><b>FPS</b>: effective control frequency (1000 / mean_latency_ms).</li>
</ul>
</body>
</html>"""

    out_path.write_text(html)
    print(f"  HTML → {out_path}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",      required=True, help="JSON file or directory")
    p.add_argument("--output-dir", required=True, help="Output directory")
    p.add_argument("--title", default="FleetSafe VisualNav Benchmark Report")
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = _load_results(Path(args.input))
    print(f"[export_report] Loaded {len(results)} result file(s)")

    _export_csv(results, out_dir / "benchmark_results.csv")
    _export_html(results, out_dir / "benchmark_report.html", title=args.title)

    print(f"\n  Done.  Reports in: {out_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
