"""VLNTraceLogger — append VLNTrace records to a JSONL file.

Every VLN decision timestep writes one line. This makes the system fully
auditable: language parse, visual grounding, model output, safety result,
and certificate reference are all in one record.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fleet_safe_vla.vln.instruction_schema import VLNTrace


class VLNTraceLogger:
    """Append VLNTrace records to a JSONL file, one per timestep."""

    def __init__(self, output_path: str | Path, *, auto_timestamp: bool = True):
        self._path = Path(output_path)
        self._auto_ts = auto_timestamp
        self._fh = None
        self._count = 0
        self._open()

    # ── File management ───────────────────────────────────────────────────────

    def _open(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self._path.open("a", encoding="utf-8", buffering=1)

    def close(self):
        if self._fh is not None:
            self._fh.flush()
            self._fh.close()
            self._fh = None

    def flush(self):
        if self._fh is not None:
            self._fh.flush()
            os.fsync(self._fh.fileno())

    # ── Writing ───────────────────────────────────────────────────────────────

    def append(self, trace: VLNTrace) -> None:
        if self._fh is None:
            self._open()
        if self._auto_ts and trace.timestamp_ns == 0:
            trace.timestamp_ns = int(time.time() * 1e9)
        self._fh.write(trace.to_json() + "\n")
        self._fh.flush()
        self._count += 1

    def append_from_values(
        self,
        *,
        instruction_source:      str  = "",
        raw_instruction:         str  = "",
        parsed_instruction:      Dict[str, Any] | None = None,
        grounding_candidates:    List[Dict[str, Any]] | None = None,
        chosen_subgoal:          Dict[str, Any] | None = None,
        current_camera_frame_id: str  = "",
        model_name:              str  = "",
        u_nom:                   List[float] | None = None,
        u_safe:                  List[float] | None = None,
        cbf_active:              bool  = False,
        qp_status:               str  = "not_available",
        min_dist_m:              float = 0.0,
        h_min:                   float = 0.0,
        latency_ms:              float = 0.0,
        stop_reason:             Optional[str] = None,
        certificate_id:          str  = "",
        notes:                   str  = "",
        timestamp_ns:            int  = 0,
    ) -> None:
        trace = VLNTrace(
            timestamp_ns=timestamp_ns,
            instruction_source=instruction_source,
            raw_instruction=raw_instruction,
            parsed_instruction=parsed_instruction or {},
            grounding_candidates=grounding_candidates or [],
            chosen_subgoal=chosen_subgoal or {},
            current_camera_frame_id=current_camera_frame_id,
            model_name=model_name,
            u_nom=u_nom or [0.0, 0.0],
            u_safe=u_safe or [0.0, 0.0],
            cbf_active=cbf_active,
            qp_status=qp_status,
            min_dist_m=min_dist_m,
            h_min=h_min,
            latency_ms=latency_ms,
            stop_reason=stop_reason,
            certificate_id=certificate_id,
            notes=notes,
        )
        self.append(trace)

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "VLNTraceLogger":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── Introspection ─────────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._path

    @property
    def count(self) -> int:
        return self._count

    def __repr__(self) -> str:
        return f"VLNTraceLogger(path={self._path!r}, count={self._count})"

    # ── Reading ───────────────────────────────────────────────────────────────

    @staticmethod
    def read_jsonl(path: str | Path) -> List[VLNTrace]:
        records = []
        with Path(path).open() as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(VLNTrace.from_json(line))
        return records
