"""Live Isaac Sim camera-state dashboard for the Yahboom M3Pro.

The main panel is the robot's front-facing 2D RGB camera view — what the
model sees — never a spectator/top-down render. Start / Current / Goal
panels share the same front-camera convention (ImageNav framing).

Run with the SYSTEM python after sourcing ROS 2 Humble, from the repo root:
    python3 scripts/robots/camera_state_dashboard.py [port]

The dashboard is a thin governance/UI layer: it subscribes to the live
camera and odometry topics, launches the existing episode runner
(m3pro_ros2_bringup.py) for policy rollouts, tails the episode's
trajectory log for metrics, and never bypasses the safety envelope.
E-stop publishes zero velocity AND terminates the policy process.

Claim boundary (shown in the UI): 2D RGB camera view from the robot
front camera in Isaac Sim — not a physical-robot camera, not a full
VLNVerse benchmark; collision counts appear only when the episode runs
with PhysX contact reporting (--collision-report).
"""

import io
import json
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from PIL import Image as PILImage
from rclpy.node import Node
from sensor_msgs.msg import Image

REPO = Path(__file__).resolve().parents[2]
GOALS_DIR = REPO / "assets/experiments/goals"
ISAAC_PY = "/home/favl/miniforge3/envs/isaac/bin/python"
DEFAULT_CKPT = "checkpoints/ablation_mnv2_baseline/best.pt"

STATE = {
    "scene": "hospital",
    "goal_id": None,
    "checkpoint": DEFAULT_CKPT,
    "policy_running": False,
    "recording": False,
    "stop_reason": None,
    "episode_name": None,
    "pose": None,
    "last_row": {},
    "start_frame": None,   # JPEG bytes captured at rollout start
    "proc": None,
}
LOCK = threading.Lock()


class CameraStateNode(Node):
    def __init__(self):
        super().__init__("camera_state_dashboard")
        self.latest_jpeg = None
        self.latest_stamp = 0.0
        self.create_subscription(Image, "/camera/image_raw", self.on_image, 5)
        self.create_subscription(Odometry, "/odom", self.on_odom, 5)
        self.cmd_pub = self.create_publisher(Twist, "/cmd_vel", 5)

    def on_image(self, msg):
        if msg.encoding != "rgb8":
            return
        img = PILImage.frombytes("RGB", (msg.width, msg.height),
                                 bytes(msg.data))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        self.latest_jpeg = buf.getvalue()
        self.latest_stamp = time.time()
        with LOCK:
            if STATE["policy_running"] and STATE["start_frame"] is None:
                STATE["start_frame"] = self.latest_jpeg

    def on_odom(self, msg):
        p = msg.pose.pose.position
        with LOCK:
            STATE["pose"] = [round(p.x, 3), round(p.y, 3), round(p.z, 4)]

    def publish_zero(self, n=10):
        for _ in range(n):
            self.cmd_pub.publish(Twist())
            time.sleep(0.05)


NODE = None


def list_goals():
    goals = []
    for d in sorted(GOALS_DIR.iterdir()):
        m = d / "goal_metadata.json"
        if m.exists():
            meta = json.loads(m.read_text())
            goals.append({"goal_id": d.name,
                          "scene": meta.get("scene", "unknown"),
                          "goal_pose": meta.get("goal_pose"),
                          "start_pose": meta.get("start_pose")})
    return goals


def newest_traj_row(episode_name):
    if not episode_name:
        return {}
    dirs = sorted((REPO / "assets/experiments/trajectories").glob(
        f"{episode_name}_*"))
    if not dirs:
        return {}
    f = dirs[-1] / "trajectory.jsonl"
    if not f.exists():
        return {}
    try:
        lines = f.read_bytes().splitlines()
        return json.loads(lines[-1]) if lines else {}
    except (json.JSONDecodeError, OSError):
        return {}


def run_policy(goal_id, ckpt, steps, record):
    with LOCK:
        if STATE["proc"] and STATE["proc"].poll() is None:
            return False, "policy already running"
        ep = f"dash_{goal_id}_{time.strftime('%H%M%S')}"
        cmd = [ISAAC_PY, "-u", "scripts/robots/m3pro_ros2_bringup.py",
               "--gnm-control", "--collision-report", "--scene", "hospital",
               "--policy-ckpt", ckpt, "--goal-id", goal_id,
               "--episode-name", ep, "--steps", str(steps),
               "--experiment-id", "camera_state_dashboard",
               "--condition", "dashboard_live"]
        if record:
            cmd.append("--episode")
        meta = json.loads((GOALS_DIR / goal_id /
                           "goal_metadata.json").read_text())
        sp = meta.get("start_pose")
        if isinstance(sp, dict):
            sp = [sp.get("x", 0), sp.get("y", 0),
                  sp.get("yaw_rad", sp.get("yaw", 0))]
        if sp:
            cmd += ["--spawn-pose", ",".join(str(float(v)) for v in sp)]
        log = open(REPO / f"logs/{ep}.log", "w")
        STATE["proc"] = subprocess.Popen(cmd, cwd=REPO, stdout=log,
                                         stderr=subprocess.STDOUT)
        STATE.update(policy_running=True, recording=record, goal_id=goal_id,
                     checkpoint=ckpt, episode_name=ep, stop_reason=None,
                     start_frame=None)
        return True, ep


def stop_policy(reason):
    with LOCK:
        proc = STATE["proc"]
        STATE.update(policy_running=False, stop_reason=reason)
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGINT)
    NODE.publish_zero()
    return True


PAGE = """<!doctype html><meta charset="utf-8">
<title>Yahboom Camera-State Dashboard</title>
<style>
body{font-family:sans-serif;margin:0;display:grid;
     grid-template-columns:230px 1fr;gap:10px;background:#111;color:#eee}
#controls{padding:12px;background:#1a1a1a}
#controls button,#controls select{width:100%;margin:4px 0;padding:8px}
#estop{background:#b00;color:#fff;font-weight:bold}
#main{padding:12px}
#live{width:640px;max-width:100%;border:2px solid #444}
.caption{font-size:.85em;color:#aaa}
#strip{display:flex;gap:10px;margin-top:8px}
#strip img{width:200px;border:1px solid #444}
#metrics{font-family:monospace;font-size:.85em;background:#1a1a1a;
         padding:8px;margin-top:8px;white-space:pre}
.claim{font-size:.8em;color:#e6b800;margin-top:6px}
</style>
<div id="controls">
 <h3>Controls</h3>
 <label>Scene</label><select id="scene"><option>hospital</option></select>
 <label>Goal</label><select id="goal"></select>
 <label>Checkpoint</label><select id="ckpt">
   <option>checkpoints/ablation_mnv2_baseline/best.pt</option>
   <option>checkpoints/scene_holdout_mnv2_baseline/best.pt</option></select>
 <button onclick="api('run',{record:false})">Run Policy</button>
 <button onclick="api('run',{record:true})">Record Episode</button>
 <button id="estop" onclick="api('stop',{reason:'user_estop'})">STOP / E-STOP</button>
 <div class="claim">2D RGB camera view from the robot front camera in
 Isaac Sim. Not a physical-robot camera. Not a full VLNVerse benchmark.
 Collision counts shown only when measured from Isaac PhysX contact
 events.</div>
</div>
<div id="main">
 <h3>Main View: Yahboom Front RGB Camera — Task: Image-Goal Navigation (ImageNav)</h3>
 <img id="live" src="/stream.mjpg">
 <div class="caption">Current State: live front-facing RGB image from /camera/image_raw — the robot-eye view, not a 3D spectator view or top-down map</div>
 <div id="strip">
  <div><img id="startimg" src="/start_state.jpg"><div class="caption">Start State: front-facing RGB at start pose</div></div>
  <div><img id="curimg" src="/current.jpg"><div class="caption">Current State: live front-facing RGB (snapshot)</div></div>
  <div><img id="goalimg" src="/goal_state.jpg"><div class="caption">Goal State: front-facing RGB goal at target pose</div></div>
 </div>
 <div id="metrics">loading…</div>
</div>
<script>
async function api(ep, body){ body = Object.assign({goal_id:goalSel(),
  ckpt:document.getElementById('ckpt').value, steps:900}, body||{});
  await fetch('/api/'+ep, {method:'POST', body:JSON.stringify(body)});
  refresh(); }
function goalSel(){ return document.getElementById('goal').value; }
async function refresh(){
  const s = await (await fetch('/api/state')).json();
  document.getElementById('metrics').textContent =
   `scene: ${s.scene}   goal: ${s.goal_id}   ckpt: ${s.checkpoint}\\n` +
   `pose: ${JSON.stringify(s.pose)}   d2g: ${s.d2g ?? 'n/a'} m\\n` +
   `cmd: v=${s.cmd_v ?? 'n/a'} w=${s.cmd_w ?? 'n/a'}   ` +
   `contacts: ${s.contacts ?? 'n/a (PhysX only)'}\\n` +
   `policy: ${s.policy_running ? 'RUNNING' : 'stopped'}   ` +
   `recording: ${s.recording}   stop_reason: ${s.stop_reason}`;
  const g = await (await fetch('/api/goals')).json();
  const sel = document.getElementById('goal');
  if (sel.options.length !== g.length){ sel.innerHTML='';
    g.forEach(x=>{const o=document.createElement('option');
      o.value=x.goal_id;o.textContent=x.goal_id;sel.appendChild(o);}); }
  document.getElementById('startimg').src='/start_state.jpg?'+Date.now();
  document.getElementById('curimg').src='/current.jpg?'+Date.now();
  document.getElementById('goalimg').src='/goal_state.jpg?goal='+goalSel()+'&'+Date.now();
}
setInterval(refresh, 1500); refresh();
</script>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._send(200, "text/html", PAGE.encode())
        elif path == "/current.jpg":
            jpg = NODE.latest_jpeg or b""
            self._send(200 if jpg else 503, "image/jpeg", jpg)
        elif path == "/start_state.jpg":
            with LOCK:
                jpg = STATE["start_frame"] or b""
            self._send(200 if jpg else 503, "image/jpeg", jpg)
        elif path == "/goal_state.jpg":
            q = dict(p.split("=", 1) for p in self.path.split("?")[1:]
                     for p in p.split("&") if "=" in p) if "?" in self.path else {}
            gid = q.get("goal") or STATE["goal_id"] or "hospital_goal_A"
            p = GOALS_DIR / gid / "goal_image.png"
            if p.exists():
                buf = io.BytesIO()
                PILImage.open(p).convert("RGB").save(buf, "JPEG", quality=85)
                self._send(200, "image/jpeg", buf.getvalue())
            else:
                self._send(404, "text/plain", b"no goal image")
        elif path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Content-Type",
                             "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while True:
                    jpg = NODE.latest_jpeg
                    if jpg:
                        self.wfile.write(b"--frame\r\nContent-Type: "
                                         b"image/jpeg\r\n\r\n" + jpg + b"\r\n")
                    time.sleep(0.15)
            except (BrokenPipeError, ConnectionResetError):
                return
        elif path == "/api/goals":
            self._send(200, "application/json",
                       json.dumps(list_goals()).encode())
        elif path == "/api/state":
            with LOCK:
                row = newest_traj_row(STATE["episode_name"])
                proc = STATE["proc"]
                if STATE["policy_running"] and proc and proc.poll() is not None:
                    STATE.update(policy_running=False,
                                 stop_reason=STATE["stop_reason"]
                                 or "episode_complete")
                out = {k: STATE[k] for k in
                       ("scene", "goal_id", "checkpoint", "policy_running",
                        "recording", "stop_reason", "episode_name", "pose")}
            out["d2g"] = row.get("distance_to_goal_m")
            out["cmd_v"] = row.get("actual_linear_velocity_cmd")
            out["cmd_w"] = row.get("actual_angular_velocity_cmd")
            out["contacts"] = row.get("collision_count_so_far")
            out["camera_age_s"] = round(time.time() - NODE.latest_stamp, 1) \
                if NODE.latest_stamp else None
            self._send(200, "application/json", json.dumps(out).encode())
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/run":
            ok, msg = run_policy(body.get("goal_id", "hospital_goal_A"),
                                 body.get("ckpt", DEFAULT_CKPT),
                                 int(body.get("steps", 900)),
                                 bool(body.get("record", False)))
            self._send(200 if ok else 409, "application/json",
                       json.dumps({"ok": ok, "episode": msg}).encode())
        elif self.path == "/api/stop":
            stop_policy(body.get("reason", "user_estop"))
            self._send(200, "application/json", b'{"ok": true}')
        else:
            self._send(404, "text/plain", b"not found")


def main():
    global NODE
    rclpy.init()
    NODE = CameraStateNode()
    threading.Thread(target=rclpy.spin, args=(NODE,), daemon=True).start()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
    print(f"[dashboard] http://localhost:{port}  (main panel = Yahboom "
          "front RGB camera; claim labels in UI)")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
