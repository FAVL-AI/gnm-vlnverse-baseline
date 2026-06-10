"""FleetSafe Command Center — FastAPI backend."""
from __future__ import annotations

import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .routers import artifacts, launcher, stream, replay, isaac, fleet, safety, missions, sessions, commissioning, robot_control, safety_v7, evidence, experiments, console, demo_supervisor, digital_twin, vln, vln_hub
from .routers.vln_hub import yahboom_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .services.watchdog import watchdog
    watchdog.start()
    yield
    watchdog.stop()


app = FastAPI(
    title="FleetSafe Command Center API",
    version="0.9.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(launcher.router)
app.include_router(artifacts.router)
app.include_router(stream.router)
app.include_router(replay.router)
app.include_router(isaac.router)
app.include_router(fleet.router)
app.include_router(safety.router)
app.include_router(missions.router)
app.include_router(sessions.router)
app.include_router(commissioning.router)
app.include_router(robot_control.router)
app.include_router(safety_v7.router)
app.include_router(evidence.router)
app.include_router(experiments.router)
app.include_router(console.router)
app.include_router(demo_supervisor.router)
app.include_router(digital_twin.router)
app.include_router(vln.router)
app.include_router(vln_hub.router)
app.include_router(yahboom_router)


@app.get("/api/health")
async def api_health() -> dict:
    return {"status": "ok", "version": "0.9.0"}


@app.get("/api/git")
async def git_info() -> dict:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(settings.repo_root),
        ).decode().strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(settings.repo_root),
        ).decode().strip()
    except Exception:
        commit, branch = "unknown", "unknown"
    return {"commit": commit, "branch": branch, "repo_root": str(settings.repo_root)}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )

@app.get("/health")
async def root_health():
    return {
        "ok": True,
        "service": "fleetsafe-backend",
        "status": "healthy",
    }


@app.get("/api/status")
async def api_status() -> dict:
    return {
        "ok": True,
        "service": "fleetsafe-backend",
        "version": "0.9.0",
        "status": "healthy",
        "endpoints": {
            "health": "/health",
            "api_health": "/api/health",
            "demo_status": "/api/demo/status",
            "docs": "/api/docs",
        },
    }



@app.get("/")
async def root():
    return {
        "ok": True,
        "service": "fleetsafe-backend",
        "status": "healthy",
        "health": "/health",
    }
