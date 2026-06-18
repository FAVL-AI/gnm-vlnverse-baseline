#!/usr/bin/env python3
"""
Per-scene breakdown of Track A stop-policy results across all 5 methods.

Input:  results/research_audit/tracka_all_methods_per_episode_metric_provenance.csv  (75 rows)
Output: results/research_audit/tracka_per_scene_breakdown.csv
        results/research_audit/tracka_per_scene_breakdown.md
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IN_CSV = ROOT / "results/research_audit/tracka_all_methods_per_episode_metric_provenance.csv"
OUT_CSV = ROOT / "results/research_audit/tracka_per_scene_breakdown.csv"
OUT_MD = ROOT / "results/research_audit/tracka_per_scene_breakdown.md"

N_BOOT = 10_000
BOOT_SEED = 42
SUCCESS_RADIUS = 3.0

METHOD_ORDER = [
    "baseline_gnm",
    "hand_tuned_waypoint_gate",
    "logistic_stop_head",
    "temporal_neural_stop_head",
    "geometry_aware_oracle",
]


def bootstrap_ci(values: list[float], stat_fn, n=N_BOOT, seed=BOOT_SEED) -> tuple[float, float]:
    rng = random.Random(seed)
    boot = sorted(stat_fn(rng.choices(values, k=len(values))) for _ in range(n))
    lo = boot[int(0.025 * n)]
    hi = boot[int(0.975 * n)]
    return lo, hi


def sr(rows: list[dict]) -> float:
    return 100 * sum(r["success_flag"] == "True" for r in rows) / len(rows)


def osr(rows: list[dict]) -> float:
    return 100 * sum(r["oracle_success_flag"] == "True" for r in rows) / len(rows)


def ne(rows: list[dict]) -> float:
    return sum(float(r["navigation_error"]) for r in rows) / len(rows)


def analyse(rows: list[dict]) -> dict:
    sr_val = sr(rows)
    osr_val = osr(rows)
    ne_val = ne(rows)

    successes = [1.0 if r["success_flag"] == "True" else 0.0 for r in rows]
    ne_vals = [float(r["navigation_error"]) for r in rows]

    sr_lo, sr_hi = bootstrap_ci(successes, lambda v: 100 * sum(v) / len(v))
    ne_lo, ne_hi = bootstrap_ci(ne_vals, lambda v: sum(v) / len(v))

    return {
        "n": len(rows),
        "sr": round(sr_val, 1),
        "osr": round(osr_val, 1),
        "ne": round(ne_val, 2),
        "sr_ci_lo": round(sr_lo, 1),
        "sr_ci_hi": round(sr_hi, 1),
        "ne_ci_lo": round(ne_lo, 2),
        "ne_ci_hi": round(ne_hi, 2),
    }


def main() -> int:
    all_rows = list(csv.DictReader(IN_CSV.open()))
    if not all_rows:
        print(f"[ERROR] {IN_CSV} is empty")
        return 1

    # Organise: {method: {scene: [row, ...]}}
    data: dict[str, dict[str, list[dict]]] = {}
    all_scenes: set[str] = set()
    for row in all_rows:
        data.setdefault(row["method"], {}).setdefault(row["scene_id"], []).append(row)
        all_scenes.add(row["scene_id"])

    scenes = sorted(all_scenes)

    # Write CSV
    csv_rows = []
    for method in METHOD_ORDER:
        method_rows = data.get(method, {})
        for scene in scenes:
            scene_rows = method_rows.get(scene, [])
            if not scene_rows:
                continue
            a = analyse(scene_rows)
            csv_rows.append({
                "method": method,
                "scene_id": scene,
                "n_episodes": a["n"],
                "sr_pct": a["sr"],
                "osr_pct": a["osr"],
                "ne_m": a["ne"],
                "sr_ci95_lo": a["sr_ci_lo"],
                "sr_ci95_hi": a["sr_ci_hi"],
                "ne_ci95_lo": a["ne_ci_lo"],
                "ne_ci95_hi": a["ne_ci_hi"],
            })

    fieldnames = [
        "method", "scene_id", "n_episodes",
        "sr_pct", "osr_pct", "ne_m",
        "sr_ci95_lo", "sr_ci95_hi",
        "ne_ci95_lo", "ne_ci95_hi",
    ]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(csv_rows)
    print(f"[OK] {OUT_CSV.name}: {len(csv_rows)} rows")

    # Write markdown
    lines = [
        "# Track A Per-Scene Breakdown",
        "",
        f"All results use success radius = {SUCCESS_RADIUS} m, 15 val episodes, "
        f"bootstrap 95% CI ({N_BOOT:,} resamples, seed={BOOT_SEED}).",
        "",
        "> **Note:** kujiale_0092 has 2 episodes, kujiale_0118 and kujiale_0271 have 3 each, "
        "kujiale_0203 has 7. Per-scene CIs are wide given small N — use for diagnostic "
        "pattern inspection, not point-estimate reporting.",
        "",
    ]

    for scene in scenes:
        scene_episode_count = len(data.get("baseline_gnm", {}).get(scene, []))
        lines += [
            f"## {scene}  (n={scene_episode_count})",
            "",
            "| Method | SR % | OSR % | NE (m) | SR 95% CI |",
            "|---|---:|---:|---:|---|",
        ]
        for method in METHOD_ORDER:
            scene_rows = data.get(method, {}).get(scene, [])
            if not scene_rows:
                lines.append(f"| {method} | — | — | — | — |")
                continue
            a = analyse(scene_rows)
            lines.append(
                f"| {method} | {a['sr']:.0f} | {a['osr']:.0f} | {a['ne']:.2f} "
                f"| [{a['sr_ci_lo']:.0f}, {a['sr_ci_hi']:.0f}] |"
            )
        lines.append("")

    # All-scenes aggregate for sanity check
    lines += [
        "## All scenes combined (n=15)",
        "",
        "| Method | SR % | OSR % | NE (m) | SR 95% CI |",
        "|---|---:|---:|---:|---|",
    ]
    for method in METHOD_ORDER:
        method_rows = [r for scene_rows in data.get(method, {}).values() for r in scene_rows]
        if not method_rows:
            continue
        a = analyse(method_rows)
        lines.append(
            f"| {method} | {a['sr']:.0f} | {a['osr']:.0f} | {a['ne']:.2f} "
            f"| [{a['sr_ci_lo']:.0f}, {a['sr_ci_hi']:.0f}] |"
        )
    lines.append("")

    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"[OK] {OUT_MD.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
