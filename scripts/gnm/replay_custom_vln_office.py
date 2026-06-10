"""
replay_custom_vln_office.py — Replay a CustomVLN-Office episode in Isaac Sim
=============================================================================
Loads one collected episode and opens the custom scene with:
  - START / GOAL markers
  - Cyan path dots
  - Robot marker (moving along trajectory)
  - Orange local waypoint cones (derived labels, NOT model predictions)
  - Current RGB + goal RGB panels
  - Evidence HUD panel

Dry-run: prints episode info and generates panel PNGs without Isaac Sim.

NO VLNVerse assets are used.

Usage:
  python3 scripts/gnm/replay_custom_vln_office.py --dry-run
  EPISODE=cvlo_ep003 conda run -n isaac python scripts/gnm/replay_custom_vln_office.py
"""
import argparse
import json
import math
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np

REPO     = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO / "datasets/custom_vln_office"
SCENE_USD = REPO / "assets/custom_vln_office/custom_vln_office.usd"
FIG_DIR   = REPO / "results/figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

EPISODE  = os.environ.get("EPISODE", "cvlo_ep001")
SPEED    = float(os.environ.get("SPEED", "1.0"))


def _find_episode(ep_id: str) -> tuple[Path, str]:
    for split in ("train", "val"):
        d = DATA_ROOT / split / ep_id
        if (d / "traj_data.pkl").exists():
            return d, split
    return None, None


def _load_episode(ep_dir: Path) -> dict:
    with open(ep_dir / "traj_data.pkl", "rb") as f:
        data = pickle.load(f)
    meta_path = ep_dir / "metadata.json"
    if meta_path.exists():
        with open(meta_path) as f:
            data["_meta"] = json.load(f)
    return data


def _font(size):
    from PIL import ImageFont
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _font_r(size):
    from PIL import ImageFont
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _make_panel(title, lines, width=680, bg=(15, 18, 30), title_color=(255, 210, 60)):
    from PIL import Image, ImageDraw
    PAD, LINE_H, TITLE_H = 18, 28, 48
    height = TITLE_H + len(lines) * LINE_H + PAD * 2
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (width, TITLE_H)], fill=(30, 35, 55))
    fB18 = _font(18)
    tw = draw.textbbox((0, 0), title, font=fB18)[2]
    draw.text(((width - tw) // 2, 10), title, fill=title_color, font=fB18)
    fR15, fB15 = _font_r(15), _font(15)
    y = TITLE_H + PAD
    for text, color in lines:
        if text.startswith("──"):
            draw.line([(PAD, y + 6), (width - PAD, y + 6)], fill=(50, 55, 75))
        else:
            lbl, _, val = text.partition(" : ")
            if val:
                draw.text((PAD, y), lbl + " :", fill=(155, 160, 175), font=fR15)
                lw = draw.textbbox((0, 0), lbl + " :", font=fR15)[2]
                draw.text((PAD + lw + 5, y), val, fill=color, font=fB15)
            else:
                draw.text((PAD, y), text, fill=color, font=fR15)
        y += LINE_H
    return img


def generate_evidence_panels(data: dict, ep_dir: Path, ep_id: str, split: str) -> dict:
    from PIL import Image
    pos = np.array(data["position"])
    yaw = np.array(data.get("yaw", np.zeros(len(pos))))
    T   = len(pos)
    sx, sy  = float(pos[0][0]),  float(pos[0][1])
    gx, gy  = float(pos[-1][0]), float(pos[-1][1])
    path_len = float(np.linalg.norm(np.diff(pos, axis=0), axis=1).sum())
    instr   = data.get("instruction", "N/A")
    meta    = data.get("_meta", {})

    WHITE  = (235, 235, 235)
    GREY   = (150, 155, 165)
    GREEN  = (60,  210,  90)
    YELLOW = (255, 210,  60)
    CYAN   = (60,  185, 225)
    RED    = (225,  80,  80)
    ORANGE = (255, 150,  40)

    panels = {}

    # Custom scene name panel
    img = _make_panel("CustomVLN-Office — INDEPENDENT ISAAC SIM SCENE", [
        ("Scene       : custom_vln_office  (no VLNVerse assets)",          CYAN),
        ("Source      : Isaac Sim USD primitives",                         WHITE),
        ("Episode     : " + ep_id,                                         WHITE),
        ("Split       : " + split,                                         YELLOW),
        ("Instruction : " + instr[:70],                                    GREY),
        ("── ──", GREY),
        (f"Start  : ({sx:.2f}, {sy:.2f})  yaw={math.degrees(float(yaw[0])):.0f}°", GREEN),
        (f"Goal   : ({gx:.2f}, {gy:.2f})  yaw={math.degrees(float(yaw[-1])):.0f}°", RED),
        (f"Frames : {T}   path = {path_len:.2f} m",                        WHITE),
        ("── ──", GREY),
        ("GNM input  : current RGB image  +  goal RGB image",             CYAN),
        ("GNM output : local waypoint (delta_x, delta_y) in robot frame", CYAN),
        ("Labels     : derived from traj_data.pkl  (NOT model output)",   ORANGE),
    ], title_color=CYAN, width=760)
    p = FIG_DIR / f"cvlo_{ep_id}_scene_panel.png"
    img.save(p)
    panels["scene_name"] = p

    # Dataset proof panel
    img = _make_panel("DATASET PROOF — CustomVLN-Office", [
        ("vlnverse_assets_used : False",                                   GREEN),
        ("isaac_assets_used    : USD primitives (cube, sphere, mesh)",     YELLOW),
        ("RGB frames collected : from robot camera at 1.2 m height",       WHITE),
        ("x/y/yaw recorded     : per-frame from robot marker position",    WHITE),
        ("label_source         : consecutive trajectory poses",             ORANGE),
        ("── ──", GREY),
        (f"Train episodes : {len(list((DATA_ROOT / 'train').glob('cvlo_*')))}",  WHITE),
        (f"Val   episodes : {len(list((DATA_ROOT / 'val').glob('cvlo_*')))}",    WHITE),
        ("── ──", GREY),
        ("Full evidence : results/bo_reviewer_packet/12_custom_vln_office_independent_isaac_scene.md", GREY),
    ], title_color=GREEN, width=760)
    p = FIG_DIR / f"cvlo_{ep_id}_dataset_proof.png"
    img.save(p)
    panels["dataset_proof"] = p

    # Current obs + goal side-by-side
    rgb_dir = ep_dir / "rgb"
    mid_i   = T // 2
    obs_path  = rgb_dir / f"{mid_i:06d}.jpg"
    goal_path = rgb_dir / f"{T - 1:06d}.jpg"
    W, H = 320, 240
    gnm_in = Image.new("RGB", (W * 2 + 4, H + 44), (15, 18, 30))
    from PIL import ImageDraw as _IDraw
    dr = _IDraw.Draw(gnm_in)
    dr.rectangle([(0, 0), (W * 2 + 4, 44)], fill=(30, 35, 55))
    dr.text((8, 8),       "GNM INPUT: current obs",  fill=CYAN, font=_font(14))
    dr.text((W + 12, 8),  "GNM INPUT: goal image",   fill=RED,  font=_font(14))
    if obs_path.exists():
        gnm_in.paste(Image.open(obs_path).convert("RGB").resize((W, H)), (0, 44))
    if goal_path.exists():
        gnm_in.paste(Image.open(goal_path).convert("RGB").resize((W, H)), (W + 4, 44))
    p = FIG_DIR / f"cvlo_{ep_id}_gnm_input.png"
    gnm_in.save(p)
    panels["gnm_input"] = p

    return panels


def run_dry_run(ep_id: str) -> None:
    ep_dir, split = _find_episode(ep_id)
    if ep_dir is None:
        print(f"Episode '{ep_id}' not found. Run --dry-run collect first:")
        print("  python3 scripts/gnm/collect_custom_vln_office_data.py --dry-run")
        sys.exit(1)
    data = _load_episode(ep_dir)
    pos  = np.array(data["position"])
    T    = len(pos)
    path_len = float(np.linalg.norm(np.diff(pos, axis=0), axis=1).sum())

    print("CustomVLN-Office Replay — dry-run")
    print("=" * 60)
    print(f"Episode   : {ep_id}  [{split}]")
    print(f"Frames    : {T}")
    print(f"Path len  : {path_len:.2f} m")
    print(f"Instruction: {data.get('instruction', 'N/A')}")
    print(f"Start     : ({pos[0][0]:.3f}, {pos[0][1]:.3f})")
    print(f"Goal      : ({pos[-1][0]:.3f}, {pos[-1][1]:.3f})")
    print(f"VLNVerse assets : NONE")
    print()
    panels = generate_evidence_panels(data, ep_dir, ep_id, split)
    print("Evidence panels generated:")
    for name, p in panels.items():
        print(f"  {name:<20} {p}")
    print()
    print("To replay in Isaac Sim:")
    print(f"  EPISODE={ep_id} conda run -n isaac python scripts/gnm/replay_custom_vln_office.py")


def run_isaac(ep_id: str) -> None:
    ep_dir, split = _find_episode(ep_id)
    if ep_dir is None:
        print(f"Episode '{ep_id}' not found. Collect data first.")
        sys.exit(1)
    data  = _load_episode(ep_dir)
    pos   = np.array(data["position"])
    yaws  = np.array(data.get("yaw", np.zeros(len(pos))))
    T     = len(pos)
    sx, sy = float(pos[0][0]), float(pos[0][1])
    gx, gy = float(pos[-1][0]), float(pos[-1][1])
    instr  = data.get("instruction", "")

    panels = generate_evidence_panels(data, ep_dir, ep_id, split)

    from isaacsim import SimulationApp
    app = SimulationApp({"headless": False, "renderer": "RayTracedLighting"})
    import omni.usd
    from pxr import UsdGeom, UsdShade, Gf, Sdf, Usd

    ctx = omni.usd.get_context()
    if SCENE_USD.exists():
        ctx.open_stage(str(SCENE_USD))
    else:
        ctx.new_stage()
    for _ in range(120):
        app.update()
        time.sleep(0.01)
    stage = ctx.get_stage()

    def _mat(path, r, g, b):
        mat = UsdShade.Material.Define(stage, path)
        sh  = UsdShade.Shader.Define(stage, f"{path}/S")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(r, g, b))
        sh.CreateInput("roughness",    Sdf.ValueTypeNames.Float).Set(0.4)
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
        return mat

    def _bind(prim, mat):
        UsdShade.MaterialBindingAPI(prim).Bind(mat)

    def _tex_panel(prim_path, img_path, x, y, z, hw=2.0, hh=1.5):
        mesh = UsdGeom.Mesh.Define(stage, prim_path)
        mesh.CreatePointsAttr([Gf.Vec3f(-hw, -hh, 0), Gf.Vec3f(hw, -hh, 0),
                                Gf.Vec3f(hw,  hh, 0), Gf.Vec3f(-hw,  hh, 0)])
        mesh.CreateFaceVertexCountsAttr([4])
        mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
        mesh.CreateNormalsAttr([Gf.Vec3f(0, 0, 1)] * 4)
        mesh.SetNormalsInterpolation("vertex")
        pvapi = UsdGeom.PrimvarsAPI(mesh.GetPrim())
        pvapi.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray,
                            UsdGeom.Tokens.varying).Set(
            [(0., 0.), (1., 0.), (1., 1.), (0., 1.)])
        mesh.AddTranslateOp().Set(Gf.Vec3d(x, y, z))
        mat = UsdShade.Material.Define(stage, f"{prim_path}/mat")
        sh  = UsdShade.Shader.Define(stage, f"{prim_path}/mat/S")
        sh.CreateIdAttr("UsdPreviewSurface")
        tex = UsdShade.Shader.Define(stage, f"{prim_path}/mat/T")
        tex.CreateIdAttr("UsdUVTexture")
        tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(img_path)
        tex.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
        tex.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
        tex_out = tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        st_rd = UsdShade.Shader.Define(stage, f"{prim_path}/mat/ST")
        st_rd.CreateIdAttr("UsdPrimvarReader_float2")
        st_rd.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        st_out = st_rd.CreateOutput("result", Sdf.ValueTypeNames.Float2)
        tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st_out)
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(tex_out)
        sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
        _bind(mesh.GetPrim(), mat)

    root = "/World/CVLO_Replay"
    UsdGeom.Xform.Define(stage, root)
    UsdGeom.Xform.Define(stage, f"{root}/Mats")

    mat_dot  = _mat(f"{root}/Mats/dot",  0.2, 0.6, 1.0)
    mat_st   = _mat(f"{root}/Mats/st",   0.1, 0.9, 0.2)
    mat_gl   = _mat(f"{root}/Mats/gl",   1.0, 0.2, 0.1)
    mat_rob  = _mat(f"{root}/Mats/rob",  0.2, 0.4, 1.0)
    mat_wp   = _mat(f"{root}/Mats/wp",   1.0, 0.6, 0.1)

    Z = 0.8
    for i in range(T):
        s = UsdGeom.Sphere.Define(stage, f"{root}/path_{i:04d}")
        s.CreateRadiusAttr(0.06)
        s.AddTranslateOp().Set(Gf.Vec3d(float(pos[i][0]), float(pos[i][1]), Z))
        _bind(s.GetPrim(), mat_dot)

    for k in range(5):
        wi = min(T // 2 + k + 1, T - 1)
        c = UsdGeom.Cone.Define(stage, f"{root}/WP_{k:02d}")
        c.CreateRadiusAttr(0.15)
        c.CreateHeightAttr(0.4)
        xf = UsdGeom.Xformable(c.GetPrim())
        xf.AddTranslateOp().Set(Gf.Vec3d(float(pos[wi][0]), float(pos[wi][1]), Z + 0.2))
        _bind(c.GetPrim(), mat_wp)
        c.GetPrim().CreateAttribute("gnm:type",   Sdf.ValueTypeNames.String, custom=True)\
            .Set("local_waypoint_target")
        c.GetPrim().CreateAttribute("gnm:source", Sdf.ValueTypeNames.String, custom=True)\
            .Set("derived_from_traj_data_pkl")

    st_s = UsdGeom.Sphere.Define(stage, f"{root}/START")
    st_s.CreateRadiusAttr(0.3)
    st_s.AddTranslateOp().Set(Gf.Vec3d(sx, sy, Z + 0.3))
    _bind(st_s.GetPrim(), mat_st)

    gl_s = UsdGeom.Sphere.Define(stage, f"{root}/GOAL")
    gl_s.CreateRadiusAttr(0.35)
    gl_s.AddTranslateOp().Set(Gf.Vec3d(gx, gy, Z + 0.35))
    _bind(gl_s.GetPrim(), mat_gl)

    cx, cy = (sx + gx) / 2, (sy + gy) / 2
    PZ, SEP = 3.5, 4.5
    for panel_name, png_path, px, py, pz, hw, hh in [
        ("CUSTOM_SCENE_NAME_PANEL", str(panels["scene_name"]),   cx - SEP,     cy, PZ + 2.5, 3.8, 1.5),
        ("DATASET_PROOF_PANEL",     str(panels["dataset_proof"]),cx + SEP,     cy, PZ + 2.5, 3.8, 1.3),
        ("GNM_INPUT_PANEL",         str(panels["gnm_input"]),    cx,           cy, PZ + 1.5, 3.2, 1.2),
    ]:
        try:
            _tex_panel(f"{root}/{panel_name}", png_path, px, py, pz, hw, hh)
        except Exception as e:
            print(f"  Panel {panel_name} failed: {e}")

    # Robot marker
    rob_xf = UsdGeom.Xform.Define(stage, f"{root}/ROBOT")
    rob_bd = UsdGeom.Cube.Define(stage, f"{root}/ROBOT/body")
    rob_bd.CreateSizeAttr(0.4)
    rob_bd.AddTranslateOp().Set(Gf.Vec3d(0, 0, 0.4))
    _bind(rob_bd.GetPrim(), mat_rob)
    rxt = UsdGeom.Xformable(rob_xf.GetPrim())
    rxt.ClearXformOpOrder()
    t_op = rxt.AddTranslateOp()
    r_op = rxt.AddRotateZOp()
    t_op.Set(Gf.Vec3d(sx, sy, 0.0))
    r_op.Set(math.degrees(float(yaws[0])))

    print("=" * 60)
    print(f"CustomVLN-Office Replay — {ep_id} [{split}]")
    print(f"  Instruction: {instr}")
    print(f"  Frames: {T}  |  Orange cones = derived waypoint labels")
    print(f"  No VLNVerse assets used.")
    print("Press Ctrl-C to exit.")
    print("=" * 60)

    idx = 0
    dt  = 0.05 / SPEED
    while True:
        t_op.Set(Gf.Vec3d(float(pos[idx][0]), float(pos[idx][1]), 0.0))
        r_op.Set(math.degrees(float(yaws[idx])))
        app.update()
        time.sleep(dt)
        idx = (idx + 1) % T


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--episode", default=EPISODE)
    args = parser.parse_args()
    ep = args.episode
    if args.dry_run:
        run_dry_run(ep)
    else:
        run_isaac(ep)


if __name__ == "__main__":
    main()
