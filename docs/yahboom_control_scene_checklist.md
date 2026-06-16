# Yahboom M3 Pro — Control Scene Checklist (Placeholder)

## Scope

This is a placeholder checklist for the Yahboom M3 Pro control scene in Isaac Sim.
Full Yahboom integration is scheduled for a later release.

The checklist records what must be in place before live GNM control can be enabled
on the Yahboom platform.

---

## Asset Status

| Item | Status |
|---|---|
| Yahboom M3 Pro URDF | Present — `assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf` |
| USD reference stage | Present — `assets/robots/yahboom_m3_pro/yahboom_m3pro_reference.usda` |
| Isaac Sim import report | Present — `assets/robots/yahboom_m3_pro/asset_report.json` |
| Differential drive action graph | Pending |
| Camera sensor prim attached | Pending |
| Lidar sensor prim attached | Pending |
| `/cmd_vel` subscriber wired to drive joints | Pending |
| ROS 2 bridge topics verified live | Pending |

---

## Control Scene Checklist

### Stage preparation

- [ ] Open `assets/robots/yahboom_m3_pro/yahboom_m3pro_reference.usda` in Isaac Sim.
- [ ] Confirm the robot prim loads without physics errors.
- [ ] Add a ground plane prim and enable physics simulation.

### ROS 2 bridge wiring

- [ ] Enable the ROS 2 Bridge extension (Window → Extensions → ROS2 Bridge).
- [ ] Add an OmniGraph with a `ROS2PublishImage` node connected to the camera prim.
- [ ] Add an OmniGraph with a `ROS2PublishOdometry` node connected to the drive articulation.
- [ ] Add an OmniGraph with a `ROS2PublishTransformTree` node.
- [ ] Add an OmniGraph with a `ROS2PublishLaserScan` node connected to the lidar prim.
- [ ] Add an OmniGraph with a `ROS2SubscribeTwist` node driving the wheel joints via `/cmd_vel`.

### Live topic verification

Run after completing the wiring above:

```bash
bash scripts/gnm/check_isaac_bridge.sh --strict
python3 scripts/gnm/verify_live_topics.py --strict
```

All five topics must pass:

- [ ] `/camera/image_raw`
- [ ] `/odom`
- [ ] `/tf`
- [ ] `/scan`
- [ ] `/cmd_vel`

### Manual control test

Before enabling GNM inference:

- [ ] Publish a manual twist command and confirm the robot moves:

  ```bash
  ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
    '{linear: {x: 0.1}, angular: {z: 0.0}}'
  ```

- [ ] Confirm odometry updates in response.
- [ ] Confirm camera image is received.

---

## When Integration is Complete

Once all checklist items above are ticked:

1. Proceed to `docs/FLEETSAFE_GNM_IMPLEMENTATION_MANUAL.md` for the GNM inference
   integration steps.
2. Do not enable live GNM control until all five topics pass `--strict` verification.
