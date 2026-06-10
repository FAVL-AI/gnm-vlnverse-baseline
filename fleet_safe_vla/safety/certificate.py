"""Per-timestep safety certificate for the FleetSafe CBF-QP filter.

Each time the safety filter runs it should emit one SafetyCertificate.
Certificates are the primary audit artifact proving that every command sent
to the robot passed a mathematically defined safety check.

No external dependencies beyond the standard library (numpy is optional and
used only for finite-value checks when available).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class SafetyCertificate:
    """Per-timestep safety certificate emitted by the CBF-QP filter."""

    # ── Identity ──────────────────────────────────────────────────────────────
    timestamp: float = 0.0
    model_name: str = ""

    # ── Commands ──────────────────────────────────────────────────────────────
    u_nom: List[float] = field(default_factory=lambda: [0.0, 0.0])
    u_safe: List[float] = field(default_factory=lambda: [0.0, 0.0])

    # ── CBF state ─────────────────────────────────────────────────────────────
    h_min: float = 0.0
    min_dist_m: float = 0.0
    cbf_active: bool = False
    qp_status: str = "optimal"           # "optimal" | "estop_fallback" | "infeasible" | "skipped"
    constraint_margin_min: float = 0.0   # min slack across all CBF constraints

    # ── Timing ────────────────────────────────────────────────────────────────
    latency_ms: float = 0.0

    # ── Overall verdict ───────────────────────────────────────────────────────
    safe: bool = True
    notes: str = ""

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict."""
        return asdict(self)

    def to_json(self) -> str:
        """Return a single-line JSON string (JSONL-compatible)."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> "SafetyCertificate":
        """Construct from a plain dict (e.g., parsed from JSONL)."""
        return cls(
            timestamp=float(d.get("timestamp", 0.0)),
            model_name=str(d.get("model_name", "")),
            u_nom=list(d.get("u_nom", [0.0, 0.0])),
            u_safe=list(d.get("u_safe", [0.0, 0.0])),
            h_min=float(d.get("h_min", 0.0)),
            min_dist_m=float(d.get("min_dist_m", 0.0)),
            cbf_active=bool(d.get("cbf_active", False)),
            qp_status=str(d.get("qp_status", "optimal")),
            constraint_margin_min=float(d.get("constraint_margin_min", 0.0)),
            latency_ms=float(d.get("latency_ms", 0.0)),
            safe=bool(d.get("safe", True)),
            notes=str(d.get("notes", "")),
        )

    @classmethod
    def from_json(cls, line: str) -> "SafetyCertificate":
        """Construct from a JSONL line."""
        return cls.from_dict(json.loads(line))

    # ── Validity checks ───────────────────────────────────────────────────────

    def is_valid(
        self,
        d_safe: float = 0.5,
        h_tol: float = 0.02,
        latency_ms_max: float = 100.0,
    ) -> bool:
        """Return True if this certificate represents a safe, well-formed step.

        Args:
            d_safe: minimum required clearance distance (metres).
            h_tol: tolerance on barrier value (small negatives accepted for
                   numerical precision).
            latency_ms_max: maximum acceptable sensor-to-command latency.
        """
        if not self._u_safe_finite():
            return False
        # estop_fallback is always considered safe (robot stopped)
        if self.qp_status == "estop_fallback":
            return True
        if self.qp_status not in ("optimal", "skipped"):
            return False
        if self.h_min < -h_tol:
            return False
        if self.min_dist_m < d_safe - h_tol:
            return False
        if self.constraint_margin_min < -h_tol:
            return False
        if self.latency_ms > latency_ms_max:
            return False
        return True

    def _u_safe_finite(self) -> bool:
        """Return True if every component of u_safe is a finite number."""
        try:
            import numpy as np  # optional fast path
            return bool(np.all(np.isfinite(self.u_safe)))
        except ImportError:
            return all(math.isfinite(v) for v in self.u_safe)

    def violation_reasons(
        self,
        d_safe: float = 0.5,
        h_tol: float = 0.02,
        latency_ms_max: float = 100.0,
    ) -> List[str]:
        """Return a list of human-readable violation strings (empty → valid)."""
        reasons: List[str] = []
        if not self._u_safe_finite():
            reasons.append(f"u_safe contains non-finite values: {self.u_safe}")
        if self.h_min < -h_tol:
            reasons.append(f"h_min={self.h_min:.4f} < -{h_tol}")
        if self.min_dist_m < d_safe - h_tol:
            reasons.append(
                f"min_dist_m={self.min_dist_m:.4f} < d_safe-tol={d_safe - h_tol:.4f}"
            )
        if self.qp_status not in ("optimal", "estop_fallback", "skipped"):
            reasons.append(f"qp_status={self.qp_status!r} is not acceptable")
        elif self.qp_status not in ("estop_fallback", "skipped"):
            if self.constraint_margin_min < -h_tol:
                reasons.append(
                    f"constraint_margin_min={self.constraint_margin_min:.4f} < -{h_tol}"
                )
        if self.latency_ms > latency_ms_max:
            reasons.append(
                f"latency_ms={self.latency_ms:.1f} > {latency_ms_max:.1f}"
            )
        return reasons
