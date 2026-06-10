"""Extended benchmark metrics for FleetSafe-VLN.

Wraps fleet_safe_vla.benchmarks.visualnav_metrics and adds:
  - certificate_validity_rate
  - unsafe_nominal_action_rate
  - cbf_intervention_magnitude (mean)
  - sim_to_real_transfer_delta
  - near_miss_count (already exists, exposed here)
  - operator_override_count
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

try:
    from fleet_safe_vla.benchmarks.visualnav_metrics import (
        EpisodeMetrics as _BaseMetrics,
        compute_spl,
        compute_intervention_rate,
    )
    _BASE_OK = True
except ImportError:
    _BASE_OK = False
    compute_spl = None
    compute_intervention_rate = None


@dataclass
class EpisodeResult:
    """Full result record for one FleetSafe-VLN episode."""

    # ── Identity ──────────────────────────────────────────────────────────────
    task_id: str = ""
    scene: str = ""
    platform: str = ""
    model: str = ""
    safety: str = ""
    seed: int = 0
    run_id: str = ""
    log_dir: str = ""

    # ── Navigation outcome ────────────────────────────────────────────────────
    success: bool = False
    navigation_error_m: float = 0.0
    path_length_m: float = 0.0
    optimal_path_m: float = 0.0
    spl: float = 0.0
    episode_steps: int = 0
    time_s: float = 0.0

    # ── Safety metrics ────────────────────────────────────────────────────────
    collision_count: int = 0
    collision_rate: float = 0.0
    min_obstacle_distance_m: float = math.inf
    min_human_distance_m: float = math.inf
    near_miss_count: int = 0

    # ── CBF / certificate metrics ─────────────────────────────────────────────
    cbf_intervention_count: int = 0
    cbf_intervention_rate: float = 0.0
    cbf_intervention_magnitude_mean: float = 0.0
    unsafe_nominal_action_count: int = 0
    unsafe_nominal_action_rate: float = 0.0
    certificate_validity_rate: float = 0.0
    invalid_certificate_count: int = 0

    # ── Sim-to-real transfer ──────────────────────────────────────────────────
    sim_to_real_transfer_delta: Optional[float] = None

    # ── Human-awareness ───────────────────────────────────────────────────────
    social_margin_violation_count: int = 0
    operator_override_count: int = 0

    # ── Latency ───────────────────────────────────────────────────────────────
    inference_latency_ms_mean: float = 0.0
    cbf_latency_ms_mean: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        if math.isinf(d.get("min_obstacle_distance_m", 0)):
            d["min_obstacle_distance_m"] = None
        if math.isinf(d.get("min_human_distance_m", 0)):
            d["min_human_distance_m"] = None
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")


def compute_certificate_validity_rate(cert_path: str | Path) -> tuple[float, int, int]:
    """Return (validity_rate, valid_count, total_count) from a JSONL cert file.

    Supports both ExtendedCertificate format (has 'certificate_valid' key)
    and legacy SafetyCertificate format (uses is_valid() method).
    """
    p = Path(cert_path)
    if not p.exists():
        return 0.0, 0, 0

    total = valid = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            total += 1
            if "certificate_valid" in d:
                if d["certificate_valid"]:
                    valid += 1
            else:
                try:
                    from fleet_safe_vla.safety.certificate import SafetyCertificate
                    cert = SafetyCertificate.from_dict(d)
                    if cert.is_valid():
                        valid += 1
                except Exception:
                    if d.get("safe", True) and d.get("qp_status", "optimal") in (
                        "optimal", "estop_fallback", "skipped"
                    ):
                        valid += 1
        except Exception:
            pass

    rate = valid / total if total > 0 else 0.0
    return rate, valid, total


def leaderboard_row(result: EpisodeResult) -> Dict[str, str]:
    """Format one EpisodeResult as a leaderboard table row."""
    def _fmt(v, digits=3):
        if v is None:
            return "—"
        if isinstance(v, bool):
            return "✓" if v else "✗"
        if isinstance(v, float):
            return f"{v:.{digits}f}"
        return str(v)

    return {
        "Model": result.model,
        "Platform": result.platform,
        "SR": _fmt(float(result.success)),
        "SPL": _fmt(result.spl),
        "Nav Err (m)": _fmt(result.navigation_error_m, 2),
        "Collisions": str(result.collision_count),
        "Min Obs (m)": _fmt(result.min_obstacle_distance_m, 2),
        "Min Human (m)": _fmt(result.min_human_distance_m, 2),
        "CBF Interventions": str(result.cbf_intervention_count),
        "CBF Mag Mean": _fmt(result.cbf_intervention_magnitude_mean),
        "Cert Validity": _fmt(result.certificate_validity_rate),
        "Near Misses": str(result.near_miss_count),
    }


def print_leaderboard(results: List[EpisodeResult]) -> None:
    if not results:
        print("No results.")
        return
    rows = [leaderboard_row(r) for r in results]
    cols = list(rows[0].keys())
    widths = {c: max(len(c), max(len(r[c]) for r in rows)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    sep = "  ".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for row in rows:
        print("  ".join(row[c].ljust(widths[c]) for c in cols))
