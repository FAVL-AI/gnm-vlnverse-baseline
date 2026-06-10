# M3Pro Simulation Asset Requirements

This document is the single source of truth for what must be created before
M3Pro simulation is valid. Do not start Isaac Lab training (Stage 1+) or
MuJoCo validation until all **required** assets pass Stage 0.

```bash
./scripts/isaaclab/train_yahboom.sh --stage 0   # validate all assets
```

---

## 1. URDF — `urdf/yahboom_m3pro.urdf`

**Required for:** Isaac Lab (all stages), ROS2 `robot_state_publisher`

### Joint specification

```xml
<!-- All 4 wheel joints must be type="continuous" (unbounded rotation) -->
<joint name="fl_wheel_joint" type="continuous">...</joint>
<joint name="fr_wheel_joint" type="continuous">...</joint>
<joint name="rl_wheel_joint" type="continuous">...</joint>
<joint name="rr_wheel_joint" type="continuous">...</joint>
```

Joint names are **fixed** — the obs_adapter, env_cfg, safety_node, and
ROS2 launch files all reference them by name.

### Link structure

Minimum required links:
```
base_footprint (virtual, origin at ground centre)
└── base_link   (rigid body, all fixed links merged)
    ├── fl_wheel (continuous, mesh optional)
    ├── fr_wheel (continuous)
    ├── rl_wheel (continuous)
    ├── rr_wheel (continuous)
    ├── lidar_link    (fixed, sensor frame)
    └── camera_link   (fixed, sensor frame)
```

### Inertials

These **must** be measured from the physical robot, not guessed:

| Component | Method |
|---|---|
| Base mass | Weigh with scale; subtract wheel masses |
| Wheel mass | Weigh one wheel × 4 |
| Base inertia tensor | SolidWorks/CAD export, or approximate as box |
| Wheel inertia | Approximate as cylinder: I = 0.5·m·r² (axial) |

Using wrong inertials is the primary cause of sim-to-real transfer failure
for wheeled robots. Even 2× error in mass causes ~30% velocity tracking error.

### Geometry verification checklist

Before committing the URDF, verify against the physical robot:

```
[ ] Wheel radius:    measure with calipers → should be ~0.048 m
[ ] Wheelbase:       measure axle-to-axle → should be ~0.155 m
[ ] Track width:     measure wheel-centre to wheel-centre → ~0.170 m
[ ] Body length:     ~0.290 m
[ ] Body width:      ~0.235 m
[ ] Lidar height:    measure from ground → ~0.16 m above base
[ ] Camera height:   measure from ground → ~0.13 m above base
[ ] Base mass:       weigh → ~2.4 kg total (robot alone, no payload)
```

### Mecanum wheel orientation

Mecanum rollers must be oriented correctly or strafing will behave
incorrectly in simulation:

```
Front-left  (fl): rollers at +45°  (X-pattern)
Front-right (fr): rollers at −45°
Rear-left   (rl): rollers at −45°
Rear-right  (rr): rollers at +45°
```

In MuJoCo (MJCF), mecanum slip is approximated with box friction or
explicit roller geoms (see MJCF section). In Isaac Sim (USD/URDF), use
`ImplicitActuatorCfg` with velocity control — physics-accurate mecanum
roller simulation is NOT required for Stage 1–3 training.

### How to get the CAD

- Yahboom product page: search "RosMaster M3Pro" at yahboom.net
- Request STEP/STP file from Yahboom support
- Export URDF with:
  ```bash
  # solidworks-to-urdf (if using SolidWorks):
  ros2 run xacro xacro robot.urdf.xacro > yahboom_m3pro.urdf
  # or manually write URDF from measurements
  ```
- Validate URDF:
  ```bash
  check_urdf fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf
  ros2 run urdf_parser_py urdf_check yahboom_m3pro.urdf
  ```

---

## 2. MJCF — `mjcf/yahboom_m3pro.xml`

**Required for:** MuJoCo validation (smoke tests, physics regression tests)

### Mecanum friction model

True mecanum roller geometry in MuJoCo is expensive. Two acceptable approaches:

**Approach A — Box friction approximation (recommended for Stage 1–2):**
```xml
<geom name="fl_wheel" type="cylinder" size="0.048 0.025"
      friction="1.0 0.1 0.1"   <!-- frictdir1 (axial slip) = 0.1 -->
      contype="1" conaffinity="1"/>
```
The low axial friction approximates the mecanum rollers allowing strafe.
This is NOT physically accurate but sufficient for velocity-command training.

**Approach B — Explicit roller geoms (Stage 4–5, sim-to-real):**
Model each mecanum roller as a small cylinder with correct orientation.
Computationally expensive but gives realistic strafe behaviour.
Reference: [MuJoCo mecanum model examples](https://github.com/deepmind/mujoco/tree/main/model)

### Actuator specification

```xml
<actuator>
  <!-- Velocity actuators — matches Isaac Lab ImplicitActuatorCfg -->
  <velocity name="fl_drive" joint="fl_wheel_joint" gear="1.0" kv="0.5"/>
  <velocity name="fr_drive" joint="fr_wheel_joint" gear="1.0" kv="0.5"/>
  <velocity name="rl_drive" joint="rl_wheel_joint" gear="1.0" kv="0.5"/>
  <velocity name="rr_drive" joint="rr_wheel_joint" gear="1.0" kv="0.5"/>
</actuator>
```

Tune `kv` (velocity feedback gain) against the X3 MJCF as a baseline:
- Too high → wheel oscillation
- Too low → slow tracking, real robot divergence

### Contact parameters

Start from the X3 values and adjust:
```xml
<contact>
  <pair geom1="floor" geom2="fl_wheel" friction="0.8 0.1 0.001 0.001 0.001"/>
  ...
</contact>
```

### MuJoCo validation (after MJCF exists)

```bash
python scripts/yahboom/validate_motion.py --robot m3pro
pytest tests/test_obs_adapter_m3pro.py -v     # kinematics (no MuJoCo needed)
pytest tests/test_mujoco_m3pro.py -v          # physics (MuJoCo needed, TODO)
```

---

## 3. USD cache — `usd/yahboom_m3pro.usd`

**Auto-generated** by Isaac Sim on first run — no manual creation needed.

Isaac Sim converts the URDF to USD format and caches it:
```
fleet_safe_vla/robots/yahboom/m3pro/usd/
├── yahboom_m3pro.usd           ← generated, ~3 min first run
└── yahboom_m3pro/              ← generated cache directory
```

The USD cache is regenerated automatically if the URDF changes.
Do not commit USD files to git (large binary files, auto-regenerated).

Add to `.gitignore` (already in project root):
```
fleet_safe_vla/robots/yahboom/m3pro/usd/*.usd
fleet_safe_vla/robots/yahboom/m3pro/usd/yahboom_m3pro/
```

---

## 4. Obs adapter — `../controllers/obs_adapter_m3pro.py`

**Status: EXISTS** (created in v0.4)

Implements:
- `M3ProGeometry` — physical constants dataclass
- `M3ProState` — typed sensor state container
- `M3ProCommand` — typed 3-DoF velocity command
- `WheelSpeeds` — typed 4-wheel velocity container
- `mecanum_cmd_to_wheel_speeds()` — pure inverse kinematics
- `wheel_speeds_to_mecanum_cmd()` — pure forward kinematics
- `M3ProObsAdapter` — stateful 47-dim obs vector builder
- `validate_m3pro_contract()` — programmatic asset validation

Tests: `tests/test_obs_adapter_m3pro.py`

---

## Dependency graph

```
Physical M3Pro hardware
      │
      ▼ measurements
  URDF (urdf/yahboom_m3pro.urdf)
      │
      ├──► USD cache (auto, Isaac Sim)
      │         │
      │         └──► Isaac Lab training (Stage 1+)
      │
      ├──► MJCF (mjcf/yahboom_m3pro.xml)
      │         │
      │         └──► MuJoCo validation + smoke tests
      │
      └──► obs_adapter_m3pro.py  ← already exists (pure math, no assets needed)
                │
                └──► ROS2 bridge (real robot, already works)
                └──► Unit tests (already pass)
```

---

## Validation commands

```bash
# Stage 0: check all assets (no GPU, < 5 seconds)
./scripts/isaaclab/train_yahboom.sh --stage 0

# Programmatic check (no scripts needed):
python3 -c "
from fleet_safe_vla.robots.yahboom.controllers.obs_adapter_m3pro import validate_m3pro_contract
r = validate_m3pro_contract(); print(r.summary())
"

# Kinematics unit tests (no assets, no GPU):
pytest tests/test_obs_adapter_m3pro.py -v
```
