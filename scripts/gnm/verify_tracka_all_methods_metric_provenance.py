#!/usr/bin/env python3
"""
Verify per-episode metric provenance for all five Track A stop-policy methods.

Checks that SR, OSR, and NE recomputed from the 75-row per-episode CSV match
the values reported in the paper table. Also computes bootstrap 95% confidence
intervals (10 000 resamples) for SR, OSR, NE, and the SR–OSR gap.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CSV = ROOT / "results/research_audit/tracka_all_methods_per_episode_metric_provenance.csv"
DEFAULT_OUT_MD = ROOT / "results/research_audit/tracka_all_methods_metric_provenance_report.md"
DEFAULT_OUT_JSON = ROOT / "results/research_audit/tracka_all_methods_metric_provenance_report.json"

EXPECTED = {
    "baseline_gnm":            {"sr": 20.0, "osr": 46.7, "ne": 6.51, "episodes": 15},
    "hand_tuned_waypoint_gate": {"sr": 26.7, "osr": 26.7, "ne": 5.34, "episodes": 15},
    "logistic_stop_head":       {"sr": 20.0, "osr": 46.7, "ne": 6.51, "episodes": 15},
    "temporal_neural_stop_head": {"sr": 33.3, "osr": 33.3, "ne": 4.47, "episodes": 15},
    "geometry_aware_oracle":    {"sr": 46.7, "osr": 46.7, "ne": 3.79, "episodes": 15},
}

TOLERANCE = 0.06
N_BOOTSTRAP = 10_000
BOOTSTRAP_SEED = 42
CI_ALPHA = 0.05


def close(a: float, b: float, tol: float = TOLERANCE) -> bool:
    return abs(a - b) <= tol


def bootstrap_ci(
    values: list[float],
    stat_fn,
    n: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
    alpha: float = CI_ALPHA,
) -> tuple[float, float]:
    rng = random.Random(seed)
    k = len(values)
    stats = sorted(stat_fn(rng.choices(values, k=k)) for _ in range(n))
    lo = stats[int(alpha / 2 * n)]
    hi = stats[int((1 - alpha / 2) * n) - 1]
    return lo, hi


def compute_method_stats(group: pd.DataFrame) -> dict:
    n = len(group)
    success = group["success_flag"].astype(bool).tolist()
    oracle = group["oracle_success_flag"].astype(bool).tolist()
    ne_vals = group["navigation_error"].astype(float).tolist()

    final_succ = sum(success)
    oracle_succ = sum(oracle)
    sr = final_succ / n * 100.0 if n else math.nan
    osr = oracle_succ / n * 100.0 if n else math.nan
    ne = float(sum(ne_vals) / n) if n else math.nan

    sr_lo, sr_hi = bootstrap_ci(success, lambda s: 100.0 * sum(s) / len(s))
    osr_lo, osr_hi = bootstrap_ci(oracle, lambda s: 100.0 * sum(s) / len(s))
    ne_lo, ne_hi = bootstrap_ci(ne_vals, lambda s: sum(s) / len(s))

    gap = osr - sr
    gap_lo = osr_lo - sr_hi
    gap_hi = osr_hi - sr_lo

    return {
        "episodes": n,
        "final_successes": final_succ,
        "oracle_successes": oracle_succ,
        "sr": sr,
        "osr": osr,
        "ne": ne,
        "sr_ci95": [sr_lo, sr_hi],
        "osr_ci95": [osr_lo, osr_hi],
        "ne_ci95": [ne_lo, ne_hi],
        "stopping_gap": gap,
        "stopping_gap_ci95": [gap_lo, gap_hi],
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    parser.add_argument("--out-json", default=str(DEFAULT_OUT_JSON))
    args = parser.parse_args()

    csv_path = Path(args.csv)
    out_md = Path(args.out_md)
    out_json = Path(args.out_json)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    if not csv_path.exists():
        print(f"[FAIL] Missing CSV: {csv_path}")
        print("       Run: python3 scripts/gnm/generate_all_methods_provenance.py")
        return 1

    df = pd.read_csv(csv_path)
    required = {"episode_id", "method", "success_flag", "oracle_success_flag", "navigation_error"}
    missing_cols = sorted(required - set(df.columns))
    if missing_cols:
        print(f"[FAIL] Missing columns: {missing_cols}")
        return 1

    report: dict = {
        "input_csv": str(csv_path),
        "n_rows": len(df),
        "n_methods": df["method"].nunique(),
        "bootstrap_resamples": N_BOOTSTRAP,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "ci_alpha": CI_ALPHA,
        "status": "fail",
        "methods": {},
        "small_sample_note": (
            f"Validation set is {len(df) // df['method'].nunique()} episodes per method. "
            "Bootstrap 95% CIs reflect this small-sample uncertainty."
        ),
    }

    md_lines = [
        "# Track A All-Methods Metric Provenance Report",
        "",
        "Per-episode provenance for all five Track A stop-policy methods.",
        f"Bootstrap 95% CI: {N_BOOTSTRAP} resamples, seed {BOOTSTRAP_SEED}.",
        "",
        f"> **Small-sample note:** The validation set is {len(df) // df['method'].nunique()} episodes "
        f"per method. Proportions such as SR=20.0% represent 3/15 and SR=33.3% represents 5/15. "
        f"Bootstrap confidence intervals below reflect this uncertainty.",
        "",
        "## Method results",
        "",
        "| Method | N | SR | SR 95% CI | OSR | OSR 95% CI | NE | NE 95% CI | SR–OSR gap | Match |",
        "|---|---:|---:|---|---:|---|---:|---|---:|---|",
    ]

    all_ok = True

    for method_name in [
        "baseline_gnm",
        "hand_tuned_waypoint_gate",
        "logistic_stop_head",
        "temporal_neural_stop_head",
        "geometry_aware_oracle",
    ]:
        group = df[df["method"] == method_name]
        if group.empty:
            md_lines.append(f"| {method_name} | — | — | — | — | — | — | — | — | MISSING |")
            report["methods"][method_name] = {"status": "MISSING"}
            all_ok = False
            continue

        stats = compute_method_stats(group)
        expected = EXPECTED.get(method_name)

        if expected:
            checks = [
                stats["episodes"] == expected["episodes"],
                close(stats["sr"], expected["sr"]),
                close(stats["osr"], expected["osr"]),
                close(stats["ne"], expected["ne"]),
            ]
            match = "PASS" if all(checks) else "FAIL"
            all_ok = all_ok and all(checks)
        else:
            match = "not registered"

        report["methods"][method_name] = {**stats, "expected_match": match}

        sr_ci = stats["sr_ci95"]
        osr_ci = stats["osr_ci95"]
        ne_ci = stats["ne_ci95"]
        gap_ci = stats["stopping_gap_ci95"]

        md_lines.append(
            f"| {method_name} "
            f"| {stats['episodes']} "
            f"| {stats['sr']:.1f}% "
            f"| [{sr_ci[0]:.1f}%, {sr_ci[1]:.1f}%] "
            f"| {stats['osr']:.1f}% "
            f"| [{osr_ci[0]:.1f}%, {osr_ci[1]:.1f}%] "
            f"| {stats['ne']:.2f} "
            f"| [{ne_ci[0]:.2f}, {ne_ci[1]:.2f}] "
            f"| {stats['stopping_gap']:.1f}pp [{gap_ci[0]:.1f}, {gap_ci[1]:.1f}] "
            f"| **{match}** |"
        )

    md_lines += [
        "",
        "## Formula",
        "",
        "- success_flag: `final_distance_to_goal <= success_radius`",
        "- oracle_success_flag: `minimum_distance_to_goal <= success_radius`",
        "- SR: `sum(success_flag) / N * 100`",
        "- OSR: `sum(oracle_success_flag) / N * 100`",
        "- NE: `mean(navigation_error)`",
        "- SR–OSR gap: `OSR − SR` (positive = more oracle than final successes)",
        "",
        "## Statistical honesty",
        "",
        f"The validation set contains {len(df) // df['method'].nunique()} episodes. "
        "Each percentage point change in SR or OSR corresponds to 1/15 ≈ 6.7 episodes. "
        "The bootstrap CIs reflect this granularity. Improvements of one episode are "
        "meaningful but should be interpreted cautiously at this sample size.",
    ]

    report["status"] = "pass" if all_ok else "fail"

    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    if all_ok:
        print(f"[PASS] All-methods provenance verified: {out_md.relative_to(ROOT)}")
        return 0

    print(f"[FAIL] All-methods provenance: {out_md.relative_to(ROOT)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
