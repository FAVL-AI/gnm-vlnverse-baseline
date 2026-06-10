#!/usr/bin/env python3
"""
m3pro_nav_audit_dashboard.py — Navigation audit dashboard.

Reads all JSON benchmark outputs (Gazebo + benchmark mock + Isaac Sim) from
one or more input directories and produces:

  nav_audit_summary.csv    sortable table (Excel/ICRA-ready)
  nav_audit_summary.json   machine-readable aggregate
  nav_audit_report.md      human-readable comparison with FleetSafe Δ
  nav_audit_table.tex      booktabs LaTeX table for paper

Supports three JSON schemas:
  • m3pro_gazebo_benchmark.py output  (benchmark_summary.json + per-world files)
  • benchmark.py output          (benchmark_results.json))
  • may29_evaluation_full.json        (direct evaluation matrix output)

Usage
-----
  # Single directory:
  python scripts/benchmarks/m3pro_nav_audit_dashboard.py \\
      --input-dir results/gazebo_benchmark

  # Multiple directories (Gazebo + benchmark mock + real checkpoint):
  python scripts/benchmarks/m3pro_nav_audit_dashboard.py \\
      --input-dir results/gazebo_benchmark results/benchmark_smoke \\
      --extra-json results/may29_evaluation_full.json \\
      --output-dir results/audit

  # Full audit including paper results:
  python scripts/benchmarks/m3pro_nav_audit_dashboard.py \\
      --input-dir results/ \\
      --output-dir results/audit_$(date +%Y%m%d) \\
      --latex
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))


# ── Row schema ────────────────────────────────────────────────────────────────

COLUMNS = [
    "sim",           "world",          "model",          "condition",
    "n_episodes",    "success_rate",   "collision_rate", "spl",
    "near_miss_rate","min_dist_obs_m", "min_dist_ppl_m",
    "intervention_rate", "path_deviation_m",
    "inference_ms",  "cbf_ms",
    "success_ci_lo", "success_ci_hi",  "collision_ci_lo","collision_ci_hi",
    "source_file",
]


def _row(**kwargs) -> dict[str, Any]:
    r = {c: None for c in COLUMNS}
    r.update(kwargs)
    return r


# ── JSON schema parsers ───────────────────────────────────────────────────────

def _parse_gazebo_summary(path: Path) -> list[dict]:
    """Parse benchmark_summary.json from m3pro_gazebo_benchmark.py."""
    with open(path) as f:
        data = json.load(f)
    rows = []
    config = data.get("config", {})
    sim = config.get("mode", "mock")
    for key, agg in data.get("results", {}).items():
        world_n, model_n, cond_n = key.split("|")
        rows.append(_row(
            sim             = sim,
            world           = world_n,
            model           = model_n,
            condition       = cond_n,
            n_episodes      = agg.get("n_episodes"),
            success_rate    = agg.get("success_rate"),
            collision_rate  = agg.get("collision_rate"),
            spl             = agg.get("spl"),
            near_miss_rate  = None,
            min_dist_obs_m  = agg.get("mean_min_dist_obs_m"),
            min_dist_ppl_m  = agg.get("mean_min_dist_people_m"),
            intervention_rate = agg.get("intervention_rate"),
            path_deviation_m = agg.get("mean_path_deviation_m"),
            inference_ms    = agg.get("mean_inference_ms"),
            cbf_ms          = agg.get("mean_cbf_ms"),
            success_ci_lo   = (agg["success_rate_ci95"][0]
                               if "success_rate_ci95" in agg else None),
            success_ci_hi   = (agg["success_rate_ci95"][1]
                               if "success_rate_ci95" in agg else None),
            collision_ci_lo = (agg["collision_rate_ci95"][0]
                               if "collision_rate_ci95" in agg else None),
            collision_ci_hi = (agg["collision_rate_ci95"][1]
                               if "collision_rate_ci95" in agg else None),
            source_file     = str(path),
        ))
    return rows


def _parse_benchmark_results(path: Path) -> list[dict]:
    """Parse benchmark_results.json from benchmark.py."""
    with open(path) as f:
        data = json.load(f)
    rows = []
    cfg = data.get("config", {})
    sim = cfg.get("backend", "mock")
    for c in data.get("conditions", []):
        cond = "fleetsafe" if c.get("fleetsafe") else "baseline"
        rows.append(_row(
            sim             = sim,
            world           = "multi-scene",
            model           = c.get("model", ""),
            condition       = cond,
            n_episodes      = c.get("n_episodes"),
            success_rate    = c.get("success_rate"),
            collision_rate  = c.get("collision_rate"),
            spl             = c.get("spl"),
            near_miss_rate  = c.get("near_miss_rate"),
            min_dist_obs_m  = c.get("min_dist_m"),
            min_dist_ppl_m  = None,
            intervention_rate = c.get("intervention_rate"),
            path_deviation_m = None,
            inference_ms    = c.get("inference_latency_p50"),
            cbf_ms          = c.get("cbf_latency_p50"),
            success_ci_lo   = c["success_ci"][0] if "success_ci" in c else None,
            success_ci_hi   = c["success_ci"][1] if "success_ci" in c else None,
            collision_ci_lo = c["collision_ci"][0] if "collision_ci" in c else None,
            collision_ci_hi = c["collision_ci"][1] if "collision_ci" in c else None,
            source_file     = str(path),
        ))
    return rows


def _parse_may29_results(path: Path) -> list[dict]:
    """Parse may29_evaluation_full.json (real-checkpoint evaluation matrix)."""
    with open(path) as f:
        data = json.load(f)
    rows = []
    for r in data.get("results", []):
        cond = "fleetsafe" if r.get("fleetsafe") else "baseline"
        rows.append(_row(
            sim             = "mock+realckpt",
            world           = "hospital+cluttered",
            model           = r.get("model", ""),
            condition       = cond,
            n_episodes      = r.get("n_episodes"),
            success_rate    = r.get("success_rate", 0.0),
            collision_rate  = r.get("collision_rate"),
            spl             = None,
            near_miss_rate  = r.get("near_miss_rate"),
            min_dist_obs_m  = r.get("mean_min_dist_m"),
            min_dist_ppl_m  = None,
            intervention_rate = r.get("intervention_rate"),
            path_deviation_m = None,
            inference_ms    = r.get("mean_inference_ms"),
            cbf_ms          = r.get("mean_cbf_ms"),
            source_file     = str(path),
        ))
    return rows


def _auto_parse(path: Path) -> list[dict]:
    """Detect schema from filename / content."""
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return []

    name = path.name
    if "summary" in name and "results" in data:
        return _parse_gazebo_summary(path)
    if "benchmark_results" in name or ("conditions" in data and "config" in data):
        return _parse_benchmark_results(path)
    if "may29" in name or ("results" in data and isinstance(data.get("results"), list)
                           and data["results"] and "collision_rate" in data["results"][0]):
        return _parse_may29_results(path)
    # Try per-world file from m3pro_gazebo_benchmark.py
    if "aggregate" in data and "episodes" in data:
        world_n = data.get("world", "unknown")
        model_n = data.get("model", "unknown")
        cond_n  = "fleetsafe" if data.get("fleetsafe") else "baseline"
        agg     = data["aggregate"]
        return [_row(
            sim            = data.get("sim_mode", "mock"),
            world          = world_n,
            model          = model_n,
            condition      = cond_n,
            n_episodes     = agg.get("n_episodes"),
            success_rate   = agg.get("success_rate"),
            collision_rate = agg.get("collision_rate"),
            spl            = agg.get("spl"),
            min_dist_obs_m = agg.get("mean_min_dist_obs_m"),
            min_dist_ppl_m = agg.get("mean_min_dist_people_m"),
            intervention_rate = agg.get("intervention_rate"),
            inference_ms   = agg.get("mean_inference_ms"),
            cbf_ms         = agg.get("mean_cbf_ms"),
            source_file    = str(path),
        )]
    return []


# ── FleetSafe Δ computation ────────────────────────────────────────────────────

def _compute_deltas(rows: list[dict]) -> list[dict]:
    """For each (sim, world, model) pair, add Δ fields comparing baseline→fleetsafe."""
    # Index by (sim, world, model) → {condition: row}
    index: dict[tuple, dict] = {}
    for r in rows:
        key = (r["sim"], r["world"], r["model"])
        if key not in index:
            index[key] = {}
        index[key][r["condition"]] = r

    augmented = []
    for r in rows:
        r = dict(r)
        key = (r["sim"], r["world"], r["model"])
        bl = index[key].get("baseline")
        fs = index[key].get("fleetsafe")

        if bl and fs and r["condition"] == "fleetsafe":
            r["delta_collision"]  = _safe_sub(fs["collision_rate"], bl["collision_rate"])
            r["delta_spl"]        = _safe_sub(fs["spl"],            bl["spl"])
            r["delta_min_dist"]   = _safe_sub(fs["min_dist_obs_m"], bl["min_dist_obs_m"])
        else:
            r["delta_collision"]  = None
            r["delta_spl"]        = None
            r["delta_min_dist"]   = None

        augmented.append(r)
    return augmented


def _safe_sub(a, b):
    if a is None or b is None:
        return None
    return round(float(a) - float(b), 4)


# ── Output writers ────────────────────────────────────────────────────────────

def _write_csv(rows: list[dict], path: Path) -> None:
    all_cols = list({k for r in rows for k in r.keys()})
    # Enforce COLUMNS order, then extras
    ordered = [c for c in COLUMNS if c in all_cols]
    ordered += [c for c in all_cols if c not in ordered]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ordered)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) for k in ordered})
    print(f"  CSV → {path}")


def _write_latex(rows: list[dict], path: Path) -> None:
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{M3Pro Hospital Navigation Benchmark across three world types.",
        r"  SR = success rate; Coll = collision rate; SPL = success weighted path length;",
        r"  Dist = mean minimum obstacle surface distance; Interv = FleetSafe intervention rate.",
        r"  Values are mean over N episodes. \dag\ mock simulator; * real GNM/ViNT checkpoint.}",
        r"\label{tab:m3pro_benchmark}",
        r"\resizebox{\columnwidth}{!}{%",
        r"\begin{tabular}{llcccccc}",
        r"\toprule",
        r"\textbf{World} & \textbf{Condition} & \textbf{SR}$\uparrow$ & \textbf{Coll}$\downarrow$"
        r" & \textbf{SPL}$\uparrow$ & \textbf{Dist (m)}$\uparrow$"
        r" & \textbf{Interv\%} & \textbf{N} \\",
        r"\midrule",
    ]

    prev_world = None
    for r in rows:
        world = r.get("world", "—")
        model = (r.get("model") or "").upper()
        cond  = r.get("condition", "baseline")
        is_fs = cond == "fleetsafe"

        if prev_world and world != prev_world:
            lines.append(r"\midrule")
        prev_world = world

        world_str = world.replace("_", r"\_") if world != prev_world else ""
        cond_label = f"\\textbf{{{model} + FleetSafe}}" if is_fs else f"{model} (baseline)"
        sr_str   = f"{r['success_rate']*100:.1f}\\%" if r.get("success_rate") is not None else "—"
        col_str  = f"{r['collision_rate']*100:.1f}\\%" if r.get("collision_rate") is not None else "—"
        if is_fs and r.get("collision_rate") == 0.0:
            col_str = r"\textbf{\textcolor{ProvenGreen}{0.0\%}}"
        spl_str  = f"{r['spl']:.3f}" if r.get("spl") is not None else "—"
        dist_str = f"{r['min_dist_obs_m']:.3f}" if r.get("min_dist_obs_m") is not None else "—"
        interv   = f"{r['intervention_rate']*100:.1f}\\%" if is_fs and r.get("intervention_rate") else "—"
        n_str    = str(r.get("n_episodes") or "—")

        lines.append(
            f"{world_str} & {cond_label} & {sr_str} & {col_str} & {spl_str}"
            f" & {dist_str} & {interv} & {n_str} \\\\"
        )

    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"}",
        r"\end{table}",
    ]
    path.write_text("\n".join(lines) + "\n")
    print(f"  LaTeX → {path}")


def _write_report(rows: list[dict], path: Path) -> None:
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# M3Pro Navigation Audit Dashboard",
        f"Generated: {ts}",
        f"Total rows: {len(rows)}",
        "",
        "## Summary Table",
        "",
        "| Sim | World | Model | Cond | SR | Coll | SPL | MinDist | Interv% | N |",
        "|-----|-------|-------|------|----|------|-----|---------|---------|---|",
    ]
    for r in rows:
        sr    = f"{r['success_rate']*100:.0f}%" if r.get("success_rate") is not None else "—"
        col   = f"{r['collision_rate']*100:.0f}%" if r.get("collision_rate") is not None else "—"
        spl   = f"{r['spl']:.3f}" if r.get("spl") is not None else "—"
        dist  = f"{r['min_dist_obs_m']:.3f}" if r.get("min_dist_obs_m") is not None else "—"
        interv = f"{r['intervention_rate']*100:.0f}%" if r.get("intervention_rate") and r.get("condition") == "fleetsafe" else "—"
        lines.append(
            f"| {r.get('sim','?')} | {r.get('world','?')} | {r.get('model','?').upper()} "
            f"| {r.get('condition','?')} | {sr} | {col} | {spl} | {dist} | {interv}"
            f" | {r.get('n_episodes','?')} |"
        )

    # FleetSafe effect summary
    lines += ["", "## FleetSafe Safety Effect", ""]
    seen = set()
    for r in rows:
        if r.get("condition") != "fleetsafe" or r.get("delta_collision") is None:
            continue
        key = (r.get("sim"), r.get("world"), r.get("model"))
        if key in seen:
            continue
        seen.add(key)
        dc  = r["delta_collision"]
        dd  = r.get("delta_min_dist")
        ds  = r.get("delta_spl")
        arrow = "↓" if dc and dc < 0 else "↑"
        lines.append(
            f"- **{r.get('model','').upper()}** ({r.get('world','?')}, {r.get('sim','?')}): "
            f"collision {arrow} {dc*100:+.1f}%  "
            + (f"min_dist {dd:+.3f}m  " if dd is not None else "")
            + (f"SPL {ds:+.3f}" if ds is not None else "")
        )

    lines += [
        "",
        "## Data Sources",
        "",
    ]
    sources = sorted({r.get("source_file", "") for r in rows})
    for s in sources:
        lines.append(f"- `{s}`")

    path.write_text("\n".join(lines) + "\n")
    print(f"  Report → {path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--input-dir",  nargs="+", type=Path, default=[Path("results")])
    ap.add_argument("--extra-json", nargs="+", type=Path, default=[])
    ap.add_argument("--output-dir", type=Path, default=Path("results/audit"))
    ap.add_argument("--latex",      action="store_true", help="Write LaTeX table")
    ap.add_argument("--model",      default=None, help="Filter to one model")
    ap.add_argument("--world",      default=None, help="Filter to one world")
    args = ap.parse_args()

    print()
    print("=" * 60)
    print("  M3Pro Navigation Audit Dashboard")
    print("=" * 60)

    # Collect all JSON files
    json_paths: list[Path] = list(args.extra_json)
    for d in args.input_dir:
        if d.is_dir():
            json_paths.extend(sorted(d.rglob("*.json")))
        elif d.is_file():
            json_paths.append(d)

    print(f"  Scanning {len(json_paths)} JSON files …")

    all_rows: list[dict] = []
    parsed_files = 0
    for p in json_paths:
        rows = _auto_parse(p)
        if rows:
            all_rows.extend(rows)
            parsed_files += 1

    print(f"  Parsed {parsed_files} files  →  {len(all_rows)} condition rows")

    if not all_rows:
        print("  No benchmark data found. Run a benchmark first:")
        print("    python scripts/benchmarks/benchmark.py  # or: make benchmark")
        print("    python scripts/benchmarks/m3pro_gazebo_benchmark.py")
        return 1

    # Filter
    if args.model:
        all_rows = [r for r in all_rows if r.get("model", "").lower() == args.model.lower()]
    if args.world:
        all_rows = [r for r in all_rows if args.world in (r.get("world") or "")]

    # Compute FleetSafe Δ
    all_rows = _compute_deltas(all_rows)

    # Sort: sim → world → model → condition
    all_rows.sort(key=lambda r: (
        r.get("sim") or "", r.get("world") or "", r.get("model") or "",
        0 if r.get("condition") == "baseline" else 1,
    ))

    args.output_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(all_rows, args.output_dir / "nav_audit_summary.csv")

    summary_json = {
        "generated": datetime.now(tz=timezone.utc).isoformat(),
        "n_rows":    len(all_rows),
        "rows":      all_rows,
    }
    (args.output_dir / "nav_audit_summary.json").write_text(json.dumps(summary_json, indent=2))
    print(f"  JSON → {args.output_dir / 'nav_audit_summary.json'}")

    _write_report(all_rows, args.output_dir / "nav_audit_report.md")

    if args.latex:
        _write_latex(all_rows, args.output_dir / "nav_audit_table.tex")

    # Terminal summary
    print()
    print("  Key findings (FleetSafe Δ):")
    seen = set()
    for r in all_rows:
        if r.get("condition") != "fleetsafe" or r.get("delta_collision") is None:
            continue
        key = (r.get("sim"), r.get("world"), r.get("model"))
        if key in seen:
            continue
        seen.add(key)
        dc = r["delta_collision"]
        dd = r.get("delta_min_dist")
        print(
            f"    {r.get('model','').upper():5s}  {r.get('world',''):18s}  "
            f"collision {dc*100:+.0f}%  "
            + (f"min_dist {dd:+.3f}m" if dd is not None else "")
        )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
