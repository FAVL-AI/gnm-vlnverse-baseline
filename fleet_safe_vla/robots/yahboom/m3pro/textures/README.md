# M3Pro PBR Texture Maps

Place PNG files here to upgrade the Isaac Sim robot from constant-colour PBR to
full texture-mapped PBR. `load_nvidia_assets.py` auto-detects these files and
connects them via `UsdUVTexture` nodes — no code changes needed.

## Required files (1024×1024 px, linear colour space)

| File | Channel | Description |
|------|---------|-------------|
| `m3pro_chassis_diffuse.png`   | RGB | Chassis body colour (anodised dark grey) |
| `m3pro_chassis_normal.png`    | RGB | Chassis surface normals (tangent space) |
| `m3pro_chassis_metalness.png` | R   | Metallic mask (0=plastic, 1=aluminium) |
| `m3pro_chassis_roughness.png` | R   | Roughness map (0=mirror, 1=matte) |
| `m3pro_wheel_diffuse.png`     | RGB | Tyre/wheel colour |
| `m3pro_wheel_normal.png`      | RGB | Wheel surface normals |
| `m3pro_wheel_metalness.png`   | R   | Metallic mask |
| `m3pro_wheel_roughness.png`   | R   | Roughness map |

Sensor links (lidar, camera) use constant PBR values and do not have texture files.

## How to create these from Blender / the Yahboom STEP file

```bash
# If Yahboom provides a STEP/STP CAD file:
# 1. Import STEP into Blender: File → Import → STEP
# 2. Separate chassis / wheel objects
# 3. UV-unwrap each mesh (Smart UV Project)
# 4. Bake to textures: Cycles → Bake → Diffuse, Normal, Roughness
# 5. Export 1024×1024 PNGs to this directory
# 6. Re-run: python scripts/isaaclab/load_nvidia_assets.py --env hospital
```

## Without texture files (current state)

The PBR materials still work — `load_nvidia_assets.py` uses physically correct
constant values:
- Chassis: metallic=0.55, roughness=0.40, diffuse=(0.12, 0.12, 0.12)  ← anodised aluminium
- Wheels:  metallic=0.00, roughness=0.90, diffuse=(0.05, 0.05, 0.05)  ← rubber
- LiDAR:   metallic=0.30, roughness=0.25, diffuse=(0.05, 0.20, 0.70)  ← blue sensor
- Camera:  metallic=0.10, roughness=0.60, diffuse=(0.03, 0.03, 0.03)  ← matte black
