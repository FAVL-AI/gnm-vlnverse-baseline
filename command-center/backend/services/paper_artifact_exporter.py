"""
Paper Artifact Exporter — v0.9.

Generates publication-ready outputs from the experiment registry:
  publication_tables/   — Markdown + CSV comparison tables
  publication_figures/  — data files for matplotlib/pgfplots
  publication_metrics.json  — all metrics with CI and evidence status
  publication_manifest.json — hashes, git commits, run IDs (reproducibility)

One-click export via .bundle() writes everything to a timestamped directory.
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

from .experiment_registry import experiment_registry
from .metrics_pipeline import metrics_pipeline, PAPER_METRIC_KEYS
from ..config import settings

EXPORT_ROOT = settings.repo_root / "command-center" / "recordings" / "publication"

METRIC_LABELS = {
    "success_rate":                "SR (%)",
    "collision_rate":              "CR (%)",
    "spl_mean":                    "SPL",
    "intervention_rate_mean":      "IR (int/step)",
    "inference_latency_ms_mean":   "L_cmd (ms)",
    "min_obstacle_distance_m_mean":"d_min (m)",
    "near_violation_count_mean":   "Violations",
    "steps_red_mean":              "T_red (steps)",
    "smoothness_mean":             "Smoothness",
    "crowding_risk_score_mean":    "ρ_crowd",
}

STATUS_SYMBOL = {
    "PROVEN":        "✓",
    "PRELIMINARY":   "~",
    "SYNTHETIC":     "s",
    "RECORDED_ONLY": "r",
    "NOT_VALIDATED": "✗",
}


def _fmt(val: float | None, decimals: int = 3) -> str:
    if val is None:
        return "—"
    return f"{val:.{decimals}f}"


def _pct(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val * 100:.1f}"


class PaperArtifactExporter:

    def export_comparison_table(self, backend: str | None = None) -> tuple[str, list[dict]]:
        """
        Generate Markdown table + CSV rows for backbone × safety_mode comparison.
        Returns (markdown_str, csv_rows).
        """
        result = metrics_pipeline.full_table(backend=backend)
        rows   = result["table"]

        # Focus metrics for main table (paper Table 1)
        main_keys = ["success_rate", "collision_rate", "intervention_rate_mean",
                     "spl_mean", "inference_latency_ms_mean"]

        header = "| Backbone | Safety Mode | " + " | ".join(METRIC_LABELS.get(k, k) for k in main_keys) + " | N | Status |"
        sep    = "|" + "|".join(["-" * 12] * (len(main_keys) + 4)) + "|"
        lines  = [header, sep]
        csv_rows = []

        for row in rows:
            cells = [row["backbone"], row["safety_mode"].replace("_", " ")]
            csv_row = {"backbone": row["backbone"], "safety_mode": row["safety_mode"]}
            for k in main_keys:
                m = row["metrics"].get(k, {})
                v = m.get("value")
                ci = m.get("ci_95")
                sym = STATUS_SYMBOL.get(m.get("status", ""), "?")
                if k in ("success_rate", "collision_rate", "intervention_rate_mean"):
                    cell = f"{_pct(v)}{sym}"
                    if ci:
                        cell += f" [{_pct(ci[0])}–{_pct(ci[1])}]"
                else:
                    cell = f"{_fmt(v)}{sym}"
                    if ci:
                        cell += f" [{_fmt(ci[0])}–{_fmt(ci[1])}]"
                cells.append(cell)
                csv_row[k] = v
                csv_row[f"{k}_ci_lo"] = ci[0] if ci else None
                csv_row[f"{k}_ci_hi"] = ci[1] if ci else None
                csv_row[f"{k}_status"] = m.get("status")
            cells += [str(row["n_runs"]), STATUS_SYMBOL.get(row["evidence_status"], "?")]
            csv_row["n_runs"] = row["n_runs"]
            csv_row["evidence_status"] = row["evidence_status"]
            lines.append("| " + " | ".join(cells) + " |")
            csv_rows.append(csv_row)

        legend = (
            "\n**Status legend:** ✓ PROVEN  ~ PRELIMINARY  s SYNTHETIC  "
            "r RECORDED_ONLY  ✗ NOT_VALIDATED"
        )
        return "\n".join(lines) + "\n" + legend, csv_rows

    def export_delta_table(self) -> str:
        """Markdown table of FleetSafe improvement over baseline."""
        deltas = metrics_pipeline.delta_analysis()
        if not deltas:
            return "_No comparison data available._"

        lines = [
            "| Backbone | Backend | Δ SR (%) | Δ CR (%) | Δ IR (%) | Δ SPL (%) | N_base | N_fs | Status |",
            "|----------|---------|----------|----------|----------|-----------|--------|------|--------|",
        ]
        for d in deltas:
            dp = d["delta_pct"]
            lines.append(
                f"| {d['backbone']} | {d['backend']} "
                f"| {_fmt(dp.get('success_rate'), 1)} "
                f"| {_fmt(dp.get('collision_rate'), 1)} "
                f"| {_fmt(dp.get('intervention_rate_mean'), 1)} "
                f"| {_fmt(dp.get('spl_mean'), 1)} "
                f"| {d['n_baseline']} | {d['n_fleetsafe']} "
                f"| {STATUS_SYMBOL.get(d['evidence_status'], '?')} |"
            )
        return "\n".join(lines)

    def export_metrics_json(self) -> dict:
        """Full metrics JSON with all evidence metadata."""
        table = metrics_pipeline.full_table()
        claims = metrics_pipeline.claim_validation_report()
        deltas = metrics_pipeline.delta_analysis()

        return {
            "generated_at":    time.time(),
            "total_runs":      experiment_registry.summary()["total_runs"],
            "comparison_table": table["table"],
            "delta_analysis":   deltas,
            "claim_validation": claims,
        }

    def export_manifest(self) -> dict:
        """Reproducibility manifest: every run with git commit + artifact hashes."""
        runs = experiment_registry.scan()
        entries = []
        for r in runs:
            entries.append({
                "run_id":         r["run_id"],
                "git_commit":     r["git_commit"],
                "backbone":       r["backbone"],
                "safety_mode":    r["safety_mode"],
                "backend":        r["backend"],
                "seed":           r["seed"],
                "n_episodes":     r["n_episodes"],
                "evidence_status": r["evidence_status"],
                "hashes":         r["hashes"],
                "claim_scope":    r["claim_scope"],
            })

        return {
            "generated_at": time.time(),
            "total_runs": len(runs),
            "entries": entries,
            "verification_command": (
                "python tools/verify_manifest.py publication_manifest.json"
            ),
        }

    def export_figure_data(self) -> dict:
        """
        Data for paper figures — ready for matplotlib/pgfplots.
        Fig 1: SR vs backbone (baseline vs FleetSafe)
        Fig 2: CR vs backbone
        Fig 3: Intervention rate
        Fig 4: Cross-backend corridor (central paper figure)
        """
        table = metrics_pipeline.full_table()["table"]

        def extract(backbone: str, mode: str, key: str) -> float | None:
            for row in table:
                if row["backbone"] == backbone and row["safety_mode"] == mode:
                    return row["metrics"].get(key, {}).get("value")
            return None

        backbones = sorted({r["backbone"] for r in table if r["backbone"] != "MOCK"})
        modes = ["nominal_only", "FleetSafe_full"]
        keys_fig = ["success_rate", "collision_rate", "intervention_rate_mean", "spl_mean"]

        figures = {}
        for key in keys_fig:
            figures[key] = {
                "x_labels": backbones,
                "series": {
                    mode: [extract(bb, mode, key) for bb in backbones]
                    for mode in modes
                },
                "y_label": METRIC_LABELS.get(key, key),
                "status": "PRELIMINARY",
                "note": "All values are simulation results — 1 seed each",
            }

        # Fig 4: Cross-backend corridor collision + IR (central paper figure)
        try:
            from .publication_run_scanner import cross_backend_comparison
            cb = cross_backend_comparison()
            models_order = ["gnm", "vint", "nomad"]

            def _cb_row(backend: str, model: str, fleetsafe: bool) -> dict:
                for r in cb.get(backend, {}).get("rows", []):
                    if (r["model"] == model and r["scene"] == "hospital_corridor"
                            and r["fleetsafe"] == fleetsafe):
                        return r
                return {}

            figures["corridor_cross_backend"] = {
                "x_labels":  models_order,
                "backends":  ["mujoco", "isaaclab"],
                "series": {
                    f"{b}_raw_collision": [
                        _cb_row(b, m, False).get("collision_rate") for m in models_order
                    ]
                    for b in ["mujoco", "isaaclab"]
                } | {
                    f"{b}_fs_collision": [
                        _cb_row(b, m, True).get("collision_rate") for m in models_order
                    ]
                    for b in ["mujoco", "isaaclab"]
                } | {
                    f"{b}_fs_ir": [
                        _cb_row(b, m, True).get("intervention_rate_mean") for m in models_order
                    ]
                    for b in ["mujoco", "isaaclab"]
                },
                "proven": {
                    "mujoco":   cb["mujoco"].get("proven", False),
                    "isaaclab": cb["isaaclab"].get("proven", False),
                },
                "n_seeds": {
                    "mujoco":   cb["mujoco"].get("n_seeds", 0),
                    "isaaclab": cb["isaaclab"].get("n_seeds", 0),
                },
                "y_label": "Collision Rate / Intervention Rate",
                "title": "Hospital Corridor: RAW vs FleetSafe (MuJoCo PROVEN + Isaac)",
                "note": (
                    "Central figure: invisible map-hazard mode (Isaac) and visible "
                    "corridor obstacles (MuJoCo). All models, both backends."
                ),
            }
        except Exception:
            pass

        return figures

    def bundle(self, output_dir: Path | None = None) -> Path:
        """Write all exports to a timestamped directory, return its path."""
        ts = int(time.time())
        out = (output_dir or EXPORT_ROOT) / f"bundle_{ts}"
        out.mkdir(parents=True, exist_ok=True)

        tables_dir  = out / "publication_tables"
        figures_dir = out / "publication_figures"
        tables_dir.mkdir()
        figures_dir.mkdir()

        # Tables
        md_main, csv_rows = self.export_comparison_table()
        (tables_dir / "table1_main.md").write_text(md_main)

        if csv_rows:
            keys = list(csv_rows[0].keys())
            with (tables_dir / "table1_main.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                w.writerows(csv_rows)

        (tables_dir / "table2_delta.md").write_text(self.export_delta_table())

        # Metrics JSON
        metrics_data = self.export_metrics_json()
        (out / "publication_metrics.json").write_text(json.dumps(metrics_data, indent=2))

        # Manifest
        manifest = self.export_manifest()
        (out / "publication_manifest.json").write_text(json.dumps(manifest, indent=2))

        # Figure data
        fig_data = self.export_figure_data()
        (figures_dir / "figure_data.json").write_text(json.dumps(fig_data, indent=2))

        # Claim validation report
        claims = metrics_pipeline.claim_validation_report()
        (out / "claim_validation.json").write_text(json.dumps(claims, indent=2))

        # Cross-backend comparison (MuJoCo vs Isaac)
        try:
            from .publication_run_scanner import cross_backend_comparison
            cb = cross_backend_comparison()
            (out / "cross_backend_comparison.json").write_text(
                json.dumps(cb, indent=2, default=str)
            )
        except Exception:
            pass

        # README
        readiness_pct = claims.get("summary", {}).get("readiness_pct", 0.0)
        readme = f"""# FleetSafe Publication Bundle

Generated: {__import__('datetime').datetime.utcfromtimestamp(ts).isoformat()}Z
Overall readiness: {readiness_pct:.1f}% (target ≥ 100%)

## Contents

- `publication_tables/table1_main.md` — Main comparison table (backbone × safety)
- `publication_tables/table1_main.csv` — Same as CSV
- `publication_tables/table2_delta.md` — FleetSafe vs baseline delta table
- `publication_figures/figure_data.json` — Data for Figures 1–3
- `publication_metrics.json` — All metrics with CI and evidence status
- `publication_manifest.json` — Every run ID, git commit, artifact hash
- `claim_validation.json` — Paper claim ↔ evidence audit
- `cross_backend_comparison.json` — MuJoCo PROVEN vs Isaac (best available)

## Evidence Status Key

| Symbol | Meaning                                          |
|--------|--------------------------------------------------|
| ✓      | PROVEN — ≥10 seeds, CI < 5pp, hash-verified      |
| ~      | PRELIMINARY — data exists, insufficient seeds    |
| s      | SYNTHETIC — simulation only, real-world pending  |
| r      | RECORDED_ONLY — data captured, not yet analyzed  |
| ✗      | NOT_VALIDATED — no evidence collected yet        |

## Reproduction

```bash
git checkout <git_commit>
python benchmarks/visualnav/run_benchmark.py --backbone <backbone> --seed <seed>
sha256sum results/<run_id>/aggregate_metrics.json
```
"""
        (out / "README.md").write_text(readme)

        return out


paper_exporter = PaperArtifactExporter()
