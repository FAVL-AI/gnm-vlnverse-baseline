"""Tests for SafetyCertificateLogger — JSONL writing, context manager, count."""
from __future__ import annotations

import json
import math
import os
import tempfile
import time
from pathlib import Path

import pytest

from fleet_safe_vla.safety.certificate import SafetyCertificate
from fleet_safe_vla.safety.certificate_logger import SafetyCertificateLogger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_path() -> Path:
    """Return a fresh temp path (not yet created)."""
    td = tempfile.mkdtemp()
    return Path(td) / "certs.jsonl"


def _read_jsonl(path: Path) -> list[dict]:
    lines = path.read_text().strip().splitlines()
    return [json.loads(l) for l in lines if l.strip()]


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_creates_file_and_parent_dirs(self):
        td = tempfile.mkdtemp()
        out = Path(td) / "nested" / "deep" / "certs.jsonl"
        logger = SafetyCertificateLogger(out)
        logger.close()
        assert out.exists()

    def test_path_property(self):
        p = _tmp_path()
        logger = SafetyCertificateLogger(p)
        logger.close()
        assert logger.path == p

    def test_count_starts_at_zero(self):
        p = _tmp_path()
        logger = SafetyCertificateLogger(p)
        assert logger.count == 0
        logger.close()

    def test_repr_contains_count(self):
        p = _tmp_path()
        logger = SafetyCertificateLogger(p)
        logger.close()
        assert "count=0" in repr(logger)


# ---------------------------------------------------------------------------
# Appending
# ---------------------------------------------------------------------------

class TestAppend:
    def test_append_writes_one_line(self):
        p = _tmp_path()
        cert = SafetyCertificate(model_name="gnm", min_dist_m=1.5, safe=True)
        with SafetyCertificateLogger(p) as logger:
            logger.append(cert)
        lines = _read_jsonl(p)
        assert len(lines) == 1

    def test_append_increments_count(self):
        p = _tmp_path()
        with SafetyCertificateLogger(p) as logger:
            for _ in range(5):
                logger.append(SafetyCertificate())
            assert logger.count == 5

    def test_append_writes_valid_json(self):
        p = _tmp_path()
        cert = SafetyCertificate(
            model_name="vint",
            u_nom=[0.2, 0.1],
            u_safe=[0.1, 0.05],
            h_min=0.5,
            min_dist_m=1.2,
            cbf_active=True,
            qp_status="optimal",
            safe=True,
        )
        with SafetyCertificateLogger(p) as logger:
            logger.append(cert)
        row = _read_jsonl(p)[0]
        assert row["model_name"] == "vint"
        assert row["cbf_active"] is True
        assert row["qp_status"] == "optimal"
        assert row["u_nom"] == [0.2, 0.1]

    def test_multiple_appends_multiple_lines(self):
        p = _tmp_path()
        with SafetyCertificateLogger(p) as logger:
            for i in range(10):
                logger.append(SafetyCertificate(min_dist_m=float(i)))
        rows = _read_jsonl(p)
        assert len(rows) == 10
        assert [r["min_dist_m"] for r in rows] == list(range(10))

    def test_partial_run_readable(self):
        """File should be readable even if the process never calls close()."""
        p = _tmp_path()
        logger = SafetyCertificateLogger(p)
        logger.append(SafetyCertificate(model_name="partial"))
        # Don't close — simulate unexpected exit
        rows = _read_jsonl(p)
        assert len(rows) == 1
        assert rows[0]["model_name"] == "partial"
        logger.close()


# ---------------------------------------------------------------------------
# append_from_values
# ---------------------------------------------------------------------------

class TestAppendFromValues:
    def test_writes_all_fields(self):
        p = _tmp_path()
        with SafetyCertificateLogger(p) as logger:
            logger.append_from_values(
                timestamp=1234.5,
                model_name="nomad",
                u_nom=[0.3, -0.1],
                u_safe=[0.2, -0.05],
                h_min=0.8,
                min_dist_m=1.4,
                cbf_active=False,
                qp_status="skipped",
                constraint_margin_min=0.8,
                latency_ms=12.3,
                safe=True,
                notes="test note",
            )
        row = _read_jsonl(p)[0]
        assert row["timestamp"] == 1234.5
        assert row["model_name"] == "nomad"
        assert row["qp_status"] == "skipped"
        assert row["notes"] == "test note"
        assert math.isclose(row["latency_ms"], 12.3)

    def test_defaults_work(self):
        p = _tmp_path()
        with SafetyCertificateLogger(p) as logger:
            logger.append_from_values(model_name="gnm")
        row = _read_jsonl(p)[0]
        assert row["model_name"] == "gnm"
        assert row["u_nom"] == [0.0, 0.0]
        assert row["safe"] is True


# ---------------------------------------------------------------------------
# Auto-timestamp
# ---------------------------------------------------------------------------

class TestAutoTimestamp:
    def test_auto_timestamp_fills_zero_ts(self):
        p = _tmp_path()
        before = time.time()
        with SafetyCertificateLogger(p, auto_timestamp=True) as logger:
            logger.append(SafetyCertificate(timestamp=0.0))
        after = time.time()
        row = _read_jsonl(p)[0]
        assert before <= row["timestamp"] <= after

    def test_auto_timestamp_off_keeps_zero(self):
        p = _tmp_path()
        with SafetyCertificateLogger(p, auto_timestamp=False) as logger:
            logger.append(SafetyCertificate(timestamp=0.0))
        row = _read_jsonl(p)[0]
        assert row["timestamp"] == 0.0

    def test_nonzero_timestamp_not_overwritten(self):
        p = _tmp_path()
        with SafetyCertificateLogger(p, auto_timestamp=True) as logger:
            logger.append(SafetyCertificate(timestamp=42.0))
        row = _read_jsonl(p)[0]
        assert row["timestamp"] == 42.0


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_enter_returns_logger(self):
        p = _tmp_path()
        with SafetyCertificateLogger(p) as logger:
            assert isinstance(logger, SafetyCertificateLogger)

    def test_exit_closes_file(self):
        p = _tmp_path()
        with SafetyCertificateLogger(p) as logger:
            pass
        # After context exit, internal file handle should be None
        assert logger._fh is None

    def test_exception_inside_context_still_closes(self):
        p = _tmp_path()
        try:
            with SafetyCertificateLogger(p) as logger:
                logger.append(SafetyCertificate(model_name="pre-exception"))
                raise RuntimeError("simulated crash")
        except RuntimeError:
            pass
        assert logger._fh is None
        rows = _read_jsonl(p)
        assert rows[0]["model_name"] == "pre-exception"


# ---------------------------------------------------------------------------
# Append mode (resuming an existing file)
# ---------------------------------------------------------------------------

class TestAppendMode:
    def test_appends_to_existing_file(self):
        p = _tmp_path()
        with SafetyCertificateLogger(p) as logger:
            logger.append(SafetyCertificate(model_name="first"))
        with SafetyCertificateLogger(p) as logger:
            logger.append(SafetyCertificate(model_name="second"))
        rows = _read_jsonl(p)
        assert len(rows) == 2
        assert rows[0]["model_name"] == "first"
        assert rows[1]["model_name"] == "second"
