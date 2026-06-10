"""
Procedural rough terrain generator for Fleet-Safe-VLA-OS.

Generates heightfield-based terrains compatible with both Isaac Lab and
MuJoCo. Terrain types are composable and curriculum-friendly.

Terrain catalog:
  - flat         : baseline, height=0 everywhere
  - rough        : Perlin-noise heightfield (amplitude 0–5 cm per level)
  - stairs_up    : upward staircase (rise 8 cm, run 30 cm)
  - stairs_down  : downward staircase
  - slope_up     : ramp (4° per level)
  - discrete     : random stepping stones
  - pit          : narrow bridge / gap crossing

Usage (MuJoCo):
    terrain = RoughTerrain(seed=42, level=3)
    hfield_data = terrain.generate_heightfield(rows=256, cols=256, size_m=10.0)

Usage (Isaac Lab terrain generator config):
    from fleet_safe_vla.assets.terrains.rough_terrain import build_isaaclab_terrain_cfg
    terrain_cfg = build_isaaclab_terrain_cfg(num_levels=8, num_cols=10)
"""
from __future__ import annotations

import math
from typing import Literal

import numpy as np

TerrainType = Literal["flat", "rough", "stairs_up", "stairs_down", "slope_up", "slope_down", "discrete", "pit"]


# ── Perlin noise helpers ──────────────────────────────────────────────────────

def _fade(t: np.ndarray) -> np.ndarray:
    return t * t * t * (t * (t * 6 - 15) + 10)


def _lerp(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
    return a + t * (b - a)


def _perlin_noise_2d(shape: tuple[int, int], scale: float, seed: int = 0) -> np.ndarray:
    """
    Generate 2D Perlin noise array with values in [-1, 1].

    Args:
        shape: (rows, cols) output shape
        scale: noise frequency (higher = more detail)
        seed: random seed
    """
    rng = np.random.default_rng(seed)
    rows, cols = shape

    # Grid size
    gx = math.ceil(rows / scale) + 2
    gy = math.ceil(cols / scale) + 2

    # Random gradient vectors
    angles = rng.uniform(0, 2 * np.pi, (gx, gy))
    gvx = np.cos(angles)
    gvy = np.sin(angles)

    # Sample coordinates
    x = np.linspace(0, gx - 2, rows)
    y = np.linspace(0, gy - 2, cols)
    xi = x.astype(int)
    yi = y.astype(int)
    xf = x - xi
    yf = y - yi

    xf2d = xf[:, np.newaxis]
    yf2d = yf[np.newaxis, :]

    # Dot products at 4 corners
    def dot(gx_idx, gy_idx, dx, dy):
        return gvx[xi + gx_idx, :][:, yi + gy_idx] * dx + gvy[xi + gx_idx, :][:, yi + gy_idx] * dy

    n00 = dot(0, 0, xf2d, yf2d)
    n10 = dot(1, 0, xf2d - 1, yf2d)
    n01 = dot(0, 1, xf2d, yf2d - 1)
    n11 = dot(1, 1, xf2d - 1, yf2d - 1)

    u = _fade(xf2d)
    v = _fade(yf2d)

    noise = _lerp(
        _lerp(n00, n10, u),
        _lerp(n01, n11, u),
        v,
    )
    return noise


# ── Terrain generators ────────────────────────────────────────────────────────

class RoughTerrain:
    """
    Procedural terrain generator.

    Args:
        terrain_type: type of terrain to generate
        level: curriculum level 0–9 (0=easiest)
        seed: random seed for reproducibility
    """

    # Amplitude per curriculum level (meters)
    ROUGH_AMPLITUDE = [0.0, 0.01, 0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20]
    SLOPE_ANGLE_DEG = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0]
    STAIR_RISE_CM   = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 18.0, 22.0]

    def __init__(
        self,
        terrain_type: TerrainType = "rough",
        level: int = 0,
        seed: int = 42,
    ) -> None:
        self.terrain_type = terrain_type
        self.level = max(0, min(level, 9))
        self.seed = seed

    def generate_heightfield(
        self,
        rows: int = 256,
        cols: int = 256,
        size_m: float = 10.0,
    ) -> np.ndarray:
        """
        Generate heightfield array of shape (rows, cols).

        Returns height values in meters. Use size_m to convert to world coordinates:
            x_world = col * (size_m / cols)
            y_world = row * (size_m / rows)
        """
        if self.terrain_type == "flat":
            return self._flat(rows, cols)
        elif self.terrain_type == "rough":
            return self._rough(rows, cols, size_m)
        elif self.terrain_type == "stairs_up":
            return self._stairs(rows, cols, size_m, direction=1)
        elif self.terrain_type == "stairs_down":
            return self._stairs(rows, cols, size_m, direction=-1)
        elif self.terrain_type == "slope_up":
            return self._slope(rows, cols, size_m, direction=1)
        elif self.terrain_type == "slope_down":
            return self._slope(rows, cols, size_m, direction=-1)
        elif self.terrain_type == "discrete":
            return self._discrete_obstacles(rows, cols, size_m)
        elif self.terrain_type == "pit":
            return self._pit(rows, cols)
        else:
            raise ValueError(f"Unknown terrain type: {self.terrain_type}")

    def _flat(self, rows: int, cols: int) -> np.ndarray:
        return np.zeros((rows, cols), dtype=np.float32)

    def _rough(self, rows: int, cols: int, size_m: float) -> np.ndarray:
        amplitude = self.ROUGH_AMPLITUDE[self.level]
        if amplitude == 0.0:
            return np.zeros((rows, cols), dtype=np.float32)
        # Multi-octave Perlin noise
        scale = max(4.0, size_m * 0.8)
        noise = _perlin_noise_2d((rows, cols), scale=scale, seed=self.seed)
        # Add finer detail
        noise += 0.5 * _perlin_noise_2d((rows, cols), scale=scale * 0.4, seed=self.seed + 1)
        noise /= 1.5
        return (noise * amplitude).astype(np.float32)

    def _stairs(self, rows: int, cols: int, size_m: float, direction: int = 1) -> np.ndarray:
        rise_m = self.STAIR_RISE_CM[self.level] / 100.0
        run_m = 0.30  # 30 cm per step
        run_cells = max(1, int(run_m / size_m * cols))

        hfield = np.zeros((rows, cols), dtype=np.float32)
        for col in range(cols):
            step_idx = col // run_cells
            height = step_idx * rise_m * direction
            hfield[:, col] = height
        return hfield

    def _slope(self, rows: int, cols: int, size_m: float, direction: int = 1) -> np.ndarray:
        angle_rad = math.radians(self.SLOPE_ANGLE_DEG[self.level])
        x = np.linspace(0, size_m, cols)
        slope = (np.tan(angle_rad) * x * direction).astype(np.float32)
        return np.tile(slope, (rows, 1))

    def _discrete_obstacles(self, rows: int, cols: int, size_m: float) -> np.ndarray:
        rng = np.random.default_rng(self.seed)
        hfield = np.zeros((rows, cols), dtype=np.float32)
        amplitude = self.ROUGH_AMPLITUDE[self.level]
        n_obs = int(rows * cols * 0.05)  # 5% coverage
        obs_r = max(1, int(0.05 / size_m * rows))  # ~5 cm radius
        for _ in range(n_obs):
            cx = rng.integers(0, rows)
            cy = rng.integers(0, cols)
            h = rng.uniform(0.01, max(0.01, amplitude))
            r0 = max(0, cx - obs_r)
            r1 = min(rows, cx + obs_r)
            c0 = max(0, cy - obs_r)
            c1 = min(cols, cy + obs_r)
            hfield[r0:r1, c0:c1] = np.maximum(hfield[r0:r1, c0:c1], h)
        return hfield

    def _pit(self, rows: int, cols: int) -> np.ndarray:
        hfield = np.zeros((rows, cols), dtype=np.float32)
        # Platform sections at start and end; gap in the middle
        gap_start = int(cols * 0.4)
        gap_end = int(cols * 0.6)
        hfield[:, gap_start:gap_end] = -1.0  # pit depth
        return hfield


# ── Isaac Lab terrain config builder ─────────────────────────────────────────

def build_isaaclab_terrain_cfg(num_levels: int = 8, num_cols: int = 10) -> dict:
    """
    Build a terrain config dict compatible with Isaac Lab's SubTerrainBaseCfg.

    Usage:
        from isaaclab.terrains import TerrainImporterCfg
        cfg = build_isaaclab_terrain_cfg()
        # Pass cfg["sub_terrains"] to TerrainGeneratorCfg

    This function does NOT import isaaclab — it returns a plain dict.
    """
    terrain_types = [
        {"type": "flat",        "weight": 1.0, "proportion": 0.10},
        {"type": "rough",       "weight": 2.0, "proportion": 0.30},
        {"type": "stairs_up",   "weight": 1.5, "proportion": 0.15},
        {"type": "stairs_down", "weight": 1.5, "proportion": 0.15},
        {"type": "slope_up",    "weight": 1.0, "proportion": 0.10},
        {"type": "slope_down",  "weight": 1.0, "proportion": 0.10},
        {"type": "discrete",    "weight": 1.0, "proportion": 0.10},
    ]
    return {
        "num_rows": num_levels,
        "num_cols": num_cols,
        "curriculum": True,
        "size": (10.0, 10.0),
        "border_width": 5.0,
        "difficulty_range": (0.0, 1.0),
        "sub_terrains": terrain_types,
    }


# ── MuJoCo heightfield injection helper ──────────────────────────────────────

def terrain_to_mujoco_hfield(
    terrain: RoughTerrain,
    rows: int = 128,
    cols: int = 128,
    size_m: float = 10.0,
) -> tuple[np.ndarray, float]:
    """
    Convert RoughTerrain to MuJoCo heightfield format.

    MuJoCo heightfield values are in [0, 1] normalized by max_height.
    Returns (hfield_nchw, max_height_m).
    """
    hfield = terrain.generate_heightfield(rows, cols, size_m)
    h_min = hfield.min()
    hfield -= h_min  # shift so min = 0
    h_max = hfield.max()
    if h_max < 1e-6:
        return hfield.astype(np.float32), 0.01
    normalized = hfield / h_max
    return normalized.astype(np.float32), float(h_max)
