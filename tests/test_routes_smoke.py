"""
Route smoke tests — v0.9.

Verifies every critical route is registered in the FastAPI app without
starting a real server. Uses TestClient to confirm 200/non-404 status.

Tests:
  A. Core health routes still respond.
  B. Evidence v0.8 routes all registered.
  C. YOLO v0.9 routes registered under /api/robot.
  D. Experiment v0.9b routes registered.
  E. No route shadowing: /api/robot/status still reachable after safety_v7.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "command-center"))
os.environ.setdefault("FLEETSAFE_ROBOT_DRY_RUN", "true")

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app, raise_server_exceptions=False)


# ── A. Health ─────────────────────────────────────────────────────────────────

def test_health_returns_200():
    r = client.get("/api/health")
    assert r.status_code == 200

def test_health_version_is_090():
    r = client.get("/api/health")
    assert r.json()["version"] == "0.9.0"

def test_git_returns_200():
    r = client.get("/api/git")
    assert r.status_code == 200


# ── B. Evidence v0.8 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/api/evidence/stats",
    "/api/evidence/ledger",
    "/api/evidence/manifest",
    "/api/evidence/training",
    "/api/evidence/ros2",
    "/api/evidence/timeline",
    "/api/evidence/heatmap",
])
def test_evidence_route_not_404(path):
    r = client.get(path)
    assert r.status_code != 404, f"{path} returned 404 — route not registered"

def test_evidence_stats_returns_200():
    r = client.get("/api/evidence/stats")
    assert r.status_code == 200

def test_evidence_stats_has_total():
    r = client.get("/api/evidence/stats")
    body = r.json()
    assert "total" in body
    assert "hashed" in body

def test_evidence_manifest_returns_200():
    r = client.get("/api/evidence/manifest")
    assert r.status_code == 200

def test_evidence_manifest_has_categories():
    r = client.get("/api/evidence/manifest")
    body = r.json()
    assert "categories" in body
    assert len(body["categories"]) >= 9


# ── C. YOLO v0.9 ─────────────────────────────────────────────────────────────

def test_yolo_status_not_404():
    r = client.get("/api/robot/yolo/status")
    assert r.status_code != 404, "GET /api/robot/yolo/status is 404 — route not registered"

def test_yolo_status_returns_200():
    r = client.get("/api/robot/yolo/status")
    assert r.status_code == 200

def test_yolo_status_has_mode():
    r = client.get("/api/robot/yolo/status")
    body = r.json()
    assert "mode" in body
    assert body["mode"] in ("yolo", "mock")

def test_yolo_start_not_404():
    r = client.post("/api/robot/yolo/start")
    assert r.status_code != 404, "POST /api/robot/yolo/start is 404"

def test_yolo_stop_not_404():
    r = client.post("/api/robot/yolo/stop")
    assert r.status_code != 404, "POST /api/robot/yolo/stop is 404"


# ── D. Experiments v0.9b ──────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/api/experiments/runs",
    "/api/experiments/summary",
    "/api/experiments/table",
    "/api/experiments/deltas",
    "/api/experiments/claims",
    "/api/experiments/manifest",
    "/api/experiments/figure-data",
])
def test_experiments_route_not_404(path):
    r = client.get(path)
    assert r.status_code != 404, f"{path} returned 404 — route not registered"

def test_experiments_runs_returns_list():
    r = client.get("/api/experiments/runs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

def test_experiments_summary_has_total():
    r = client.get("/api/experiments/summary")
    assert r.status_code == 200
    body = r.json()
    assert "total_runs" in body
    assert body["total_runs"] > 0

def test_experiments_claims_has_summary():
    r = client.get("/api/experiments/claims")
    assert r.status_code == 200
    body = r.json()
    assert "claims" in body
    assert "summary" in body
    assert "readiness_pct" in body["summary"]


# ── E. No shadowing — robot_control still reachable ───────────────────────────

def test_robot_status_still_200():
    r = client.get("/api/robot/status")
    assert r.status_code == 200, "/api/robot/status shadowed by safety_v7 router"

def test_robot_audit_still_200():
    r = client.get("/api/robot/audit")
    assert r.status_code == 200

def test_robot_relay_guard_still_200():
    r = client.get("/api/robot/relay-guard")
    assert r.status_code == 200

def test_estop_status_still_200():
    r = client.get("/api/robot/estop/status")
    assert r.status_code == 200

def test_relay_status_still_200():
    r = client.get("/api/robot/relay/status")
    assert r.status_code == 200

def test_watchdog_status_still_200():
    r = client.get("/api/robot/watchdog/status")
    assert r.status_code == 200

def test_session_list_still_200():
    r = client.get("/api/robot/session/list")
    assert r.status_code == 200
