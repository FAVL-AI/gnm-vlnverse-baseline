# Isaac Sim Streaming Dashboard — Runbook

## Purpose

This document describes how to launch the Isaac Sim streaming server on the
Isaac workstation and connect to it for interactive visualization and episode
replay.

**Isaac Sim is the visualization and replay layer**, not the current physics
backend for benchmark evaluation.  All published metric claims come from the
MuJoCo backend (see `docs/governance/CLAIMS_AND_LIMITATIONS.md`).  Isaac Sim
is used for:

- Interactive frame-by-frame intervention replay
- 3-D scene inspection of obstacle placement and robot trajectories
- Future Isaac Lab physics-backed evaluation (gated, not yet enabled)

---

## Prerequisites

| Requirement | Check |
|---|---|
| Isaac Sim installed at `~/isaacsim/` | `ls ~/isaacsim/isaac-sim.streaming.sh` |
| NVIDIA GPU with driver ≥ 535 | `nvidia-smi` |
| conda env `isaac` with Isaac Lab | `conda activate isaac && python -c "import isaaclab"` |
| OMNI_KIT_ACCEPT_EULA set | auto-set by launcher scripts |

---

## Step 1 — Launch the streaming server (Isaac workstation)

```bash
cd ~/isaacsim
./isaac-sim.streaming.sh
```

Wait for the log line:
```
[omni.kit.livestream.websocket] Streaming app loaded
```

This typically takes 60–90 seconds on first launch (shader compilation).
Subsequent launches are faster.

The server listens on:
- WebRTC port: **4000** (default)
- HTTP/WebSocket: **8211** (default)

Only one client may be connected per Isaac instance at a time.

---

## Step 2 — Connect from desktop

### Option A: NVIDIA WebRTC Streaming Client (recommended)

Download from: https://developer.nvidia.com/isaac-sim  
Select **Streaming Client** in the download options.

```
Host: <isaac-workstation-ip>
Port: 4000
```

Click **Connect**.

### Option B: Web browser via Docker Compose

NVIDIA provides a containerised web viewer:

```bash
# On the machine with browser access (can be the workstation itself)
docker pull nvcr.io/nvidia/isaac-sim:webrtc-client
docker compose -f ~/isaacsim/kit/exts/omni.kit.livestream.webrtc/docker-compose.yml up
```

Then open: `http://localhost:8080` in a browser.

> **Note:** Only the Docker Compose web path provides a full browser-based
> viewer.  Pointing a browser directly at port 4000 or 8211 will not work
> without the WebRTC client frontend.

---

## Step 3 — Run the FleetSafe viewer (Isaac workstation, second terminal)

After the streaming server is up:

```bash
conda activate isaac
cd ~/robotics/FleetSafe-VisualNav-Benchmark

# Asset viewer (no episode required)
./scripts/isaaclab/view_m3pro.sh

# Intervention replay (requires a benchmark episode directory)
./scripts/isaaclab/replay_intervention.sh \
  --episode-dir benchmarks/visualnav/results/<run_id>/episodes/episode_0008 \
  --jump-to-interventions

# Replay with speed control
./scripts/isaaclab/replay_intervention.sh \
  --episode-dir <path> \
  --speed 0.5 \
  --show-counterfactual
```

The viewer script prints the streaming status and evidence contract at startup.

---

## Keyboard controls (Isaac GUI active)

| Key | Action |
|---|---|
| `Space` | Pause / resume |
| `n` | Next frame |
| `p` | Previous frame |
| `i` | Jump to next intervention frame |
| `j` | Jump to previous intervention frame |
| `q` | Quit |

---

## What the replay viewer shows

Every visual element maps to a field in `intervention_evidence.jsonl`.
No interpolation or extrapolated physics is displayed.

| Visual | Source field |
|---|---|
| Robot sphere (blue/red) | `scene_graph_before.nodes.robot.position` |
| Trail color | `intervention_applied` per frame |
| Red arrow | `raw_action` |
| Green arrow | `safe_action` |
| Edge colors | `scene_graph_before.edges[*].relation` |
| Overlay text | `intervention_reason`, `causal_explanation` |
| Counterfactual paths | `counterfactual_explanation` (mock backend only) |

Missing required artifacts → explicit red overlay warning.
Mock backend → `MOCK COUNTERFACTUAL ROLLOUT` overlay always shown.

---

## Headless export (no Isaac required)

To generate a replay GIF or MP4 without Isaac Sim:

```bash
python scripts/visualnav/export_intervention_video.py \
  --episode-dir benchmarks/visualnav/results/<run_id>/episodes/episode_0008 \
  --output replay.gif \
  --fps 4

# Interventions-only cut
python scripts/visualnav/export_intervention_video.py \
  --episode-dir <path> \
  --output interventions_only.gif \
  --interventions-only
```

Requires: `matplotlib`, `pillow`.  Fallback: PNG frame dump if neither
`ffmpeg` nor Pillow is available.

---

## Streaming troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Client can't connect | Firewall blocking port 4000 | Open port 4000/UDP on workstation |
| Black screen after connect | Shaders still compiling | Wait 60 s, retry |
| `Streaming app loaded` never appears | Isaac Sim crash | Check `~/.nvidia-omniverse/logs/` |
| Second client fails to connect | Only one client allowed | Disconnect existing client first |
| `conda activate isaac` fails | Wrong env | `conda env list` — look for `isaac` |

---

## Evidence boundary

The Isaac streaming viewer is for **visualization and audit**, not for
generating benchmark metrics.

```
MuJoCo physics backend   ← metric generation (collision, SPL, intervention rate)
Isaac Sim streaming      ← visual audit of intervention evidence
```

Until the Isaac Lab backend passes its implementation gates
(`BACKEND_ISAACLAB` in `visualnav_runner.py`), no metric claims may be
attributed to Isaac Sim runs.
