"""Artifact/run browser router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import settings
from ..services.artifact_indexer import get_run_detail, list_runs

router = APIRouter(prefix="/api", tags=["artifacts"])


@router.get("/runs")
async def runs() -> list[dict]:
    return list_runs(settings._results_dir)


@router.get("/runs/{run_id}")
async def run_detail(run_id: str) -> dict:
    detail = get_run_detail(settings._results_dir, run_id)
    if detail is None:
        raise HTTPException(404, f"Run {run_id!r} not found")
    return detail


@router.get("/runs/{run_id}/file")
async def serve_file(run_id: str, rel: str) -> FileResponse:
    """Serve a raw artifact file (for download / inline view)."""
    safe_rel = rel.lstrip("/")
    p = settings._results_dir / run_id / safe_rel
    # Refuse path traversal
    try:
        p.relative_to(settings._results_dir)
    except ValueError:
        raise HTTPException(400, "Invalid path")
    if not p.exists() or not p.is_file():
        raise HTTPException(404)
    return FileResponse(str(p))
