"""ExtendedCertificateLogger — writes ExtendedCertificate records to JSONL.

Wraps fleet_safe_vla SafetyCertificateLogger with the FleetSafe-VLN
extended certificate format (pose, human distance, intervention magnitude).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from fleetsafe_vln.safety.cbf_qp_shield import ExtendedCertificate


class ExtendedCertificateLogger:
    """Append ExtendedCertificate records to a JSONL file, one per timestep."""

    def __init__(self, output_path: str | Path):
        self._path = Path(output_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self._path.open("a", encoding="utf-8", buffering=1)
        self._count = 0

    def append(self, cert: ExtendedCertificate) -> None:
        if cert.t == 0.0:
            cert.t = time.time()
        self._fh.write(json.dumps(cert.to_dict()) + "\n")
        self._fh.flush()
        self._count += 1

    def append_from_values(
        self,
        *,
        t: float = 0.0,
        pose: tuple = (0.0, 0.0, 0.0),
        u_nominal: list = None,
        u_safe: list = None,
        cbf_active: bool = False,
        barrier_value_h: float = 0.0,
        min_obstacle_distance_m: float = 0.0,
        min_human_distance_m: float = float("inf"),
        certificate_valid: bool = True,
        qp_status: str = "optimal",
        latency_ms: float = 0.0,
        model_name: str = "",
    ) -> None:
        cert = ExtendedCertificate(
            t=t if t != 0.0 else time.time(),
            pose=tuple(pose),
            u_nominal=u_nominal or [0.0, 0.0],
            u_safe=u_safe or [0.0, 0.0],
            cbf_active=cbf_active,
            barrier_value_h=barrier_value_h,
            min_obstacle_distance_m=min_obstacle_distance_m,
            min_human_distance_m=min_human_distance_m,
            certificate_valid=certificate_valid,
            qp_status=qp_status,
            latency_ms=latency_ms,
            model_name=model_name,
        )
        self.append(cert)

    def flush(self) -> None:
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def close(self) -> None:
        if self._fh is not None:
            self._fh.flush()
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "ExtendedCertificateLogger":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    @property
    def count(self) -> int:
        return self._count

    @property
    def path(self) -> Path:
        return self._path
