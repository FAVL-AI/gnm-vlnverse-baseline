# Yahboom M3 Pro: URDF → USD Import (Isaac Sim)

Converts the Yahboom ROSMASTER M3 Pro URDF to a USD file for use in Isaac Sim.

## Automatic (headless)

```bash
cd ~/robotics/FleetSafe-VisualNav-Benchmark
bash scripts/import_yahboom_m3_urdf_to_isaac.sh
```

This attempts a headless Isaac Sim launch. If Isaac Sim is not available from
the command line, it writes a `manual_import_required` status and exits cleanly.

Check the result:

```bash
cat assets/robots/yahboom_m3_pro/isaac_import_status.json
ls -lh assets/robots/yahboom_m3_pro/yahboom_m3pro.usd
```

---

## Manual (Isaac Sim UI)

Use this if the automatic script reports `manual_import_required`.

### 1. Open Isaac Sim

Launch Isaac Sim normally (not headless).

### 2. Enable the URDF Importer extension

```
Window → Extensions
```

In the search box type: `URDF`

Enable one of:
- `Isaac URDF Importer` (`omni.isaac.urdf` / `omni.importer.urdf`)
- `Asset Importer URDF` (`isaacsim.asset.importer.urdf`)

### 3. Import the URDF

```
File → Import → URDF
```

Select:

```
/home/favl/robotics/FleetSafe-VisualNav-Benchmark/assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf
```

Import settings (recommended):
- Merge fixed joints: OFF
- Fix base: OFF
- Import inertia tensors: ON

### 4. Save as USD

After the robot appears in the stage:

```
File → Save As
```

Save to:

```
/home/favl/robotics/FleetSafe-VisualNav-Benchmark/assets/robots/yahboom_m3_pro/yahboom_m3pro.usd
```

### 5. Verify

```bash
cd ~/robotics/FleetSafe-VisualNav-Benchmark
ls -lh assets/robots/yahboom_m3_pro/yahboom_m3pro.usd
bash scripts/check_fleetsafe_vlnverse_plus_demo.sh
```

Expected after USD exists:

```
31 PASS / 0 FAIL / 1 BLOCKED
```

(Remaining blocker: episode trajectory/image output, which requires running the
IAmGoodNavigator demo interactively end-to-end inside Isaac Sim.)

---

## Do not substitute

Do NOT use TurtleBot, JetBot, Carter, or any generic Isaac robot as a stand-in.
Only `assets/robots/yahboom_m3_pro/yahboom_m3pro.usd` is accepted.
