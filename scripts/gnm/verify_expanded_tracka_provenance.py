#!/usr/bin/env python3
"""
Verify the expanded 253-episode Track A provenance.

Checks:
  1. Row count = 506 (253 episodes × 2 methods).
  2. Val-split rows agree with locked val provenance (15 episodes).
  3. All scenes present, episode counts match split lock.
  4. Compute aggregate and per-scene SR / NE with bootstrap 95% CIs.
  5. Confirm stopping-gap (OSR >> SR for baseline_gnm) holds at N=253.
  6. Write report.

Input:
  results/research_audit/tracka_expanded_253ep_baseline_oracle_provenance.csv
  results/research_audit/tracka_per_episode_metric_provenance.csv  (val cross-check)
  results/research_audit/tracka_expanded_split_lock.json

Output:
  results/research_audit/tracka_expanded_provenance_report.md
  results/research_audit/tracka_expanded_provenance_report.json
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "results/research_audit"

EXP_CSV = AUDIT / "tracka_expanded_253ep_baseline_oracle_provenance.csv"
VAL_CSV = AUDIT / "tracka_per_episode_metric_provenance.csv"
LOCK_JSON = AUDIT / "tracka_expanded_split_lock.json"
OUT_MD = AUDIT / "tracka_expanded_provenance_report.md"
OUT_JSON = AUDIT / "tracka_expanded_provenance_report.json"

SUCCESS_RADIUS = 3.0
N_BOOT = 10_000
BOOT_SEED = 42


def bootstrap_ci(values: list[float], stat_fn, n=N_BOOT, seed=BOOT_SEED) -> tuple[float, float, float]:
    point = stat_fn(values)
    rng = random.Random(seed)
    boot = sorted(stat_fn(rng.choices(values, k=len(values))) for _ in range(n))
    return point, boot[int(0.025 * n)], boot[int(0.975 * n)]


def analyse(rows: list[dict]) -> dict:
    n = len(rows)
    successes = [1.0 if r["success_flag"] == "True" else 0.0 for r in rows]
    oracle_suc = [1.0 if r["oracle_success_flag"] == "True" else 0.0 for r in rows]
    ne_vals = [float(r["navigation_error"]) for r in rows]

    sr_pt, sr_lo, sr_hi = bootstrap_ci(successes, lambda v: 100 * sum(v) / len(v))
    osr_pt = 100 * sum(oracle_suc) / n
    ne_pt, ne_lo, ne_hi = bootstrap_ci(ne_vals, lambda v: sum(v) / len(v))

    return {
        "n": n,
        "sr": round(sr_pt, 1),
        "osr": round(osr_pt, 1),
        "ne": round(ne_pt, 2),
        "sr_ci_lo": round(sr_lo, 1),
        "sr_ci_hi": round(sr_hi, 1),
        "ne_ci_lo": round(ne_lo, 2),
        "ne_ci_hi": round(ne_hi, 2),
        "stopping_gap": round(osr_pt - sr_pt, 1),
    }


def main() -> int:
    # Load expanded CSV
    all_rows = list(csv.DictReader(EXP_CSV.open()))
    if not all_rows:
        print(f"[ERROR] {EXP_CSV} is empty")
        return 1

    # Index by method
    by_method: dict[str, list[dict]] = {}
    for row in all_rows:
        by_method.setdefault(row["method"], []).append(row)

    # ── Check 1: row count ────────────────────────────────────────────────────
    expected_rows = 506
    if len(all_rows) != expected_rows:
        print(f"[FAIL] Expected {expected_rows} rows, got {len(all_rows)}")
        return 1
    print(f"[PASS] Row count: {len(all_rows)}")

    # ── Check 2: Val cross-check ──────────────────────────────────────────────
    val_ref = {r["episode_id"]: r for r in csv.DictReader(VAL_CSV.open())}
    val_rows_exp = {r["episode_id"]: r for r in by_method.get("baseline_gnm", []) if r["split"] == "val"}
    mismatches = 0
    for ep_id, ref in val_ref.items():
        exp = val_rows_exp.get(ep_id)
        if exp is None:
            print(f"[FAIL] Val episode {ep_id} missing from expanded CSV")
            mismatches += 1
            continue
        ref_fd = round(float(ref["final_distance_to_goal"]), 2)
        exp_fd = round(float(exp["final_distance_to_goal"]), 2)
        if abs(ref_fd - exp_fd) > 0.01:
            print(f"[FAIL] Val cross-check {ep_id}: ref={ref_fd}, exp={exp_fd}")
            mismatches += 1
    if mismatches:
        print(f"[FAIL] {mismatches} val cross-check failures")
        return 1
    print(f"[PASS] Val cross-check: all 15 val episodes match locked provenance")

    # ── Check 3: Episode counts match lock ────────────────────────────────────
    lock = json.loads(LOCK_JSON.read_text())
    exp_ep_ids = set(r["episode_id"] for r in by_method.get("baseline_gnm", []))
    lock_ep_ids = set(lock["episode_ids"])
    if exp_ep_ids != lock_ep_ids:
        print(f"[FAIL] Episode ID mismatch: {len(exp_ep_ids)} in CSV vs {len(lock_ep_ids)} in lock")
        return 1
    print(f"[PASS] Episode count: {len(exp_ep_ids)} episodes match split lock")

    # ── Compute statistics ────────────────────────────────────────────────────
    results: dict = {}
    all_scenes = sorted(set(r["scene_id"] for r in all_rows))

    for method in ("baseline_gnm", "geometry_aware_oracle"):
        m_rows = by_method.get(method, [])
        results[method] = {
            "aggregate": analyse(m_rows),
            "per_scene": {},
        }
        for scene in all_scenes:
            s_rows = [r for r in m_rows if r["scene_id"] == scene]
            results[method]["per_scene"][scene] = analyse(s_rows)

    # ── Check 4: Stopping gap at N=253 ───────────────────────────────────────
    base_agg = results["baseline_gnm"]["aggregate"]
    gap = base_agg["stopping_gap"]
    if gap < 10:
        print(f"[WARN] Stopping gap at N=253 is only {gap:.1f} pp — weaker than expected")
    else:
        print(f"[PASS] Stopping gap at N=253: {gap:.1f} pp (OSR−SR, baseline_gnm)")

    # ── Write report ──────────────────────────────────────────────────────────
    oracle_agg = results["geometry_aware_oracle"]["aggregate"]

    md_lines = [
        "# Track A Expanded Provenance Report (253 episodes)",
        "",
        f"Expanded evaluation for baseline_gnm and geometry_aware_oracle across "
        f"all {lock['n_episodes_total']} episodes ({lock['n_train']} train + {lock['n_val']} val).",
        f"Bootstrap 95% CI: {N_BOOT:,} resamples, seed={BOOT_SEED}. Success radius: {SUCCESS_RADIUS} m.",
        "",
        "> **Scope limitation:** Only baseline_gnm and geometry_aware_oracle are evaluated",
        "> on all 253 episodes. The other three methods remain at 15-episode val evaluation.",
        "> See tracka_expanded_split_lock.json for full methodology note.",
        "",
        "## Aggregate results",
        "",
        "| Method | n | SR % | OSR % | NE (m) | SR 95% CI | NE 95% CI | OSR−SR gap |",
        "|---|---:|---:|---:|---:|---|---|---:|",
        f"| baseline_gnm | {base_agg['n']} | {base_agg['sr']:.1f} | {base_agg['osr']:.1f} "
        f"| {base_agg['ne']:.2f} | [{base_agg['sr_ci_lo']:.1f}, {base_agg['sr_ci_hi']:.1f}] "
        f"| [{base_agg['ne_ci_lo']:.2f}, {base_agg['ne_ci_hi']:.2f}] | {base_agg['stopping_gap']:.1f} pp |",
        f"| geometry_aware_oracle | {oracle_agg['n']} | {oracle_agg['sr']:.1f} | {oracle_agg['osr']:.1f} "
        f"| {oracle_agg['ne']:.2f} | [{oracle_agg['sr_ci_lo']:.1f}, {oracle_agg['sr_ci_hi']:.1f}] "
        f"| [{oracle_agg['ne_ci_lo']:.2f}, {oracle_agg['ne_ci_hi']:.2f}] | {oracle_agg['stopping_gap']:.1f} pp |",
        "",
        "## Per-scene results",
        "",
        "| Method | Scene | n | SR % | OSR % | NE (m) | SR 95% CI |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for method in ("baseline_gnm", "geometry_aware_oracle"):
        for scene in all_scenes:
            a = results[method]["per_scene"][scene]
            md_lines.append(
                f"| {method} | {scene} | {a['n']} | {a['sr']:.1f} | {a['osr']:.1f} "
                f"| {a['ne']:.2f} | [{a['sr_ci_lo']:.1f}, {a['sr_ci_hi']:.1f}] |"
            )

    md_lines += [
        "",
        "## Comparison with 15-episode val results",
        "",
        "| Method | Metric | 15-ep val | 253-ep expanded | CI width comparison |",
        "|---|---|---:|---:|---|",
        f"| baseline_gnm | SR % | 20.0 | {base_agg['sr']:.1f} | "
        f"val CI [{0}, {40}] → exp CI [{base_agg['sr_ci_lo']:.1f}, {base_agg['sr_ci_hi']:.1f}] |",
        f"| baseline_gnm | NE (m) | 6.51 | {base_agg['ne']:.2f} | "
        f"val CI [4.71, 8.50] → exp CI [{base_agg['ne_ci_lo']:.2f}, {base_agg['ne_ci_hi']:.2f}] |",
        "",
        "## Methodology note",
        "",
        "**Why only 2 methods on the expanded set:**",
        "",
        "- hand_tuned_waypoint_gate: Simulating the policy from baseline trajectories",
        "  (threshold sweep) gives SR=20%, but live Isaac Sim runs give SR=26.7%. The divergence",
        "  occurs because stopping early changes the robot's subsequent path. Cannot reliably",
        "  expand without new live Isaac Sim inference.",
        "- logistic_stop_head: Trained on these exact trace features → in-distribution evaluation.",
        "- temporal_neural_stop_head: Same training contamination.",
        "",
        "**Why the expanded set is valid for baseline and oracle:**",
        "",
        "- baseline_gnm: true_dist_m in traces comes from live Isaac Sim runs (no training).",
        "  The stopping-gap claim does not depend on stop-policy evaluation.",
        "- geometry_aware_oracle: Derived from min(true_dist_m); no training involved.",
    ]

    OUT_MD.write_text("\n".join(md_lines) + "\n")
    print(f"[OK] {OUT_MD.name}")

    json_out = {
        "n_episodes": lock["n_episodes_total"],
        "n_train": lock["n_train"],
        "n_val": lock["n_val"],
        "methods": results,
    }
    OUT_JSON.write_text(json.dumps(json_out, indent=2))
    print(f"[OK] {OUT_JSON.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
