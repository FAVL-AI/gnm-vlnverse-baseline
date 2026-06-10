#!/usr/bin/env python3
"""Summarise temporal stop-head feature-set ablation."""

from __future__ import annotations

import csv
import json
from pathlib import Path


BASE_DIR = Path("results/bo_reviewer_packet/temporal_stop_feature_ablation")
OUT_CSV = BASE_DIR / "25_temporal_stop_feature_ablation.csv"
OUT_MD = BASE_DIR / "25_temporal_stop_feature_ablation.md"


def read_one(run_dir: Path) -> dict:
    summary_csv = run_dir / "22_temporal_stop_head.csv"
    meta_json = run_dir / "22_temporal_stop_head_meta.json"

    with summary_csv.open() as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"No rows found in {summary_csv}")

    row = dict(rows[0])
    meta = {}
    if meta_json.exists():
        meta = json.loads(meta_json.read_text())

    row["feature_set"] = meta.get("feature_set", run_dir.name)
    row["feature_dim"] = str(meta.get("feature_dim", ""))
    row["feature_columns"] = ", ".join(meta.get("feature_columns", []))
    row["seq_len"] = str(meta.get("seq_len", "8"))
    row["stable_k"] = str(meta.get("stable_k", "3"))
    row["run_dir"] = str(run_dir)

    return row


def score(row: dict) -> tuple[float, float, float]:
    return (
        float(row["SR_percent"]),
        float(row["OSR_percent"]),
        -float(row["NE_m"]),
    )


def main() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    run_dirs = sorted(
        d for d in BASE_DIR.iterdir()
        if d.is_dir() and (d / "22_temporal_stop_head.csv").exists()
    )

    if not run_dirs:
        raise SystemExit(f"No completed feature ablation runs found in {BASE_DIR}")

    rows = [read_one(d) for d in run_dirs]
    rows = sorted(rows, key=score, reverse=True)
    best = rows[0]

    fieldnames = [
        "feature_set",
        "feature_dim",
        "feature_columns",
        "seq_len",
        "stable_k",
        "best_threshold",
        "episodes",
        "SR_percent",
        "OSR_percent",
        "NE_m",
        "TL_m",
        "stop_fired",
        "mean_stop_step",
        "run_dir",
    ]

    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    md = [
        "# Temporal Stop-Head Feature-Set Ablation",
        "",
        "This ablation evaluates which runtime feature group drives the temporal neural stop-head improvement.",
        "",
        "All runs use the same train/eval protocol as v1.1:",
        "",
        "- Train split: Track A train",
        "- Eval split: held-out Track A validation",
        "- Sequence length: 8",
        "- Stable-stop confirmation window: 3",
        "- Runtime-only inputs from GNM outputs and derived temporal features",
        "- Ground-truth geometry is used only for training labels and final metrics",
        "",
        "## Best result",
        "",
        "| feature_set | feature_dim | threshold | SR | OSR | NE (m) | TL (m) | stop_fired | mean_stop_step |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| {best['feature_set']} | {best['feature_dim']} | {best['best_threshold']} | {best['SR_percent']}% | {best['OSR_percent']}% | {best['NE_m']} | {best['TL_m']} | {best['stop_fired']} | {best.get('mean_stop_step', '') or 'n/a'} |",
        "",
        "## Full ablation table",
        "",
        "| feature_set | columns | threshold | SR | OSR | NE (m) | TL (m) | stop_fired | mean_stop_step |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for row in rows:
        md.append(
            f"| {row['feature_set']} | {row['feature_columns']} | {row['best_threshold']} | "
            f"{row['SR_percent']}% | {row['OSR_percent']}% | {row['NE_m']} | {row['TL_m']} | "
            f"{row['stop_fired']} | {row.get('mean_stop_step', '') or 'n/a'} |"
        )

    md.extend([
        "",
        "## Interpretation",
        "",
        "This table isolates whether deployable stopping is driven primarily by distance predictions, waypoint/action magnitude, the combination of raw distance and waypoint signals, or the full temporal feature vector.",
        "",
        "The v1.1 reference setting used the full temporal feature vector with seq_len=8 and stable_k=3.",
        "",
    ])

    OUT_MD.write_text("\n".join(md))

    print(f"[OK] wrote {OUT_CSV}")
    print(f"[OK] wrote {OUT_MD}")
    print(f"[BEST] {best}")


if __name__ == "__main__":
    main()

