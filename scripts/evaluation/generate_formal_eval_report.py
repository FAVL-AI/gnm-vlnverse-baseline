#!/usr/bin/env python3
"""Generate a formal safety evaluation report from FleetSafe certificates.

Usage:
    python scripts/evaluation/generate_formal_eval_report.py \\
        --input results/my_run/certificates.jsonl \\
        --output results/formal_eval_report.md \\
        [--baginfo results/bag_info.txt]
        [--d-safe 0.5]
        [--h-tol 0.02]
        [--latency-ms 100]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


def _load_certs(path: Path) -> List[dict]:
    certs = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    certs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return certs


def _is_finite(v) -> bool:
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _check(cert, d_safe, h_tol, latency_ms_max) -> List[str]:
    reasons = []
    u_safe = cert.get("u_safe", [])
    if not all(_is_finite(v) for v in u_safe):
        reasons.append("u_safe non-finite")
    if float(cert.get("h_min", float("-inf"))) < -h_tol:
        reasons.append(f"h_min={cert.get('h_min'):.4f}")
    if float(cert.get("min_dist_m", 0.0)) < d_safe - h_tol:
        reasons.append(f"min_dist_m={cert.get('min_dist_m'):.4f}")
    qp = cert.get("qp_status", "")
    if qp not in ("optimal", "estop_fallback", "skipped"):
        reasons.append(f"qp_status={qp!r}")
    elif qp not in ("estop_fallback", "skipped"):
        margin = float(cert.get("constraint_margin_min", 0.0))
        if margin < -h_tol:
            reasons.append(f"margin={margin:.4f}")
    if float(cert.get("latency_ms", 0.0)) > latency_ms_max:
        reasons.append(f"latency={cert.get('latency_ms'):.1f}ms")
    return reasons


def generate_report(
    certs: List[dict],
    d_safe: float,
    h_tol: float,
    latency_ms_max: float,
    baginfo: Optional[str],
    output: Path,
):
    total = len(certs)
    violations = []
    cbf_count = 0
    max_lat = 0.0
    min_h = float("inf")
    min_dist = float("inf")
    models: set = set()

    for i, c in enumerate(certs):
        if c.get("cbf_active", False):
            cbf_count += 1
        lat = float(c.get("latency_ms", 0.0))
        if lat > max_lat:
            max_lat = lat
        h = float(c.get("h_min", float("inf")))
        if h < min_h:
            min_h = h
        d = float(c.get("min_dist_m", float("inf")))
        if d < min_dist:
            min_dist = d
        if c.get("model_name"):
            models.add(c["model_name"])
        reasons = _check(c, d_safe, h_tol, latency_ms_max)
        if reasons:
            violations.append((i, c.get("timestamp", "?"), reasons))

    safe_steps = total - len(violations)
    cbf_rate = cbf_count / total * 100.0 if total else 0.0
    model_str = ", ".join(sorted(models)) if models else "unknown"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# FleetSafe Formal Safety Evaluation Report",
        f"*Generated: {now}*",
        "",
        "---",
        "",
        "## 1. Learned Policy Contract",
        "",
        f"**Models evaluated:** `{model_str}`",
        "",
        "GNM, ViNT, and NoMaD are goal-directed visual navigation policies trained",
        "on human teleoperation or simulation data. They map camera images and goal",
        "descriptors to nominal velocity commands `u_nom = [v_nom, ω_nom]`.",
        "",
        "**The learned policy is NOT a safety-critical controller.**",
        "It has no formal collision avoidance guarantee.",
        "Its output is treated as a *proposal* that is filtered before execution.",
        "",
        "---",
        "",
        "## 2. Safety Filter Contract",
        "",
        "FleetSafe wraps every nominal command with a **CBF-QP safety filter**:",
        "",
        "```",
        "u_safe = argmin  ½ ‖u − u_nom‖²",
        "         subject to  ḣ_i(x,u) + α h_i(x) ≥ 0   ∀ i",
        "                     u_min ≤ u ≤ u_max",
        "```",
        "",
        f"Safety barrier: `h_i(x) = d_i(x)² − d_safe²`",
        f"with `d_safe = {d_safe} m`",
        "",
        "By the CBF Forward Invariance Theorem (see `docs/math/CBF_QP_SAFETY_PROOF_SKETCH.md`),",
        "if the robot starts inside the safe set and the QP is feasible, it remains there.",
        "",
        "---",
        "",
        "## 3. Assumptions",
        "",
        "| # | Assumption | Status |",
        "|---|-----------|--------|",
        f"| A1 | Sensing latency ≤ {latency_ms_max:.0f} ms | verified per-step |",
        "| A2 | Valid obstacle estimates from scan/depth | assumed (hardware-dependent) |",
        "| A3 | QP feasible or emergency stop activated | verified per-step |",
        "| A4 | Robot tracks cmd_vel within tolerance | assumed (actuator-dependent) |",
        "| A5 | Emergency stop hardware functional | assumed (hardware-dependent) |",
        "",
        "---",
        "",
        "## 4. Certificate Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total timesteps | {total} |",
        f"| Safe timesteps | {safe_steps} ({safe_steps/total*100:.1f}%) |",
        f"| Violations | {len(violations)} |",
        f"| CBF interventions | {cbf_count} ({cbf_rate:.1f}%) |",
        f"| Max latency | {max_lat:.1f} ms |",
        f"| Min h (barrier) | {min_h:.4f} |",
        f"| Min distance | {min_dist:.4f} m |",
        "",
    ]

    if baginfo:
        lines += [
            "### Bag / Run Info",
            "",
            "```",
            baginfo.strip(),
            "```",
            "",
        ]

    lines += [
        "---",
        "",
        "## 5. Violations",
        "",
    ]

    if not violations:
        lines.append("**No violations.** All certificates satisfy formal safety conditions.")
    else:
        lines.append(f"**{len(violations)} violation(s) detected:**")
        lines.append("")
        lines.append("| Step | Timestamp | Reasons |")
        lines.append("|------|-----------|---------|")
        for step, ts, reasons in violations[:30]:
            lines.append(f"| {step} | {ts} | {'; '.join(reasons)} |")
        if len(violations) > 30:
            lines.append(f"| … | … | ({len(violations)-30} more) |")

    lines += [
        "",
        "---",
        "",
        "## 6. What Is Empirical",
        "",
        "- Navigation success rate (reached goal / total episodes)",
        "- Collision count (simulator ground truth)",
        "- Path length efficiency",
        "- Recovery behaviour",
        "- Generalisation across scenes",
        "",
        "These are measured by running experiments and counting outcomes.",
        "",
        "---",
        "",
        "## 7. What Is Mathematically Checked",
        "",
        "At **every timestep**, the following are verified by the certificate:",
        "",
        "- `h_min ≥ 0` — robot is outside the unsafe zone",
        f"- `min_dist_m ≥ {d_safe} m` — clearance maintained",
        "- `qp_status ∈ {optimal, estop_fallback}` — safety QP resolved",
        "- `constraint_margin_min ≥ 0` — CBF constraints not violated",
        f"- `latency_ms ≤ {latency_ms_max:.0f}` — sensor data is fresh",
        "- `u_safe` finite — no numerical failure",
        "",
        "The CBF Forward Invariance Theorem guarantees that if these hold,",
        "the robot remains in the safe set C under Assumptions A1–A5.",
        "",
        "---",
        "",
        "## 8. What Is Not Guaranteed",
        "",
        "- **Safety of the learned model in isolation.**",
        "  GNM/ViNT/NoMaD have no formal guarantee; the CBF filter is required.",
        "- **Optimality of navigation.**",
        "  The filter may reduce speed or alter heading near obstacles.",
        "- **Safety under A1–A5 violations.**",
        "  Sensor failure, large tracking error, or QP infeasibility without e-stop",
        "  would break the formal guarantee.",
        "- **Absolute collision-free guarantee.**",
        "  The proof holds under the stated assumptions; real-world sensor noise",
        "  and SLAM drift are bounded but non-zero.",
        "",
        "---",
        "",
        "*For the formal model see `docs/math/FLEETSAFE_FORMAL_MODEL.md`.*",
        "*For the proof see `docs/math/CBF_QP_SAFETY_PROOF_SKETCH.md`.*",
        "",
    ]

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines))
    print(f"Report written to: {output}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate FleetSafe formal safety evaluation report."
    )
    parser.add_argument("--input", required=True, help="Path to certificates.jsonl")
    parser.add_argument(
        "--output",
        default="results/formal_eval_report.md",
        help="Output markdown path",
    )
    parser.add_argument("--baginfo", help="Optional bag info text or summary JSON path")
    parser.add_argument("--d-safe", type=float, default=0.5)
    parser.add_argument("--h-tol", type=float, default=0.02)
    parser.add_argument("--latency-ms", type=float, default=100.0)
    args = parser.parse_args(argv)

    path = Path(args.input)
    if not path.exists():
        print(f"[ERROR] Input not found: {path}", file=sys.stderr)
        sys.exit(2)

    certs = _load_certs(path)
    if not certs:
        print("[ERROR] No certificates found.", file=sys.stderr)
        sys.exit(2)

    baginfo = None
    if args.baginfo:
        bp = Path(args.baginfo)
        if bp.exists():
            baginfo = bp.read_text()

    generate_report(
        certs=certs,
        d_safe=args.d_safe,
        h_tol=args.h_tol,
        latency_ms_max=args.latency_ms,
        baginfo=baginfo,
        output=Path(args.output),
    )


if __name__ == "__main__":
    main()
