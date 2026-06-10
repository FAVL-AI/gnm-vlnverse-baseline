#!/usr/bin/env python3
"""
analyze_real_robot_session.py — Full evidence extraction from a rosbag2 session.

Uses the `rosbags` pure-Python library (pip install rosbags) — no ROS2 needed.

Outputs (written into the session directory):
  latency_stats.json          p50/p95/p99 Jetson inference latency
  motion_proof.json           odometry arc, displacement, motion verdict
  trajectory_xy.csv           timestamp_ns, x, y for every odom sample
  latency_histogram.png       all latency samples vs 50ms threshold
  trajectory_plot.png         x/y path coloured by time
  cmd_vel_plot.png            linear.x and angular.z over time
  safety_zone_timeline.png    social_risk score + zone string over time
  real_robot_session_report.md  markdown summary of the full session

Usage:
  python scripts/ros2/analyze_real_robot_session.py [--session PATH]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

SESSION_ROOT = (
    REPO_ROOT / "recordings" / "real_robot" / "session_20260519_030843"
)


# ── rosbags decoding ──────────────────────────────────────────────────────────

def _open_typestore():
    from rosbags.typesys import get_typestore, Stores
    return get_typestore(Stores.ROS2_HUMBLE)


def _iter_topic(reader, conns: dict, topic: str, typestore):
    """Yield (timestamp_ns, msg) for every message on a topic."""
    conn = conns.get(topic)
    if conn is None:
        return
    for _, ts, raw in reader.messages([conn]):
        yield ts, typestore.deserialize_cdr(raw, conn.msgtype)


# ── Latency ───────────────────────────────────────────────────────────────────

def _analyze_latency(reader, conns, typestore) -> dict:
    samples: list[float] = []
    for _, msg in _iter_topic(reader, conns, "/fleetsafe/latency", typestore):
        v = float(msg.data)
        if 0 < v < 5000:
            samples.append(v)
    if not samples:
        return {"n": 0, "status": "NO_DATA", "verdict": "No latency data"}
    s = sorted(samples)
    n = len(s)
    under50 = sum(1 for v in s if v < 50) / n
    status  = "PROVEN" if under50 >= 0.95 else "RECORDED"
    return {
        "n":              n,
        "min_ms":         round(s[0], 3),
        "p50_ms":         round(s[n // 2], 3),
        "p95_ms":         round(s[int(n * 0.95)], 3),
        "p99_ms":         round(s[int(n * 0.99)], 3),
        "max_ms":         round(s[-1], 3),
        "mean_ms":        round(sum(s) / n, 3),
        "under_50ms_pct": round(100 * under50, 1),
        "under_10ms_pct": round(100 * sum(1 for v in s if v < 10) / n, 1),
        "status":         status,
        "verdict": (
            "≥95% samples <50ms — real-time constraint SATISFIED"
            if status == "PROVEN" else
            f"Only {100*under50:.1f}% samples under 50ms"
        ),
    }


# ── Odometry ──────────────────────────────────────────────────────────────────

def _analyze_odom(reader, conns, typestore) -> tuple[dict, list[tuple[int, float, float]]]:
    """Returns (motion_proof dict, [(ts_ns, x, y), ...])."""
    traj: list[tuple[int, float, float]] = []
    for ts, msg in _iter_topic(reader, conns, "/odom_raw", typestore):
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        if abs(x) < 200 and abs(y) < 200:
            traj.append((ts, x, y))

    if len(traj) < 10:
        return {"n_odom_msgs": len(traj), "status": "NO_DATA",
                "verdict": "Insufficient odom data"}, traj

    xs = [p[1] for p in traj]
    ys = [p[2] for p in traj]
    arc = sum(
        math.hypot(traj[i][1] - traj[i-1][1], traj[i][2] - traj[i-1][2])
        for i in range(1, len(traj))
    )
    disp = math.hypot(xs[-1] - xs[0], ys[-1] - ys[0])
    dur  = (traj[-1][0] - traj[0][0]) / 1e9

    status = "PROVEN" if arc > 0.1 else "RECORDED_ONLY"
    verdict = (
        f"Robot moved {arc:.3f}m arc-length over {dur:.0f}s "
        f"(Δ displacement={disp:.3f}m). Motion PROVEN on real hardware."
        if status == "PROVEN" else
        "Minimal motion detected — robot may have been stationary."
    )
    proof = {
        "n_odom_msgs":    len(traj),
        "duration_s":     round(dur, 1),
        "start_x":        round(xs[0], 4),
        "start_y":        round(ys[0], 4),
        "end_x":          round(xs[-1], 4),
        "end_y":          round(ys[-1], 4),
        "displacement_m": round(disp, 4),
        "arc_length_m":   round(arc, 4),
        "x_range_m":      round(max(xs) - min(xs), 4),
        "y_range_m":      round(max(ys) - min(ys), 4),
        "motion_detected": arc > 0.1,
        "status":         status,
        "verdict":        verdict,
    }
    return proof, traj


# ── cmd_vel ───────────────────────────────────────────────────────────────────

def _read_cmd_vel(reader, conns, typestore) -> list[tuple[int, float, float]]:
    """Returns [(ts_ns, linear_x, angular_z), ...]."""
    out = []
    for ts, msg in _iter_topic(reader, conns, "/cmd_vel", typestore):
        out.append((ts, float(msg.linear.x), float(msg.angular.z)))
    return out


# ── Safety ────────────────────────────────────────────────────────────────────

def _read_safety(reader, conns, typestore) -> dict:
    risk  = []  # (ts_ns, risk_float)
    zones = []  # (ts_ns, zone_str)
    for ts, msg in _iter_topic(reader, conns, "/fleetsafe/social_risk", typestore):
        risk.append((ts, float(msg.data)))
    for ts, msg in _iter_topic(reader, conns, "/fleetsafe/zone", typestore):
        zones.append((ts, str(msg.data).strip()))
    return {"risk": risk, "zones": zones}


# ── Plots ─────────────────────────────────────────────────────────────────────

def _dark_fig(w: float, h: float):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("#111827")
    ax.set_facecolor("#111827")
    ax.tick_params(colors="#6b7280", labelsize=7.5)
    for sp in ax.spines.values():
        sp.set_edgecolor("#374151")
    return fig, ax


def plot_latency_histogram(latency: dict, out_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches

        n  = latency["n"]
        s  = sorted([0.0] * n)   # placeholder — we don't re-read, use stats only for title
        # We need raw samples — pass them in via side-channel CSV if needed.
        # For now build from stats (histogram shape is approximate).
        # Actual samples are written to CSV; this plot uses the real data.
        print("[plot] latency_histogram requires raw samples — skipped in stats-only mode")
        return
    except Exception as e:
        print(f"[plot] WARNING latency_histogram: {e}")


def plot_latency_histogram_raw(samples: list[float], stats: dict, out_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches

        fig, ax = _dark_fig(12, 6)
        clip = sorted(samples)[int(len(samples) * 0.999)]
        vals = [v for v in samples if v <= clip]
        n_bins = min(200, len(set(round(v, 1) for v in vals)))
        counts, edges, patches = ax.hist(vals, bins=n_bins,
                                         color="#34d399", alpha=0.75, edgecolor="none")
        for patch, left in zip(patches, edges[:-1]):
            if left >= 50:
                patch.set_facecolor("#f87171")
                patch.set_alpha(0.8)
        ax.axvline(50, color="#fbbf24", lw=1.5, ls="--", label="50ms RT threshold", zorder=5)
        s = sorted(samples)
        for lbl, pct, col in [("p50", 0.50, "#6ee7b7"), ("p99", 0.99, "#f87171")]:
            v = s[int(len(s) * pct)]
            ax.axvline(v, color=col, lw=1.0, ls=":", alpha=0.7)
            ax.text(v + 0.3, ax.get_ylim()[1] * 0.85, f"{lbl}={v:.1f}ms",
                    color=col, fontsize=7.5, fontfamily="monospace")
        ax.set_xlabel("Inference latency (ms)", color="#9ca3af", fontsize=9,
                      fontfamily="monospace")
        ax.set_ylabel("Count", color="#9ca3af", fontsize=9, fontfamily="monospace")
        ax.set_title(
            f"FleetSafe Jetson Inference Latency  ·  n={stats['n']:,}  "
            f"·  p99={stats['p99_ms']}ms  ·  {stats['under_50ms_pct']}% <50ms",
            color="#f9fafb", fontsize=10, fontfamily="monospace", pad=10,
        )
        ax.legend(handles=[
            mpatches.Patch(color="#34d399", alpha=0.75, label="<50ms (green zone)"),
            mpatches.Patch(color="#f87171", alpha=0.8,  label="≥50ms (over threshold)"),
            mpatches.Patch(color="#fbbf24", label="50ms RT limit"),
        ], loc="upper right", fontsize=7, facecolor="#1f2937",
           edgecolor="#374151", labelcolor="white")
        ax.text(0.5, -0.10,
                f"Yahboom M3Pro Jetson · FleetSafe CBF-QP · "
                f"p50={stats['p50_ms']}ms p95={stats['p95_ms']}ms p99={stats['p99_ms']}ms  "
                f"verdict: {stats['verdict']}",
                ha="center", va="top", color="#6b7280", fontsize=6.5,
                fontfamily="monospace", transform=ax.transAxes)
        out = out_dir / "latency_histogram.png"
        plt.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#111827")
        plt.close(fig)
        print(f"[plot] → {out}")
    except Exception as e:
        print(f"[plot] WARNING latency_histogram: {e}")


def plot_trajectory(traj: list[tuple[int, float, float]], stats: dict,
                    out_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        xs = [p[1] for p in traj]
        ys = [p[2] for p in traj]
        fig, ax = _dark_fig(10, 8)
        n = len(xs)
        for i in range(n - 1):
            t = i / max(n - 1, 1)
            col = f"#{int(34 + 170*t):02x}{int(211 - 100*t):02x}{int(153 - 50*t):02x}"
            ax.plot(xs[i:i+2], ys[i:i+2], color=col, lw=0.9, alpha=0.7)
        ax.scatter(xs[0],  ys[0],  s=120, color="#34d399", marker="^", zorder=8,
                   edgecolors="white", lw=0.8, label="Start")
        ax.scatter(xs[-1], ys[-1], s=120, color="#f87171", marker="s", zorder=8,
                   edgecolors="white", lw=0.8, label="End")
        ax.set_xlabel("x (m)", color="#9ca3af", fontsize=9, fontfamily="monospace")
        ax.set_ylabel("y (m)", color="#9ca3af", fontsize=9, fontfamily="monospace")
        ax.set_title(
            f"M3Pro Odometry Trajectory  ·  arc={stats['arc_length_m']:.3f}m  "
            f"·  disp={stats['displacement_m']:.3f}m  ·  {stats['duration_s']:.0f}s",
            color="#f9fafb", fontsize=10, fontfamily="monospace", pad=10,
        )
        ax.set_aspect("equal")
        ax.legend(loc="upper right", fontsize=7.5, facecolor="#1f2937",
                  edgecolor="#374151", labelcolor="white")
        out = out_dir / "trajectory_plot.png"
        plt.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#111827")
        plt.close(fig)
        print(f"[plot] → {out}")
    except Exception as e:
        print(f"[plot] WARNING trajectory_plot: {e}")


def plot_cmd_vel(cmd_vel: list[tuple[int, float, float]], out_dir: Path) -> None:
    if not cmd_vel:
        print("[plot] cmd_vel_plot: no data")
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        t0 = cmd_vel[0][0]
        ts  = [(r[0] - t0) / 1e9 for r in cmd_vel]
        vxs = [r[1] for r in cmd_vel]
        wzs = [r[2] for r in cmd_vel]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 6), sharex=True)
        fig.patch.set_facecolor("#111827")
        for ax in (ax1, ax2):
            ax.set_facecolor("#111827")
            ax.tick_params(colors="#6b7280", labelsize=7.5)
            for sp in ax.spines.values():
                sp.set_edgecolor("#374151")

        ax1.plot(ts, vxs, color="#34d399", lw=0.9, alpha=0.85)
        ax1.axhline(0, color="#374151", lw=0.5, ls="--")
        ax1.set_ylabel("linear.x (m/s)", color="#9ca3af", fontsize=9,
                       fontfamily="monospace")
        ax1.set_title(
            f"cmd_vel timeline  ·  n={len(cmd_vel)}  "
            f"·  max_vx={max(abs(v) for v in vxs):.3f} m/s",
            color="#f9fafb", fontsize=10, fontfamily="monospace", pad=8,
        )

        ax2.plot(ts, wzs, color="#60a5fa", lw=0.9, alpha=0.85)
        ax2.axhline(0, color="#374151", lw=0.5, ls="--")
        ax2.set_ylabel("angular.z (rad/s)", color="#9ca3af", fontsize=9,
                       fontfamily="monospace")
        ax2.set_xlabel("time (s)", color="#9ca3af", fontsize=9,
                       fontfamily="monospace")

        nonzero = sum(1 for v, w in zip(vxs, wzs) if abs(v) > 0.001 or abs(w) > 0.001)
        ax2.text(0.5, -0.22,
                 f"Non-zero commands: {nonzero}/{len(cmd_vel)} "
                 f"({100*nonzero/max(len(cmd_vel),1):.1f}%)",
                 ha="center", va="top", color="#6b7280", fontsize=7,
                 fontfamily="monospace", transform=ax2.transAxes)

        plt.tight_layout(pad=1.2)
        out = out_dir / "cmd_vel_plot.png"
        plt.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#111827")
        plt.close(fig)
        print(f"[plot] → {out}")
    except Exception as e:
        print(f"[plot] WARNING cmd_vel_plot: {e}")


def plot_safety_timeline(safety: dict, out_dir: Path) -> None:
    risk  = safety.get("risk", [])
    zones = safety.get("zones", [])
    if not risk and not zones:
        print("[plot] safety_zone_timeline: no data")
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = _dark_fig(14, 5)
        zone_colors = {"GREEN": "#34d399", "YELLOW": "#fbbf24", "RED": "#f87171"}

        if risk:
            t0  = risk[0][0]
            ts  = [(r[0] - t0) / 1e9 for r in risk]
            rs  = [r[1] for r in risk]
            ax.plot(ts, rs, color="#a78bfa", lw=0.9, alpha=0.85, label="social_risk")

        if zones:
            t0z = zones[0][0]
            for i, (ts_ns, z) in enumerate(zones):
                t = (ts_ns - t0z) / 1e9
                col = zone_colors.get(z, "#9ca3af")
                ax.axvspan(
                    t,
                    (zones[i+1][0] - t0z) / 1e9 if i + 1 < len(zones) else t + 1,
                    alpha=0.12, color=col,
                )

        ax.set_xlabel("time (s)", color="#9ca3af", fontsize=9, fontfamily="monospace")
        ax.set_ylabel("social risk score", color="#9ca3af", fontsize=9,
                      fontfamily="monospace")
        ax.set_ylim(-0.05, 1.05)
        ax.set_title(
            f"FleetSafe Safety Timeline  ·  "
            f"risk samples={len(risk)}  ·  zone changes={len(set(z for _, z in zones))} states",
            color="#f9fafb", fontsize=10, fontfamily="monospace", pad=8,
        )
        for label, col in zone_colors.items():
            ax.plot([], [], color=col, lw=6, alpha=0.3, label=f"zone: {label}")
        ax.legend(loc="upper right", fontsize=7, facecolor="#1f2937",
                  edgecolor="#374151", labelcolor="white")

        out = out_dir / "safety_zone_timeline.png"
        plt.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#111827")
        plt.close(fig)
        print(f"[plot] → {out}")
    except Exception as e:
        print(f"[plot] WARNING safety_zone_timeline: {e}")


# ── CSV export ────────────────────────────────────────────────────────────────

def export_trajectory_csv(traj: list[tuple[int, float, float]], out_dir: Path) -> None:
    out = out_dir / "trajectory_xy.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp_ns", "x_m", "y_m"])
        w.writerows(traj)
    print(f"[csv]  → {out}  ({len(traj)} rows)")


# ── Markdown report ───────────────────────────────────────────────────────────

def write_session_report(
    out_dir: Path,
    session_id: str,
    latency: dict,
    motion: dict,
    cmd_vel: list,
    safety: dict,
) -> None:
    lat_status  = latency.get("status", "NO_DATA")
    mot_status  = motion.get("status", "NO_DATA")
    nonzero_vel = sum(1 for _, vx, wz in cmd_vel if abs(vx) > 0.001 or abs(wz) > 0.001)

    zone_counts: dict[str, int] = {}
    for _, z in safety.get("zones", []):
        zone_counts[z] = zone_counts.get(z, 0) + 1

    lines = [
        f"# Real Robot Session Report — {session_id}",
        "",
        "## Evidence Status",
        "",
        f"| Dimension            | Status        | Key metric |",
        f"|----------------------|---------------|------------|",
        f"| Jetson inference     | **{lat_status}**  | "
        f"p99 = {latency.get('p99_ms', 'n/a')} ms, "
        f"{latency.get('under_50ms_pct', 'n/a')}% < 50 ms |",
        f"| Real-robot motion    | **{mot_status}** | "
        f"arc = {motion.get('arc_length_m', 'n/a')} m, "
        f"disp = {motion.get('displacement_m', 'n/a')} m |",
        f"| cmd_vel non-zero     | {'**PROVEN**' if nonzero_vel > 0 else 'NO_DATA'}  | "
        f"{nonzero_vel} / {len(cmd_vel)} commands |",
        "",
        "## Latency",
        "",
        f"- Samples  : {latency.get('n', 0):,}",
        f"- p50      : {latency.get('p50_ms', 'n/a')} ms",
        f"- p95      : {latency.get('p95_ms', 'n/a')} ms",
        f"- p99      : {latency.get('p99_ms', 'n/a')} ms",
        f"- max      : {latency.get('max_ms', 'n/a')} ms",
        f"- < 50 ms  : {latency.get('under_50ms_pct', 'n/a')} %",
        f"- Verdict  : {latency.get('verdict', 'n/a')}",
        "",
        "## Odometry Motion",
        "",
        f"- Messages decoded : {motion.get('n_odom_msgs', 0):,}",
        f"- Duration         : {motion.get('duration_s', 'n/a')} s",
        f"- Arc length       : {motion.get('arc_length_m', 'n/a')} m",
        f"- Displacement     : {motion.get('displacement_m', 'n/a')} m",
        f"- x range          : {motion.get('x_range_m', 'n/a')} m",
        f"- y range          : {motion.get('y_range_m', 'n/a')} m",
        f"- Verdict          : {motion.get('verdict', 'n/a')}",
        "",
        "## Velocity Commands",
        "",
        f"- Total /cmd_vel messages : {len(cmd_vel)}",
        f"- Non-zero commands        : {nonzero_vel} ({100*nonzero_vel/max(len(cmd_vel),1):.1f}%)",
        "",
        "## Safety Layer",
        "",
        f"- Social risk samples : {len(safety.get('risk', []))}",
        f"- Zone distribution   : {zone_counts}",
        "",
        "## Output Files",
        "",
        "| File | Description |",
        "|------|-------------|",
        "| `latency_stats.json`         | Latency percentiles + PROVEN verdict |",
        "| `motion_proof.json`          | Odom arc, displacement, status |",
        "| `trajectory_xy.csv`          | Raw (timestamp_ns, x, y) trajectory |",
        "| `latency_histogram.png`      | Histogram vs 50ms threshold |",
        "| `trajectory_plot.png`        | XY path coloured by time |",
        "| `cmd_vel_plot.png`           | linear.x + angular.z over time |",
        "| `safety_zone_timeline.png`   | social_risk + zone shading |",
        "| `real_robot_session_report.md` | This report |",
        "",
        "---",
        "_Generated by analyze_real_robot_session.py · FleetSafe VisualNav Benchmark_",
    ]
    out = out_dir / "real_robot_session_report.md"
    out.write_text("\n".join(lines))
    print(f"[report] → {out}")


# ── Main ──────────────────────────────────────────────────────────────────────

def analyze(bag_dir: Path, session_dir: Path) -> dict:
    from rosbags.rosbag2 import Reader

    typestore = _open_typestore()

    db3s = list(bag_dir.glob("*.db3"))
    if not db3s:
        print(f"[analyze] ERROR: no .db3 in {bag_dir}")
        sys.exit(1)
    print(f"[analyze] Bag   : {bag_dir.name}  ({db3s[0].stat().st_size // 1_048_576} MB)")

    with Reader(str(bag_dir)) as reader:
        conns = {c.topic: c for c in reader.connections}
        print(f"[analyze] Topics: {sorted(conns)}")

        # ── Decode all topics ────────────────────────────────────────────────
        print("[analyze] Decoding latency …")
        latency = _analyze_latency(reader, conns, typestore)
        print(f"[analyze]   n={latency.get('n',0)}  status={latency.get('status')}")

        # Collect raw latency samples for histogram
        lat_samples: list[float] = []
        for _, msg in _iter_topic(reader, conns, "/fleetsafe/latency", typestore):
            v = float(msg.data)
            if 0 < v < 5000:
                lat_samples.append(v)

        print("[analyze] Decoding odom …")
        motion, traj = _analyze_odom(reader, conns, typestore)
        print(f"[analyze]   arc={motion.get('arc_length_m','?')}m  "
              f"status={motion.get('status')}")

        print("[analyze] Decoding cmd_vel …")
        cmd_vel = _read_cmd_vel(reader, conns, typestore)
        nonzero = sum(1 for _, vx, wz in cmd_vel
                      if abs(vx) > 0.001 or abs(wz) > 0.001)
        print(f"[analyze]   n={len(cmd_vel)}  non-zero={nonzero}")

        print("[analyze] Decoding safety …")
        safety = _read_safety(reader, conns, typestore)
        print(f"[analyze]   risk_n={len(safety['risk'])}  zones={len(safety['zones'])}")

    # ── Write JSON outputs ───────────────────────────────────────────────────
    session_dir.mkdir(parents=True, exist_ok=True)

    (session_dir / "latency_stats.json").write_text(json.dumps(latency, indent=2))
    print(f"[json] → latency_stats.json")

    (session_dir / "motion_proof.json").write_text(json.dumps(motion, indent=2))
    print(f"[json] → motion_proof.json")

    combined = {
        "session_id":         session_dir.name,
        "bag_dir":            str(bag_dir),
        "latency":            latency,
        "motion":             motion,
        "real_time_inference": {
            "status":  latency.get("status", "NOT_VALIDATED"),
            "verdict": latency.get("verdict", ""),
            "p99_ms":  latency.get("p99_ms"),
        },
        "real_robot_motion": {
            "status":       motion.get("status", "NO_DATA"),
            "verdict":      motion.get("verdict", ""),
            "arc_length_m": motion.get("arc_length_m"),
        },
    }
    (session_dir / "session_analysis.json").write_text(json.dumps(combined, indent=2))
    print("[json] → session_analysis.json")

    # ── CSV ──────────────────────────────────────────────────────────────────
    if traj:
        export_trajectory_csv(traj, session_dir)

    # ── Plots ────────────────────────────────────────────────────────────────
    if lat_samples:
        plot_latency_histogram_raw(lat_samples, latency, session_dir)
    if traj:
        plot_trajectory(traj, motion, session_dir)
    if cmd_vel:
        plot_cmd_vel(cmd_vel, session_dir)
    if safety["risk"] or safety["zones"]:
        plot_safety_timeline(safety, session_dir)

    # ── Markdown report ──────────────────────────────────────────────────────
    write_session_report(
        session_dir, session_dir.name,
        latency, motion, cmd_vel, safety,
    )

    return combined


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", default=str(SESSION_ROOT),
                        help="Session directory (contains rosbag2_* subdir) or bag dir")
    args = parser.parse_args()

    given = Path(args.session)
    if list(given.glob("*.db3")):
        bag_dir     = given
        session_dir = given.parent
    else:
        bag_dirs = sorted(given.glob("rosbag2_*"))
        if not bag_dirs:
            print(f"[main] ERROR: no rosbag2_* dir in {given}")
            return 1
        bag_dir     = bag_dirs[-1]
        session_dir = given

    print(f"[main] Session : {session_dir.name}")
    print(f"[main] Bag     : {bag_dir.name}")

    result = analyze(bag_dir, session_dir)

    print("\n" + "─" * 60)
    print("ANALYSIS SUMMARY")
    print("─" * 60)
    lat = result.get("latency", {})
    mot = result.get("motion", {})
    print(f"  Latency  p50={lat.get('p50_ms','?')}ms  p99={lat.get('p99_ms','?')}ms  "
          f"<50ms={lat.get('under_50ms_pct','?')}%  → {lat.get('status','?')}")
    print(f"  Motion   arc={mot.get('arc_length_m','?')}m  "
          f"disp={mot.get('displacement_m','?')}m  → {mot.get('status','?')}")
    print("─" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
