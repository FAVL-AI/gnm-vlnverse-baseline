"""Simple risk map: per-cell risk score accumulated over an episode."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class RiskCell:
    visits: int = 0
    cbf_active_count: int = 0
    near_human_count: int = 0

    @property
    def risk_score(self) -> float:
        if self.visits == 0:
            return 0.0
        return (self.cbf_active_count + 2.0 * self.near_human_count) / self.visits


class RiskMap:
    """Discretize the environment and accumulate risk scores per cell."""

    def __init__(self, resolution_m: float = 0.5):
        self._res = resolution_m
        self._cells: Dict[Tuple[int, int], RiskCell] = {}

    def _key(self, x: float, y: float) -> Tuple[int, int]:
        return (int(x / self._res), int(y / self._res))

    def update(
        self,
        robot_xy: Tuple[float, float],
        cbf_active: bool = False,
        near_human: bool = False,
    ) -> None:
        k = self._key(*robot_xy)
        if k not in self._cells:
            self._cells[k] = RiskCell()
        cell = self._cells[k]
        cell.visits += 1
        if cbf_active:
            cell.cbf_active_count += 1
        if near_human:
            cell.near_human_count += 1

    def high_risk_cells(self, threshold: float = 0.5) -> List[Tuple[Tuple[int, int], float]]:
        return [
            (k, c.risk_score) for k, c in self._cells.items()
            if c.risk_score >= threshold
        ]

    def to_dict(self) -> dict:
        return {
            f"{k[0]},{k[1]}": {
                "visits": c.visits,
                "risk": round(c.risk_score, 3),
            }
            for k, c in self._cells.items()
        }

    def reset(self) -> None:
        self._cells.clear()
