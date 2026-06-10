"""
Metrics Pipeline — v0.9.

Standardizes, enriches, and validates metrics from experiment registry runs.
Computes:
  - Paper-facing aggregate table (backbone × safety_mode × metric)
  - FleetSafe delta over baseline
  - 95% CI across seeds (when N ≥ 3)
  - Claim validation: PROVEN / PRELIMINARY / SYNTHETIC / NOT_VALIDATED

Every output metric carries:
  value       — the point estimate
  n           — number of runs contributing
  ci_95       — (low, high) or null when N < 3
  status      — evidence status string
  note        — human-readable honesty note
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .experiment_registry import experiment_registry, EvidenceStatus

# Keys that must appear in the paper table
PAPER_METRIC_KEYS = [
    "success_rate",
    "collision_rate",
    "spl_mean",
    "intervention_rate_mean",
    "inference_latency_ms_mean",
    "min_obstacle_distance_m_mean",
    "near_violation_count_mean",
    "steps_red_mean",
    "smoothness_mean",
    "crowding_risk_score_mean",
]

# Higher is better (for delta interpretation)
HIGHER_IS_BETTER = {
    "success_rate", "spl_mean", "min_obstacle_distance_m_mean", "smoothness_mean",
}

# Paper claim bounds — what we're trying to show
SAFETY_IMPROVEMENT_THRESHOLDS = {
    "collision_rate":          {"direction": "lower", "target_delta_pct": -20},
    "near_violation_count_mean": {"direction": "lower", "target_delta_pct": -30},
    "steps_red_mean":          {"direction": "lower", "target_delta_pct": -40},
    "success_rate":            {"direction": "higher_or_equal", "target_delta_pct": -5},
}


def _load_delay_claim() -> dict:
    """Read delay_claim_validation.json from recordings/delay_injection/ if present."""
    try:
        from ..config import settings
        path = settings.repo_root / "recordings" / "delay_injection" / "delay_claim_validation.json"
    except Exception:
        path = Path(__file__).resolve().parents[4] / "recordings" / "delay_injection" / "delay_claim_validation.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _t_ci_95(values: list[float]) -> tuple[float, float] | None:
    """95% CI using t-distribution approximation. Returns None when N < 3."""
    n = len(values)
    if n < 3:
        return None
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    std = math.sqrt(variance)
    # t-value for 95% CI (conservative approximation)
    t_val = 2.0 + 6.0 / n  # approaches 1.96 as n → ∞
    margin = t_val * std / math.sqrt(n)
    return (round(mean - margin, 4), round(mean + margin, 4))


def _aggregate(values: list[float]) -> dict:
    if not values:
        return {"value": None, "n": 0, "ci_95": None}
    mean = sum(values) / len(values)
    return {
        "value": round(mean, 4),
        "n": len(values),
        "ci_95": _t_ci_95(values),
    }


def _status_note(status: EvidenceStatus, n: int) -> str:
    if status == "PROVEN":
        return f"Verified across {n} seeds; publication-ready."
    if status == "PRELIMINARY":
        return f"Only {n} run(s). Increase to ≥10 seeds for PROVEN status."
    if status == "SYNTHETIC":
        return f"Simulation result ({n} run(s)). Real-robot validation pending."
    if status == "RECORDED_ONLY":
        return "Real data captured but metrics not yet computed."
    return "No evidence collected yet for this condition."


def _build_delay_claim() -> dict:
    """Read delay_claim_validation.json; return status/evidence/gap dict."""
    data = _load_delay_claim()
    if not data:
        return {
            "status":   "NOT_VALIDATED",
            "evidence": "No delay injection experiment run",
            "gap":      "Run: python scripts/benchmarks/run_delay_injection_matrix.py",
        }
    status = data.get("status", "NOT_VALIDATED")
    per_model = data.get("per_model", [])
    n_proven  = sum(1 for m in per_model if m.get("status") == "PROVEN")
    models    = [m["model"] for m in per_model]
    evidence  = (
        f"delay_injection matrix: {n_proven}/{len(models)} models PROVEN "
        f"({', '.join(models)})"
    ) if per_model else data.get("claim", "")
    gap = None if status == "PROVEN" else (
        "; ".join(
            m["note"] for m in per_model if m.get("status") != "PROVEN"
        ) or "See delay_claim_validation.json"
    )
    return {"status": status, "evidence": evidence, "gap": gap}


class MetricsPipeline:
    def full_table(self, backend: str | None = None) -> dict:
        """
        Build the full backbone × safety_mode × metric table used in the paper.
        Returns per-row dicts with value, n, ci_95, evidence_status, note.
        """
        runs = experiment_registry.scan()
        if backend:
            runs = [r for r in runs if r["backend_raw"] == backend]

        # Group by (backbone, safety_mode)
        groups: dict[tuple[str, str], list[dict]] = {}
        for r in runs:
            key = (r["backbone"], r["safety_mode"])
            groups.setdefault(key, []).append(r)

        rows = []
        for (backbone, safety_mode), group_runs in sorted(groups.items()):
            # Per-metric aggregation
            metrics_out: dict[str, dict] = {}
            for key in PAPER_METRIC_KEYS:
                vals = [
                    r["paper_metrics"][key]
                    for r in group_runs
                    if r["paper_metrics"].get(key) is not None
                ]
                agg = _aggregate(vals)
                # Determine status from runs
                statuses = {r["evidence_status"] for r in group_runs}
                if "PROVEN" in statuses and agg["n"] >= 10:
                    status: EvidenceStatus = "PROVEN"
                elif statuses <= {"PRELIMINARY", "PROVEN"}:
                    status = "PRELIMINARY"
                else:
                    status = "SYNTHETIC"
                agg["status"] = status
                agg["note"] = _status_note(status, agg["n"])
                metrics_out[key] = agg

            rows.append({
                "backbone":      backbone,
                "safety_mode":   safety_mode,
                "n_runs":        len(group_runs),
                "backend":       group_runs[0]["backend"] if group_runs else "—",
                "metrics":       metrics_out,
                "evidence_status": min(
                    (r["evidence_status"] for r in group_runs),
                    key=lambda s: ["PROVEN","PRELIMINARY","SYNTHETIC","RECORDED_ONLY","NOT_VALIDATED"].index(s),
                ) if group_runs else "NOT_VALIDATED",
            })

        return {
            "table": rows,
            "n_total_runs": len(runs),
            "backend_filter": backend or "all",
            "generated_at": __import__("time").time(),
        }

    def delta_analysis(self) -> list[dict]:
        """
        For each backbone, compute FleetSafe improvement over nominal_only.
        Returns list of delta entries with claim validation.
        """
        backbones = {r["backbone"] for r in experiment_registry.scan()}
        results = []

        for backbone in sorted(backbones):
            if backbone == "MOCK":
                continue
            for backend_filter in (None, "mujoco", "isaaclab"):
                cmp = experiment_registry.compare(backbone, backend_filter)
                if cmp["n_baseline"] == 0 or cmp["n_fleetsafe"] == 0:
                    continue

                # Validate against paper claims
                claim_checks = {}
                for metric, spec in SAFETY_IMPROVEMENT_THRESHOLDS.items():
                    delta = cmp["delta_pct"].get(metric)
                    if delta is None:
                        claim_checks[metric] = {"met": None, "delta_pct": None, "note": "no data"}
                        continue
                    target = spec["target_delta_pct"]
                    if spec["direction"] == "lower":
                        met = delta <= target
                    else:  # higher_or_equal
                        met = delta >= target
                    claim_checks[metric] = {
                        "met": met,
                        "delta_pct": delta,
                        "target_delta_pct": target,
                        "note": "✓ meets target" if met else f"✗ need {target}%, got {delta}%",
                    }

                results.append({
                    **cmp,
                    "claim_checks": claim_checks,
                })

        return results

    def cmd_jitter(self, run_id: str) -> dict:
        """
        Compute cmd_vel jitter from trajectory CSV if available.
        Returns {'jitter_ms': float, 'n_samples': int, 'status': str}.
        """
        from ..config import settings
        traj = settings.repo_root / "benchmarks" / "visualnav" / "results" / run_id / "aggregate_metrics.csv"
        if not traj.exists():
            return {"jitter_ms": None, "n_samples": 0, "status": "NOT_VALIDATED",
                    "note": "No trajectory CSV found"}

        try:
            import csv
            rows = list(csv.DictReader(traj.open()))
            if not rows:
                return {"jitter_ms": None, "n_samples": 0, "status": "NOT_VALIDATED",
                        "note": "Empty CSV"}
            latencies = [float(r["inference_latency_ms_mean"]) for r in rows
                         if "inference_latency_ms_mean" in r]
            if not latencies:
                return {"jitter_ms": None, "n_samples": 0, "status": "NOT_VALIDATED",
                        "note": "No latency column"}
            mean = sum(latencies) / len(latencies)
            variance = sum((v - mean) ** 2 for v in latencies) / max(len(latencies) - 1, 1)
            jitter = math.sqrt(variance)
            return {
                "jitter_ms": round(jitter, 3),
                "n_samples": len(latencies),
                "status": "SYNTHETIC",
                "note": "Computed from inference_latency_ms across scenes",
            }
        except Exception as e:
            return {"jitter_ms": None, "n_samples": 0, "status": "NOT_VALIDATED", "note": str(e)}

    def claim_validation_report(self) -> dict:  # noqa: C901
        """
        For every paper claim, report current evidence status.

        Evidence promotion rules (honest — must reflect actual data):
          PROVEN       — ≥10 seeds, non-MOCK backbone, mujoco or isaaclab backend,
                         both FleetSafe and baseline arms present
          PRELIMINARY  — data exists but insufficient seeds or only one arm
          NOT_VALIDATED — no runs at all
        """
        runs = experiment_registry.scan()

        # Filter to publication-grade runs only (exclude mock backbone/backend)
        pub_runs = [
            r for r in runs
            if r["backbone"] not in ("MOCK",)
            and r["backend_raw"] in ("mujoco", "isaaclab")
        ]
        backbones_with_data = {r["backbone"] for r in pub_runs}

        # Per-backbone, per-safety-mode counts
        def _n(bb: str | None, mode: str | None, backend: str | None = None) -> int:
            return len([
                r for r in pub_runs
                if (bb is None or r["backbone"] == bb)
                and (mode is None or r["safety_mode"] == mode)
                and (backend is None or r["backend_raw"] == backend)
            ])

        PROVEN_SEEDS = 10

        # GNM (our primary backbone) — check seed counts
        n_gnm_fs   = _n("GNM", "FleetSafe_full")
        n_gnm_base = _n("GNM", "nominal_only")
        gnm_proven = n_gnm_fs >= PROVEN_SEEDS and n_gnm_base >= PROVEN_SEEDS

        n_vint  = _n("ViNT",  None)
        n_nomad = _n("NoMaD", None)
        n_gnm   = n_gnm_fs + n_gnm_base

        has_vint  = n_vint  >= 1
        has_nomad = n_nomad >= 1
        has_gnm   = n_gnm   >= 1
        vint_proven  = _n("ViNT",  "FleetSafe_full") >= PROVEN_SEEDS and _n("ViNT",  "nominal_only") >= PROVEN_SEEDS
        nomad_proven = _n("NoMaD", "FleetSafe_full") >= PROVEN_SEEDS and _n("NoMaD", "nominal_only") >= PROVEN_SEEDS

        # Hospital scene count
        n_hospital = len([r for r in pub_runs if r.get("scene") == "hospital_corridor"])
        n_hosp_fs  = len([r for r in pub_runs if r.get("scene") == "hospital_corridor"
                          and r["safety_mode"] == "FleetSafe_full"])
        n_hosp_base = len([r for r in pub_runs if r.get("scene") == "hospital_corridor"
                           and r["safety_mode"] == "nominal_only"])
        hospital_proven = n_hosp_fs >= PROVEN_SEEDS and n_hosp_base >= PROVEN_SEEDS

        all_pub = len(pub_runs)

        claims = [
            {
                "claim": "FleetSafe reduces collision rate over nominal backbone",
                "status": (
                    "PROVEN" if gnm_proven
                    else "PRELIMINARY" if n_gnm_fs >= 1 and n_gnm_base >= 1
                    else "NOT_VALIDATED"
                ),
                "evidence": (
                    f"GNM: {n_gnm_fs} FleetSafe, {n_gnm_base} baseline runs "
                    f"(mujoco/isaaclab, excl. mock)"
                ),
                "gap": (
                    None if gnm_proven
                    else f"GNM needs ≥{PROVEN_SEEDS} seeds each arm "
                         f"(have {n_gnm_fs} FS, {n_gnm_base} base)"
                ),
            },
            {
                "claim": "FleetSafe preserves task success within 5%",
                "status": (
                    "PROVEN" if gnm_proven
                    else "PRELIMINARY" if n_gnm_fs >= 1 and n_gnm_base >= 1
                    else "NOT_VALIDATED"
                ),
                "evidence": f"SR tracked across {all_pub} publication-grade runs",
                "gap": (
                    None if gnm_proven
                    else f"Need ≥{PROVEN_SEEDS} seeds per condition (GNM: {n_gnm_base} base, {n_gnm_fs} FS)"
                ),
            },
            {
                "claim": "Backbone-agnostic: works with ViNT, NoMaD, GNM",
                "status": (
                    "PROVEN" if (vint_proven and nomad_proven and gnm_proven)
                    else "PRELIMINARY" if (has_vint and has_nomad and has_gnm)
                    else "PARTIAL"
                ),
                "evidence": (
                    f"Tested: {', '.join(sorted(backbones_with_data))} "
                    f"(ViNT n={n_vint}, NoMaD n={n_nomad}, GNM n={n_gnm})"
                ),
                "gap": (
                    None if (vint_proven and nomad_proven and gnm_proven)
                    else (f"ViNT needs ≥{PROVEN_SEEDS} seeds each arm (have {n_vint}); "
                          f"NoMaD needs ≥{PROVEN_SEEDS} (have {n_nomad})")
                    if has_vint and has_nomad
                    else f"Need ViNT + NoMaD data (currently only {', '.join(sorted(backbones_with_data))})"
                ),
            },
            {
                "claim": "Delay-robust operation at 100ms cmd latency",
                **_build_delay_claim(),
            },
            {
                "claim": "Operates on real Yahboom M3Pro hardware",
                "status": "RECORDED_ONLY",
                "evidence": "ROS2 bag session recorder deployed, YOLO node wired",
                "gap": "Need ≥3 real sessions with FleetSafe active + video",
            },
            {
                "claim": "Hospital scene social safety (zone model)",
                "status": (
                    "PROVEN" if hospital_proven
                    else "PRELIMINARY" if n_hospital >= 1
                    else "NOT_VALIDATED"
                ),
                "evidence": (
                    f"{n_hospital} hospital_corridor runs "
                    f"({n_hosp_fs} FS, {n_hosp_base} baseline)"
                ),
                "gap": (
                    None if hospital_proven
                    else f"Need ≥{PROVEN_SEEDS} seeds each arm in hospital_corridor "
                         f"(have {n_hosp_fs} FS, {n_hosp_base} base); "
                         "need human-verified zone boundaries"
                ),
            },
            {
                "claim": "Real-time inference (<50ms) on Jetson",
                "status": "NOT_VALIDATED",
                "evidence": "Sim latency measured in benchmark; on-device not profiled",
                "gap": "Need on-device profiling on Jetson Orin (jetson_latency_benchmark.py)",
            },
        ]

        proven   = sum(1 for c in claims if c["status"] == "PROVEN")
        prelim   = sum(1 for c in claims if c["status"] == "PRELIMINARY")
        partial  = sum(1 for c in claims if c["status"] == "PARTIAL")
        not_val  = sum(1 for c in claims if c["status"] == "NOT_VALIDATED")
        recorded = sum(1 for c in claims if c["status"] == "RECORDED_ONLY")

        return {
            "claims": claims,
            "summary": {
                "total":         len(claims),
                "proven":        proven,
                "preliminary":   prelim,
                "partial":       partial,
                "recorded_only": recorded,
                "not_validated": not_val,
                "readiness_pct": round((proven + prelim * 0.5) / len(claims) * 100, 1),
            },
        }


metrics_pipeline = MetricsPipeline()
