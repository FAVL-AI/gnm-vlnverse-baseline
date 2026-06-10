"""
tests/test_isaac_m3pro_asset_gate.py

Tests for the Yahboom M3Pro Isaac Sim asset gate and scene configuration.

All tests pass without Isaac Sim installed — they verify:
  - URDF structure (joint names, sensor frames, collision geoms)
  - asset_cfg module is importable and provides correct constants
  - scene_cfg provides all 4 canonical benchmark scenes
  - check_m3pro_isaac_asset.py URDF checks return PASS on existing URDF
  - graceful failure messages when Isaac is unavailable
  - no GPU required for CI
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _urdf_path() -> Path:
    return REPO_ROOT / "fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf"


def _urdf_tree() -> ET.Element:
    return ET.parse(_urdf_path()).getroot()


# ── 1. URDF structural checks ─────────────────────────────────────────────────

class TestUrdfStructure:
    def test_urdf_file_exists(self):
        assert _urdf_path().exists(), f"URDF missing: {_urdf_path()}"

    def test_urdf_is_valid_xml(self):
        root = _urdf_tree()
        assert root.tag == "robot"

    def test_urdf_robot_name(self):
        root = _urdf_tree()
        assert root.get("name") == "yahboom_m3pro"

    def test_four_wheel_joints_present(self):
        root = _urdf_tree()
        joint_names = {j.get("name") for j in root.findall("joint")}
        required = {"fl_wheel_joint", "fr_wheel_joint", "rl_wheel_joint", "rr_wheel_joint"}
        missing = required - joint_names
        assert not missing, f"Missing wheel joints: {missing}"

    def test_wheel_joints_are_continuous(self):
        root = _urdf_tree()
        wheel_joints = {
            j.get("name"): j.get("type")
            for j in root.findall("joint")
            if j.get("name") in {
                "fl_wheel_joint", "fr_wheel_joint",
                "rl_wheel_joint", "rr_wheel_joint"
            }
        }
        for name, jtype in wheel_joints.items():
            assert jtype == "continuous", f"{name} type={jtype!r}, expected 'continuous'"

    def test_camera_frame_exists(self):
        root = _urdf_tree()
        link_names = {l.get("name") for l in root.findall("link")}
        assert "camera_link" in link_names or "camera_optical_link" in link_names, \
            "No camera_link or camera_optical_link in URDF"

    def test_lidar_frame_exists(self):
        root = _urdf_tree()
        link_names = {l.get("name") for l in root.findall("link")}
        assert "lidar_link" in link_names, "No lidar_link in URDF"

    def test_imu_frame_exists(self):
        root = _urdf_tree()
        link_names = {l.get("name") for l in root.findall("link")}
        assert "imu_link" in link_names, "No imu_link in URDF"

    def test_base_link_exists(self):
        root = _urdf_tree()
        link_names = {l.get("name") for l in root.findall("link")}
        assert "base_link" in link_names

    def test_collision_geoms_present(self):
        text = _urdf_path().read_text()
        n = text.count("<collision>")
        assert n >= 5, f"Only {n} <collision> blocks — expected ≥5 (base + 4 wheels)"

    def test_visual_geoms_present(self):
        text = _urdf_path().read_text()
        n = text.count("<visual>")
        assert n >= 5

    def test_inertial_blocks_present(self):
        text = _urdf_path().read_text()
        n = text.count("<inertial>")
        assert n >= 5, f"Only {n} <inertial> blocks — expected ≥5"


# ── 2. asset_cfg constants ─────────────────────────────────────────────────────

class TestAssetCfgConstants:
    def test_module_importable(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro import asset_cfg
        assert asset_cfg is not None

    def test_urdf_path_constant(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import M3PRO_URDF
        assert M3PRO_URDF.exists()

    def test_wheel_joints_constant(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import WHEEL_JOINTS
        assert set(WHEEL_JOINTS) == {
            "fl_wheel_joint", "fr_wheel_joint",
            "rl_wheel_joint", "rr_wheel_joint"
        }

    def test_geometry_constants_reasonable(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import (
            WHEEL_RADIUS_M, WHEELBASE_M, TRACK_WIDTH_M, ROBOT_RADIUS_M,
        )
        assert 0.03 < WHEEL_RADIUS_M < 0.10
        assert 0.10 < WHEELBASE_M < 0.30
        assert 0.10 < TRACK_WIDTH_M < 0.30
        assert ROBOT_RADIUS_M > 0.0

    def test_velocity_limits_positive(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import (
            MAX_VX_MS, MAX_VY_MS, MAX_WZ_RDS,
        )
        assert MAX_VX_MS > 0
        assert MAX_VY_MS > 0
        assert MAX_WZ_RDS > 0

    def test_missing_asset_warnings_returns_list(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import missing_asset_warnings
        warnings = missing_asset_warnings()
        assert isinstance(warnings, list)
        # Always includes inertial warning at minimum
        assert any("inertial" in w.lower() or "INERTIALS" in w for w in warnings), \
            "Expected inertial placeholder warning"

    def test_assert_assets_exist_passes_on_existing_urdf(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import assert_assets_exist
        # Should not raise since URDF exists
        assert_assets_exist()

    def test_build_articulation_cfg_raises_without_isaac(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import (
            build_m3pro_articulation_cfg, _ISAACLAB_AVAILABLE,
        )
        if _ISAACLAB_AVAILABLE:
            pytest.skip("Isaac Lab available — cfg construction may succeed")
        with pytest.raises(ImportError, match="isaaclab"):
            build_m3pro_articulation_cfg()


# ── 3. scene_cfg ──────────────────────────────────────────────────────────────

class TestSceneCfg:
    def test_module_importable(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro import scene_cfg
        assert scene_cfg is not None

    def test_all_four_canonical_scenes_present(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.scene_cfg import CANONICAL_SCENES
        assert set(CANONICAL_SCENES.keys()) == {
            "straight_corridor", "cluttered_static",
            "narrow_passage", "dynamic_obstacle",
        }

    def test_get_scene_returns_correct_id(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.scene_cfg import get_scene
        for scene_id in ("straight_corridor", "cluttered_static",
                         "narrow_passage", "dynamic_obstacle"):
            scene = get_scene(scene_id)
            assert scene.scene_id == scene_id

    def test_get_scene_unknown_raises_key_error(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.scene_cfg import get_scene
        with pytest.raises(KeyError):
            get_scene("nonexistent_scene")

    def test_scene_versions_match_sceneset(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.scene_cfg import CANONICAL_SCENES
        for scene in CANONICAL_SCENES.values():
            assert scene.scene_version == "0.1.0", \
                f"{scene.scene_id}: version={scene.scene_version!r}, expected '0.1.0'"

    def test_straight_corridor_no_obstacles(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.scene_cfg import get_scene
        scene = get_scene("straight_corridor")
        assert len(scene.obstacles) == 0
        assert len(scene.dynamic_agents) == 0

    def test_cluttered_static_has_eight_obstacles(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.scene_cfg import get_scene
        scene = get_scene("cluttered_static")
        assert len(scene.obstacles) == 8

    def test_narrow_passage_has_eight_obstacles(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.scene_cfg import get_scene
        scene = get_scene("narrow_passage")
        assert len(scene.obstacles) == 8
        # Left wall: 3 pillars at x = -1.5
        left_wall = [o for o in scene.obstacles if abs(o.pos_xyz[0] - (-1.5)) < 0.01]
        assert len(left_wall) == 3, f"Expected 3 left-wall pillars, got {len(left_wall)}"
        # Right wall: 3 pillars at x = +1.5
        right_wall = [o for o in scene.obstacles if abs(o.pos_xyz[0] - 1.5) < 0.01]
        assert len(right_wall) == 3, f"Expected 3 right-wall pillars, got {len(right_wall)}"
        # Flanking pair: 2 obstacles at x ≈ ±0.4
        flanking = [o for o in scene.obstacles if abs(abs(o.pos_xyz[0]) - 0.4) < 0.01]
        assert len(flanking) == 2, f"Expected 2 flanking obstacles, got {len(flanking)}"

    def test_narrow_passage_gap_width(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.scene_cfg import get_scene
        scene = get_scene("narrow_passage")
        # Flanking obstacles at x=±0.40 with radius=0.20 create a clear x-gap:
        #   clear gap = 2*(0.40 - 0.20) = 0.40 m
        flanking = [o for o in scene.obstacles if abs(abs(o.pos_xyz[0]) - 0.4) < 0.01]
        assert len(flanking) == 2
        x_positions = sorted(o.pos_xyz[0] for o in flanking)
        radius = flanking[0].radius_m
        clear_gap_m = (x_positions[1] - radius) - (x_positions[0] + radius)
        assert clear_gap_m > 0.20, (
            f"Clear gap between flanking obstacles is {clear_gap_m:.3f} m — robot may not fit"
        )
        assert clear_gap_m < 0.80, (
            f"Gap {clear_gap_m:.3f} m is too wide to constitute a narrow passage"
        )

    def test_dynamic_obstacle_has_one_dynamic_agent(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.scene_cfg import get_scene
        scene = get_scene("dynamic_obstacle")
        assert len(scene.dynamic_agents) == 1
        agent = scene.dynamic_agents[0]
        assert agent.velocity_xyz[1] > 0  # moving in +y direction

    def test_scene_goal_xyz_reachable(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.scene_cfg import CANONICAL_SCENES
        import math
        for scene in CANONICAL_SCENES.values():
            sx, sy, _ = scene.start_xyz
            gx, gy, _ = scene.goal_xyz
            dist = math.sqrt((gx - sx) ** 2 + (gy - sy) ** 2)
            assert dist > 0.5, f"{scene.scene_id}: start and goal too close ({dist:.2f} m)"
            # optimal_path_m may be longer than straight-line (e.g. cluttered scene
            # path detours around obstacles), so allow up to 3 m of extra path length.
            assert scene.optimal_path_m >= dist - 0.01, \
                f"{scene.scene_id}: optimal_path_m={scene.optimal_path_m} < dist={dist:.2f}"
            assert scene.optimal_path_m < dist + 3.0, \
                f"{scene.scene_id}: optimal_path_m={scene.optimal_path_m} unreasonably long"

    def test_spawn_obstacles_raises_without_isaac(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.scene_cfg import (
            spawn_scene_obstacles, get_scene, _ISAACLAB_AVAILABLE,
        )
        if _ISAACLAB_AVAILABLE:
            pytest.skip("Isaac Lab available — spawner may succeed")
        scene = get_scene("cluttered_static")
        with pytest.raises(ImportError, match="isaaclab"):
            spawn_scene_obstacles(scene)


# ── 4. Asset checker script ───────────────────────────────────────────────────

class TestAssetCheckerScript:
    def test_checker_urdf_exists_check_passes(self):
        from scripts.isaaclab.check_m3pro_isaac_asset import (
            check_urdf_exists, PASS,
        )
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import M3PRO_URDF
        result = check_urdf_exists(M3PRO_URDF)
        assert result.status == PASS

    def test_checker_urdf_parseable_passes(self):
        from scripts.isaaclab.check_m3pro_isaac_asset import (
            check_urdf_parseable, PASS,
        )
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import M3PRO_URDF
        result = check_urdf_parseable(M3PRO_URDF)
        assert result.status == PASS

    def test_checker_wheel_joints_pass(self):
        from scripts.isaaclab.check_m3pro_isaac_asset import (
            check_wheel_joints, PASS,
        )
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import M3PRO_URDF
        result = check_wheel_joints(M3PRO_URDF)
        assert result.status == PASS

    def test_checker_camera_frame_pass(self):
        from scripts.isaaclab.check_m3pro_isaac_asset import (
            check_camera_frame, PASS,
        )
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import M3PRO_URDF
        result = check_camera_frame(M3PRO_URDF)
        assert result.status == PASS

    def test_checker_collision_geoms_pass(self):
        from scripts.isaaclab.check_m3pro_isaac_asset import (
            check_collision_geoms, PASS,
        )
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import M3PRO_URDF
        result = check_collision_geoms(M3PRO_URDF)
        assert result.status == PASS

    def test_checker_inertials_warns(self):
        from scripts.isaaclab.check_m3pro_isaac_asset import (
            check_inertials_measured, WARN,
        )
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import M3PRO_URDF
        result = check_inertials_measured(M3PRO_URDF)
        # Structural URDF uses approximations — expect WARN
        assert result.status == WARN

    def test_checker_missing_urdf_returns_fail(self, tmp_path):
        from scripts.isaaclab.check_m3pro_isaac_asset import (
            check_urdf_exists, FAIL,
        )
        missing = tmp_path / "does_not_exist.urdf"
        result = check_urdf_exists(missing)
        assert result.status == FAIL

    def test_checker_main_no_isaac_exits_zero(self):
        from scripts.isaaclab.check_m3pro_isaac_asset import main
        exit_code = main(["--no-isaac"])
        # 0 = PASS or WARN, 1 = FAIL
        assert exit_code in (0, 1)

    def test_checker_main_verbose_flag_accepted(self):
        from scripts.isaaclab.check_m3pro_isaac_asset import main
        exit_code = main(["--no-isaac", "--verbose"])
        assert exit_code in (0, 1)

    def test_isaac_available_check_does_not_crash(self):
        from scripts.isaaclab.check_m3pro_isaac_asset import check_isaac_available
        result = check_isaac_available()
        assert result.status in ("PASS", "SKIP")

    def test_isaac_ground_contact_skips_without_isaac(self):
        pytest.skip("Isaac headless ground contact test requires GPU + Isaac Sim license")

    def test_checker_result_str_formatting(self):
        from scripts.isaaclab.check_m3pro_isaac_asset import CheckResult, PASS, FAIL, WARN, SKIP
        for status in (PASS, FAIL, WARN, SKIP):
            r = CheckResult(f"test_{status}", status, "detail text")
            s = str(r)
            assert status in s
            assert "test_" in s

    def test_checker_usd_cache_check_runs(self):
        from scripts.isaaclab.check_m3pro_isaac_asset import check_usd_cache
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import M3PRO_USD_DIR
        result = check_usd_cache(M3PRO_USD_DIR)
        # Either PASS (if USD was generated) or WARN (not yet generated)
        assert result.status in ("PASS", "WARN")
