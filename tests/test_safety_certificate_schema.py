"""Tests for the FleetSafe SafetyCertificate dataclass.

Verifies:
  - Default construction
  - Certificate validity (is_valid)
  - Invalid certificates fail is_valid
  - JSON / dict round-trip
  - violation_reasons reports the right cause
"""

from __future__ import annotations

import json
import math
import pytest

from fleet_safe_vla.safety.certificate import SafetyCertificate


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _valid_cert(**kwargs) -> SafetyCertificate:
    """Return a valid certificate with optional overrides."""
    defaults = dict(
        timestamp=1.0,
        model_name="gnm",
        u_nom=[0.2, 0.1],
        u_safe=[0.1, 0.05],
        h_min=0.25,
        min_dist_m=1.0,
        cbf_active=False,
        qp_status="optimal",
        constraint_margin_min=0.1,
        latency_ms=20.0,
        safe=True,
        notes="",
    )
    defaults.update(kwargs)
    return SafetyCertificate(**defaults)


# ── Construction ──────────────────────────────────────────────────────────────

class TestConstruction:
    def test_default_construction(self):
        cert = SafetyCertificate()
        assert cert.timestamp == 0.0
        assert cert.u_nom == [0.0, 0.0]
        assert cert.u_safe == [0.0, 0.0]
        assert cert.safe is True
        assert cert.qp_status == "optimal"

    def test_valid_cert_is_valid(self):
        cert = _valid_cert()
        assert cert.is_valid()

    def test_model_name_stored(self):
        cert = _valid_cert(model_name="vint")
        assert cert.model_name == "vint"


# ── is_valid ──────────────────────────────────────────────────────────────────

class TestIsValid:
    def test_h_min_too_negative_fails(self):
        cert = _valid_cert(h_min=-0.1)
        assert not cert.is_valid(h_tol=0.02)

    def test_h_min_within_tolerance_passes(self):
        # Small negative within tolerance should pass
        cert = _valid_cert(h_min=-0.01)
        assert cert.is_valid(h_tol=0.02)

    def test_min_dist_below_d_safe_fails(self):
        cert = _valid_cert(min_dist_m=0.3)
        assert not cert.is_valid(d_safe=0.5, h_tol=0.02)

    def test_min_dist_at_d_safe_passes(self):
        cert = _valid_cert(min_dist_m=0.5)
        assert cert.is_valid(d_safe=0.5, h_tol=0.02)

    def test_latency_exceeded_fails(self):
        cert = _valid_cert(latency_ms=150.0)
        assert not cert.is_valid(latency_ms_max=100.0)

    def test_latency_at_limit_passes(self):
        cert = _valid_cert(latency_ms=100.0)
        assert cert.is_valid(latency_ms_max=100.0)

    def test_bad_qp_status_fails(self):
        cert = _valid_cert(qp_status="error")
        assert not cert.is_valid()

    def test_estop_fallback_is_valid(self):
        """Emergency stop is always considered safe."""
        cert = _valid_cert(qp_status="estop_fallback", h_min=-0.5, min_dist_m=0.1)
        assert cert.is_valid()

    def test_skipped_is_valid(self):
        cert = _valid_cert(qp_status="skipped")
        assert cert.is_valid()

    def test_negative_constraint_margin_fails(self):
        cert = _valid_cert(constraint_margin_min=-0.1, qp_status="optimal")
        assert not cert.is_valid(h_tol=0.02)

    def test_non_finite_u_safe_fails(self):
        cert = _valid_cert(u_safe=[float("nan"), 0.0])
        assert not cert.is_valid()

    def test_inf_u_safe_fails(self):
        cert = _valid_cert(u_safe=[float("inf"), 0.0])
        assert not cert.is_valid()


# ── violation_reasons ─────────────────────────────────────────────────────────

class TestViolationReasons:
    def test_valid_cert_no_reasons(self):
        cert = _valid_cert()
        assert cert.violation_reasons() == []

    def test_h_min_violation_reported(self):
        cert = _valid_cert(h_min=-0.1)
        reasons = cert.violation_reasons(h_tol=0.02)
        assert any("h_min" in r for r in reasons)

    def test_dist_violation_reported(self):
        cert = _valid_cert(min_dist_m=0.2)
        reasons = cert.violation_reasons(d_safe=0.5)
        assert any("min_dist_m" in r for r in reasons)

    def test_latency_violation_reported(self):
        cert = _valid_cert(latency_ms=200.0)
        reasons = cert.violation_reasons(latency_ms_max=100.0)
        assert any("latency" in r for r in reasons)

    def test_multiple_violations_all_reported(self):
        cert = _valid_cert(h_min=-0.5, latency_ms=999.0)
        reasons = cert.violation_reasons(h_tol=0.02, latency_ms_max=100.0)
        assert len(reasons) >= 2


# ── JSON / dict round-trip ────────────────────────────────────────────────────

class TestSerialization:
    def test_to_dict_keys(self):
        cert = _valid_cert()
        d = cert.to_dict()
        for key in ("timestamp", "model_name", "u_nom", "u_safe",
                    "h_min", "min_dist_m", "cbf_active", "qp_status",
                    "constraint_margin_min", "latency_ms", "safe", "notes"):
            assert key in d, f"Missing key: {key}"

    def test_from_dict_roundtrip(self):
        cert = _valid_cert(model_name="nomad", cbf_active=True, h_min=0.12)
        d = cert.to_dict()
        cert2 = SafetyCertificate.from_dict(d)
        assert cert2.model_name == "nomad"
        assert cert2.cbf_active is True
        assert cert2.h_min == pytest.approx(0.12)

    def test_to_json_is_valid_json(self):
        cert = _valid_cert()
        s = cert.to_json()
        parsed = json.loads(s)
        assert parsed["model_name"] == "gnm"

    def test_from_json_roundtrip(self):
        cert = _valid_cert(timestamp=42.5, latency_ms=33.3)
        cert2 = SafetyCertificate.from_json(cert.to_json())
        assert cert2.timestamp == pytest.approx(42.5)
        assert cert2.latency_ms == pytest.approx(33.3)

    def test_from_dict_missing_keys_use_defaults(self):
        """from_dict should not raise on incomplete dicts."""
        cert = SafetyCertificate.from_dict({"model_name": "gnm"})
        assert cert.model_name == "gnm"
        assert cert.timestamp == 0.0
        assert cert.safe is True

    def test_json_roundtrip_preserves_cbf_active(self):
        for flag in (True, False):
            cert = _valid_cert(cbf_active=flag)
            cert2 = SafetyCertificate.from_json(cert.to_json())
            assert cert2.cbf_active is flag

    def test_json_roundtrip_list_fields(self):
        cert = _valid_cert(u_nom=[0.25, -0.1], u_safe=[0.1, 0.05])
        cert2 = SafetyCertificate.from_json(cert.to_json())
        assert cert2.u_nom == pytest.approx([0.25, -0.1])
        assert cert2.u_safe == pytest.approx([0.1, 0.05])
