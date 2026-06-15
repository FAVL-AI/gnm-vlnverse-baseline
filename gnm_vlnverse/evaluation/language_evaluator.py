"""Track B offline retrieval evaluation.

Measures how accurately a subgoal-selection method localises the goal
described in a language instruction, without running the GNM policy.

Metric definitions
------------------
Retrieval Euclidean Error (REE)
    REE = sqrt((retrieved_x − goal_x)² + (retrieved_y − goal_y)²)
    where retrieved_x/y and goal_x/y are world-coordinate positions in metres.
    This is Euclidean world-position distance, NOT route/geodesic distance and
    NOT frame-index displacement.

Retrieval Success Rate (RSR)
    RSR = n_success / n_episodes
    where n_success = number of episodes with REE ≤ success_threshold_m.
    Default threshold: 3.0 m  (same as Track A navigation success_threshold).

Separation from navigation
--------------------------
These metrics evaluate language-to-image grounding only.
They do not prove GNM navigation success.
Oracle retrieval (REE = 0) removes retrieval error but does not establish
closed-loop navigation performance.
Full language-conditioned navigation requires retrieval followed by actual
GNM rollout and stopping criterion evaluation.
Retrieval success and navigation success must not be combined into a single
claim unless both stages are executed for the same episode.

Methods
-------
"oracle"  Diagnostic upper bound — not deployable.
          Selects the last keyframe within success_threshold_m of the goal.
          Quantifies how much of the goal geometry the trajectory covers.

"last"    Non-language lower/comparison baseline.
          Selects the final keyframe of the trajectory.
          Does not use the language instruction.

"clip"    Deployable semantic-retrieval baseline.
          Uses CLIP text-image cosine similarity.
          Requires the language dependency group:
              pip install 'gnm-vlnverse[language]'
          Returns ENCODER_UNAVAILABLE status if the dependency is absent.
          Never silently falls back to the last frame.

Install command
---------------
    pip install 'gnm-vlnverse[language]'
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from gnm_vlnverse.vln.language_episode import LanguageEpisode
from gnm_vlnverse.vln.subgoal_selector import EncoderUnavailable, SubgoalSelector

logger = logging.getLogger(__name__)

SUCCESS_THRESHOLD_M: float = 3.0
_REE_FORMULA = "sqrt((retrieved_x - goal_x)^2 + (retrieved_y - goal_y)^2)"
_RSR_FORMULA = "n_success / n_episodes  where success := ree_m <= threshold_m"
_REE_METRIC  = "euclidean_world_position_metres"


@dataclass
class RetrievalResult:
    """Per-episode retrieval outcome."""

    episode_id:         str
    instruction:        str
    true_goal:          tuple
    retrieved_pos:      tuple
    retrieval_error_m:  float
    success:            bool
    method:             str    # "oracle" | "last" | "clip"
    status:             str    # "OK" | "ENCODER_UNAVAILABLE"
    failure_reason:     str | None = None
    retrieved_idx:      int = -1
    n_keyframes:        int = 0


@dataclass
class EvaluationSummary:
    """Aggregated Track B retrieval metrics across all episodes."""

    method:             str
    method_label:       str
    n_episodes:         int
    n_success:          int
    rsr:                float         # Retrieval Success Rate  (0–1)
    mean_ree_m:         float | None
    median_ree_m:       float | None
    std_ree_m:          float | None
    min_ree_m:          float | None
    max_ree_m:          float | None
    status:             str   = "OK"  # "OK" | "ENCODER_UNAVAILABLE" | "NOT_RUN"
    reason:             str | None = None
    ree_metric:         str   = _REE_METRIC
    ree_formula:        str   = _REE_FORMULA
    rsr_formula:        str   = _RSR_FORMULA
    per_episode:        list  = field(default_factory=list)

    def __str__(self) -> str:
        if self.status != "OK":
            return (
                f"[Track B | {self.method}]  "
                f"STATUS={self.status}  reason={self.reason}"
            )
        return (
            f"[Track B | {self.method}]  "
            f"RSR={self.n_success}/{self.n_episodes} ({self.rsr:.1%})  "
            f"mean-REE={self.mean_ree_m:.4f} m  "
            f"std={self.std_ree_m:.4f} m  "
            f"[{self.min_ree_m:.4f}, {self.max_ree_m:.4f}]"
        )


_METHOD_LABELS = {
    "oracle": "Diagnostic upper bound — not deployable",
    "last":   "Non-language lower/comparison baseline",
    "clip":   "Deployable semantic-retrieval baseline",
}


def _unavailable_summary(method: str, reason: str, n_episodes: int) -> EvaluationSummary:
    return EvaluationSummary(
        method=method,
        method_label=_METHOD_LABELS.get(method, method),
        n_episodes=n_episodes,
        n_success=0,
        rsr=0.0,
        mean_ree_m=None,
        median_ree_m=None,
        std_ree_m=None,
        min_ree_m=None,
        max_ree_m=None,
        status="ENCODER_UNAVAILABLE",
        reason=reason,
        per_episode=[],
    )


def _retrieve_one(
    episode: LanguageEpisode,
    method: str,
    threshold_m: float,
    selector: SubgoalSelector | None,
) -> RetrievalResult:
    """Retrieve a subgoal for one episode and measure REE."""

    if method == "oracle":
        idx = episode.oracle_idx(threshold_m)
        status = "OK"
        failure_reason = None

    elif method == "last":
        idx = len(episode.keyframes) - 1
        status = "OK"
        failure_reason = None

    elif method == "clip":
        assert selector is not None
        try:
            _, _, idx = selector.select(episode.instruction)
            status = "OK"
            failure_reason = None
        except EncoderUnavailable as exc:
            return RetrievalResult(
                episode_id=episode.episode_id,
                instruction=episode.instruction,
                true_goal=episode.goal_pos,
                retrieved_pos=(float("nan"), float("nan")),
                retrieval_error_m=float("nan"),
                success=False,
                method=method,
                status="ENCODER_UNAVAILABLE",
                failure_reason=str(exc),
                retrieved_idx=-1,
                n_keyframes=len(episode.keyframes),
            )

    else:
        raise ValueError(
            f"Unknown retrieval method: {method!r}. "
            f"Choose from: 'oracle', 'last', 'clip'."
        )

    ree   = episode.retrieval_error_m(idx)
    rpos  = episode.positions[idx]

    if not math.isfinite(ree):
        success = False
        failure_reason = f"Non-finite REE: {ree}"
    else:
        success = ree <= threshold_m
        failure_reason = (
            None if success
            else f"REE {ree:.4f} m > threshold {threshold_m} m"
        )

    return RetrievalResult(
        episode_id=episode.episode_id,
        instruction=episode.instruction,
        true_goal=episode.goal_pos,
        retrieved_pos=rpos,
        retrieval_error_m=ree,
        success=success,
        method=method,
        status=status,
        failure_reason=failure_reason,
        retrieved_idx=idx,
        n_keyframes=len(episode.keyframes),
    )


def evaluate(
    episodes: Sequence[LanguageEpisode],
    method: str = "clip",
    success_threshold_m: float = SUCCESS_THRESHOLD_M,
    clip_device: str = "cpu",
    clip_model_name: str = "openai/clip-vit-base-patch16",
) -> EvaluationSummary:
    """Evaluate subgoal retrieval across all episodes.

    Parameters
    ----------
    episodes : sequence of LanguageEpisode
    method : "oracle" | "last" | "clip"
    success_threshold_m : float
        Euclidean world-position distance threshold for retrieval success.
    clip_device : str
        Device for CLIP inference ("cpu" or "cuda").
    clip_model_name : str
        HuggingFace CLIP model identifier.

    Returns
    -------
    EvaluationSummary with per-episode results and aggregate metrics.
    When CLIP is unavailable, returns a summary with status="ENCODER_UNAVAILABLE"
    and an empty per_episode list.  Does NOT fall back to last-frame retrieval.
    """
    if not episodes:
        return EvaluationSummary(
            method=method,
            method_label=_METHOD_LABELS.get(method, method),
            n_episodes=0,
            n_success=0,
            rsr=0.0,
            mean_ree_m=None,
            median_ree_m=None,
            std_ree_m=None,
            min_ree_m=None,
            max_ree_m=None,
            status="OK",
            per_episode=[],
        )

    if method not in ("oracle", "last", "clip"):
        raise ValueError(
            f"Unknown retrieval method: {method!r}. "
            "Choose from: 'oracle', 'last', 'clip'."
        )

    selector: SubgoalSelector | None = None

    if method == "clip":
        try:
            import transformers  # noqa: F401
        except ImportError:
            reason = (
                "DEPENDENCY_MISSING: transformers not installed. "
                f"Install with: pip install 'gnm-vlnverse[language]'"
            )
            logger.warning(
                f"CLIP requested but transformers not installed. "
                f"Returning ENCODER_UNAVAILABLE — NOT falling back to last-frame. "
                f"Install with: pip install 'gnm-vlnverse[language]'"
            )
            return _unavailable_summary(method, reason, len(episodes))

        # Build one selector with keyframes from the first episode; CLIP inference
        # is done per-call to select() so the same model is reused.
        selector = SubgoalSelector(
            keyframes=episodes[0].keyframes,
            keyframe_positions=episodes[0].positions,
            device=clip_device,
            model_name=clip_model_name,
        )
        if selector._clip_model is None:
            reason = f"ENCODER_UNAVAILABLE: CLIP model '{clip_model_name}' failed to load."
            return _unavailable_summary(method, reason, len(episodes))

    results: list[RetrievalResult] = []
    for ep in episodes:
        if method == "clip" and selector is not None:
            ep_selector = SubgoalSelector.from_language_episode(
                ep,
                device=clip_device,
                model_name=clip_model_name,
            )
        else:
            ep_selector = None

        result = _retrieve_one(ep, method, success_threshold_m, ep_selector)
        results.append(result)
        logger.debug(
            f"{ep.episode_id}  [{method}]  "
            f"idx={result.retrieved_idx}/{result.n_keyframes - 1 if result.n_keyframes else '?'}  "
            f"REE={result.retrieval_error_m:.4f} m  "
            f"{'✓' if result.success else '✗'}"
        )

    finite_errors = [
        r.retrieval_error_m for r in results
        if math.isfinite(r.retrieval_error_m)
    ]
    arr = np.array(finite_errors) if finite_errors else np.array([])
    n   = len(results)
    n_ok = sum(1 for r in results if r.success)

    return EvaluationSummary(
        method=method,
        method_label=_METHOD_LABELS.get(method, method),
        n_episodes=n,
        n_success=n_ok,
        rsr=float(n_ok / n) if n else 0.0,
        mean_ree_m=float(np.mean(arr))   if arr.size else None,
        median_ree_m=float(np.median(arr)) if arr.size else None,
        std_ree_m=float(np.std(arr, ddof=0)) if arr.size else None,
        min_ree_m=float(np.min(arr))     if arr.size else None,
        max_ree_m=float(np.max(arr))     if arr.size else None,
        status="OK",
        per_episode=results,
    )


def compare_methods(
    episodes: Sequence[LanguageEpisode],
    methods: Sequence[str] = ("oracle", "last", "clip"),
    success_threshold_m: float = SUCCESS_THRESHOLD_M,
    **kwargs,
) -> dict[str, EvaluationSummary]:
    """Evaluate and compare multiple retrieval methods on the same episode set."""
    return {
        m: evaluate(episodes, method=m, success_threshold_m=success_threshold_m, **kwargs)
        for m in methods
    }
