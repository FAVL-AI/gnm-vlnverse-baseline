#!/usr/bin/env python3
"""Verify a JSONL file of FleetSafe per-timestep safety certificates.

Usage:
    python scripts/evaluation/verify_cbf_certificates.py \\
        --input path/to/certificates.jsonl \\
        --d-safe 0.5 \\
        --h-tol 0.02 \\
        --latency-ms 100 \\
        --allow-violations 0

Exit codes:
    0 — all certificates valid (within --allow-violations budget)
    1 — violations exceed budget
    2 — input file not found or empty
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import List


# ── Inline certificate check (no import needed for standalone use) ─────────────

def _u_safe_finite(u_safe: list) -> bool:
    return all(math.isfinite(v) for v in u_safe)


def check_certificate(
    cert: dict,
    d_safe: float,
    h_tol: float,
    latency_ms_max: float,
) -> List[str]:
    """Return list of violation strings (empty = valid)."""
    reasons: List[str] = []

    u_safe = cert.get("u_safe", [])
    if not u_safe or not _u_safe_finite(u_safe):
        reasons.append(f"u_safe non-finite or missing: {u_safe}")

    h_min = float(cert.get("h_min", float("-inf")))
    if h_min < -h_tol:
        reasons.append(f"h_min={h_min:.4f} < -{h_tol} (barrier violated)")

    min_dist = float(cert.get("min_dist_m", 0.0))
    if min_dist < d_safe - h_tol:
        reasons.append(f"min_dist_m={min_dist:.4f} < d_safe-tol={d_safe-h_tol:.4f}")

    qp = str(cert.get("qp_status", ""))
    if qp not in ("optimal", "estop_fallback", "skipped"):
        reasons.append(f"qp_status={qp!r} not acceptable")
    elif qp not in ("estop_fallback", "skipped"):
        margin = float(cert.get("constraint_margin_min", 0.0))
        if margin < -h_tol:
            reasons.append(f"constraint_margin_min={margin:.4f} < -{h_tol}")

    lat = float(cert.get("latency_ms", 0.0))
    if lat > latency_ms_max:
        reasons.append(f"latency_ms={lat:.1f} > {latency_ms_max:.1f}")

    return reasons


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Verify FleetSafe CBF safety certificates (JSONL)."
    )
    parser.add_argument("--input", required=True, help="Path to .jsonl certificate file")
    parser.add_argument("--d-safe", type=float, default=0.5, help="Min clearance (m)")
    parser.add_argument("--h-tol", type=float, default=0.02, help="Barrier tolerance")
    parser.add_argument("--latency-ms", type=float, default=100.0, help="Max latency (ms)")
    parser.add_argument(
        "--allow-violations",
        type=int,
        default=0,
        help="Number of violations allowed before non-zero exit",
    )
    args = parser.parse_args(argv)

    path = Path(args.input)
    if not path.exists():
        print(f"[ERROR] Input file not found: {path}", file=sys.stderr)
        sys.exit(2)

    certs = []
    with path.open() as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                certs.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"[WARN] Line {lineno}: JSON parse error — {exc}", file=sys.stderr)

    if not certs:
        print("[ERROR] No certificates found in input file.", file=sys.stderr)
        sys.exit(2)

    total = len(certs)
    violations: List[dict] = []
    cbf_active_count = 0
    max_latency = 0.0
    min_h = float("inf")
    min_dist = float("inf")

    for i, cert in enumerate(certs):
        if cert.get("cbf_active", False):
            cbf_active_count += 1
        lat = float(cert.get("latency_ms", 0.0))
        if lat > max_latency:
            max_latency = lat
        h = float(cert.get("h_min", float("inf")))
        if h < min_h:
            min_h = h
        d = float(cert.get("min_dist_m", float("inf")))
        if d < min_dist:
            min_dist = d

        reasons = check_certificate(cert, args.d_safe, args.h_tol, args.latency_ms)
        if reasons:
            violations.append({"index": i, "timestamp": cert.get("timestamp"), "reasons": reasons})

    safe_steps = total - len(violations)
    cbf_rate = cbf_active_count / total * 100.0 if total > 0 else 0.0

    print("=" * 60)
    print("  FleetSafe CBF Certificate Verification")
    print("=" * 60)
    print(f"  Input            : {path}")
    print(f"  d_safe           : {args.d_safe} m")
    print(f"  h_tol            : {args.h_tol}")
    print(f"  latency budget   : {args.latency_ms} ms")
    print()
    print(f"  Total steps      : {total}")
    print(f"  Safe steps       : {safe_steps}")
    print(f"  Violations       : {len(violations)}")
    print(f"  CBF intervention : {cbf_active_count} / {total}  ({cbf_rate:.1f}%)")
    print(f"  Max latency      : {max_latency:.1f} ms")
    print(f"  Min h            : {min_h:.4f}")
    print(f"  Min distance     : {min_dist:.4f} m")
    print()

    if violations:
        print(f"  VIOLATIONS ({len(violations)}):")
        for v in violations[:20]:
            print(f"    step {v['index']}  t={v['timestamp']}  →  {'; '.join(v['reasons'])}")
        if len(violations) > 20:
            print(f"    ... and {len(violations) - 20} more")
        print()

    if len(violations) <= args.allow_violations:
        print(f"  RESULT: PASS  ({len(violations)} violations ≤ allowed {args.allow_violations})")
        sys.exit(0)
    else:
        print(f"  RESULT: FAIL  ({len(violations)} violations > allowed {args.allow_violations})")
        sys.exit(1)


if __name__ == "__main__":
    main()
