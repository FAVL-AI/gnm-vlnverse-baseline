#!/usr/bin/env python3
"""
Verify Track A metric provenance from per-episode rows.

This script is intentionally strict. It does not trust aggregate tables alone.
It requires per-episode rows with final distance, minimum distance, and success
radius, then regenerates SR, OSR, and NE from those rows.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {
    "episode_id",
    "scene_id",
    "method",
    "final_distance_to_goal",
    "minimum_distance_to_goal",
    "success_radius",
}


EXPECTED = {
    "baseline_gnm": {"sr": 20.0, "osr": 46.7, "ne": 6.51, "episodes": 15},
    "hand_tuned_waypoint_gate": {"sr": 26.7, "osr": 26.7, "ne": 5.34, "episodes": 15},
    "logistic_stop_head": {"sr": 20.0, "osr": 46.7, "ne": 6.51, "episodes": 15},
    "temporal_neural_stop_head": {"sr": 33.3, "osr": 33.3, "ne": 4.47, "episodes": 15},
    "geometry_aware_oracle": {"sr": 46.7, "osr": 46.7, "ne": 3.79, "episodes": 15},
}


def close(a: float, b: float, tol: float = 0.06) -> bool:
    return abs(a - b) <= tol


def calculate_metrics(df: pd.DataFrame) -> dict:
    df = df.copy()

    df["final_distance_to_goal"] = pd.to_numeric(df["final_distance_to_goal"])
    df["minimum_distance_to_goal"] = pd.to_numeric(df["minimum_distance_to_goal"])
    df["success_radius"] = pd.to_numeric(df["success_radius"])

    df["success_flag"] = (df["final_distance_to_goal"] <= df["success_radius"]).astype(int)
    df["oracle_success_flag"] = (
        df["minimum_distance_to_goal"] <= df["success_radius"]
    ).astype(int)
    df["navigation_error"] = df["final_distance_to_goal"]

    n = len(df)
    final_successes = int(df["success_flag"].sum())
    oracle_successes = int(df["oracle_success_flag"].sum())

    return {
        "episodes": n,
        "success_radius_values": sorted(df["success_radius"].dropna().unique().tolist()),
        "final_successes": final_successes,
        "oracle_successes": oracle_successes,
        "sr": final_successes / n * 100.0 if n else math.nan,
        "osr": oracle_successes / n * 100.0 if n else math.nan,
        "ne": float(df["navigation_error"].mean()) if n else math.nan,
        "rows": df,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        default="results/research_audit/tracka_per_episode_metric_provenance.csv",
        help="Per-episode CSV containing all methods.",
    )
    parser.add_argument(
        "--out-md",
        default="results/research_audit/tracka_metric_provenance_report.md",
    )
    parser.add_argument(
        "--out-json",
        default="results/research_audit/tracka_metric_provenance_report.json",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    out_md = Path(args.out_md)
    out_json = Path(args.out_json)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "input_csv": str(csv_path),
        "status": "fail",
        "methods": {},
        "missing": [],
    }

    if not csv_path.exists():
        report["missing"].append(str(csv_path))
        out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        out_md.write_text(
            "# Track A Metric Provenance Report\n\n"
            "## Status\n\n"
            "FAIL — per-episode provenance CSV is missing.\n\n"
            f"Expected file:\n\n```text\n{csv_path}\n```\n\n"
            "This means the aggregate Track A results remain reported, but not fully "
            "auditable at per-episode level until this CSV is generated.\n",
            encoding="utf-8",
        )
        print(f"[FAIL] Missing per-episode CSV: {csv_path}")
        return 1

    df = pd.read_csv(csv_path)
    missing_cols = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing_cols:
        report["missing_columns"] = missing_cols
        out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[FAIL] Missing required columns: {missing_cols}")
        return 1

    md = [
        "# Track A Metric Provenance Report",
        "",
        "This report regenerates SR, OSR, and NE from per-episode rows.",
        "",
        "Required columns:",
        "",
        ", ".join(sorted(REQUIRED_COLUMNS)),
        "",
        "## Formula",
        "",
        "- final success: `final_distance_to_goal <= success_radius`",
        "- oracle success: `minimum_distance_to_goal <= success_radius`",
        "- SR: `sum(success_flag) / episodes * 100`",
        "- OSR: `sum(oracle_success_flag) / episodes * 100`",
        "- NE: `mean(final_distance_to_goal)`",
        "",
        "## Method results",
        "",
        "| Method | Episodes | Success radius | Final successes | Oracle successes | SR | OSR | NE | Expected match |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    all_ok = True

    for method, group in df.groupby("method"):
        metrics = calculate_metrics(group)
        expected = EXPECTED.get(method)

        expected_match = "not registered"
        if expected:
            checks = [
                metrics["episodes"] == expected["episodes"],
                close(metrics["sr"], expected["sr"]),
                close(metrics["osr"], expected["osr"]),
                close(metrics["ne"], expected["ne"]),
            ]
            expected_match = "PASS" if all(checks) else "FAIL"
            all_ok = all_ok and all(checks)

        radius_values = metrics["success_radius_values"]
        radius_display = ",".join(f"{v:g}" for v in radius_values)

        report["methods"][method] = {
            k: v
            for k, v in metrics.items()
            if k != "rows"
        }
        report["methods"][method]["expected_match"] = expected_match

        md.append(
            f"| {method} | {metrics['episodes']} | {radius_display} | "
            f"{metrics['final_successes']} | {metrics['oracle_successes']} | "
            f"{metrics['sr']:.1f}% | {metrics['osr']:.1f}% | {metrics['ne']:.2f} | "
            f"{expected_match} |"
        )

    report["status"] = "pass" if all_ok else "fail"

    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")

    if all_ok:
        print(f"[PASS] Metric provenance verified: {out_md}")
        return 0

    print(f"[FAIL] Metric provenance did not match expected results: {out_md}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
