"""
FleetSafe Robot Web Viewer — FastAPI Application.

Serves a Three.js URDF viewer with real-time joint state streaming.
Reads from ROS2 /joint_states if available, else generates dummy walking data.

Endpoints:
  GET  /                     → static/index.html
  GET  /api/robot/info       → robot URDF metadata
  GET  /api/safety/status    → safety filter state
  WS   /ws/joint_states      → WebSocket joint state stream (50 Hz)
  GET  /api/fleet/status     → fleet-wide risk status

Usage:
    conda activate isaac  # or any env with fastapi/uvicorn
    python web/robot_web_viewer/app.py
    # Open http://localhost:8080

    # With ROS2:
    source /opt/ros/humble/setup.bash
    python web/robot_web_viewer/app.py --ros2
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from pathlib import Path
from typing import AsyncGenerator

import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="FleetSafe Robot Web Viewer",
    description="Real-time H1 humanoid robot state visualization",
    version="0.1.0",
)

_STATIC_DIR = Path(__file__).parent / "static"
_STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# ── ROS2 bridge (optional) ────────────────────────────────────────────────────

_ros2_available = False
_joint_state_cache: dict = {
    "names": [],
    "positions": [],
    "velocities": [],
    "timestamp": 0.0,
}
_safety_state_cache: dict = {
    "state": "NOMINAL",
    "base_tilt_rad": 0.0,
    "base_height_m": 1.0,
    "is_safe": True,
    "last_trigger": "",
    "timestamp": 0.0,
}

try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import JointState
    import threading

    _ros2_available = True

    class _JointStateListener(Node):
        def __init__(self):
            super().__init__("fleet_safe_web_viewer")
            self.create_subscription(
                JointState, "/joint_states", self._callback, 10
            )

        def _callback(self, msg):
            _joint_state_cache.update({
                "names": list(msg.name),
                "positions": list(msg.position),
                "velocities": list(msg.velocity),
                "timestamp": time.time(),
            })

    def _start_ros2_node():
        rclpy.init()
        node = _JointStateListener()
        try:
            rclpy.spin(node)
        except Exception:
            pass
        finally:
            node.destroy_node()
            rclpy.shutdown()

    _ros2_thread = threading.Thread(target=_start_ros2_node, daemon=True)
    _ros2_thread.start()

except ImportError:
    pass

# ── Joint names and defaults ──────────────────────────────────────────────────

JOINT_NAMES = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
    "left_shoulder_pitch", "left_shoulder_roll", "left_elbow", "left_wrist",
    "right_shoulder_pitch", "right_shoulder_roll", "right_elbow", "right_wrist",
]

_DEFAULT_POS = [0, 0, -0.4, 0.8, -0.4, 0, 0, -0.4, 0.8, -0.4,
                0, 0, 0, 0, 0, 0, 0, 0]


# ── Dummy data generator ──────────────────────────────────────────────────────

def _generate_dummy_joint_state() -> dict:
    """Generate synthetic walking joint state for visualization."""
    t = time.time()
    freq = 1.2  # step frequency Hz

    pos = list(_DEFAULT_POS)
    # Walking gait: sinusoidal hip and knee motion
    phase = 2 * math.pi * freq * t
    amplitude = 0.3

    # Left leg
    pos[2] = -0.4 + amplitude * math.sin(phase)
    pos[3] =  0.8 + amplitude * abs(math.sin(phase))
    pos[4] = -0.4 - amplitude * 0.3 * math.sin(phase)

    # Right leg (opposite phase)
    pos[7] = -0.4 + amplitude * math.sin(phase + math.pi)
    pos[8] =  0.8 + amplitude * abs(math.sin(phase + math.pi))
    pos[9] = -0.4 - amplitude * 0.3 * math.sin(phase + math.pi)

    # Arms (counter-swing)
    pos[10] = 0.3 * math.sin(phase + math.pi)
    pos[14] = 0.3 * math.sin(phase)

    return {
        "names": JOINT_NAMES,
        "positions": [round(p, 4) for p in pos],
        "velocities": [0.0] * len(JOINT_NAMES),
        "timestamp": t,
        "source": "dummy",
    }


def _get_joint_state() -> dict:
    """Get current joint state from ROS2 or dummy generator."""
    if _ros2_available and _joint_state_cache["names"]:
        return dict(_joint_state_cache, source="ros2")
    return _generate_dummy_joint_state()


# ── REST API endpoints ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main viewer page."""
    index_path = _STATIC_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text())
    return HTMLResponse(_FALLBACK_HTML)


@app.get("/yahboom", response_class=HTMLResponse)
async def yahboom_dashboard():
    """Isaac Sim Yahboom Digital Twin operator dashboard."""
    page = _STATIC_DIR / "yahboom_dashboard.html"
    if page.exists():
        return HTMLResponse(page.read_text())
    return HTMLResponse(
        "<h2>Dashboard not found</h2>"
        "<p>Ensure <code>static/yahboom_dashboard.html</code> exists.</p>"
    )


@app.get("/visualnav", response_class=HTMLResponse)
async def visualnav_dashboard():
    """FleetSafe × VisualNav-Transformer benchmark dashboard."""
    page = _STATIC_DIR / "visualnav_dashboard.html"
    if page.exists():
        return HTMLResponse(page.read_text())
    return HTMLResponse(
        "<h2>VisualNav dashboard not found</h2>"
        "<p>Ensure <code>static/visualnav_dashboard.html</code> exists.</p>"
    )


@app.get("/api/robot/info")
async def robot_info():
    """Return H1 robot URDF metadata."""
    return JSONResponse({
        "name": "H1 Humanoid Robot",
        "version": "1.0",
        "dof": 18,
        "mass_kg": 47.0,
        "height_m": 1.8,
        "joints": [
            {
                "name": name,
                "index": i,
                "type": "revolute",
                "limits": {
                    "lower": lim[0],
                    "upper": lim[1],
                },
                "default_pos": _DEFAULT_POS[i],
            }
            for i, (name, lim) in enumerate(zip(JOINT_NAMES, [
                [-0.785, 0.785], [-0.523, 0.523], [-1.57, 1.57], [-0.087, 2.443], [-0.785, 0.785],
                [-0.785, 0.785], [-0.523, 0.523], [-1.57, 1.57], [-0.087, 2.443], [-0.785, 0.785],
                [-3.14, 3.14], [-1.57, 1.57], [-1.57, 1.57], [-1.57, 1.57],
                [-3.14, 3.14], [-1.57, 1.57], [-1.57, 1.57], [-1.57, 1.57],
            ]))
        ],
        "urdf_available": True,
        "ros2_connected": _ros2_available,
        "data_source": "ros2" if (_ros2_available and _joint_state_cache["names"]) else "dummy",
    })


@app.get("/api/safety/status")
async def safety_status():
    """Return current safety filter state."""
    # Try to import fleet safety for real state
    try:
        from fleet_safe_vla.fleet_safety.cbf_filter import h_tilt
        obs = np.zeros(45, dtype=np.float32)
        obs[3:6] = [0.0, 0.0, -1.0]
        h = h_tilt(obs[3:6], max_tilt_rad=0.7)
        state = _safety_state_cache.copy()
        state["h_min"] = float(h)
    except Exception:
        state = _safety_state_cache.copy()

    state["timestamp"] = time.time()
    return JSONResponse(state)


@app.get("/api/fleet/status")
async def fleet_status_route():
    """Return fleet-wide safety status (demo data if not running live)."""
    return JSONResponse({
        "timestamp": time.time(),
        "fleet_risk_level": "NOMINAL",
        "n_robots": 1,
        "n_nominal": 1,
        "n_emergency": 0,
        "fraction_safe": 1.0,
        "mean_risk_score": 0.05,
        "fleet_risk_score": 0.05,
        "alerts": [],
    })


# ── VisualNav API endpoints ───────────────────────────────────────────────────

_VNT_ROOT   = Path(__file__).parents[2] / "third_party" / "visualnav-transformer"
_RESULTS_DIR = Path(__file__).parents[2] / "benchmarks" / "visualnav" / "results"
_REPORTS_DIR = Path(__file__).parents[2] / "benchmarks" / "visualnav" / "reports"

# Live step cache for WebSocket streaming (updated by background benchmark run)
_visualnav_step_cache: dict = {
    "pose":       {"x": 0.0, "y": 0.0, "yaw": 0.0},
    "goal_xy":    {"x": 2.0, "y": 0.0},
    "raw_cmd":    {"vx": 0.0, "vy": 0.0, "wz": 0.0},
    "safe_cmd":   {"vx": 0.0, "vy": 0.0, "wz": 0.0},
    "action":     {"model": "—", "goal_distance": None, "goal_reached": False,
                   "waypoints": [], "inference_ms": 0.0},
    "safety":     {"enabled": False, "intervention_count": 0, "estop_count": 0,
                   "min_dist_m": None, "intervention_rate": 0.0,
                   "intervened": False, "estop": False, "reason": ""},
    "episode":    {"success": False, "collision": False, "path_length_m": 0.0,
                   "near_violation_count": 0, "steps": 0},
    "timestamp":  0.0,
}


@app.get("/api/visualnav/gates")
async def visualnav_gates():
    """Run VisualNav reproduction gates 0–6 and return results."""
    try:
        import sys
        _repo_root = str(Path(__file__).parents[2])
        if _repo_root not in sys.path:
            sys.path.insert(0, _repo_root)
        from fleet_safe_vla.integrations.visualnav_transformer.validate_gates import (
            gate_0_upstream_exists, gate_1_checkpoints_exist,
            gate_2_static_inference, gate_3_camera_adapter,
            gate_4_sim_cmd_vel, gate_5_fleetsafe_wrapper, gate_6_report_export,
        )
        gate_fns = [
            gate_0_upstream_exists, gate_1_checkpoints_exist,
            gate_2_static_inference, gate_3_camera_adapter,
            gate_4_sim_cmd_vel, gate_5_fleetsafe_wrapper, gate_6_report_export,
        ]
        results = []
        for fn in gate_fns:
            r = fn()
            results.append({"gate": r.gate, "name": r.name,
                             "passed": r.passed, "message": r.message, "ms": r.ms})
        return JSONResponse({"gates": results})
    except Exception as exc:
        return JSONResponse({"gates": [], "error": str(exc)}, status_code=500)


@app.get("/api/visualnav/status")
async def visualnav_status():
    """Return current live step state for the dashboard."""
    return JSONResponse(dict(_visualnav_step_cache, timestamp=time.time()))


@app.post("/api/visualnav/run-smoke")
async def visualnav_run_smoke(request: dict = None):
    """
    Run a smoke benchmark (1 seed, 1 scene, 50 steps) in the background.
    Returns aggregate results when complete.
    """
    import subprocess, sys as _sys
    from pathlib import Path as _Path
    repo = _Path(__file__).parents[2]
    script = repo / "scripts" / "visualnav" / "_run_benchmark.py"

    body = {}
    try:
        from fastapi import Request
    except Exception:
        pass

    model     = (request or {}).get("model", "gnm") if isinstance(request, dict) else "gnm"
    fleetsafe = (request or {}).get("fleetsafe", False) if isinstance(request, dict) else False

    vnt_dir = repo / "third_party" / "visualnav-transformer"
    ckpt    = vnt_dir / "model_weights" / model / f"{model}.pth"

    if not ckpt.exists():
        return JSONResponse({
            "error": f"Checkpoint not found: {ckpt}",
            "hint": "Run: bash scripts/visualnav/setup_visualnav.sh --download-weights",
        }, status_code=400)

    out_dir = _RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{model}_{'fleetsafe' if fleetsafe else 'baseline'}_smoke.json"

    try:
        result = subprocess.run(
            [_sys.executable, str(script),
             "--model",      model,
             "--checkpoint", str(ckpt),
             "--config",     str(repo / "configs" / "visualnav" / "isaac_benchmark.yaml"),
             "--output",     str(out_file),
             "--fleetsafe",  "true" if fleetsafe else "false",
             "--smoke-test",
             "--max-steps",  "50"],
            capture_output=True, text=True, timeout=120,
            env={"PYTHONPATH": f"{repo}:{vnt_dir/'train'}", **__import__("os").environ},
        )
        if result.returncode == 0 and out_file.exists():
            import json as _json
            data = _json.loads(out_file.read_text())
            return JSONResponse(data)
        else:
            return JSONResponse({
                "error": "Benchmark run failed",
                "stderr": result.stderr[-500:],
            }, status_code=500)
    except subprocess.TimeoutExpired:
        return JSONResponse({"error": "Timeout (120 s) — try fewer steps"}, status_code=504)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/visualnav/export-report")
async def visualnav_export_report():
    """Export consolidated HTML/CSV report from all results JSON files."""
    import subprocess, sys as _sys
    repo    = Path(__file__).parents[2]
    script  = repo / "scripts" / "visualnav" / "export_report.py"

    if not _RESULTS_DIR.exists() or not list(_RESULTS_DIR.glob("*.json")):
        return JSONResponse({"message": "No results found. Run a benchmark first."})

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [_sys.executable, str(script),
         "--input",      str(_RESULTS_DIR),
         "--output-dir", str(_REPORTS_DIR)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        return JSONResponse({"message": f"Report exported to {_REPORTS_DIR}/benchmark_report.html"})
    return JSONResponse({"message": f"Export failed: {result.stderr[-200:]}"}, status_code=500)


@app.websocket("/ws/visualnav")
async def ws_visualnav(websocket: WebSocket):
    """WebSocket stream for live visualnav step updates (2 Hz poll of cache)."""
    await _manager.connect(websocket)
    try:
        while True:
            payload = json.dumps(_visualnav_step_cache)
            await websocket.send_text(payload)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        _manager.disconnect(websocket)
    except Exception:
        _manager.disconnect(websocket)


# ── WebSocket joint state stream ──────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active_connections:
            self.active_connections.remove(ws)

    async def broadcast(self, data: str):
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


_manager = ConnectionManager()


@app.websocket("/ws/joint_states")
async def ws_joint_states(websocket: WebSocket):
    """
    WebSocket endpoint that streams joint states at 50 Hz.
    Send message "cmd:STOP" to stop streaming.
    """
    await _manager.connect(websocket)
    try:
        while True:
            state = _get_joint_state()
            payload = json.dumps(state)
            await websocket.send_text(payload)
            await asyncio.sleep(0.02)  # 50 Hz
    except WebSocketDisconnect:
        _manager.disconnect(websocket)
    except Exception:
        _manager.disconnect(websocket)


# ── Fallback HTML (inline, for when static/index.html is missing) ─────────────

_FALLBACK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>FleetSafe Robot Viewer</title>
<style>
  body { margin: 0; background: #1a1a2e; color: #eee; font-family: monospace; }
  #header { padding: 10px 20px; background: #16213e; border-bottom: 1px solid #0f3460; }
  #status { padding: 5px 20px; background: #0f3460; font-size: 12px; }
  #canvas-container { display: flex; height: calc(100vh - 80px); }
  #viewer { flex: 1; display: flex; align-items: center; justify-content: center; }
  #sidebar { width: 320px; overflow-y: auto; padding: 10px; background: #16213e; }
  .joint-bar { margin: 3px 0; }
  .joint-name { font-size: 11px; color: #aaa; }
  .bar-container { height: 8px; background: #0f3460; border-radius: 4px; }
  .bar-fill { height: 100%; background: #00d4ff; border-radius: 4px; transition: width 0.05s; }
  canvas { border: 1px solid #0f3460; }
</style>
</head>
<body>
<div id="header">
  <h2 style="margin:0;color:#00d4ff">FleetSafe H1 Robot Viewer</h2>
</div>
<div id="status" id="status-bar">Connecting to /ws/joint_states...</div>
<div id="canvas-container">
  <div id="viewer">
    <canvas id="stick-canvas" width="600" height="500"></canvas>
  </div>
  <div id="sidebar">
    <h3 style="color:#00d4ff;margin:0 0 10px">Joint States</h3>
    <div id="joint-bars"></div>
    <hr style="border-color:#0f3460;margin:10px 0">
    <div id="safety-info" style="font-size:12px;">
      <div>Safety State: <span id="safety-state">NOMINAL</span></div>
      <div>Data Source: <span id="data-source">connecting...</span></div>
    </div>
  </div>
</div>

<script>
const jointNames = [
  'left_hip_yaw','left_hip_roll','left_hip_pitch','left_knee','left_ankle',
  'right_hip_yaw','right_hip_roll','right_hip_pitch','right_knee','right_ankle',
  'left_shoulder_pitch','left_shoulder_roll','left_elbow','left_wrist',
  'right_shoulder_pitch','right_shoulder_roll','right_elbow','right_wrist'
];
const jointLimits = [
  [-0.785,0.785],[-0.523,0.523],[-1.57,1.57],[-0.087,2.443],[-0.785,0.785],
  [-0.785,0.785],[-0.523,0.523],[-1.57,1.57],[-0.087,2.443],[-0.785,0.785],
  [-3.14,3.14],[-1.57,1.57],[-1.57,1.57],[-1.57,1.57],
  [-3.14,3.14],[-1.57,1.57],[-1.57,1.57],[-1.57,1.57],
];

// Create joint bar UI
const barsDiv = document.getElementById('joint-bars');
const barElements = {};
jointNames.forEach((name, i) => {
  const div = document.createElement('div');
  div.className = 'joint-bar';
  div.innerHTML = `
    <div class="joint-name">${name} <span id="val-${i}">0.000</span></div>
    <div class="bar-container"><div class="bar-fill" id="bar-${i}" style="width:50%"></div></div>`;
  barsDiv.appendChild(div);
  barElements[i] = {bar: document.getElementById(`bar-${i}`), val: document.getElementById(`val-${i}`)};
});

function updateBars(positions) {
  positions.forEach((pos, i) => {
    if (!barElements[i]) return;
    const [lo, hi] = jointLimits[i] || [-3.14, 3.14];
    const pct = ((pos - lo) / (hi - lo)) * 100;
    barElements[i].bar.style.width = Math.max(0, Math.min(100, pct)) + '%';
    barElements[i].val.textContent = pos.toFixed(3);
  });
}

// Stick figure renderer
const canvas = document.getElementById('stick-canvas');
const ctx = canvas.getContext('2d');
const W = canvas.width, H = canvas.height;
const cx = W/2, cy = H*0.45;
const scale = 130;

function drawStickFigure(pos) {
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#1a1a2e';
  ctx.fillRect(0, 0, W, H);

  // Simple 2D stick figure from joint angles
  const hipY = cy;
  const hipX = cx;

  // Spine / torso
  const torsoLen = scale * 0.55;
  const headY = hipY - torsoLen;
  ctx.strokeStyle = '#00d4ff';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(hipX, hipY);
  ctx.lineTo(cx, headY);
  ctx.stroke();

  // Head
  ctx.beginPath();
  ctx.arc(cx, headY - 18, 18, 0, 2*Math.PI);
  ctx.strokeStyle = '#00d4ff';
  ctx.stroke();

  // Legs
  const legColor = ['#ff6b6b', '#6bcfff'];
  const sides = [-1, 1];
  sides.forEach((sign, si) => {
    const hipOffset = sign * scale * 0.08;
    const hipPitch = pos[2 + si * 5] || -0.4;
    const knee = pos[3 + si * 5] || 0.8;
    const thigh = scale * 0.45;
    const shank = scale * 0.45;
    const thighX = hipX + hipOffset + thigh * Math.sin(hipPitch);
    const thighY = hipY + thigh * Math.cos(hipPitch);
    const kneeAngle = hipPitch + knee;
    const footX = thighX + shank * Math.sin(kneeAngle);
    const footY = thighY + shank * Math.cos(kneeAngle);

    ctx.strokeStyle = legColor[si];
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(hipX + hipOffset, hipY);
    ctx.lineTo(thighX, thighY);
    ctx.lineTo(footX, footY);
    ctx.stroke();
  });

  // Arms
  const armColor = ['#ffd166', '#06d6a0'];
  sides.forEach((sign, si) => {
    const shoulderX = cx + sign * scale * 0.2;
    const shoulderY = headY + 20;
    const pitch = pos[10 + si * 4] || 0;
    const elbowAngle = pitch - 0.3;
    const upper = scale * 0.3;
    const lower = scale * 0.27;
    const elbowX = shoulderX + upper * Math.sin(pitch) * sign;
    const elbowY = shoulderY + upper * Math.cos(pitch);
    const handX = elbowX + lower * Math.sin(elbowAngle) * sign;
    const handY = elbowY + lower * Math.cos(elbowAngle);

    ctx.strokeStyle = armColor[si];
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(shoulderX, shoulderY);
    ctx.lineTo(elbowX, elbowY);
    ctx.lineTo(handX, handY);
    ctx.stroke();
  });

  // Ground line
  ctx.strokeStyle = '#0f3460';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, H*0.92);
  ctx.lineTo(W, H*0.92);
  ctx.stroke();

  // Label
  ctx.fillStyle = '#aaa';
  ctx.font = '11px monospace';
  ctx.fillText('H1 Stick Figure (Sagittal Plane)', 10, 20);
}

// WebSocket connection
let ws, retryCount = 0;
function connect() {
  ws = new WebSocket('ws://' + location.host + '/ws/joint_states');
  ws.onopen = () => {
    document.getElementById('status').textContent = 'Connected — streaming at 50 Hz';
    retryCount = 0;
  };
  ws.onmessage = (evt) => {
    const state = JSON.parse(evt.data);
    if (state.positions && state.positions.length > 0) {
      updateBars(state.positions);
      drawStickFigure(state.positions);
      document.getElementById('data-source').textContent = state.source || 'unknown';
    }
  };
  ws.onerror = () => {
    document.getElementById('status').textContent = 'WebSocket error';
  };
  ws.onclose = () => {
    retryCount++;
    document.getElementById('status').textContent = `Disconnected. Retry ${retryCount}...`;
    setTimeout(connect, 2000);
  };
}

// Initial stick figure with default pose
drawStickFigure([0,0,-0.4,0.8,-0.4, 0,0,-0.4,0.8,-0.4, 0,0,0,0, 0,0,0,0]);
connect();

// Fetch safety status periodically
setInterval(async () => {
  try {
    const resp = await fetch('/api/safety/status');
    const data = await resp.json();
    document.getElementById('safety-state').textContent = data.state;
    document.getElementById('safety-state').style.color =
      data.is_safe ? '#06d6a0' : '#ff6b6b';
  } catch (e) {}
}, 2000);
</script>
</body>
</html>"""


# ── Static files ──────────────────────────────────────────────────────────────

def _ensure_static_files() -> None:
    """Write static files if they don't exist."""
    index_path = _STATIC_DIR / "index.html"
    if not index_path.exists():
        index_path.write_text(_FALLBACK_HTML)

    viewer_js = _STATIC_DIR / "viewer.js"
    if not viewer_js.exists():
        viewer_js.write_text(_VIEWER_JS)


_VIEWER_JS = """
/**
 * FleetSafe Three.js URDF Viewer
 * Connects to WebSocket joint state stream and animates robot.
 * Requires: three.js, URDFLoader (optional)
 */
(function() {
  'use strict';

  // Simple WebSocket joint state subscriber
  class JointStateStream {
    constructor(url, onUpdate) {
      this.url = url;
      this.onUpdate = onUpdate;
      this._connect();
    }

    _connect() {
      this.ws = new WebSocket(this.url);
      this.ws.onmessage = (evt) => {
        try {
          const state = JSON.parse(evt.data);
          this.onUpdate(state);
        } catch(e) {}
      };
      this.ws.onclose = () => {
        setTimeout(() => this._connect(), 2000);
      };
    }

    close() { this.ws.close(); }
  }

  window.FleetSafeViewer = { JointStateStream };
})();
"""


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FleetSafe Robot Web Viewer")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    _ensure_static_files()

    print(f"Starting FleetSafe Robot Web Viewer at http://{args.host}:{args.port}")
    print(f"ROS2 available: {_ros2_available}")

    uvicorn.run(
        "app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
        app_dir=str(Path(__file__).parent),
    )
