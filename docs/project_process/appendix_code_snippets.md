# Appendix: FleetSafe VLN Commands and Source-Code-Oriented Snippets

This appendix extracts the core commands and fix patterns used during the project. It is intentionally practical: a student should be able to copy the commands, understand the purpose, and know what successful output looks like.

## 1. Environment setup

```bash
cd ~/robotics/FleetSafe-VisualNav-Benchmark
conda deactivate 2>/dev/null || true
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=30
export ROS_LOCALHOST_ONLY=0
```

## 2. Jetson robot verification

```bash
ssh jetson@172.20.10.14
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ws/install/setup.bash
source ~/mircoROS_agent/install/setup.bash 2>/dev/null || true
export ROS_DOMAIN_ID=30
export ROS_LOCALHOST_ONLY=0
ros2 node list
ros2 topic list -t | grep -Ei "cmd_vel|odom|imu|scan|camera|image|depth"
```

## 3. Desktop controller launch

```bash
make vln-desktop-radius RADIUS=0.20
```

## 4. Voice input proof

```bash
ros2 topic info /fleetsafe/instruction_voice -v
ros2 topic pub --once /fleetsafe/instruction_voice std_msgs/msg/String \
"{data: 'move forward slowly while avoiding nearby obstacles'}"
```

## 5. Certificate proof

```bash
LATEST_CERT="$(ls -td results/certificates/* | head -1)"
tail -n 1 "$LATEST_CERT"/vln_certificates_m3pro.jsonl | python3 -m json.tool
```

## 6. Representative evidence schema

```json
{
  "source": "voice",
  "safe": true,
  "qp_status": "optimal",
  "h_min": 0.07155599426651008,
  "min_dist_m": 0.33399999141693115,
  "safety_radius_m": 0.2,
  "u_nominal": [0.06, 0.0],
  "u_safe": [0.04019999742507934, 0.0],
  "cbf_active": true,
  "camera_seen": true
}
```

## 7. Pseudocode for guaranteed evidence emission

```python
def handle_instruction(msg, source):
    instruction_id = make_instruction_id()
    parsed = parse_instruction(msg.data, source)
    try:
        u_nom = backbone_router(parsed, latest_camera, latest_odom)
        lidar = sanitize_scans(scan0, scan1)
        u_safe, qp_status = cbf_filter(u_nom, lidar.effective_clearance)
        decision = classify_decision(qp_status, dry_run=True)
    except Exception as exc:
        u_nom = [0.0, 0.0]
        u_safe = [0.0, 0.0]
        qp_status = "exception"
        decision = "exception"
    finally:
        emit_trace_and_certificate(
            instruction_id=instruction_id,
            parsed=parsed,
            u_nom=u_nom,
            u_safe=u_safe,
            qp_status=qp_status,
            decision=decision,
        )
```

## 8. Commit command for selected evidence only

```bash
git add results/demo_evidence_voice_vln_real_robot/
git commit -m "evidence: add voice-conditioned real-robot VLN safety trace"
git push origin main
```
