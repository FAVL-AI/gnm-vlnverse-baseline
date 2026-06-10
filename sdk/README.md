# FleetSafe Python SDK

Thin client for the FleetSafe REST + WebSocket API.

## Install

```bash
pip install -e ../.[dev]
# or just copy sdk/ into your project
```

## Usage

```python
from fleetsafe_sdk import FleetSafeClient

client = FleetSafeClient("http://localhost:8000")

# Health check
print(client.health())

# List robots
robots = client.get_robots()

# Stream telemetry (WebSocket, yields dicts)
for event in client.stream_telemetry(robot_id="m3pro_01", max_events=100):
    print(event["timestamp"], event["cbf_active"])

# Inject a safety event
client.inject_safety_event(
    robot_id="m3pro_01",
    event_type="cbf_intervention",
    payload={"margin": 0.12, "velocity_pre": 0.8},
)

# Replay an episode
client.replay_episode(episode_id="traj_0042", speed=2.0)
```

## API reference

See the auto-generated OpenAPI docs at `http://localhost:8000/docs`.
