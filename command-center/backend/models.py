"""Shared Pydantic models for API request/response."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class LaunchRequest(BaseModel):
    script_key: str
    extra_args: list[str] = []


class JobStatus(BaseModel):
    job_id: str
    script_key: str
    label: str
    status: str          # queued | running | done | error | killed
    pid: int | None
    exit_code: int | None
    started_at: float | None
    finished_at: float | None


class RunSummary(BaseModel):
    run_id: str
    model: str
    fleetsafe: bool
    backend: str
    timestamp_utc: str
    n_episodes: int
    success_rate: float
    collision_rate: float
    spl_mean: float
    intervention_rate_mean: float
    inference_latency_ms_mean: float
    claim_scope: str


class RunDetail(RunSummary):
    metrics: dict[str, Any]
    metadata: dict[str, Any]
    by_scene: dict[str, Any]
    episodes: list[dict[str, Any]]


class ScriptInfo(BaseModel):
    key: str
    label: str
    description: str
    preset: str
    backend: str
    estimated_s: int | None
