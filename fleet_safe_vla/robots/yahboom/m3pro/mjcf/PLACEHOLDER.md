# MJCF Placeholder — `yahboom_m3pro.xml`

**This directory is waiting for the M3Pro MuJoCo MJCF.**

Place the file at:
```
fleet_safe_vla/robots/yahboom/m3pro/mjcf/yahboom_m3pro.xml
```

The MJCF is needed for MuJoCo-based physics validation and smoke tests.
Isaac Lab training (Stages 1–5) uses the URDF/USD path, not this file.

---

## Starting point

Convert from URDF once the URDF exists:

```bash
# MuJoCo includes a URDF-to-MJCF converter
python3 -c "
import mujoco
mujoco.MjModel.from_xml_path(
    'fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf'
)"
# or use:
# python3 -m mujoco.viewer --mjcf <urdf>
```

Alternatively, hand-write based on `../../mjcf/yahboom_x3.xml` with these
key changes:
- Add `rl_wheel_joint` and `rr_wheel_joint` (4 wheels, not 2)
- Set friction coefficients for mecanum slip (see ASSET_REQUIREMENTS.md)
- Update geometry to M3Pro dimensions

---

## Required structure

```xml
<mujoco model="yahboom_m3pro">
  <option timestep="0.004" integrator="RK4"/>

  <worldbody>
    <body name="base_link">
      <!-- base geom + 4 wheels -->
      <joint name="fl_wheel_joint" type="hinge" axis="0 1 0"/>
      <joint name="fr_wheel_joint" type="hinge" axis="0 1 0"/>
      <joint name="rl_wheel_joint" type="hinge" axis="0 1 0"/>
      <joint name="rr_wheel_joint" type="hinge" axis="0 1 0"/>
    </body>
  </worldbody>

  <actuator>
    <!-- Velocity actuators to match Isaac Lab pattern -->
    <velocity name="fl_drive" joint="fl_wheel_joint" kv="0.5"/>
    <velocity name="fr_drive" joint="fr_wheel_joint" kv="0.5"/>
    <velocity name="rl_drive" joint="rl_wheel_joint" kv="0.5"/>
    <velocity name="rr_drive" joint="rr_wheel_joint" kv="0.5"/>
  </actuator>
</mujoco>
```

---

## Mecanum friction — two options

### Option A (approximate, recommended for initial validation)

Apply directional friction to wheel geoms:
- Normal friction: 0.8 (high grip for propulsion)
- Tangential friction: 0.1 (low for lateral slip — approximates rollers)

```xml
<geom name="fl_wheel_geom" type="cylinder" size="0.048 0.025"
      friction="0.8 0.1 0.001"/>
```

### Option B (physically accurate, for Stage 4–5 sim-to-real)

Model each of the 12 rollers per wheel as a small cylinder at ±45°.
Expensive but necessary for accurate strafing and sim-to-real on smooth floors.

---

## Validation

```bash
# After creating the MJCF:
python3 -c "
import mujoco
m = mujoco.MjModel.from_xml_path(
    'fleet_safe_vla/robots/yahboom/m3pro/mjcf/yahboom_m3pro.xml')
print(f'nq={m.nq}  nv={m.nv}  nu={m.nu}  ngeom={m.ngeom}')
"
# Expected: nu=4 (4 actuators), nq>=7 (freejoint + 4 wheels)

# Smoke test (once tests/test_mujoco_m3pro.py exists):
pytest tests/test_mujoco_m3pro.py -v
```

## Reference

- X3 MJCF for pattern reference: `../../mjcf/yahboom_x3.xml`
- Full spec: `../config/robot_contract_m3pro.yaml`
- Friction guidance: `../ASSET_REQUIREMENTS.md`
