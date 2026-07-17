from isaacsim import SimulationApp

simulation_app = SimulationApp({
    "headless": False,
    "renderer": "RaytracedLighting",
})

import carb

try:
    from isaacsim.storage.native import get_assets_root_path
except Exception as e:
    print("[ERROR] Could not import get_assets_root_path after SimulationApp start:", e)
    simulation_app.close()
    raise SystemExit(1)

root = get_assets_root_path()
print("\nASSETS_ROOT =", root)

if root is None:
    print("\n[ERROR] Isaac asset root is not configured.")
    print("Open Isaac Sim > Window > Browsers > Isaac Sim Assets.")
    print("Use the gear icon / asset settings to check or set the default assets root.")
    simulation_app.close()
    raise SystemExit(2)

candidates = {
    "hospital": root + "/Isaac/Environments/Hospital/hospital.usd",
    "office": root + "/Isaac/Environments/Office/office.usd",
    "warehouse": root + "/Isaac/Environments/Simple_Warehouse/warehouse.usd",
    "warehouse_full": root + "/Isaac/Environments/Simple_Warehouse/full_warehouse.usd",
}

print("\nCandidate environment paths:")
for name, path in candidates.items():
    print(f"{name}: {path}")

simulation_app.close()
