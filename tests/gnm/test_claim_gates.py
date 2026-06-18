"""
tests/gnm/test_claim_gates.py

CI-enforced claim-gate tests.  These convert static audit documents into
machine-checked assertions so leakage or regression is caught automatically.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AUDIT = REPO / "results/research_audit"


# ── Feature-audit / no-oracle-leakage ────────────────────────────────────────

AUDIT_MD = AUDIT / "stop_policy_feature_audit.md"

# Expected verdicts from the summary table (format: "| method | … | VERDICT |")
EXPECTED_VERDICTS = {
    "baseline_gnm": "PASS",
    "hand_tuned_waypoint_gate": "PASS",
    "logistic_stop_head": "PASS",
    "temporal_neural_stop_head": "PASS",
    "geometry_aware_oracle": "DIAGNOSTIC",
}

# These methods must NOT show "Yes" in the "Oracle geometry" column.
NO_ORACLE_METHODS = {
    "baseline_gnm",
    "hand_tuned_waypoint_gate",
    "logistic_stop_head",
    "temporal_neural_stop_head",
}


def _parse_summary_table(text: str) -> dict[str, dict[str, str]]:
    """Return {method: {col_header: cell}} for the summary table rows."""
    lines = text.splitlines()
    table_start = next(
        (i for i, l in enumerate(lines) if "| Method |" in l), None
    )
    assert table_start is not None, "Summary table not found in feature audit"

    headers = [h.strip() for h in lines[table_start].split("|") if h.strip()]
    rows: dict[str, dict[str, str]] = {}
    for line in lines[table_start + 2 :]:  # skip header + separator
        if not line.strip().startswith("|"):
            break
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) < len(headers):
            continue
        method = cells[0]
        rows[method] = dict(zip(headers, cells))
    return rows


def test_feature_audit_file_exists():
    assert AUDIT_MD.exists(), f"Feature audit missing: {AUDIT_MD}"


def test_feature_audit_all_methods_present():
    text = AUDIT_MD.read_text()
    rows = _parse_summary_table(text)
    for method in EXPECTED_VERDICTS:
        assert method in rows, f"Method '{method}' not found in audit summary table"


def test_feature_audit_verdicts():
    text = AUDIT_MD.read_text()
    rows = _parse_summary_table(text)
    for method, expected in EXPECTED_VERDICTS.items():
        actual = rows[method].get("Audit result", "")
        assert expected in actual, (
            f"Method '{method}': expected verdict '{expected}', got '{actual}'"
        )


def test_no_oracle_leakage_in_deployable_methods():
    """Deployable stop-policy methods must not use oracle geometry."""
    text = AUDIT_MD.read_text()
    rows = _parse_summary_table(text)
    for method in NO_ORACLE_METHODS:
        oracle_cell = rows[method].get("Oracle geometry", "")
        assert "Yes" not in oracle_cell, (
            f"Oracle leakage: method '{method}' shows oracle geometry in feature audit"
        )


def test_oracle_method_flagged_as_diagnostic():
    """geometry_aware_oracle must be DIAGNOSTIC, not PASS — it is not deployable."""
    text = AUDIT_MD.read_text()
    rows = _parse_summary_table(text)
    verdict = rows["geometry_aware_oracle"].get("Audit result", "")
    assert "DIAGNOSTIC" in verdict, (
        f"geometry_aware_oracle must be DIAGNOSTIC, got '{verdict}'"
    )
    assert "PASS" not in verdict, (
        "geometry_aware_oracle must NOT be PASS — it uses oracle geometry"
    )


# ── Claim-ledger sanity ───────────────────────────────────────────────────────

LEDGER_JSON = AUDIT / "research_claim_validation_ledger.json"

MUST_BE_BLOCKED = {
    "yahboom_episode_001_rosbag2",
    "yahboom_rosbag_to_gnm_conversion",
    "gnm_finetune_on_yahboom",
    "fleetsafe_gnm_closed_loop_physical",
    "trackb_language_grounding_completed",
    "global_superiority_over_gnm_vint_nomad_saferpath",
}


def test_claim_ledger_exists():
    assert LEDGER_JSON.exists(), f"Claim ledger missing: {LEDGER_JSON}"


def test_blocked_claims_remain_blocked():
    """Blocked claims must not be silently promoted to validated in the ledger."""
    rows = json.loads(LEDGER_JSON.read_text())
    ledger = {r["id"]: r["status"] for r in rows}
    for claim_id in MUST_BE_BLOCKED:
        assert claim_id in ledger, f"Claim '{claim_id}' missing from ledger"
        assert ledger[claim_id] == "BLOCKED", (
            f"Claim '{claim_id}' must be BLOCKED but is '{ledger[claim_id]}'"
        )


def test_tracka_provenance_claims_not_blocked():
    """Track A provenance claims must have evidence (not BLOCKED)."""
    rows = json.loads(LEDGER_JSON.read_text())
    ledger = {r["id"]: r["status"] for r in rows}
    for claim_id in (
        "tracka_baseline_per_episode_provenance",
        "tracka_all_methods_per_episode_provenance",
        "tracka_per_scene_breakdown_complete",
        "tracka_paired_comparison_complete",
        "tracka_robustness_summary_complete",
    ):
        assert claim_id in ledger, f"Claim '{claim_id}' missing from ledger"
        assert ledger[claim_id] != "BLOCKED", (
            f"Claim '{claim_id}' must not be BLOCKED — evidence should be present"
        )


# ── Per-scene breakdown sanity ────────────────────────────────────────────────

SCENE_CSV = AUDIT / "tracka_per_scene_breakdown.csv"

EXPECTED_SCENES = {"kujiale_0092", "kujiale_0118", "kujiale_0203", "kujiale_0271"}
EXPECTED_METHODS_SCENE = {
    "baseline_gnm", "hand_tuned_waypoint_gate", "logistic_stop_head",
    "temporal_neural_stop_head", "geometry_aware_oracle",
}


def test_per_scene_breakdown_exists():
    assert SCENE_CSV.exists(), f"Per-scene CSV missing: {SCENE_CSV}"


def test_per_scene_breakdown_structure():
    rows = list(csv.DictReader(SCENE_CSV.open()))
    assert rows, "Per-scene CSV is empty"
    assert len(rows) == 20, f"Expected 20 rows (5 methods × 4 scenes), got {len(rows)}"
    scenes = {r["scene_id"] for r in rows}
    methods = {r["method"] for r in rows}
    assert scenes == EXPECTED_SCENES, f"Scene mismatch: {scenes}"
    assert methods == EXPECTED_METHODS_SCENE, f"Method mismatch: {methods}"


def test_per_scene_kujiale_0118_hard():
    """kujiale_0118 must show 0% SR for all deployable methods — a known hard scene."""
    rows = list(csv.DictReader(SCENE_CSV.open()))
    for row in rows:
        if row["scene_id"] == "kujiale_0118" and row["method"] != "geometry_aware_oracle":
            assert float(row["sr_pct"]) == 0.0, (
                f"kujiale_0118 {row['method']} SR should be 0% "
                f"(hard scene, no episodes succeeded), got {row['sr_pct']}"
            )


# ── Robustness summary sanity ─────────────────────────────────────────────────

ROBUSTNESS_MD = AUDIT / "tracka_robustness_summary.md"


def test_robustness_summary_exists():
    assert ROBUSTNESS_MD.exists(), f"Robustness summary missing: {ROBUSTNESS_MD}"


def test_robustness_summary_acknowledges_no_extra_data():
    text = ROBUSTNESS_MD.read_text()
    assert "No additional held-out trajectories" in text, (
        "Robustness summary must explicitly state that no extra held-out data exists"
    )
    assert "train-split contamination" in text or "in-distribution" in text, (
        "Robustness summary must state why train split cannot be used"
    )


def test_robustness_summary_blocks_global_superiority():
    text = ROBUSTNESS_MD.read_text()
    assert "No global superiority" in text, (
        "Robustness summary must list 'no global superiority' as a non-supported claim"
    )
