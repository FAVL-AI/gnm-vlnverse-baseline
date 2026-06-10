"""
generate_figures.py — Generate publication-quality figures from the FleetSafe benchmark.

Usage:
  python scripts/paper/generate_figures.py --out figures/ [--show]

Generates:
  fig1_corridor_collision.pdf    — RAW vs FS collision rate by model × backend
  fig2_cbf_intervention.pdf      — CBF intervention rate (FS mode) by model × backend
  fig3_evidence_chain.pdf        — Evidence tier ladder (MUJOCO → ISAAC → REAL)
  fig4_model_agnostic.pdf        — Model-independent safety: all 3 backbones, both backends
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "command-center"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
try:
    from scipy.stats import proportion_confint
    _SCIPY = True
except ImportError:
    _SCIPY = False

from backend.services.publication_run_scanner import cross_backend_comparison
from backend.services.paper_artifact_exporter import paper_exporter


# ── Styling ───────────────────────────────────────────────────────────────────

MODELS       = ["GNM", "ViNT", "NoMaD"]
MODEL_COLORS = {"GNM": "#60a5fa", "ViNT": "#f472b6", "NoMaD": "#34d399"}
BACKEND_COLORS = {"mujoco": "#a78bfa", "isaaclab": "#fb923c"}
BACKEND_LABELS = {"mujoco": "MuJoCo (PROVEN)", "isaaclab": "Isaac Sim"}

plt.rcParams.update({
    "font.family":    "monospace",
    "font.size":      10,
    "axes.linewidth": 0.8,
    "axes.grid":      True,
    "grid.alpha":     0.3,
    "grid.linewidth": 0.5,
    "figure.dpi":     150,
})


def _get_row(cb: dict, backend: str, model: str, fleetsafe: bool) -> dict:
    for r in cb.get(backend, {}).get("rows", []):
        if (r["model"].lower() == model.lower()
                and r["scene"] == "hospital_corridor"
                and r["fleetsafe"] == fleetsafe):
            return r
    return {}


def _pct(v: float | None) -> float:
    return (v or 0.0) * 100.0


def _wilson_ci_pct(rate: float | None, n: int) -> tuple[float, float]:
    """Wilson score 95% CI, returned as (lower%, upper%) for yerr computation."""
    if rate is None or n <= 0 or not _SCIPY:
        return (0.0, 0.0)
    lo, hi = proportion_confint(round(rate * n), n, alpha=0.05, method="wilson")
    return (round((rate - lo) * 100, 1), round((hi - rate) * 100, 1))


def fig1_corridor_collision(cb: dict, out_dir: Path, show: bool) -> None:
    """Fig 1: RAW vs FS collision rate, both backends, all 3 models."""
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    fig.suptitle(
        "Hospital Corridor — Collision Rate: RAW vs FleetSafe",
        fontsize=12, fontweight="bold", y=1.02,
    )

    x = np.arange(len(MODELS))
    w = 0.35

    for ax, backend in zip(axes, ["mujoco", "isaaclab"]):
        rows_raw = [_get_row(cb, backend, m, False) for m in MODELS]
        rows_fs  = [_get_row(cb, backend, m, True)  for m in MODELS]
        raw_vals = [_pct(r.get("collision_rate")) for r in rows_raw]
        fs_vals  = [_pct(r.get("collision_rate")) for r in rows_fs]
        n_seeds  = cb.get(backend, {}).get("n_seeds", 0)
        proven   = cb.get(backend, {}).get("proven", False)

        # Wilson 95% CI error bars
        raw_ci = [_wilson_ci_pct(r.get("collision_rate"), r.get("n_episodes", n_seeds)) for r in rows_raw]
        fs_ci  = [_wilson_ci_pct(r.get("collision_rate"), r.get("n_episodes", n_seeds)) for r in rows_fs]
        raw_err = np.array([[c[0] for c in raw_ci], [c[1] for c in raw_ci]])
        fs_err  = np.array([[c[0] for c in fs_ci],  [c[1] for c in fs_ci]])

        bars_raw = ax.bar(x - w/2, raw_vals, w, label="RAW", color="#ef4444", alpha=0.8,
                          edgecolor="white", yerr=raw_err, capsize=3, error_kw={"linewidth": 0.8, "ecolor": "#991b1b"})
        bars_fs  = ax.bar(x + w/2, fs_vals,  w, label="FS",  color="#22c55e", alpha=0.8,
                          edgecolor="white", yerr=fs_err,  capsize=3, error_kw={"linewidth": 0.8, "ecolor": "#166534"})

        # Value labels
        for bar, val in zip(bars_raw, raw_vals):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 3,
                        f"{val:.0f}%", ha="center", va="bottom", fontsize=8)
        for bar, val in zip(bars_fs, fs_vals):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 3,
                        f"{val:.0f}%", ha="center", va="bottom", fontsize=8)

        proven_label = "PROVEN ✓" if proven else f"PROVISIONAL ({n_seeds or '?'} seeds)"
        ax.set_title(
            f"{BACKEND_LABELS[backend]}\n[{proven_label}]",
            fontsize=9, color=BACKEND_COLORS[backend],
        )
        ax.set_xticks(x)
        ax.set_xticklabels(MODELS)
        ax.set_ylabel("Collision Rate (%)" if backend == "mujoco" else "")
        ax.set_ylim(0, 115)
        ax.legend(fontsize=8)
        ax.axhline(5, color="orange", linewidth=0.8, linestyle="--", alpha=0.6, label="5% threshold")

    plt.tight_layout()
    path = out_dir / "fig1_corridor_collision.pdf"
    fig.savefig(path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close()
    print(f"  ✓ {path}")


def fig2_cbf_intervention(cb: dict, out_dir: Path, show: bool) -> None:
    """Fig 2: CBF intervention rate in FS mode."""
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    fig.suptitle(
        "Hospital Corridor — CBF Intervention Rate (FleetSafe mode)",
        fontsize=12, fontweight="bold", y=1.02,
    )

    x = np.arange(len(MODELS))
    w = 0.5

    for ax, backend in zip(axes, ["mujoco", "isaaclab"]):
        rows_fs = [_get_row(cb, backend, m, True) for m in MODELS]
        ir_vals = [_pct(r.get("intervention_rate_mean")) for r in rows_fs]
        n_seeds = cb.get(backend, {}).get("n_seeds", 0)
        # IR is a rate per step — use Wilson CI treating it as a Bernoulli proportion
        ir_ci  = [_wilson_ci_pct(r.get("intervention_rate_mean"), r.get("n_episodes", n_seeds)) for r in rows_fs]
        ir_err = np.array([[c[0] for c in ir_ci], [c[1] for c in ir_ci]])
        colors = [MODEL_COLORS[m] for m in MODELS]
        bars = ax.bar(x, ir_vals, w, color=colors, alpha=0.85, edgecolor="white",
                      yerr=ir_err, capsize=3, error_kw={"linewidth": 0.8, "ecolor": "#475569"})

        for bar, val in zip(bars, ir_vals):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5,
                        f"{val:.1f}%", ha="center", va="bottom", fontsize=8)

        ax.set_title(f"{BACKEND_LABELS[backend]}", fontsize=9,
                     color=BACKEND_COLORS[backend])
        ax.set_xticks(x)
        ax.set_xticklabels(MODELS)
        ax.set_ylabel("CBF Intervention Rate (%)" if backend == "mujoco" else "")
        ax.set_ylim(0, 85)
        ax.legend(
            handles=[mpatches.Patch(color=MODEL_COLORS[m], label=m) for m in MODELS],
            fontsize=8,
        )

    plt.tight_layout()
    path = out_dir / "fig2_cbf_intervention.pdf"
    fig.savefig(path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close()
    print(f"  ✓ {path}")


def fig3_evidence_chain(out_dir: Path, show: bool, cb: dict | None = None) -> None:
    """Fig 3: Evidence tier ladder diagram (dynamic from scanner data)."""
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.axis("off")

    # Dynamic status from scanner
    mujoco_proven = cb["mujoco"]["proven"] if cb else False
    isaac_proven  = cb["isaaclab"]["proven"] if cb else False
    isaac_pct     = cb["isaaclab"].get("progress_pct", 0) if cb else 0

    mujoco_detail = (
        "MuJoCo physics, procedural obs\n50 seeds · PROVEN ✓"
        if mujoco_proven else
        "MuJoCo physics, procedural obs\nIn progress"
    )
    isaac_detail = (
        "Isaac Sim + RTX, invisible map-hazards\n50 seeds · PROVEN ✓"
        if isaac_proven else
        f"Isaac Sim + RTX, invisible map-hazards\n{isaac_pct:.0f}% complete · In progress"
    )
    mujoco_color = "#22c55e" if mujoco_proven else "#a78bfa"
    isaac_color  = "#22c55e" if isaac_proven  else "#fb923c"

    tiers = [
        ("SIM-MOCK",   "#64748b", "Random walk, no vision\n(pipeline validation only)"),
        ("SIM-MUJOCO", mujoco_color, mujoco_detail),
        ("SIM-ISAAC",  isaac_color,  isaac_detail),
        ("REAL-PROVEN","#22c55e", "Yahboom M3Pro, ROS2, bag evidence\nPending physical runs"),
    ]

    y_positions = [0.80, 0.57, 0.34, 0.11]
    for (label, color, detail), y in zip(tiers, y_positions):
        # Box
        rect = mpatches.FancyBboxPatch(
            (0.05, y - 0.07), 0.90, 0.18,
            boxstyle="round,pad=0.02", linewidth=1.5,
            edgecolor=color, facecolor=color + "18",
        )
        ax.add_patch(rect)
        ax.text(0.12, y + 0.02, label, fontsize=11, fontweight="bold", color=color,
                fontfamily="monospace", transform=ax.transAxes, va="center")
        ax.text(0.12, y - 0.035, detail, fontsize=8, color="#94a3b8",
                transform=ax.transAxes, va="center")

        # Arrow to next tier
        if y > 0.15:
            ax.annotate("", xy=(0.50, y - 0.075), xytext=(0.50, y - 0.07 - 0.01),
                        xycoords="axes fraction", textcoords="axes fraction",
                        arrowprops=dict(arrowstyle="->", color="#475569", lw=1.5))

    ax.set_title("FleetSafe Evidence Chain — Tier Ladder",
                 fontsize=12, fontweight="bold", pad=12)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    path = out_dir / "fig3_evidence_chain.pdf"
    fig.savefig(path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close()
    print(f"  ✓ {path}")


def fig4_model_agnostic(cb: dict, out_dir: Path, show: bool) -> None:
    """Fig 4: Model-independent safety — key paper figure."""
    fig, ax = plt.subplots(figsize=(9, 5))

    backends    = ["mujoco", "isaaclab"]
    n_models    = len(MODELS)
    n_backends  = len(backends)
    group_w     = 0.7
    bar_w       = group_w / (n_models * 2 + 1)

    n_seeds = {b: cb.get(b, {}).get("n_seeds", 50) for b in backends}
    for gi, backend in enumerate(backends):
        for mi, model in enumerate(MODELS):
            raw_row = _get_row(cb, backend, model, False)
            fs_row  = _get_row(cb, backend, model, True)
            raw_v = _pct(raw_row.get("collision_rate"))
            fs_v  = _pct(fs_row.get("collision_rate"))
            n     = raw_row.get("n_episodes", n_seeds[backend])

            base_x = gi * (n_models * 2 * bar_w + 0.3) + mi * 2 * bar_w
            color  = MODEL_COLORS[model]

            # CI error bars
            raw_ci = _wilson_ci_pct(raw_row.get("collision_rate"), n) if raw_row else (0, 0)
            fs_ci  = _wilson_ci_pct(fs_row.get("collision_rate"),  n) if fs_row  else (0, 0)

            b1 = ax.bar(base_x,           raw_v, bar_w, color=color, alpha=0.5,
                        hatch="///", edgecolor=color, linewidth=0.5,
                        yerr=[[raw_ci[0]], [raw_ci[1]]], capsize=2,
                        error_kw={"linewidth": 0.7, "ecolor": color, "alpha": 0.6})
            b2 = ax.bar(base_x + bar_w,   fs_v,  bar_w, color=color, alpha=0.9,
                        edgecolor=color, linewidth=0.5,
                        yerr=[[fs_ci[0]], [fs_ci[1]]], capsize=2,
                        error_kw={"linewidth": 0.7, "ecolor": "#166534", "alpha": 0.6})

            if raw_v > 0:
                ax.text(base_x + bar_w/2, raw_v + 3, f"{raw_v:.0f}%",
                        ha="center", va="bottom", fontsize=7, color=color)
            if not fs_row:
                ax.text(base_x + bar_w + bar_w/2, 2, "—",
                        ha="center", va="bottom", fontsize=7, color="#64748b")
            elif fs_v == 0 and raw_v > 0:
                ax.text(base_x + bar_w + bar_w/2, 2, "0%",
                        ha="center", va="bottom", fontsize=7, color="#22c55e")
            # Annotate NoMaD Isaac RAW: naturally avoids (no collision without FleetSafe)
            if model == "NoMaD" and backend == "isaaclab" and raw_v == 0 and raw_row:
                min_d = raw_row.get("min_obstacle_distance_m_mean") or 0
                ax.text(base_x + bar_w/2, 4, f"avoids\n({min_d:.1f}m)",
                        ha="center", va="bottom", fontsize=6, color="#22c55e",
                        fontstyle="italic")

        # Backend label
        bx_center = gi * (n_models * 2 * bar_w + 0.3) + n_models * bar_w
        ax.text(bx_center, -8, BACKEND_LABELS[backend], ha="center", va="top",
                fontsize=9, color=BACKEND_COLORS[backend], fontweight="bold")

    # Legend
    legend_elements = (
        [mpatches.Patch(facecolor=MODEL_COLORS[m], label=m) for m in MODELS]
        + [mpatches.Patch(facecolor="#94a3b8", hatch="///", label="RAW",
                          alpha=0.5, edgecolor="#94a3b8"),
           mpatches.Patch(facecolor="#94a3b8", label="FS (FleetSafe)")]
    )
    ax.legend(handles=legend_elements, fontsize=8, loc="upper right",
              ncol=2, framealpha=0.9)

    ax.set_ylabel("Collision Rate (%)")
    ax.set_ylim(-12, 120)
    ax.set_xticks([])
    ax.set_title(
        "Navigation-Paradigm-Dependent Safety: FleetSafe on 3 VLA Backbones × 2 Physics Backends\n"
        "(Hospital Corridor — RAW vs FleetSafe | MuJoCo: visible obstacles · Isaac: invisible map hazards)",
        fontsize=10, fontweight="bold",
    )
    ax.axhline(5, color="orange", linewidth=0.8, linestyle="--", alpha=0.6)
    ax.text(0.01, 6, "5% safety threshold", fontsize=7, color="orange", alpha=0.8)

    path = out_dir / "fig4_model_agnostic.pdf"
    fig.savefig(path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close()
    print(f"  ✓ {path}")


def fig5_safety_margin(cb: dict, out_dir: Path, show: bool) -> None:
    """Fig 5: Min obstacle distance (safety margin) — RAW vs FS, corridor scene."""
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), sharey=False)
    fig.suptitle(
        "Hospital Corridor — Minimum Obstacle Distance: RAW vs FleetSafe",
        fontsize=12, fontweight="bold",
    )
    fig.subplots_adjust(top=0.88)

    x = np.arange(len(MODELS))
    w = 0.35

    for ax, backend in zip(axes, ["mujoco", "isaaclab"]):
        rows_raw = [_get_row(cb, backend, m, False) for m in MODELS]
        rows_fs  = [_get_row(cb, backend, m, True)  for m in MODELS]
        raw_vals = [r.get("min_obstacle_distance_m_mean") or 0.0 for r in rows_raw]
        fs_vals  = [r.get("min_obstacle_distance_m_mean") or 0.0 for r in rows_fs]

        bars_raw = ax.bar(x - w/2, raw_vals, w, label="RAW",       color="#ef4444", alpha=0.8, edgecolor="white")
        bars_fs  = ax.bar(x + w/2, fs_vals,  w, label="FleetSafe", color="#22c55e", alpha=0.8, edgecolor="white")

        for bar, val in zip(bars_raw, raw_vals):
            if val > 0.01:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                        f"{val:.2f}m", ha="center", va="bottom", fontsize=7)
        for bar, val in zip(bars_fs, fs_vals):
            if val > 0.01:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                        f"{val:.2f}m", ha="center", va="bottom", fontsize=7)

        proven = cb.get(backend, {}).get("proven", False)
        proven_label = "PROVEN ✓" if proven else "provisional"
        ax.set_title(f"{BACKEND_LABELS[backend]}\n[{proven_label}]",
                     fontsize=9, color=BACKEND_COLORS[backend])
        ax.set_xticks(x)
        ax.set_xticklabels(MODELS)
        ax.set_ylabel("Min. Obstacle Distance (m)" if backend == "mujoco" else "")
        ax.set_ylim(0, max(max(raw_vals + fs_vals, default=1.0) * 1.25, 1.0))
        ax.axhline(0.30, color="orange", linewidth=0.8, linestyle="--", alpha=0.6)
        ax.text(0.01, 0.32, "0.30m safety margin", fontsize=7, color="orange",
                transform=ax.get_yaxis_transform(), alpha=0.8)
        ax.legend(fontsize=8)

    plt.tight_layout()
    path = out_dir / "fig5_safety_margin.pdf"
    fig.savefig(path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close()
    print(f"  ✓ {path}")


def fig6_latency_overhead(cb: dict, out_dir: Path, show: bool) -> None:
    """Fig 6: Inference latency (ms) and CBF command deviation — real-time feasibility."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))
    fig.suptitle(
        "Real-Time Feasibility: Inference Latency & CBF Command Overhead",
        fontsize=12, fontweight="bold",
    )
    fig.subplots_adjust(top=0.88)

    x = np.arange(len(MODELS))
    w = 0.30

    for ax, backend, side in [(ax1, "mujoco", "left"), (ax2, "isaaclab", "right")]:
        rows_raw = [_get_row(cb, backend, m, False) for m in MODELS]
        rows_fs  = [_get_row(cb, backend, m, True)  for m in MODELS]

        lat_raw = [r.get("inference_latency_ms_mean") or 0.0 for r in rows_raw]
        lat_fs  = [r.get("inference_latency_ms_mean") or 0.0 for r in rows_fs]
        dev_fs  = [r.get("raw_vs_safe_delta_l2_mean") or 0.0 for r in rows_fs]

        colors  = [MODEL_COLORS[m] for m in MODELS]
        bars_raw = ax.bar(x - w, lat_raw, w, label="Latency RAW",
                          color=colors, alpha=0.5, hatch="///", edgecolor="white")
        bars_fs  = ax.bar(x,     lat_fs,  w, label="Latency FS",
                          color=colors, alpha=0.8, edgecolor="white")

        ax2_twin = ax.twinx()
        ax2_twin.bar(x + w, [d * 100 for d in dev_fs], w,
                     color="#94a3b8", alpha=0.6, label="Cmd deviation ×100")
        ax2_twin.set_ylabel("Cmd L2 deviation (×100)", fontsize=8, color="#64748b")
        ax2_twin.tick_params(axis="y", labelcolor="#64748b", labelsize=7)
        ax2_twin.set_ylim(0, max([d * 100 for d in dev_fs] or [1]) * 2.5)

        for bar, val in zip(bars_raw, lat_raw):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                        f"{val:.0f}", ha="center", va="bottom", fontsize=6)

        ax.axhline(100, color="orange", linewidth=0.8, linestyle="--", alpha=0.6)
        ax.text(0.01, 102, "100ms RT threshold", fontsize=7, color="orange",
                transform=ax.get_yaxis_transform(), alpha=0.8)
        ax.set_title(f"{BACKEND_LABELS[backend]}", fontsize=9,
                     color=BACKEND_COLORS[backend])
        ax.set_xticks(x)
        ax.set_xticklabels(MODELS)
        ax.set_ylabel("Inference Latency (ms)")
        ax.set_ylim(0, max(lat_raw + lat_fs or [1]) * 1.5)
        ax.legend(
            handles=[mpatches.Patch(color=MODEL_COLORS[m], label=m) for m in MODELS],
            fontsize=7, loc="upper left",
        )

    path = out_dir / "fig6_latency_overhead.pdf"
    fig.savefig(path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close()
    print(f"  ✓ {path}")


def fig7_traffic_light(cb: dict, out_dir: Path, show: bool) -> None:
    """Fig 7: Traffic-light safety zone distribution — steps in green/amber/red per FS episode."""
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    fig.suptitle(
        "Safety Zone Distribution (FS mode) — Hospital Corridor",
        fontsize=12, fontweight="bold",
    )
    fig.subplots_adjust(top=0.88)

    x = np.arange(len(MODELS))
    w = 0.22

    for ax, backend in zip(axes, ["mujoco", "isaaclab"]):
        rows_fs = [_get_row(cb, backend, m, True) for m in MODELS]
        green  = [r.get("steps_green_mean") or 0.0 for r in rows_fs]
        amber  = [r.get("steps_amber_mean") or 0.0 for r in rows_fs]
        red    = [r.get("steps_red_mean")   or 0.0 for r in rows_fs]

        # Total steps for normalisation
        totals = [g + a + r_ for g, a, r_ in zip(green, amber, red)]
        if not any(t > 0 for t in totals):
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes, color="#64748b")
            continue

        green_pct = [g / t * 100 if t > 0 else 0 for g, t in zip(green, totals)]
        amber_pct = [a / t * 100 if t > 0 else 0 for a, t in zip(amber, totals)]
        red_pct   = [r_ / t * 100 if t > 0 else 0 for r_, t in zip(red, totals)]

        # Stacked bar
        b1 = ax.bar(x, green_pct, w * 2.5, label="Green (safe)", color="#22c55e", alpha=0.85)
        b2 = ax.bar(x, amber_pct, w * 2.5, bottom=green_pct, label="Amber (near)", color="#f59e0b", alpha=0.85)
        b3 = ax.bar(x, red_pct,   w * 2.5, bottom=[g + a for g, a in zip(green_pct, amber_pct)],
                    label="Red (violation)", color="#ef4444", alpha=0.85)

        for i, (g, a, r_) in enumerate(zip(green_pct, amber_pct, red_pct)):
            if g > 5:
                ax.text(i, g / 2, f"{g:.0f}%", ha="center", va="center", fontsize=7, color="white")
            if a > 5:
                ax.text(i, g + a / 2, f"{a:.0f}%", ha="center", va="center", fontsize=7, color="white")

        proven = cb.get(backend, {}).get("proven", False)
        ax.set_title(f"{BACKEND_LABELS[backend]}\n{'PROVEN ✓' if proven else 'provisional'}",
                     fontsize=9, color=BACKEND_COLORS[backend])
        ax.set_xticks(x)
        ax.set_xticklabels(MODELS)
        ax.set_ylabel("% of episode steps" if backend == "mujoco" else "")
        ax.set_ylim(0, 115)
        ax.legend(fontsize=7, loc="lower right")

    path = out_dir / "fig7_traffic_light.pdf"
    fig.savefig(path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close()
    print(f"  ✓ {path}")


def fig8_collision_heatmap(cb: dict, out_dir: Path, show: bool) -> None:
    """Fig 8: Full collision rate heatmap — model × scene × backend × mode."""
    SCENES_SHORT = {
        "hospital_corridor":       "Corridor",
        "hospital_icu_approach":   "ICU",
        "hospital_elevator_lobby": "Elevator",
    }
    SCENES = list(SCENES_SHORT.keys())
    BACKENDS = ["mujoco", "isaaclab"]

    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    fig.suptitle(
        "Collision Rate Heatmap — All Models × Scenes × Backends × Modes",
        fontsize=12, fontweight="bold",
    )
    fig.subplots_adjust(top=0.88, hspace=0.45, wspace=0.3)

    for row_i, backend in enumerate(BACKENDS):
        for col_i, mode_fs in enumerate([False, True]):
            ax = axes[row_i][col_i]
            rows_all = cb.get(backend, {}).get("rows", [])
            mode_label = "FleetSafe (FS)" if mode_fs else "RAW"
            title = f"{'Isaac Sim' if backend == 'isaaclab' else 'MuJoCo'} — {mode_label}"

            # Build matrix: rows=models, cols=scenes
            mat = np.full((len(MODELS), len(SCENES)), np.nan)
            for mi, model in enumerate(MODELS):
                for si, scene in enumerate(SCENES):
                    r = next(
                        (x for x in rows_all
                         if x["model"].lower() == model.lower()
                         and x["scene"] == scene
                         and x["fleetsafe"] == mode_fs),
                        None,
                    )
                    if r is not None:
                        mat[mi, si] = r["collision_rate"] * 100

            cmap = plt.cm.RdYlGn_r
            cmap.set_bad(color="#1e293b")  # dark for missing data
            im = ax.imshow(mat, cmap=cmap, vmin=0, vmax=100, aspect="auto")

            ax.set_xticks(range(len(SCENES)))
            ax.set_xticklabels([SCENES_SHORT[s] for s in SCENES], fontsize=8)
            ax.set_yticks(range(len(MODELS)))
            ax.set_yticklabels(MODELS, fontsize=8)
            ax.set_title(title, fontsize=9, color=BACKEND_COLORS[backend])

            # Annotate cells
            for mi in range(len(MODELS)):
                for si in range(len(SCENES)):
                    v = mat[mi, si]
                    if not np.isnan(v):
                        text_color = "white" if v > 60 or v < 20 else "black"
                        ax.text(si, mi, f"{v:.0f}%", ha="center", va="center",
                                fontsize=9, fontweight="bold", color=text_color)
                    else:
                        ax.text(si, mi, "—", ha="center", va="center",
                                fontsize=8, color="#64748b")

            plt.colorbar(im, ax=ax, shrink=0.8, label="Collision Rate (%)")

    path = out_dir / "fig8_collision_heatmap.pdf"
    fig.savefig(path, bbox_inches="tight")
    if show:
        plt.show()
    plt.close()
    print(f"  ✓ {path}")


def _save(fig: plt.Figure, path_pdf: Path, png_dir: Path | None, show: bool) -> None:
    """Save as PDF (always) and optionally as PNG for web embedding."""
    fig.savefig(path_pdf, bbox_inches="tight")
    if png_dir:
        png_path = png_dir / path_pdf.with_suffix(".png").name
        fig.savefig(png_path, bbox_inches="tight", dpi=120)
    if show:
        plt.show()
    plt.close()
    print(f"  ✓ {path_pdf}{f'  +  {png_path}' if png_dir else ''}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate FleetSafe paper figures")
    parser.add_argument("--out",  default="figures", help="Output directory for PDFs")
    parser.add_argument("--png",  default=None,
                        help="Optional directory for PNG copies (for web/frontend)")
    parser.add_argument("--show", action="store_true", help="Display figures interactively")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    png_dir = Path(args.png) if args.png else None
    if png_dir:
        png_dir.mkdir(parents=True, exist_ok=True)

    print("[FleetSafe Figure Generator]")
    print(f"  PDF output: {out_dir.resolve()}")
    if png_dir:
        print(f"  PNG output: {png_dir.resolve()}")
    print()

    cb = cross_backend_comparison()
    print(f"  MuJoCo: proven={cb['mujoco']['proven']} n_seeds={cb['mujoco']['n_seeds']}")
    print(f"  Isaac:  proven={cb['isaaclab']['proven']} n_seeds={cb['isaaclab']['n_seeds']}")
    print()

    # Build dynamic backend labels that reflect actual proven/in-progress status
    def _backend_label(backend: str) -> str:
        bd = cb[backend]
        if bd["proven"]:
            return f"{backend.upper()} (PROVEN ✓)"
        n = bd["n_seeds"] or "?"
        n_rows = len(bd.get("rows", []))
        if n_rows > 0:
            return f"Isaac Sim ({n} seeds, {n_rows//6 if n_rows >= 6 else n_rows} model(s)/in progress)"
        return f"Isaac Sim (in progress)"
    BACKEND_LABELS["mujoco"]   = _backend_label("mujoco")
    BACKEND_LABELS["isaaclab"] = _backend_label("isaaclab")

    print("[Generating figures...]")
    fig1_corridor_collision(cb, out_dir, args.show)
    fig2_cbf_intervention(cb, out_dir, args.show)
    fig3_evidence_chain(out_dir, args.show, cb=cb)
    fig4_model_agnostic(cb, out_dir, args.show)
    fig5_safety_margin(cb, out_dir, args.show)
    fig6_latency_overhead(cb, out_dir, args.show)
    fig7_traffic_light(cb, out_dir, args.show)
    fig8_collision_heatmap(cb, out_dir, args.show)

    # Export PNGs for web embedding
    if png_dir:
        print("\n[Exporting PNGs for web...]")
        plt.rcParams["figure.dpi"] = 120
        for fn, kw in [
            (fig1_corridor_collision, {"cb": cb, "out_dir": png_dir, "show": False}),
            (fig2_cbf_intervention,   {"cb": cb, "out_dir": png_dir, "show": False}),
            (fig3_evidence_chain,     {"out_dir": png_dir, "show": False, "cb": cb}),
            (fig4_model_agnostic,     {"cb": cb, "out_dir": png_dir, "show": False}),
            (fig5_safety_margin,      {"cb": cb, "out_dir": png_dir, "show": False}),
            (fig6_latency_overhead,   {"cb": cb, "out_dir": png_dir, "show": False}),
            (fig7_traffic_light,      {"cb": cb, "out_dir": png_dir, "show": False}),
            (fig8_collision_heatmap,  {"cb": cb, "out_dir": png_dir, "show": False}),
        ]:
            fn(**kw)
        # Rename .pdf in png_dir to .png
        for p in png_dir.glob("*.pdf"):
            p.rename(p.with_suffix(".png"))
        print(f"  ✓ {len(list(png_dir.glob('*.png')))} PNGs in {png_dir}/")

    n_pdf = len(list(out_dir.glob("*.pdf")))
    print(f"\n[Done] {n_pdf} PDF figures written to {out_dir}/")


if __name__ == "__main__":
    main()
