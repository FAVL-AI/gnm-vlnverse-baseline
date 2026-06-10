#!/usr/bin/env python3
"""
load_nvidia_assets.py — Load NVIDIA photorealistic USD environments into Isaac Sim.

Pulls hospital / warehouse / office assets from the local Nucleus server
(omniverse://localhost/NVIDIA/Assets/Isaac/…), scales them from cm→m (scale=0.01),
adds collision physics, spawns the M3Pro robot, and saves the composed stage as a
reusable USD file for training and benchmark runs.

Falls back to the procedural hospital world if Nucleus is unreachable.

Usage:
    conda activate isaac
    python scripts/isaaclab/load_nvidia_assets.py --env hospital
    python scripts/isaaclab/load_nvidia_assets.py --env warehouse --clutter medium
    python scripts/isaaclab/load_nvidia_assets.py --env hospital warehouse --out-dir IsaacLabAssets/

Assets (all cm-scale, must multiply scale by 0.01):
    omniverse://localhost/NVIDIA/Assets/Isaac/Isaac/Environments/Hospital/Hospital.usd
    omniverse://localhost/NVIDIA/Assets/Isaac/Isaac/Environments/Simple_Warehouse/Warehouse.usd
    omniverse://localhost/NVIDIA/Assets/Isaac/Isaac/Environments/Modular_Warehouse/Modular_Warehouse.usd
    omniverse://localhost/NVIDIA/Assets/Isaac/Isaac/Environments/Office/Office.usd
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ── Arg parse BEFORE AppLauncher (so --help works without Isaac) ──────────────

_REPO_ROOT = Path(__file__).resolve().parents[2]

NVIDIA_BASE = "omniverse://localhost/NVIDIA/Assets/Isaac/Isaac/Environments"
ASSET_PATHS: dict[str, str] = {
    "hospital":           f"{NVIDIA_BASE}/Hospital/Hospital.usd",
    "warehouse":          f"{NVIDIA_BASE}/Simple_Warehouse/Warehouse.usd",
    "warehouse_modular":  f"{NVIDIA_BASE}/Modular_Warehouse/Modular_Warehouse.usd",
    "office":             f"{NVIDIA_BASE}/Office/Office.usd",
}

# Filled by _nucleus_reachable() — cloud root when local Nucleus is absent.
# e.g. https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1
_assets_root: str | None = None

parser = argparse.ArgumentParser(description="Load NVIDIA photorealistic USD assets into Isaac Sim.")
parser.add_argument("--env", nargs="+", default=["hospital"],
                    choices=list(ASSET_PATHS.keys()),
                    help="Environment(s) to load (default: hospital)")
parser.add_argument("--out-dir", type=Path, default=_REPO_ROOT / "IsaacLabAssets",
                    help="Output directory for composed USD files")
parser.add_argument("--robot-usd", type=Path,
                    default=_REPO_ROOT / "fleet_safe_vla/robots/yahboom/m3pro/usd/yahboom_m3pro.usd",
                    help="M3Pro USD path (skip spawn if not found)")
parser.add_argument("--robot-pos", nargs=3, type=float, default=[0.0, 0.0, 0.05],
                    metavar=("X", "Y", "Z"), help="Robot spawn position in metres")
parser.add_argument("--clutter", choices=["none", "low", "medium", "high"], default="none",
                    help="Add procedural warehouse obstacles on top of base asset")
parser.add_argument("--rtx", action="store_true", default=False,
                    help="Enable RTX path tracing (slow but photorealistic)")
parser.add_argument("--headless", action="store_true", default=False)
parser.add_argument("--validate", action="store_true", default=False,
                    help="Run checklist and write validation_report.json")
args, remaining = parser.parse_known_args()

args.out_dir.mkdir(parents=True, exist_ok=True)

# ── Isaac Sim AppLauncher ─────────────────────────────────────────────────────

from isaaclab.app import AppLauncher  # noqa: E402

launcher_args = argparse.Namespace(
    headless=args.headless,
    # Only enable cameras (RTX pipeline) when in GUI mode or RTX is requested;
    # headless asset loading doesn't need camera rendering and it avoids a
    # multi-minute RTX cleanup hang on process exit.
    enable_cameras=args.rtx or not args.headless,
)
app_launcher  = AppLauncher(launcher_args)
simulation_app = app_launcher.app

# ── Isaac / USD imports ───────────────────────────────────────────────────────

import carb.settings                                   # noqa: E402
import omni.usd                                        # noqa: E402
from isaaclab.sim import SimulationContext             # noqa: E402
from pxr import Gf, UsdGeom, UsdPhysics, PhysxSchema  # noqa: E402

try:
    from omni.isaac.core.utils.stage import add_reference_to_stage
    from omni.isaac.core.utils.nucleus import get_assets_root_path
    _HAS_CORE = True
except ImportError:
    _HAS_CORE = False
    print("[load_nvidia_assets] WARNING: omni.isaac.core not available — using stage API directly.")


def _get_stage():
    return omni.usd.get_context().get_stage()


# ── RTX settings ─────────────────────────────────────────────────────────────

def _configure_rtx(samples: int = 128) -> None:
    s = carb.settings.get_settings()
    s.set("/rtx/rendermode", "PathTracing")
    s.set("/rtx/pathtracing/spp", samples)
    s.set("/rtx/pathtracing/totalSpp", samples)
    s.set("/rtx/shadows/enabled", True)
    s.set("/rtx/indirectDiffuse/enabled", True)
    s.set("/rtx/ambientOcclusion/enabled", True)
    s.set("/rtx/post/tonemap/op", 6)  # ACES
    print(f"[load_nvidia_assets] RTX path tracing enabled ({samples} spp)")


# ── Physics helpers ───────────────────────────────────────────────────────────

def _apply_collision_to_prim(prim) -> int:
    """Recursively apply collision API to all mesh prims under `prim`."""
    count = 0
    for p in prim.GetAllChildren():
        if p.IsA(UsdGeom.Mesh):
            if not p.HasAPI(UsdPhysics.CollisionAPI):
                UsdPhysics.CollisionAPI.Apply(p)
                approx = PhysxSchema.PhysxCollisionAPI.Apply(p)
                approx.GetContactOffsetAttr().Set(0.01)
            count += 1
        count += _apply_collision_to_prim(p)
    return count


def _add_ground_plane(stage) -> None:
    from pxr import Sdf, UsdPhysics
    plane = stage.DefinePrim("/World/GroundPlane", "Plane")
    UsdGeom.Mesh(plane)  # ensure Xformable
    # Isaac Lab 5.x renamed Tokens.collisionEnabled → physicsCollisionEnabled.
    # Using Sdf.ValueTypeNames.Bool is version-agnostic and always correct.
    plane.CreateAttribute("physics:collisionEnabled", Sdf.ValueTypeNames.Bool, False).Set(True)
    UsdPhysics.CollisionAPI.Apply(plane)
    print("[load_nvidia_assets] Ground plane added.")


# ── Nucleus / cloud-assets reachability check ────────────────────────────────

def _nucleus_reachable() -> bool:
    """Check asset reachability with a 10 s threading timeout.

    get_assets_root_path() can block indefinitely when no local Nucleus is
    running and the cloud check is slow.  We run it on a daemon thread and
    give it 10 seconds; if it returns a root (local or S3 cloud), we store
    it in _assets_root so load_environment() can build the correct URL.
    """
    global _assets_root
    if not _HAS_CORE:
        return False

    import threading
    result: list[str | None] = [None]

    def _fetch():
        try:
            result[0] = get_assets_root_path()
        except Exception:
            pass

    t = threading.Thread(target=_fetch, daemon=True)
    t.start()
    t.join(timeout=10.0)

    root = result[0]
    if root:
        _assets_root = root
        print(f"[load_nvidia_assets] Assets root: {root}")
        return True
    return False


# ── Load one environment asset ────────────────────────────────────────────────

def load_environment(env_name: str, sim: SimulationContext) -> bool:
    """
    Load a NVIDIA photorealistic environment from Nucleus or the NVIDIA cloud.
    Returns True on success, False if neither is reachable (caller should
    fall back to the procedural scene).
    """
    prim_path = f"/World/{env_name.title().replace('_', '')}"

    if not _nucleus_reachable():
        print(f"[load_nvidia_assets] No asset root reachable — cannot load {env_name}.")
        return False

    # Build the asset URL from the resolved root (local Nucleus or cloud S3).
    # Local:  omniverse://localhost/NVIDIA/Assets/Isaac/Isaac/Environments/Hospital/Hospital.usd
    # Cloud:  https://…/Assets/Isaac/5.1/Isaac/Environments/Hospital/Hospital.usd
    _local_sub = ASSET_PATHS[env_name].split("/Isaac/Environments/", 1)[-1]
    if _assets_root and _assets_root.startswith("http"):
        asset_url = f"{_assets_root}/Isaac/Environments/{_local_sub}"
    else:
        asset_url = ASSET_PATHS[env_name]

    print(f"[load_nvidia_assets] Loading {env_name} from asset root …")
    print(f"  {asset_url}")

    stage = _get_stage()

    if _HAS_CORE:
        add_reference_to_stage(usd_path=asset_url, prim_path=prim_path)
    else:
        prim = stage.DefinePrim(prim_path)
        prim.GetReferences().AddReference(asset_url)

    # ── Scale: assets are in centimetres → scale to metres ───────────────────
    # CRITICAL: without this, the robot appears inside a microscopic environment.
    env_prim = stage.GetPrimAtPath(prim_path)
    xform    = UsdGeom.Xformable(env_prim)
    xform.ClearXformOpOrder()
    scale_op = xform.AddScaleOp()
    scale_op.Set(Gf.Vec3d(0.01, 0.01, 0.01))
    print(f"[load_nvidia_assets] Scale set to 0.01 (cm → m) on {prim_path}")

    # ── Add collision physics ─────────────────────────────────────────────────
    n_meshes = _apply_collision_to_prim(env_prim)
    print(f"[load_nvidia_assets] Collision API applied to {n_meshes} mesh prims.")

    return True


# ── M3Pro PBR material ────────────────────────────────────────────────────────

# Texture root relative to repo: fleet_safe_vla/robots/yahboom/m3pro/textures/
# Files expected (PNG, 1024×1024):  m3pro_diffuse.png  m3pro_normal.png
#                                    m3pro_metalness.png  m3pro_roughness.png
# If absent, constant values are used — add files later without code changes.
_TEX_ROOT = _REPO_ROOT / "fleet_safe_vla" / "robots" / "yahboom" / "m3pro" / "textures"

# M3Pro surface parameters (Yahboom chassis: anodised aluminium + ABS plastic)
_M3PRO_PBR: dict[str, dict] = {
    "chassis": {
        "diffuse":    (0.12, 0.12, 0.12),  # near-black anodised
        "metallic":   0.55,
        "roughness":  0.40,
        "ior":        1.50,
        "tex_prefix": "m3pro_chassis",
    },
    "wheel": {
        "diffuse":    (0.05, 0.05, 0.05),  # tyre black
        "metallic":   0.00,
        "roughness":  0.90,
        "ior":        1.45,
        "tex_prefix": "m3pro_wheel",
    },
    "lidar": {
        "diffuse":    (0.05, 0.20, 0.70),  # blue sensor housing
        "metallic":   0.30,
        "roughness":  0.25,
        "ior":        1.50,
        "tex_prefix": None,
    },
    "camera": {
        "diffuse":    (0.03, 0.03, 0.03),  # matte black lens housing
        "metallic":   0.10,
        "roughness":  0.60,
        "ior":        1.50,
        "tex_prefix": None,
    },
}

# Maps USD link name substrings → material key
_LINK_TO_MAT: list[tuple[str, str]] = [
    ("wheel",  "wheel"),
    ("lidar",  "lidar"),
    ("camera", "camera"),
]


def _make_pbr_material(stage, mat_path: str, params: dict) -> "UsdShade.Material":
    """
    Build a UsdPreviewSurface PBR material at `mat_path`.

    Texture wiring uses the correct UsdUVTexture → UsdPreviewSurface node graph.
    If texture files are absent, constant attribute values are used instead —
    the same code path handles both cases without branching at call sites.
    """
    from pxr import Sdf, UsdShade as _UsdShade

    material  = _UsdShade.Material.Define(stage, mat_path)
    surf_path = mat_path + "/PBRShader"
    shader    = _UsdShade.Shader.Define(stage, surf_path)
    shader.CreateIdAttr("UsdPreviewSurface")

    tex_prefix = params.get("tex_prefix")

    def _tex_input(input_name: str, value_type, constant, tex_file: str | None, channel: str = "rgb"):
        """
        Wire a PBR input:
          - If tex_file exists on disk → create UsdUVTexture node and connect its
            `channel` output to `input_name`.
          - Otherwise → set constant value directly on the shader input.
        """
        inp = shader.CreateInput(input_name, value_type)
        if tex_file and Path(tex_file).exists():
            tex_node_path = f"{surf_path}/tex_{input_name}"
            tex_node = _UsdShade.Shader.Define(stage, tex_node_path)
            tex_node.CreateIdAttr("UsdUVTexture")
            tex_node.CreateInput("file",  Sdf.ValueTypeNames.Asset).Set(tex_file)
            tex_node.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
            tex_node.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
            out = tex_node.CreateOutput(channel, value_type)
            inp.ConnectToSource(out)
        else:
            inp.Set(constant)

    from pxr import Gf, Sdf
    r, g, b = params["diffuse"]

    _tex_input(
        "diffuseColor", Sdf.ValueTypeNames.Color3f,
        constant=Gf.Vec3f(r, g, b),
        tex_file=(str(_TEX_ROOT / f"{tex_prefix}_diffuse.png") if tex_prefix else None),
        channel="rgb",
    )
    _tex_input(
        "metallic", Sdf.ValueTypeNames.Float,
        constant=float(params["metallic"]),
        tex_file=(str(_TEX_ROOT / f"{tex_prefix}_metalness.png") if tex_prefix else None),
        channel="r",
    )
    _tex_input(
        "roughness", Sdf.ValueTypeNames.Float,
        constant=float(params["roughness"]),
        tex_file=(str(_TEX_ROOT / f"{tex_prefix}_roughness.png") if tex_prefix else None),
        channel="r",
    )
    _tex_input(
        "normal", Sdf.ValueTypeNames.Normal3f,
        constant=Gf.Vec3f(0.0, 0.0, 1.0),
        tex_file=(str(_TEX_ROOT / f"{tex_prefix}_normal.png") if tex_prefix else None),
        channel="rgb",
    )

    shader.CreateInput("ior",         Sdf.ValueTypeNames.Float).Set(float(params["ior"]))
    shader.CreateInput("useSpecularWorkflow", Sdf.ValueTypeNames.Int).Set(0)

    # Wire shader surface output → material surface terminal
    surf_out = shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput().ConnectToSource(surf_out)

    return material


def _apply_m3pro_pbr(stage, robot_prim_path: str = "/World/Robot/M3Pro") -> None:
    """
    Apply per-part PBR materials to M3Pro links.

    Material hierarchy:
        /World/Looks/M3Pro/chassis  →  chassis links
        /World/Looks/M3Pro/wheel    →  *_wheel links
        /World/Looks/M3Pro/lidar    →  lidar_link
        /World/Looks/M3Pro/camera   →  camera_link, camera_optical_link

    Works without texture files (constants used) and auto-connects textures
    when PNG files are placed in fleet_safe_vla/robots/yahboom/m3pro/textures/.
    """
    from pxr import UsdShade as _UsdShade

    robot_prim = stage.GetPrimAtPath(robot_prim_path)
    if not robot_prim.IsValid():
        print(f"[load_nvidia_assets] WARNING: M3Pro prim not found at {robot_prim_path} — skipping PBR.")
        return

    looks_root = "/World/Looks/M3Pro"

    # Build one material per surface type
    materials: dict[str, "_UsdShade.Material"] = {}
    for mat_key, params in _M3PRO_PBR.items():
        mat_path = f"{looks_root}/{mat_key}"
        materials[mat_key] = _make_pbr_material(stage, mat_path, params)

    def _mat_for_link(link_name: str) -> str:
        for substr, mat_key in _LINK_TO_MAT:
            if substr in link_name.lower():
                return mat_key
        return "chassis"

    # Bind materials to mesh prims under the robot
    bound = 0

    def _bind_recursive(prim) -> None:
        nonlocal bound
        for child in prim.GetAllChildren():
            if child.IsA(UsdGeom.Mesh):
                link_name = child.GetName()
                mat_key   = _mat_for_link(link_name)
                _UsdShade.MaterialBindingAPI(child).Bind(materials[mat_key])
                bound += 1
            _bind_recursive(child)

    _bind_recursive(robot_prim)

    tex_present = any((_TEX_ROOT / f"m3pro_chassis_diffuse.png").exists() for _ in [None])
    tex_note    = "with textures" if tex_present else "constants (add PNGs to textures/ to upgrade)"
    print(f"[load_nvidia_assets] M3Pro PBR applied: {bound} meshes, {tex_note}")
    print(f"  Materials: {looks_root}/{{chassis,wheel,lidar,camera}}")


# ── Spawn M3Pro ───────────────────────────────────────────────────────────────

def spawn_robot(robot_usd: Path, position: list[float]) -> bool:
    if not robot_usd.exists():
        print(f"[load_nvidia_assets] WARNING: M3Pro USD not found at {robot_usd}")
        print("  Convert first: conda activate isaac && python scripts/isaaclab/convert_m3pro_to_usd.py")
        return False

    stage     = _get_stage()
    prim_path = "/World/Robot/M3Pro"

    if _HAS_CORE:
        add_reference_to_stage(usd_path=str(robot_usd), prim_path=prim_path)
    else:
        prim = stage.DefinePrim(prim_path)
        prim.GetReferences().AddReference(str(robot_usd))

    robot_prim = stage.GetPrimAtPath(prim_path)
    xf = UsdGeom.Xformable(robot_prim)
    xf.ClearXformOpOrder()
    t_op = xf.AddTranslateOp()
    t_op.Set(Gf.Vec3d(*position))

    # Apply PBR materials — makes the robot look physically real under RTX
    _apply_m3pro_pbr(stage, prim_path)

    print(f"[load_nvidia_assets] M3Pro spawned at {position} from {robot_usd}")
    return True


# ── Warehouse clutter ─────────────────────────────────────────────────────────

_CLUTTER_COUNTS = {"none": (0, 0, 0), "low": (5, 10, 3), "medium": (12, 30, 6), "high": (20, 50, 10)}

def add_warehouse_clutter(stage, level: str) -> None:
    n_shelves, n_boxes, n_pallets = _CLUTTER_COUNTS[level]
    if n_shelves == 0:
        return

    import random
    rng   = random.Random(42)
    clutter_root = "/World/Clutter"

    def _box(name, pos, size, color=(0.5, 0.5, 0.5)):
        p = stage.DefinePrim(f"{clutter_root}/{name}", "Cube")
        xf = UsdGeom.Xformable(p)
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(*pos))
        xf.AddScaleOp().Set(Gf.Vec3d(size[0]/2, size[1]/2, size[2]/2))
        UsdPhysics.CollisionAPI.Apply(p)

    # Shelves (tall, narrow boxes arranged in rows)
    for i in range(n_shelves):
        x = rng.uniform(-15.0, 15.0)
        y = rng.uniform(-8.0,  8.0)
        _box(f"shelf_{i}", [x, y, 0.90], [0.50, 2.40, 1.80], color=(0.6, 0.5, 0.4))

    # Cardboard boxes (short, scattered)
    for i in range(n_boxes):
        x   = rng.uniform(-14.0, 14.0)
        y   = rng.uniform(-7.0,  7.0)
        dim = rng.uniform(0.30, 0.80)
        _box(f"box_{i}", [x, y, dim/2], [dim, dim, dim])

    # Pallets (flat, floor-level)
    for i in range(n_pallets):
        x = rng.uniform(-14.0, 14.0)
        y = rng.uniform(-7.0,  7.0)
        _box(f"pallet_{i}", [x, y, 0.075], [1.20, 0.80, 0.15], color=(0.55, 0.40, 0.25))

    print(f"[load_nvidia_assets] Clutter ({level}): {n_shelves} shelves, {n_boxes} boxes, {n_pallets} pallets")


# ── Validation ────────────────────────────────────────────────────────────────

def validate_stage(stage, out_dir: Path) -> dict:
    import json

    report: dict = {"checks": {}, "passed": True}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"][name] = {"ok": ok, "detail": detail}
        if not ok:
            report["passed"] = False
            print(f"  [FAIL] {name}: {detail}")
        else:
            print(f"  [OK]   {name}" + (f": {detail}" if detail else ""))

    print("\n[load_nvidia_assets] Running validation checklist …")

    env_prim = None
    for env_name in args.env:
        pp = f"/World/{env_name.title().replace('_', '')}"
        p  = stage.GetPrimAtPath(pp)
        if p.IsValid():
            env_prim = p
            break

    check("env_prim_exists",  env_prim is not None, str(env_prim.GetPath()) if env_prim else "none")

    if env_prim is not None:
        xf    = UsdGeom.Xformable(env_prim)
        ops   = xf.GetOrderedXformOps()
        scale = None
        for op in ops:
            if "scale" in op.GetName().lower():
                scale = op.Get()
        ok_scale = scale is not None and abs(scale[0] - 0.01) < 1e-4
        check("scale_0_01", ok_scale, str(scale))

        meshes = [p for p in env_prim.GetAllChildren() if p.IsA(UsdGeom.Mesh)]
        check("meshes_present", len(meshes) > 0, f"{len(meshes)} meshes")
        colliders = [p for p in meshes if p.HasAPI(UsdPhysics.CollisionAPI)]
        check("collision_applied", len(colliders) == len(meshes),
              f"{len(colliders)}/{len(meshes)} have CollisionAPI")

    robot = stage.GetPrimAtPath("/World/Robot/M3Pro")
    check("robot_spawned", robot.IsValid())

    rpt_path = out_dir / "validation_report.json"
    rpt_path.write_text(json.dumps(report, indent=2))
    print(f"\n[load_nvidia_assets] Validation report → {rpt_path}")
    status = "PASSED" if report["passed"] else "FAILED"
    print(f"[load_nvidia_assets] Result: {status}\n")
    return report


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if args.rtx:
        _configure_rtx(samples=128)

    try:
        sim = SimulationContext(stage_units_in_meters=1.0)
    except TypeError:
        # Isaac Sim / Isaac Lab 5.x: stage_units_in_meters removed from constructor.
        # Units are now set via SimulationCfg or left at the stage-level default (m).
        sim = SimulationContext()
    stage = _get_stage()

    nucleus_ok = _nucleus_reachable()

    for env_name in args.env:
        loaded = load_environment(env_name, sim)

        if not loaded:
            print(f"[load_nvidia_assets] Falling back to procedural scene for '{env_name}' …")
            sys.path.insert(0, str(_REPO_ROOT))
            from fleet_safe_vla.envs.isaaclab.hospital.hospital_world_loader import HospitalWorldLoader
            loader = HospitalWorldLoader(verbose=True, nucleus_ok=False)
            loader.build_procedural_scene()

        if args.clutter != "none":
            add_warehouse_clutter(stage, args.clutter)

        # Save per-environment USD
        out_usd = args.out_dir / f"{env_name}_photorealistic.usd"
        sim.reset()
        for _ in range(5):
            sim.step()

        _add_ground_plane(stage)
        spawn_robot(args.robot_usd, args.robot_pos)

        if args.validate:
            validate_stage(stage, args.out_dir)

        print(f"[load_nvidia_assets] Exporting → {out_usd}")
        stage.Export(str(out_usd))
        print(f"[load_nvidia_assets] Saved: {out_usd}  ({out_usd.stat().st_size:,} bytes)")

        print()
        print("Next steps:")
        if nucleus_ok:
            print(f"  # Confirm photorealistic render (open in Isaac Sim GUI):")
            print(f"  isaac-sim.sh --usd {out_usd}")
        print(f"  # Export training images:")
        print(f"  python scripts/isaaclab/export_vint_dataset.py --usd {out_usd} --episodes 100")
        print(f"  # Run benchmark:")
        print(f"  python scripts/benchmarks/unified_benchmark.py --isaac-usd {out_usd}")
        print()

    simulation_app.close()


if __name__ == "__main__":
    main()
