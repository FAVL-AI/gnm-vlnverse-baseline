"""
fleet_safe_vla/benchmark_version.py

Single source of truth for all benchmark component versions.
Increment these when the corresponding artifact schema or protocol changes.
"""
from __future__ import annotations

BENCHMARK_VERSION      = "0.1.0"
PROTOCOL_VERSION       = "0.1.0"
SCENESET_VERSION       = "0.1.0"
METRICSET_VERSION      = "0.1.0"
EXPLAINABILITY_VERSION = "0.1.0"
GOVERNANCE_VERSION     = "0.1.0"


def version_block() -> dict[str, str]:
    """Return all version fields as a dict suitable for embedding in any artifact."""
    return {
        "benchmark_version":      BENCHMARK_VERSION,
        "protocol_version":       PROTOCOL_VERSION,
        "sceneset_version":       SCENESET_VERSION,
        "metricset_version":      METRICSET_VERSION,
        "explainability_version": EXPLAINABILITY_VERSION,
        "governance_version":     GOVERNANCE_VERSION,
    }


def _git_commit() -> str:
    """Return the current HEAD short hash, or 'unknown' if git is unavailable."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


GIT_COMMIT = _git_commit()

PROTOCOL_FILE      = "benchmarks/protocols/visualnav_v0.1.yaml"
SCENE_MANIFEST_FILE = "benchmarks/scenes/canonical/SCENESET_v0.1.yaml"
METRIC_SPEC_FILE   = "docs/metrics/METRIC_SPECIFICATION.md"
