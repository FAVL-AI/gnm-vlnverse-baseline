#!/usr/bin/env python3
"""Audit a FleetSafe run directory for no-black-box explainability coverage.

Checks that enough data is present to explain every decision:
  - Camera images or camera topic reference
  - Model name present
  - u_nom logged (nominal learned command)
  - u_safe logged (filtered command)
  - h_min logged (barrier value)
  - qp_status logged
  - cbf_active flag logged
  - latency logged
  - Final command (u_safe or cmd_vel) logged

Usage:
    python scripts/evaluation/audit_no_blackbox_logs.py --run-dir results/my_run/
    python scripts/evaluation/audit_no_blackbox_logs.py --run-dir results/my_run/ --strict
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# ── Check helpers ─────────────────────────────────────────────────────────────

def _find_jsonl(run_dir: Path):
    """Return list of JSONL files in run_dir."""
    return list(run_dir.glob("**/*.jsonl")) + list(run_dir.glob("**/*.json"))


def _sample_certs(files, max_samples=50):
    """Load up to max_samples certificate dicts from the found files."""
    certs = []
    for f in files:
        try:
            with f.open() as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            certs.append(obj)
                    except json.JSONDecodeError:
                        pass
                    if len(certs) >= max_samples:
                        return certs
        except Exception:
            pass
    return certs


def _has_key_in_any(certs, key):
    return any(key in c for c in certs)


def _has_nonzero_in_any(certs, key):
    for c in certs:
        v = c.get(key)
        if v is not None and v != 0 and v != [] and v != "" and v != "0":
            return True
    return False


def _check_images(run_dir: Path):
    """Return True if any image files or camera topic references exist."""
    image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".npy"}
    for ext in image_exts:
        if any(run_dir.glob(f"**/*{ext}")):
            return True
    # Check for camera topic in logs
    for jf in _find_jsonl(run_dir):
        try:
            text = jf.read_text(errors="replace")
            if "camera" in text.lower() or "image_raw" in text.lower():
                return True
        except Exception:
            pass
    return False


# ── Main audit ────────────────────────────────────────────────────────────────

CHECKS = [
    ("camera_data",       "Images or camera topic reference present"),
    ("model_name",        "Model name present (gnm/vint/nomad)"),
    ("u_nom",             "u_nom logged (nominal learned command)"),
    ("u_safe",            "u_safe logged (CBF-filtered command)"),
    ("h_min",             "h_min logged (CBF barrier value)"),
    ("qp_status",         "qp_status logged (optimal/fallback/infeasible)"),
    ("cbf_active",        "cbf_active flag logged"),
    ("latency_ms",        "latency_ms logged (sensing-to-command)"),
    ("final_command",     "Final command sent (u_safe or cmd_vel)"),
]


def run_audit(run_dir: Path, strict: bool = False) -> int:
    """Run the audit. Returns number of failures."""
    print("=" * 60)
    print("  FleetSafe No-Black-Box Log Audit")
    print(f"  Run directory: {run_dir}")
    print("=" * 60)
    print()

    if not run_dir.exists():
        print(f"  [ERROR] Directory not found: {run_dir}")
        print()
        print("  Guidance:")
        print("    Run FleetSafe and point --run-dir to the output directory.")
        print("    Expected structure:")
        print("      results/my_run/certificates.jsonl")
        print("      results/my_run/images/  (optional)")
        print()
        return len(CHECKS)

    jsonl_files = _find_jsonl(run_dir)
    certs = _sample_certs(jsonl_files)

    results = {}

    # Camera
    results["camera_data"] = _check_images(run_dir)

    # Certificate fields
    for key in ("model_name", "u_nom", "u_safe", "h_min",
                "qp_status", "cbf_active", "latency_ms"):
        results[key] = _has_key_in_any(certs, key)

    # Final command: u_safe or cmd_vel
    results["final_command"] = _has_key_in_any(certs, "u_safe") or any(
        "cmd_vel" in (f.name.lower() + f.read_text(errors="replace")[:200])
        for f in jsonl_files[:5]
    )

    failures = 0
    for key, description in CHECKS:
        ok = results.get(key, False)
        status = "PASS" if ok else ("FAIL" if strict else "WARN")
        if not ok:
            failures += 1
        print(f"  [{status}]  {description}")

    print()
    total = len(CHECKS)
    passed = total - failures
    print(f"  Summary: {passed}/{total} checks passed")
    print()

    if failures == 0:
        print("  RESULT: PASS — run contains full explainability data.")
    elif not strict:
        print("  RESULT: PARTIAL — some fields missing (run with --strict to fail on this).")
    else:
        print("  RESULT: FAIL — missing explainability fields.")

    print()
    if failures > 0:
        print("  To fix: ensure your FleetSafe runner logs SafetyCertificate")
        print("  at every timestep and writes them to certificates.jsonl.")
        print("  See fleet_safe_vla/safety/certificate.py")

    return failures if strict else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit FleetSafe run directory for no-black-box explainability."
    )
    parser.add_argument("--run-dir", required=True, help="Path to run output directory")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero if any check fails (default: warnings only)",
    )
    args = parser.parse_args(argv)

    failures = run_audit(Path(args.run_dir), strict=args.strict)
    sys.exit(min(failures, 1))


if __name__ == "__main__":
    main()
