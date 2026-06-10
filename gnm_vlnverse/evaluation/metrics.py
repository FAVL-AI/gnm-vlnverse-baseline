"""VLNVerse evaluation metrics.

Metrics Explained (for a 14-year-old)
---------------------------------------

Imagine the robot must walk from the bedroom to the kitchen following
the instruction "Go past the sofa and stop at the fridge."

SR — Success Rate
  Did the robot reach the fridge?  1 = yes, 0 = no.
  Success = distance to the goal at the end < success_threshold (default 3 m).
  Range: [0, 1].  Higher is better.

OSR — Oracle Success Rate
  Did the robot EVER pass within success_threshold of the goal,
  even if it didn't stop there?  Shows upper bound if we had a perfect stop.
  OSR ≥ SR always.

SPL — Success weighted by Path Length
  You succeeded, but how efficient were you?

    SPL = (1/N) Σ_i   s_i  ×  (L*_i / max(p_i, L*_i))

    s_i  = 1 if episode i was a success, 0 otherwise
    L*_i = shortest path length (from A*)
    p_i  = actual path length the robot walked

  If you went straight to the goal: SPL ≈ SR.
  If you took a huge detour: SPL << SR.
  Range: [0, 1].  Higher is better.

NE — Navigation Error
  Average distance (metres) between the robot's final position and the goal.
  Lower is better.  A perfectly successful robot has NE = 0.

TL — Trajectory Length
  Average distance the robot walked in total.
  Used to check if the robot is wandering vs going direct.

nDTW — normalized Dynamic Time Warping
  Measures how closely the robot followed the *reference path*, not just
  whether it reached the goal.

  DTW computes the minimum-cost alignment between two sequences of positions.
  Like comparing two dance routines step-by-step — even if one is faster.
  nDTW normalizes by path length so it is scale-independent.

  Range: [0, 1].  1 = perfect path match.  Higher is better.

CLS — Coverage weighted by Length Score
  Measures what fraction of the reference path was *covered* by the robot,
  weighted by path length efficiency.  Useful for partial-credit scoring.

CR — Collision Rate
  What fraction of timesteps did the robot collide with something?
  CR = 0 means perfectly safe navigation.
  This is CRITICAL for VLNVerse (physics-aware) — ghost-camera metrics ignore it.
  Range: [0, 1].  Lower is better.

SRn — nth-goal Success Rate
  For long-horizon multi-goal tasks, what fraction of goals (waypoints)
  did the robot reach?
  If a task has 3 goals and the robot reaches 2, SRn = 2/3.

All metrics are micro-averaged across episodes (not macro/trajectory).

References
----------
- Anderson et al., "On Evaluation of Embodied Navigation Agents", 2018.
- Magalhaes et al., "Effective Use of Context in Noisy Image for VLN", 2019.
- Krantz et al., "Beyond the Nav-Graph: Vision-and-Language Navigation in
  Continuous Environments", ECCV 2020.
- Lin et al., "VLNVerse", 2025.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# Success threshold: robot is "at the goal" if within this distance (metres)
DEFAULT_SUCCESS_THRESHOLD = 3.0


@dataclass
class Episode:
    """A single evaluation episode."""
    # Actual trajectory the robot walked: list of (x, y) positions
    actual_path:    list[tuple[float, float]]
    # Reference / oracle path from A*: list of (x, y) positions
    reference_path: list[tuple[float, float]]
    # Goal position
    goal_pos:       tuple[float, float]
    # Per-step collision flags (True = collision at that step)
    collisions:     list[bool] = field(default_factory=list)
    # Sub-goal positions for long-horizon tasks
    sub_goals:      list[tuple[float, float]] = field(default_factory=list)


@dataclass
class NavigationMetrics:
    """Aggregated evaluation metrics across multiple episodes."""
    SR:   float = 0.0   # Success Rate
    OSR:  float = 0.0   # Oracle Success Rate
    SPL:  float = 0.0   # Success × (shortest / actual) path
    NE:   float = 0.0   # Navigation Error (metres)
    TL:   float = 0.0   # Trajectory Length (metres)
    nDTW: float = 0.0   # normalized Dynamic Time Warping
    CLS:  float = 0.0   # Coverage × Length Score
    CR:   float = 0.0   # Collision Rate
    SRn:  float = 0.0   # nth-goal success rate (long-horizon)
    n_episodes: int = 0

    def to_dict(self) -> dict[str, float]:
        return {
            "SR":   round(self.SR,   4),
            "OSR":  round(self.OSR,  4),
            "SPL":  round(self.SPL,  4),
            "NE":   round(self.NE,   4),
            "TL":   round(self.TL,   4),
            "nDTW": round(self.nDTW, 4),
            "CLS":  round(self.CLS,  4),
            "CR":   round(self.CR,   4),
            "SRn":  round(self.SRn,  4),
            "n_episodes": self.n_episodes,
        }

    def __str__(self) -> str:
        d = self.to_dict()
        return (
            f"SR={d['SR']:.3f}  OSR={d['OSR']:.3f}  SPL={d['SPL']:.3f}  "
            f"NE={d['NE']:.2f}m  TL={d['TL']:.2f}m  "
            f"nDTW={d['nDTW']:.3f}  CR={d['CR']:.3f}  "
            f"(n={d['n_episodes']})"
        )


# ── Per-episode metric functions ──────────────────────────────────────────────

def path_length(path: list[tuple[float, float]]) -> float:
    """Total Euclidean length of a path."""
    if len(path) < 2:
        return 0.0
    return float(sum(
        math.hypot(path[i+1][0] - path[i][0], path[i+1][1] - path[i][1])
        for i in range(len(path) - 1)
    ))


def nav_error(actual_path: list[tuple[float, float]], goal: tuple[float, float]) -> float:
    """Distance from the robot's final position to the goal."""
    if not actual_path:
        return math.inf
    fx, fy = actual_path[-1]
    return math.hypot(fx - goal[0], fy - goal[1])


def success(ne: float, threshold: float = DEFAULT_SUCCESS_THRESHOLD) -> bool:
    return ne <= threshold


def oracle_success(
    actual_path: list[tuple[float, float]],
    goal: tuple[float, float],
    threshold: float = DEFAULT_SUCCESS_THRESHOLD,
) -> bool:
    """True if the robot was ever within threshold metres of the goal."""
    return any(
        math.hypot(x - goal[0], y - goal[1]) <= threshold
        for x, y in actual_path
    )


def spl(
    s: bool,
    actual_path: list[tuple[float, float]],
    shortest_path_length: float,
) -> float:
    """Success weighted by Path Length for a single episode."""
    if not s:
        return 0.0
    p = path_length(actual_path)
    return shortest_path_length / max(p, shortest_path_length)


def collision_rate(collisions: list[bool]) -> float:
    if not collisions:
        return 0.0
    return sum(collisions) / len(collisions)


def ndtw(
    actual_path: list[tuple[float, float]],
    reference_path: list[tuple[float, float]],
) -> float:
    """Normalized Dynamic Time Warping between actual and reference paths.

    DTW finds the minimum cost alignment between two sequences.
    Then we normalise by the reference path length so that longer paths
    don't automatically have higher raw DTW scores.

    Formula:
      DTW(A, R) = minimum alignment cost using ||a_i - r_j||
      nDTW = exp(-DTW / (len(R) * decay))

    decay is typically 3.0 (VLNVerse standard).
    """
    if not actual_path or not reference_path:
        return 0.0

    A = np.array(actual_path,   dtype=np.float32)
    R = np.array(reference_path, dtype=np.float32)
    n, m = len(A), len(R)

    # DP table: dtw[i][j] = min cost to align A[:i+1] with R[:j+1]
    dtw_dp = np.full((n + 1, m + 1), np.inf, dtype=np.float32)
    dtw_dp[0, 0] = 0.0

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = np.linalg.norm(A[i-1] - R[j-1])
            dtw_dp[i, j] = cost + min(
                dtw_dp[i-1, j],    # deletion
                dtw_dp[i, j-1],    # insertion
                dtw_dp[i-1, j-1],  # match
            )

    dtw_score = dtw_dp[n, m]
    # Normalize and convert to similarity [0, 1]
    decay = 3.0
    norm  = np.exp(-dtw_score / (m * decay))
    return float(np.clip(norm, 0.0, 1.0))


def cls(
    actual_path: list[tuple[float, float]],
    reference_path: list[tuple[float, float]],
    pc: float = 3.0,
) -> float:
    """Coverage weighted by Length Score (CLS).

    For each reference waypoint, check if the robot passed within pc metres.
    coverage = fraction of reference waypoints covered.
    length_score = min(len_ref, len_actual) / max(len_ref, len_actual)
    CLS = coverage × length_score

    pc is the coverage threshold (default 3 m, same as success_threshold).
    """
    if not actual_path or not reference_path:
        return 0.0

    A = np.array(actual_path,   dtype=np.float32)
    R = np.array(reference_path, dtype=np.float32)

    covered = 0
    for rp in R:
        dists = np.linalg.norm(A - rp, axis=1)
        if np.min(dists) <= pc:
            covered += 1

    coverage     = covered / len(R)
    len_actual   = path_length(actual_path)
    len_ref      = path_length(reference_path)
    length_score = min(len_actual, len_ref) / max(len_actual, len_ref, 1e-6)

    return float(coverage * length_score)


def srn(
    actual_path: list[tuple[float, float]],
    sub_goals: list[tuple[float, float]],
    threshold: float = DEFAULT_SUCCESS_THRESHOLD,
) -> float:
    """nth-goal success rate for long-horizon tasks.

    For each sub-goal in order, check if the robot was ever within threshold.
    Returns fraction of sub-goals reached.
    """
    if not sub_goals:
        return 0.0
    reached = sum(
        oracle_success(actual_path, sg, threshold)
        for sg in sub_goals
    )
    return reached / len(sub_goals)


# ── Aggregation ────────────────────────────────────────────────────────────────

def compute_all_metrics(
    episodes: list[Episode],
    success_threshold: float = DEFAULT_SUCCESS_THRESHOLD,
) -> NavigationMetrics:
    """Aggregate metrics across all episodes.

    Parameters
    ----------
    episodes : list[Episode]
        Each episode has actual_path, reference_path, goal_pos, collisions.
    success_threshold : float
        Distance (metres) within which the robot is considered to have
        reached the goal.

    Returns
    -------
    NavigationMetrics (micro-averaged)
    """
    if not episodes:
        return NavigationMetrics()

    metrics = NavigationMetrics(n_episodes=len(episodes))
    sr_vals, osr_vals, spl_vals = [], [], []
    ne_vals, tl_vals, ndtw_vals, cls_vals, cr_vals, srn_vals = [], [], [], [], [], []

    for ep in episodes:
        ne  = nav_error(ep.actual_path, ep.goal_pos)
        s   = success(ne, success_threshold)
        osr = oracle_success(ep.actual_path, ep.goal_pos, success_threshold)
        spl_val = spl(s, ep.actual_path, path_length(ep.reference_path))
        tl_val  = path_length(ep.actual_path)
        dtw_val = ndtw(ep.actual_path, ep.reference_path)
        cls_val = cls(ep.actual_path,  ep.reference_path, pc=success_threshold)
        cr_val  = collision_rate(ep.collisions)
        srn_val = srn(ep.actual_path, ep.sub_goals, success_threshold)

        sr_vals.append(float(s))
        osr_vals.append(float(osr))
        spl_vals.append(spl_val)
        ne_vals.append(ne)
        tl_vals.append(tl_val)
        ndtw_vals.append(dtw_val)
        cls_vals.append(cls_val)
        cr_vals.append(cr_val)
        srn_vals.append(srn_val)

    metrics.SR   = float(np.mean(sr_vals))
    metrics.OSR  = float(np.mean(osr_vals))
    metrics.SPL  = float(np.mean(spl_vals))
    metrics.NE   = float(np.mean(ne_vals))
    metrics.TL   = float(np.mean(tl_vals))
    metrics.nDTW = float(np.mean(ndtw_vals))
    metrics.CLS  = float(np.mean(cls_vals))
    metrics.CR   = float(np.mean(cr_vals))
    metrics.SRn  = float(np.mean(srn_vals))

    return metrics
