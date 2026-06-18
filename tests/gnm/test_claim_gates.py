"""
tests/gnm/test_claim_gates.py

CI-enforced claim-gate tests.  These convert static audit documents into
machine-checked assertions so leakage or regression is caught automatically.
"""
from __future__ import annotations

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
    ):
        assert claim_id in ledger, f"Claim '{claim_id}' missing from ledger"
        assert ledger[claim_id] != "BLOCKED", (
            f"Claim '{claim_id}' must not be BLOCKED — evidence should be present"
        )
