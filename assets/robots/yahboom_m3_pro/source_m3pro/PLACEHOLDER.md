# URDF Placeholder — `yahboom_m3pro.urdf`

**This directory is waiting for the M3Pro URDF.**

Place the file at:
```
fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf
```

---

## What must be in the URDF

### Mandatory joints (exact names — do not rename)

```xml
<joint name="fl_wheel_joint" type="continuous">
  <parent link="base_link"/>
  <child  link="fl_wheel"/>
  <origin xyz=" LX  LY  0" rpy="0 0 0"/>   <!-- front-left -->
  <axis   xyz="0 1 0"/>
</joint>
<joint name="fr_wheel_joint" type="continuous">
  <parent link="base_link"/>
  <child  link="fr_wheel"/>
  <origin xyz=" LX -LY  0" rpy="0 0 0"/>   <!-- front-right -->
  <axis   xyz="0 1 0"/>
</joint>
<joint name="rl_wheel_joint" type="continuous">
  <parent link="base_link"/>
  <child  link="rl_wheel"/>
  <origin xyz="-LX  LY  0" rpy="0 0 0"/>   <!-- rear-left -->
  <axis   xyz="0 1 0"/>
</joint>
<joint name="rr_wheel_joint" type="continuous">
  <parent link="base_link"/>
  <child  link="rr_wheel"/>
  <origin xyz="-LX -LY  0" rpy="0 0 0"/>   <!-- rear-right -->
  <axis   xyz="0 1 0"/>
</joint>
```

Substitute with physical measurements:
- `LX` = wheelbase / 2 = ~0.0775 m
- `LY` = track_width / 2 = ~0.0850 m

### Minimum inertial entries

Every link needs `<inertial>` — Isaac Sim rejects URDFs without it:

```xml
<link name="base_link">
  <inertial>
    <origin xyz="0 0 0.04" rpy="0 0 0"/>
    <mass value="1.8"/>           <!-- measured body mass (robot minus wheels) -->
    <inertia ixx="0.013" ixy="0" ixz="0"
             iyy="0.010" iyz="0"
             izz="0.020"/>        <!-- from CAD or box approximation -->
  </inertial>
  ...
</link>

<link name="fl_wheel">
  <inertial>
    <origin xyz="0 0 0" rpy="0 0 0"/>
    <mass value="0.150"/>         <!-- weigh one wheel -->
    <inertia ixx="0.000158" ixy="0" ixz="0"
             iyy="0.000272" iyz="0"
             izz="0.000158"/>     <!-- cylinder: Iaxial=0.5mr², Iradial=m(3r²+h²)/12 -->
  </inertial>
  ...
</link>
```

Cylinder inertia helper (wheel radius r=0.048 m, half-width h=0.012 m, mass m):
- `ixx = iyy = m*(3*r² + h²)/12`  (transverse)
- `izz = 0.5*m*r²`                (axial — wheel spin axis)

### Sensor frames (optional but recommended)

```xml
<joint name="lidar_joint" type="fixed">
  <parent link="base_link"/>
  <child  link="lidar_link"/>
  <origin xyz="0 0 0.16" rpy="0 0 0"/>   <!-- 0.16 m above base origin -->
</joint>

<joint name="camera_joint" type="fixed">
  <parent link="base_link"/>
  <child  link="camera_link"/>
  <origin xyz="0.10 0 0.13" rpy="0 0 0"/> <!-- 0.13 m above, 0.10 m forward -->
</joint>
```

---

## Validation after creating the URDF

```bash
# 1. Structural check (no simulation)
check_urdf fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf

# 2. Isaac Lab Stage 0 (no GPU required)
./scripts/isaaclab/train_yahboom.sh --stage 0

# 3. Visual inspection in Isaac Sim GUI
./scripts/isaaclab/view_yahboom.sh --robot m3pro

# 4. Programmatic check
python3 -c "
from fleet_safe_vla.robots.yahboom.controllers.obs_adapter_m3pro import validate_m3pro_contract
r = validate_m3pro_contract()
print(r.summary())
"
```

## Common URDF mistakes to avoid

| Mistake | Consequence |
|---|---|
| Wrong joint names (e.g. `wheel_fl` instead of `fl_wheel_joint`) | obs_adapter, env_cfg, safety_node all break silently |
| Missing `<inertial>` on any link | Isaac Sim rejects with cryptic USD error |
| `type="revolute"` instead of `type="continuous"` for wheels | wheels stop at joint limits mid-episode |
| Z-up vs Y-up confusion in mesh transforms | robot spawns upside-down or sideways |
| Mass < 0.001 kg on any link | Physics instability (NaN velocities) |
| Incorrect wheel axis (`<axis xyz="1 0 0">` instead of `0 1 0`) | Wheels spin in wrong direction; strafe reversed |

## Reference

- Full spec: `../config/robot_contract_m3pro.yaml`
- Full asset requirements: `../ASSET_REQUIREMENTS.md`
- Obs adapter (already implemented): `../../controllers/obs_adapter_m3pro.py`
