"""SafetyCertificateLogger — append SafetyCertificate records to a JSONL file.

Usage (explicit):
    logger = SafetyCertificateLogger("results/certificates/run.jsonl")
    logger.append(cert)
    logger.close()

Usage (context manager):
    with SafetyCertificateLogger("results/certificates/run.jsonl") as logger:
        for step in episode:
            logger.append_from_values(timestamp=t, model_name="gnm", ...)

Each call to append() writes one line and flushes immediately so partial runs
are always readable even if the process is killed.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from fleet_safe_vla.safety.certificate import SafetyCertificate


class SafetyCertificateLogger:
    """Write SafetyCertificate records to a JSONL file, one per timestep."""

    def __init__(self, output_path: str | Path, *, auto_timestamp: bool = True):
        """
        Args:
            output_path: Path to the output .jsonl file.
                         Parent directories are created automatically.
            auto_timestamp: If True and a certificate has timestamp=0.0,
                            replace it with the current wall-clock time.
        """
        self._path = Path(output_path)
        self._auto_ts = auto_timestamp
        self._fh = None
        self._count = 0
        self._open()

    # ── File management ───────────────────────────────────────────────────────

    def _open(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self._path.open("a", encoding="utf-8", buffering=1)

    def flush(self):
        if self._fh is not None:
            self._fh.flush()
            os.fsync(self._fh.fileno())

    def close(self):
        if self._fh is not None:
            self._fh.flush()
            self._fh.close()
            self._fh = None

    # ── Writing ───────────────────────────────────────────────────────────────

    def append(self, certificate: SafetyCertificate) -> None:
        """Append a SafetyCertificate as one JSONL line."""
        if self._fh is None:
            self._open()
        if self._auto_ts and certificate.timestamp == 0.0:
            certificate.timestamp = time.time()
        self._fh.write(certificate.to_json() + "\n")
        self._fh.flush()
        self._count += 1

    def append_from_values(
        self,
        *,
        timestamp: float = 0.0,
        model_name: str = "",
        u_nom: Optional[list] = None,
        u_safe: Optional[list] = None,
        h_min: float = 0.0,
        min_dist_m: float = 0.0,
        cbf_active: bool = False,
        qp_status: str = "optimal",
        constraint_margin_min: float = 0.0,
        latency_ms: float = 0.0,
        safe: bool = True,
        notes: str = "",
    ) -> None:
        """Construct and append a SafetyCertificate from keyword arguments."""
        cert = SafetyCertificate(
            timestamp=timestamp if timestamp != 0.0 else (time.time() if self._auto_ts else 0.0),
            model_name=model_name,
            u_nom=u_nom if u_nom is not None else [0.0, 0.0],
            u_safe=u_safe if u_safe is not None else [0.0, 0.0],
            h_min=h_min,
            min_dist_m=min_dist_m,
            cbf_active=cbf_active,
            qp_status=qp_status,
            constraint_margin_min=constraint_margin_min,
            latency_ms=latency_ms,
            safe=safe,
            notes=notes,
        )
        self.append(cert)

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "SafetyCertificateLogger":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── Introspection ─────────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._path

    @property
    def count(self) -> int:
        """Number of certificates written in this session."""
        return self._count

    def __repr__(self) -> str:
        return f"SafetyCertificateLogger(path={self._path!r}, count={self._count})"
