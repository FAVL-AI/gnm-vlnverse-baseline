#!/usr/bin/env python3
"""
run_sensor_degradation.py — Scenario 3: sensor degradation robustness suite.

Tests FleetSafe's ability to maintain safety under nine sensor conditions:
  baseline, blur_20, blur_40, blur_60,
  low_light_30, low_light_60,
  lidar_dropout_10, lidar_dropout_30,
  combined_degradation

Scene: mid_crossing (pedestrian crosses path 3 s into episode).
Runs on the mock backend — no GPU or Isaac Sim required.

PROVEN gate:
  ≥10 seeds per condition AND FleetSafe preserves safety with ≤5 %% success
  degradation across all conditions.

Outputs (written to simulations/degradation_<timestamp>/):
  degradation_matrix.csv          per-condition aggregate metrics table
  degradation_summary.json        full results + robustness scores
  robustness_score.png            bar chart of per-condition robustness
  safety_zone_heatmap.png         GREEN/AMBER/RED time fractions per condition
  sensor_degradation_report.md    evidence document

Usage:
  python scripts/sim/run_sensor_degradation.py [--seeds smoke|dev|paper] [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np

from fleet_safe_vla.benchmarks.visualnav_scenarios import SCENE_MID_CROSSING, get_seeds
from fleet_safe_vla.benchmarks.visualnav_runner import VisualNavBenchmarkRunner
from fleet_safe_vla.benchmarks.sensor_degradation import (
    DEGRADATION_SUITE,
    DegradedAdapter,
    _DroppedObstacleWrapper,
    compute_degradation_robustness_score,
    perception_confidence_proxy,
)
from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import ActionOutput, CmdVel


# ── Baseline mock adapter ──────────────────────────────────────────────────────

class _MockAdapter:
    """Checkpoint-free adapter; returns goal-directed random waypoints."""
    model_name   = "mock"
    image_size   = (85, 64)
    context_size = 5
    _loaded      = True
    _device      = None

    def is_loaded(self) -> bool:
        return True

    def load_checkpoint(self, path) -> None:
        pass

    def preprocess_observation(self, obs_imgs, goal_img) -> dict:
        return {"obs": obs_imgs[0] if obs_imgs else None, "goal": goal_img}

    def predict_action(self, preprocessed) -> ActionOutput:
        rng = np.random.default_rng()
        wp  = np.column_stack([
            rng.uniform(0.04, 0.10, 5),
            rng.uniform(-0.02, 0.02, 5),
        ])
        return ActionOutput(waypoints=wp, model_name="mock", inference_ms=0.1)

    def action_to_cmd_vel(self, action: ActionOutput, *, v_max=0.3, vy_max=0.0,
                          w_max=0.7, control_hz=4.0) -> CmdVel:
        from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import waypoints_to_cmd_vel
        return waypoints_to_cmd_vel(action.waypoints, v_max=v_max, vy_max=vy_max,
                                    w_max=w_max, control_hz=control_hz)

    def log_policy_output(self, action, cmd_vel) -> dict:
        return {}


# ── Crossing-event analysis (TTC extraction) ───────────────────────────────────

def _min_ttc_from_episode(ep_dir: Path, control_hz: float = 10.0) -> float:
    """Return minimum TTC observed in episode (inf if no events)."""
    traj_path = ep_dir / "trajectory.csv"
    acts_path = ep_dir / "actions.csv"
    if not traj_path.exists() or not acts_path.exists():
        return float("inf")

    with traj_path.open() as f:
        traj = list(csv.DictReader(f))
    dt   = 1.0 / control_hz
    min_ttc = float("inf")

    for agent in SCENE_MID_CROSSING.dynamic_agents:
        prev_d: float | None = None
        for step, row in enumerate(traj):
            rx = float(row["x"])
            ry = float(row["y"])
            t  = step * dt
            ax, ay = agent.position_at(t)
            d = math.hypot(rx - ax, ry - ay)
            if prev_d is not None and dt > 0:
                closing = (prev_d - d) / dt
                if closing > 1e-4:
                    ttc = d / closing
                    if ttc < min_ttc:
                        min_ttc = ttc
            prev_d = d
    return min_ttc


# ── One condition run ──────────────────────────────────────────────────────────

def run_condition(
    cfg_name: str,
    seeds: list[int],
    out_dir: Path,
    run_id: str,
) -> dict:
    """
    Run one degradation condition and return aggregate metric dict.
    """
    from fleet_safe_vla.benchmarks.sensor_degradation import DEGRADATION_SUITE
    cfg = DEGRADATION_SUITE[cfg_name]

    base_adapter    = _MockAdapter()
    degraded_adapter = DegradedAdapter(base_adapter, cfg, seed=42)

    runner = VisualNavBenchmarkRunner(
        adapter    = degraded_adapter,
        fleetsafe  = True,
        backend    = "mock",
        output_dir = out_dir / cfg_name,
        max_steps  = 250,
        control_hz = 10.0,
    )

    # Inject LiDAR dropout wrapper (replaces the FleetSafeWrapper shim)
    if cfg.lidar_dropout_rate > 0.0 and runner._wrapper is not None:
        runner._wrapper = _DroppedObstacleWrapper(
            runner._wrapper, cfg.lidar_dropout_rate, seed=43
        )

    ep_metrics = runner.run(
        scenes = [SCENE_MID_CROSSING],
        seeds  = seeds,
        run_id = run_id,
    )

    # Episode dir layout: out_dir/cfg_name/run_id/episodes/episode_*/
    ep_dirs = sorted((out_dir / cfg_name / run_id / "episodes").glob("episode_*"))

    # Collect min TTC across all episodes
    all_min_ttcs = [_min_ttc_from_episode(d) for d in ep_dirs]
    finite_ttcs  = [v for v in all_min_ttcs if math.isfinite(v)]

    n = len(ep_metrics)
    success_rate   = sum(1 for e in ep_metrics if e.success) / max(n, 1)
    collision_rate = sum(1 for e in ep_metrics if e.collision_count > 0) / max(n, 1)
    interv_rate    = float(np.mean([e.intervention_rate for e in ep_metrics])) if ep_metrics else 0.0
    steps_green    = sum(e.steps_green for e in ep_metrics)
    steps_amber    = sum(e.steps_amber for e in ep_metrics)
    steps_red      = sum(e.steps_red  for e in ep_metrics)
    total_steps    = steps_green + steps_amber + steps_red

    return {
        "condition":            cfg_name,
        "n_episodes":           n,
        "n_seeds":              len(seeds),
        "success_rate":         round(success_rate, 4),
        "collision_rate":       round(collision_rate, 4),
        "intervention_rate":    round(interv_rate, 4),
        "min_ttc_s":            round(float(np.min(finite_ttcs)), 3) if finite_ttcs else None,
        "median_min_ttc_s":     round(float(np.median(finite_ttcs)), 3) if finite_ttcs else None,
        "perception_confidence": perception_confidence_proxy(cfg),
        "steps_green_pct":      round(steps_green / max(total_steps, 1), 4),
        "steps_amber_pct":      round(steps_amber / max(total_steps, 1), 4),
        "steps_red_pct":        round(steps_red   / max(total_steps, 1), 4),
        "blur_sigma":           cfg.blur_sigma,
        "brightness_factor":    cfg.brightness_factor,
        "lidar_dropout_rate":   cfg.lidar_dropout_rate,
        "action_noise_sigma":   cfg.action_noise_sigma,
        "description":          cfg.description,
    }


# ── Plot functions ─────────────────────────────────────────────────────────────

def _dark_fig(w: float, h: float):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("#111827")
    ax.set_facecolor("#111827")
    ax.tick_params(colors="#6b7280", labelsize=7.5)
    for sp in ax.spines.values():
        sp.set_edgecolor("#374151")
    return fig, ax


def plot_robustness_scores(scores: dict[str, float], out: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        conditions = list(scores.keys())
        values     = [scores[c] for c in conditions]
        colours = [
            "#34d399" if v >= 0.90 else
            "#fbbf24" if v >= 0.75 else
            "#f87171"
            for v in values
        ]

        fig, ax = _dark_fig(14, 6)
        bars = ax.bar(range(len(conditions)), values, color=colours, alpha=0.85, width=0.6)

        for bar, v in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                bar.get_height() + 0.01,
                f"{v:.3f}",
                ha="center", va="bottom",
                color="#f9fafb", fontsize=8, fontfamily="monospace",
            )

        ax.axhline(0.95, color="#34d399", lw=1.0, ls="--", alpha=0.6, label="≥0.95 (robust)")
        ax.axhline(0.75, color="#fbbf24", lw=1.0, ls="--", alpha=0.6, label="≥0.75 (acceptable)")
        ax.set_xticks(range(len(conditions)))
        ax.set_xticklabels(conditions, rotation=35, ha="right",
                           fontsize=8, fontfamily="monospace", color="#9ca3af")
        ax.set_ylim(0, 1.12)
        ax.set_ylabel("Robustness Score", color="#9ca3af", fontsize=9, fontfamily="monospace")
        ax.set_title(
            "Sensor Degradation Robustness — FleetSafe · mid_crossing scene",
            color="#f9fafb", fontsize=11, fontfamily="monospace", pad=10,
        )
        ax.legend(loc="lower left", fontsize=7.5, facecolor="#1f2937",
                  edgecolor="#374151", labelcolor="white")
        plt.tight_layout()
        plt.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#111827")
        plt.close(fig)
        print(f"[plot] → {out}")
    except Exception as e:
        print(f"[plot] WARNING robustness_score: {e}")


def plot_safety_zone_heatmap(results: list[dict], out: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        conditions = [r["condition"] for r in results]
        greens     = [r["steps_green_pct"] for r in results]
        ambers     = [r["steps_amber_pct"] for r in results]
        reds       = [r["steps_red_pct"]   for r in results]

        x = np.arange(len(conditions))
        fig, ax = _dark_fig(14, 6)
        ax.bar(x, greens, label="GREEN",  color="#34d399", alpha=0.85, width=0.6)
        ax.bar(x, ambers, bottom=greens,  label="AMBER", color="#fbbf24", alpha=0.85, width=0.6)
        ax.bar(x, reds,   bottom=[g + a for g, a in zip(greens, ambers)],
               label="RED", color="#f87171", alpha=0.85, width=0.6)

        ax.set_xticks(x)
        ax.set_xticklabels(conditions, rotation=35, ha="right",
                           fontsize=8, fontfamily="monospace", color="#9ca3af")
        ax.set_ylim(0, 1.12)
        ax.set_ylabel("Step fraction", color="#9ca3af", fontsize=9, fontfamily="monospace")
        ax.set_title(
            "Safety Zone Distribution by Degradation Condition",
            color="#f9fafb", fontsize=11, fontfamily="monospace", pad=10,
        )
        ax.legend(loc="upper right", fontsize=8, facecolor="#1f2937",
                  edgecolor="#374151", labelcolor="white")
        plt.tight_layout()
        plt.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#111827")
        plt.close(fig)
        print(f"[plot] → {out}")
    except Exception as e:
        print(f"[plot] WARNING safety_zone_heatmap: {e}")


# ── CSV / JSON outputs ─────────────────────────────────────────────────────────

MATRIX_COLS = [
    "condition", "n_episodes", "n_seeds",
    "success_rate", "collision_rate", "intervention_rate",
    "min_ttc_s", "median_min_ttc_s",
    "perception_confidence",
    "steps_green_pct", "steps_amber_pct", "steps_red_pct",
    "blur_sigma", "brightness_factor", "lidar_dropout_rate", "action_noise_sigma",
]


def write_degradation_matrix(results: list[dict], out: Path) -> None:
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MATRIX_COLS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(f"[csv] → {out}")


def write_degradation_summary(
    results: list[dict],
    scores:  dict[str, float],
    run_id:  str,
    n_seeds: int,
    proven:  bool,
    out:     Path,
) -> None:
    payload = {
        "run_id":    run_id,
        "generated": datetime.now(timezone.utc).isoformat(),
        "n_seeds":   n_seeds,
        "backend":   "mock",
        "scene":     "mid_crossing",
        "proven":    proven,
        "verdict":   (
            "PROVEN: FleetSafe maintains safety across all sensor degradation conditions "
            f"with ≤5%% success degradation." if proven else
            "RECORDED_ONLY: Success degradation exceeds 5%% threshold under some conditions."
        ),
        "robustness_scores":  scores,
        "conditions":         {r["condition"]: r for r in results},
    }
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(f"[json] → {out}")


# ── Markdown report ────────────────────────────────────────────────────────────

def write_degradation_report(
    results:   list[dict],
    scores:    dict[str, float],
    run_id:    str,
    n_seeds:   int,
    proven:    bool,
    out:       Path,
) -> None:
    baseline = next((r for r in results if r["condition"] == "baseline"), {})

    def fmt(v, pct=False):
        if v is None:
            return "—"
        if pct:
            return f"{100.0 * float(v):.1f}%"
        return f"{float(v):.4f}" if isinstance(v, float) else str(v)

    lines = [
        f"# Sensor Degradation Robustness Report — {run_id}",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}  "
        f"|  Seeds: {n_seeds}  |  Backend: mock  |  Scene: mid_crossing",
        "",
        f"**Status: {'✓ PROVEN' if proven else '✗ RECORDED_ONLY'}**",
        "",
        "## Summary",
        "",
        "FleetSafe is tested under nine sensor degradation conditions (one baseline + eight "
        "degraded).  The robustness score measures how well the safety layer preserves "
        "navigation success and collision avoidance compared to clean conditions.",
        "",
        "Robustness score formula:",
        "```",
        "score = (1 − success_degradation_frac) × (1 − collision_increase)",
        "  where success_degradation_frac = max(0, base_success − deg_success)",
        "                                   / max(base_success, 0.01)",
        "        collision_increase = max(0, collision_rate_degraded",
        "                                   − collision_rate_baseline)",
        "```",
        "When baseline and degraded conditions both show 0% success (mock backend),",
        "score = 1.0 − collision_increase, making collision avoidance the primary axis.",
        "",
        "## Degradation Matrix",
        "",
        "| Condition | Success % | Collision % | Interv. Rate | Min TTC (s) | Perc. Conf. | Robustness |",
        "|-----------|-----------|-------------|--------------|-------------|-------------|------------|",
    ]

    for r in results:
        cond  = r["condition"]
        score = scores.get(cond, 0.0)
        flag  = " ✓" if score >= 0.95 else (" !" if score >= 0.75 else " ✗")
        lines.append(
            f"| `{cond}` "
            f"| {fmt(r['success_rate'], pct=True)} "
            f"| {fmt(r['collision_rate'], pct=True)} "
            f"| {fmt(r['intervention_rate'])} "
            f"| {r['min_ttc_s'] if r['min_ttc_s'] is not None else '—'} "
            f"| {fmt(r['perception_confidence'])} "
            f"| {score:.3f}{flag} |"
        )

    lines += [
        "",
        "Legend: ✓ ≥ 0.95 (robust), ! ≥ 0.75 (acceptable), ✗ < 0.75 (degraded)",
        "",
        "## Baseline Reference",
        "",
        f"- Success rate:       {fmt(baseline.get('success_rate'), pct=True)}",
        f"- Collision rate:     {fmt(baseline.get('collision_rate'), pct=True)}",
        f"- Intervention rate:  {fmt(baseline.get('intervention_rate'))}",
        f"- Min TTC (s):        {baseline.get('min_ttc_s', '—')}",
        "",
        "## Degradation Axis Analysis",
        "",
        "### Image Blur (blur_20 / blur_40 / blur_60)",
        "",
        "Gaussian blur simulates camera motion shake.  The DegradedAdapter adds proportional "
        "waypoint noise to model increased VLA uncertainty under degraded visual input. "
        "CBF-QP safety filtering is unaffected (lidar dropout = 0).",
        "",
        "### Low Light (low_light_30 / low_light_60)",
        "",
        "Brightness reduction simulates dim hospital corridors at night. "
        "Action noise is calibrated to match typical confidence degradation of "
        "vision-language models under low-SNR images.",
        "",
        "### LiDAR Dropout (lidar_dropout_10 / lidar_dropout_30)",
        "",
        "Obstacle detections are randomly withheld from the CBF-QP filter at the specified "
        "rate.  This directly reduces the safety filter's situational awareness: the robot "
        "may fail to slow down for obstacles it cannot detect.  This is the highest-fidelity "
        "degradation in the suite.",
        "",
        "### Combined Degradation",
        "",
        "Simultaneous blur + low-light + LiDAR dropout at moderate severity. "
        "Represents the realistic worst case where multiple sensor systems degrade together.",
        "",
        "## Output Files",
        "",
        "| File | Description |",
        "|------|-------------|",
        "| `degradation_matrix.csv` | Per-condition aggregate metrics table |",
        "| `degradation_summary.json` | Full results + robustness scores |",
        "| `robustness_score.png` | Bar chart of per-condition robustness |",
        "| `safety_zone_heatmap.png` | GREEN/AMBER/RED time fractions per condition |",
        "",
        "---",
        "_Generated by run_sensor_degradation.py · FleetSafe VisualNav Benchmark_",
    ]

    out.write_text("\n".join(lines))
    print(f"[report] → {out}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--seeds", default="dev",
                        help="Seed mode: smoke (3), dev (10), paper (50), or comma list")
    parser.add_argument("--out", default=None,
                        help="Output directory (default: simulations/degradation_<timestamp>)")
    parser.add_argument("--conditions", default=None,
                        help="Comma-separated subset of conditions to run (default: all)")
    args = parser.parse_args()

    seeds = get_seeds(args.seeds)
    ts    = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"degradation_{ts}"
    out_dir = Path(args.out) if args.out else REPO_ROOT / "simulations" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    all_conditions = list(DEGRADATION_SUITE.keys())
    if args.conditions:
        all_conditions = [c.strip() for c in args.conditions.split(",")]
        unknown = [c for c in all_conditions if c not in DEGRADATION_SUITE]
        if unknown:
            print(f"[ERROR] Unknown conditions: {unknown}")
            print(f"Available: {list(DEGRADATION_SUITE.keys())}")
            return 1

    print(f"\n{'='*60}")
    print(f"Scenario 3: Sensor Degradation Suite")
    print(f"  seeds:      {len(seeds)} ({args.seeds})")
    print(f"  conditions: {len(all_conditions)}")
    print(f"  scene:      mid_crossing")
    print(f"  out_dir:    {out_dir}")
    print(f"{'='*60}\n")

    results: list[dict] = []

    for i, cond_name in enumerate(all_conditions, 1):
        cfg = DEGRADATION_SUITE[cond_name]
        print(f"\n[{i}/{len(all_conditions)}] {cond_name}: {cfg.description}")
        t0 = time.perf_counter()
        result = run_condition(cond_name, seeds, out_dir, run_id)
        elapsed = time.perf_counter() - t0
        results.append(result)
        print(
            f"  success={result['success_rate']:.3f}  "
            f"collision={result['collision_rate']:.3f}  "
            f"intervention={result['intervention_rate']:.3f}  "
            f"min_ttc={result['min_ttc_s']}s  "
            f"({elapsed:.1f}s)"
        )

    # ── Compute robustness scores ────────────────────────────────────────────
    baseline   = next((r for r in results if r["condition"] == "baseline"), results[0])
    non_base   = {r["condition"]: r for r in results if r["condition"] != "baseline"}
    scores     = compute_degradation_robustness_score(baseline, non_base)
    scores["baseline"] = 1.0  # baseline is always 1.0 by definition

    # PROVEN:
    #   1. ≥10 seeds per condition (statistical reliability)
    #   2. All non-baseline robustness scores ≥ 0.95 (≤5% degradation)
    #   3. At least one degraded condition shows CBF intervention > 0
    #      (proves the safety layer stays active under degradation)
    n_seeds_ok    = len(seeds) >= 10
    all_robust    = all(v >= 0.95 for k, v in scores.items() if k != "baseline")
    cbf_active    = any(
        r["intervention_rate"] > 0.0
        for r in results if r["condition"] != "baseline"
    )
    proven        = n_seeds_ok and all_robust and cbf_active

    print(f"\n{'='*60}")
    print(f"ROBUSTNESS SCORES:")
    for cond, score in sorted(scores.items()):
        flag = "✓ ROBUST" if score >= 0.95 else ("! ACCEPTABLE" if score >= 0.75 else "✗ DEGRADED")
        print(f"  {cond:30s}  {score:.4f}  {flag}")
    print(f"\nSeeds OK (≥10):   {n_seeds_ok}  ({len(seeds)} seeds)")
    print(f"All robust (≥0.95): {all_robust}")
    print(f"STATUS: {'PROVEN' if proven else 'RECORDED_ONLY'}")
    print(f"{'='*60}\n")

    # ── Outputs ──────────────────────────────────────────────────────────────
    write_degradation_matrix(results, out_dir / "degradation_matrix.csv")
    write_degradation_summary(results, scores, run_id, len(seeds), proven,
                              out_dir / "degradation_summary.json")
    plot_robustness_scores(scores, out_dir / "robustness_score.png")
    plot_safety_zone_heatmap(results, out_dir / "safety_zone_heatmap.png")
    write_degradation_report(results, scores, run_id, len(seeds), proven,
                             out_dir / "sensor_degradation_report.md")

    print(f"\n[done] All outputs written to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
