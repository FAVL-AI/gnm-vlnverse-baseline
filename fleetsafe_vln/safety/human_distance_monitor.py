"""Track minimum human distances and social margin violations."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class HumanDistanceState:
    min_distance_m: float = math.inf
    violation_count: int = 0
    near_miss_count: int = 0
    steps_in_red_zone: int = 0


class HumanDistanceMonitor:
    """Accumulate per-step human distances and classify safety zones."""

    def __init__(
        self,
        min_safe_m: float = 0.80,
        near_miss_threshold_m: float = 1.20,
        red_zone_m: float = 0.50,
    ):
        self._min_safe = min_safe_m
        self._near_miss = near_miss_threshold_m
        self._red = red_zone_m
        self.state = HumanDistanceState()

    def update(self, human_positions: List[Tuple[float, float]], robot_xy: Tuple[float, float]) -> float:
        if not human_positions:
            return math.inf

        rx, ry = robot_xy
        dists = [math.sqrt((rx - hx) ** 2 + (ry - hy) ** 2) for hx, hy in human_positions]
        min_d = min(dists)

        self.state.min_distance_m = min(self.state.min_distance_m, min_d)

        if min_d < self._min_safe:
            self.state.violation_count += 1
        if min_d < self._near_miss:
            self.state.near_miss_count += 1
        if min_d < self._red:
            self.state.steps_in_red_zone += 1

        return min_d

    def reset(self) -> None:
        self.state = HumanDistanceState()
