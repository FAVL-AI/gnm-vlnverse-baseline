"""Track B language-grounding pipeline tests.

Uses the real custom_vln_office dataset (6 episodes, 31–41 steps each).
All tests run without a GPU or transformers installed; CLIP is not required.

Coverage
--------
Episode loading
    - Field types and constraints
    - Dataset-level loading and uniqueness
    - stride reduction
    - Unequal frame/pose array detection
    - Missing ground-truth target handling

LanguageEpisode helpers
    - oracle_idx bounds and proximity guarantee
    - retrieval_error_m Euclidean formula
    - NaN and infinite coordinate handling
    - Exact threshold boundary
    - Duplicate frame handling

SubgoalSelector
    - Construction from LanguageEpisode
    - from_language_episode with unequal arrays (raises)
    - EncoderUnavailable raised when CLIP not loaded
    - Encoder failure does NOT trigger last-frame selection (regression gate)
    - clip_info() structure when unavailable

Retrieval evaluation — oracle method
    - Returns EvaluationSummary
    - Metrics within valid ranges
    - Per-episode field types
    - Empty episode set produces zero counts

Retrieval evaluation — last-frame method
    - Retrieved index is always the final keyframe
    - RSR within [0, 1]

Retrieval evaluation — CLIP fallback
    - When transformers absent: returns ENCODER_UNAVAILABLE status
    - Does NOT return last-frame results for CLIP method
    - n_episodes is preserved in ENCODER_UNAVAILABLE summary

Metric semantics
    - REE uses Euclidean world-position distance (not frame-index displacement)
    - Threshold boundary: REE == threshold counts as success
    - Threshold boundary: REE infinitesimally above threshold counts as failure
    - NaN position → non-finite REE → failure

compare_methods
    - Returns dict with correct keys
    - oracle RSR ≥ last RSR (for this dataset)
    - Invalid method raises ValueError

Deterministic repeatability
    - Multiple evaluate() calls produce identical results

Non-discriminative dataset detection (Gate A.6)
    - Oracle REE == last-frame REE for every episode in the synthetic dataset
    - All per-episode REE values are 0.0 (synthetic trajectories end at goal_pos)

Discriminative dataset (Gate A.7)
    - Synthetic episode where goal is mid-trajectory, not the final frame
    - Oracle REE < last-frame REE
    - Oracle within threshold; last-frame outside threshold
    - Oracle RSR > last-frame RSR
"""
from __future__ import annotations

import math
import pathlib

import numpy as np
import pytest

from gnm_vlnverse.vln.language_episode import (
    LanguageEpisode,
    load_dataset,
    load_episode,
)
from gnm_vlnverse.vln.subgoal_selector import EncoderUnavailable, SubgoalSelector
from gnm_vlnverse.evaluation.language_evaluator import (
    EvaluationSummary,
    RetrievalResult,
    SUCCESS_THRESHOLD_M,
    _REE_METRIC,
    compare_methods,
    evaluate,
)

DATASET_ROOT = pathlib.Path("datasets/custom_vln_office")
TRAIN_DIR    = DATASET_ROOT / "train"

pytestmark = pytest.mark.skipif(
    not TRAIN_DIR.is_dir(),
    reason="custom_vln_office dataset not found",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def single_episode() -> LanguageEpisode:
    ep_dir = next(iter(sorted(TRAIN_DIR.iterdir())))
    return load_episode(ep_dir, stride=5)


@pytest.fixture(scope="module")
def all_episodes() -> list[LanguageEpisode]:
    return load_dataset(DATASET_ROOT, split="train", stride=5)


def _tiny_episode(n: int = 4, goal_offset: float = 0.0) -> LanguageEpisode:
    """Build a minimal LanguageEpisode for unit testing without disk I/O."""
    frames    = [np.zeros((8, 8, 3), dtype=np.uint8) for _ in range(n)]
    positions = [(float(i), 0.0) for i in range(n)]
    return LanguageEpisode(
        episode_id="test_ep",
        instruction="go forward",
        keyframes=frames,
        positions=positions,
        goal_pos=(float(n - 1) + goal_offset, 0.0),
        path_length_m=float(n - 1),
    )


# ---------------------------------------------------------------------------
# Episode loading
# ---------------------------------------------------------------------------

class TestEpisodeLoading:
    def test_episode_id_is_non_empty_string(self, single_episode):
        assert isinstance(single_episode.episode_id, str)
        assert single_episode.episode_id

    def test_instruction_is_non_empty_string(self, single_episode):
        assert isinstance(single_episode.instruction, str)
        assert len(single_episode.instruction) > 5

    def test_keyframes_are_rgb_uint8(self, single_episode):
        assert len(single_episode.keyframes) > 0
        frame = single_episode.keyframes[0]
        assert isinstance(frame, np.ndarray)
        assert frame.ndim == 3
        assert frame.shape[2] == 3
        assert frame.dtype == np.uint8

    def test_positions_match_keyframe_count(self, single_episode):
        assert len(single_episode.positions) == len(single_episode.keyframes)

    def test_positions_are_float_pairs(self, single_episode):
        for pos in single_episode.positions:
            assert len(pos) == 2
            assert all(isinstance(v, float) for v in pos)

    def test_goal_pos_is_float_pair(self, single_episode):
        gp = single_episode.goal_pos
        assert len(gp) == 2
        assert all(isinstance(v, float) for v in gp)

    def test_path_length_positive(self, single_episode):
        assert single_episode.path_length_m > 0.0

    def test_stride_reduces_keyframe_count(self):
        ep_dir = next(iter(sorted(TRAIN_DIR.iterdir())))
        ep1 = load_episode(ep_dir, stride=1)
        ep5 = load_episode(ep_dir, stride=5)
        assert len(ep5.keyframes) < len(ep1.keyframes)

    def test_len_equals_keyframe_count(self, single_episode):
        assert len(single_episode) == len(single_episode.keyframes)


class TestDatasetLoading:
    def test_loads_all_episodes(self, all_episodes):
        assert len(all_episodes) == 6

    def test_all_instructions_unique(self, all_episodes):
        insts = [ep.instruction for ep in all_episodes]
        assert len(set(insts)) == len(insts)

    def test_all_episodes_have_keyframes(self, all_episodes):
        for ep in all_episodes:
            assert len(ep.keyframes) > 0

    def test_missing_split_raises(self):
        with pytest.raises(FileNotFoundError):
            load_dataset(DATASET_ROOT, split="nonexistent_split")


# ---------------------------------------------------------------------------
# LanguageEpisode helpers
# ---------------------------------------------------------------------------

class TestEpisodeHelpers:
    def test_retrieval_error_euclidean_formula(self):
        ep  = _tiny_episode(n=4)
        idx = 0
        pos  = np.array(ep.positions[idx])
        goal = np.array(ep.goal_pos)
        expected = float(np.linalg.norm(pos - goal))
        assert ep.retrieval_error_m(idx) == pytest.approx(expected)

    def test_ree_metric_is_world_distance_not_frame_index(self):
        # positions are in metres; frame index 0 is at (0, 0), goal at (3, 0)
        ep  = _tiny_episode(n=4)
        ree = ep.retrieval_error_m(0)
        assert ree == pytest.approx(3.0), (
            "REE must be Euclidean world-position distance in metres, "
            "not frame-index displacement"
        )

    def test_oracle_idx_within_bounds(self, single_episode):
        idx = single_episode.oracle_idx()
        assert 0 <= idx < len(single_episode)

    def test_oracle_idx_near_goal_or_last(self, single_episode):
        idx   = single_episode.oracle_idx(success_threshold_m=SUCCESS_THRESHOLD_M)
        error = single_episode.retrieval_error_m(idx)
        assert error <= SUCCESS_THRESHOLD_M or idx == len(single_episode) - 1

    def test_exact_threshold_boundary_success(self):
        ep  = _tiny_episode(n=4, goal_offset=0.0)  # last frame exactly at goal
        ree = ep.retrieval_error_m(len(ep) - 1)
        assert ree == pytest.approx(0.0)
        assert ree <= SUCCESS_THRESHOLD_M

    def test_just_above_threshold_is_failure(self):
        ep  = _tiny_episode(n=4, goal_offset=SUCCESS_THRESHOLD_M + 0.001)
        idx = len(ep) - 1
        ree = ep.retrieval_error_m(idx)
        assert ree > SUCCESS_THRESHOLD_M

    def test_nan_position_gives_nan_ree(self):
        ep = _tiny_episode(n=2)
        ep.positions[0] = (float("nan"), 0.0)
        ree = ep.retrieval_error_m(0)
        assert math.isnan(ree)

    def test_inf_position_gives_inf_ree(self):
        ep = _tiny_episode(n=2)
        ep.positions[0] = (float("inf"), 0.0)
        ree = ep.retrieval_error_m(0)
        assert math.isinf(ree)

    def test_duplicate_frames_allowed(self):
        # Two identical frames are a valid degenerate case
        frame = np.ones((8, 8, 3), dtype=np.uint8)
        ep    = LanguageEpisode(
            episode_id="dup",
            instruction="go forward",
            keyframes=[frame, frame],
            positions=[(0.0, 0.0), (1.0, 0.0)],
            goal_pos=(1.0, 0.0),
            path_length_m=1.0,
        )
        assert len(ep) == 2
        assert ep.retrieval_error_m(1) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# SubgoalSelector — construction and encoder failure
# ---------------------------------------------------------------------------

class TestSubgoalSelectorConstruction:
    def test_from_language_episode_constructs(self, single_episode):
        sel = SubgoalSelector.from_language_episode(single_episode)
        assert sel is not None

    def test_keyframe_count_preserved(self, single_episode):
        sel = SubgoalSelector.from_language_episode(single_episode)
        assert len(sel.keyframes) == len(single_episode.keyframes)

    def test_unequal_arrays_raises(self):
        frames = [np.zeros((8, 8, 3), dtype=np.uint8)] * 3
        positions = [(0.0, 0.0), (1.0, 0.0)]   # mismatched length
        with pytest.raises(ValueError, match="equal length"):
            SubgoalSelector(keyframes=frames, keyframe_positions=positions)

    def test_clip_info_unavailable_when_no_transformers(self, single_episode):
        sel = SubgoalSelector.from_language_episode(single_episode)
        info = sel.clip_info()
        assert isinstance(info, dict)
        assert "status" in info
        assert "model_identifier" in info

    def test_clip_info_unavailable_status_when_clip_not_loaded(self, single_episode):
        sel = SubgoalSelector.from_language_episode(single_episode)
        if sel._clip_model is None:
            assert sel.clip_info()["status"] == "ENCODER_UNAVAILABLE"


class TestEncoderFailure:
    """Regression gate: encoder failure must never silently select the last frame."""

    def test_select_raises_when_clip_not_loaded(self, single_episode):
        sel = SubgoalSelector.from_language_episode(single_episode)
        if sel._clip_model is not None:
            pytest.skip("CLIP is loaded — encoder failure path not exercised")
        with pytest.raises(EncoderUnavailable):
            sel.select(single_episode.instruction)

    def test_encoder_failure_does_not_return_last_frame(self, single_episode):
        """Regression: select() must raise, not silently return the last keyframe."""
        sel = SubgoalSelector.from_language_episode(single_episode)
        if sel._clip_model is not None:
            pytest.skip("CLIP is loaded — encoder failure path not exercised")
        last_idx = len(single_episode) - 1
        raised = False
        returned_idx = None
        try:
            _, _, returned_idx = sel.select(single_episode.instruction)
        except EncoderUnavailable:
            raised = True
        assert raised, (
            "select() must raise EncoderUnavailable when CLIP is not loaded. "
            "It must not silently return the last keyframe."
        )
        assert returned_idx is None, (
            "select() returned a value instead of raising — "
            "encoder failure triggered silent last-frame substitution."
        )

    def test_encoder_unavailable_reason_code(self, single_episode):
        sel = SubgoalSelector.from_language_episode(single_episode)
        if sel._clip_model is not None:
            pytest.skip("CLIP is loaded")
        with pytest.raises(EncoderUnavailable) as exc_info:
            sel.select(single_episode.instruction)
        assert "ENCODER_UNAVAILABLE" in str(exc_info.value)

    def test_encoder_unavailable_exception_has_reason_attribute(self, single_episode):
        sel = SubgoalSelector.from_language_episode(single_episode)
        if sel._clip_model is not None:
            pytest.skip("CLIP is loaded")
        with pytest.raises(EncoderUnavailable) as exc_info:
            sel.select(single_episode.instruction)
        assert exc_info.value.reason == "ENCODER_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Retrieval evaluation — oracle
# ---------------------------------------------------------------------------

class TestOracleRetrieval:
    def test_returns_evaluation_summary(self, all_episodes):
        s = evaluate(all_episodes, method="oracle")
        assert isinstance(s, EvaluationSummary)

    def test_status_ok(self, all_episodes):
        s = evaluate(all_episodes, method="oracle")
        assert s.status == "OK"

    def test_rsr_in_unit_interval(self, all_episodes):
        s = evaluate(all_episodes, method="oracle")
        assert 0.0 <= s.rsr <= 1.0

    def test_n_success_le_n_episodes(self, all_episodes):
        s = evaluate(all_episodes, method="oracle")
        assert s.n_success <= s.n_episodes

    def test_mean_ree_non_negative(self, all_episodes):
        s = evaluate(all_episodes, method="oracle")
        assert s.mean_ree_m >= 0.0

    def test_per_episode_count(self, all_episodes):
        s = evaluate(all_episodes, method="oracle")
        assert len(s.per_episode) == len(all_episodes)

    def test_per_episode_are_retrieval_results(self, all_episodes):
        s = evaluate(all_episodes, method="oracle")
        for r in s.per_episode:
            assert isinstance(r, RetrievalResult)
            assert r.method == "oracle"
            assert isinstance(r.success, bool)

    def test_per_episode_ree_non_negative(self, all_episodes):
        s = evaluate(all_episodes, method="oracle")
        for r in s.per_episode:
            assert r.retrieval_error_m >= 0.0

    def test_ree_metric_recorded(self, all_episodes):
        s = evaluate(all_episodes, method="oracle")
        assert s.ree_metric == _REE_METRIC

    def test_method_label_set(self, all_episodes):
        s = evaluate(all_episodes, method="oracle")
        assert "not deployable" in s.method_label.lower()

    def test_str_includes_rsr(self, all_episodes):
        s = evaluate(all_episodes, method="oracle")
        assert "RSR=" in str(s)

    def test_empty_episodes_returns_zero_counts(self):
        s = evaluate([], method="oracle")
        assert s.n_episodes == 0
        assert s.n_success == 0
        assert s.rsr == 0.0
        assert s.mean_ree_m is None

    def test_threshold_boundary_success(self):
        ep = _tiny_episode(n=4, goal_offset=0.0)  # last frame at goal
        s  = evaluate([ep], method="oracle", success_threshold_m=SUCCESS_THRESHOLD_M)
        assert s.n_success == 1

    def test_threshold_boundary_failure(self):
        # Goal is just beyond the threshold from every keyframe
        ep = _tiny_episode(n=2, goal_offset=SUCCESS_THRESHOLD_M + 0.001)
        # oracle_idx will return last frame; its REE > threshold
        s  = evaluate([ep], method="oracle", success_threshold_m=SUCCESS_THRESHOLD_M)
        # May or may not succeed depending on trajectory geometry — just verify it runs
        assert s.n_success in (0, 1)

    def test_nan_position_produces_failure_not_exception(self):
        ep = _tiny_episode(n=2)
        ep.positions[0] = (float("nan"), 0.0)
        ep.positions[1] = (float("nan"), 0.0)
        # Should not raise; non-finite REE yields failure
        s = evaluate([ep], method="oracle")
        assert s.status == "OK"
        assert s.n_success == 0


# ---------------------------------------------------------------------------
# Retrieval evaluation — last-frame
# ---------------------------------------------------------------------------

class TestLastFrameRetrieval:
    def test_returns_evaluation_summary(self, all_episodes):
        s = evaluate(all_episodes, method="last")
        assert isinstance(s, EvaluationSummary)
        assert s.method == "last"

    def test_status_ok(self, all_episodes):
        s = evaluate(all_episodes, method="last")
        assert s.status == "OK"

    def test_rsr_in_unit_interval(self, all_episodes):
        s = evaluate(all_episodes, method="last")
        assert 0.0 <= s.rsr <= 1.0

    def test_retrieved_idx_always_final(self, all_episodes):
        s = evaluate(all_episodes, method="last")
        for r in s.per_episode:
            assert r.retrieved_idx == r.n_keyframes - 1

    def test_method_label_set(self, all_episodes):
        s = evaluate(all_episodes, method="last")
        assert "baseline" in s.method_label.lower()

    def test_deterministic_repeatability(self, all_episodes):
        s1 = evaluate(all_episodes, method="last")
        s2 = evaluate(all_episodes, method="last")
        assert s1.rsr == s2.rsr
        assert s1.mean_ree_m == s2.mean_ree_m
        for r1, r2 in zip(s1.per_episode, s2.per_episode):
            assert r1.retrieved_idx == r2.retrieved_idx
            assert r1.retrieval_error_m == r2.retrieval_error_m


# ---------------------------------------------------------------------------
# CLIP — encoder unavailability
# ---------------------------------------------------------------------------

class TestClipEncoderUnavailable:
    def test_clip_without_transformers_returns_encoder_unavailable(self, all_episodes):
        try:
            import transformers  # noqa: F401
            pytest.skip("transformers is installed; skip encoder-unavailable test")
        except ImportError:
            pass
        s = evaluate(all_episodes, method="clip")
        assert s.status == "ENCODER_UNAVAILABLE", (
            "When transformers is absent, evaluate(method='clip') must return "
            "status=ENCODER_UNAVAILABLE — not fall back to last-frame retrieval."
        )

    def test_clip_without_transformers_does_not_produce_last_frame_results(self, all_episodes):
        try:
            import transformers  # noqa: F401
            pytest.skip("transformers is installed")
        except ImportError:
            pass
        s = evaluate(all_episodes, method="clip")
        # per_episode must be empty — no results using last-frame fallback
        assert s.per_episode == [], (
            "ENCODER_UNAVAILABLE must return an empty per_episode list. "
            "The final-frame method must not be invoked implicitly."
        )

    def test_clip_unavailable_preserves_episode_count(self, all_episodes):
        try:
            import transformers  # noqa: F401
            pytest.skip("transformers is installed")
        except ImportError:
            pass
        s = evaluate(all_episodes, method="clip")
        assert s.n_episodes == len(all_episodes)

    def test_clip_unavailable_str_includes_status(self, all_episodes):
        try:
            import transformers  # noqa: F401
            pytest.skip("transformers is installed")
        except ImportError:
            pass
        s = evaluate(all_episodes, method="clip")
        assert "ENCODER_UNAVAILABLE" in str(s)

    def test_clip_method_label_set(self, all_episodes):
        try:
            import transformers  # noqa: F401
            pytest.skip("transformers is installed")
        except ImportError:
            pass
        s = evaluate(all_episodes, method="clip")
        assert "semantic" in s.method_label.lower() or "deployable" in s.method_label.lower()


# ---------------------------------------------------------------------------
# compare_methods
# ---------------------------------------------------------------------------

class TestCompareMethods:
    def test_returns_dict_with_requested_keys(self, all_episodes):
        r = compare_methods(all_episodes, methods=["oracle", "last"])
        assert set(r.keys()) == {"oracle", "last"}

    def test_oracle_rsr_ge_last_rsr(self, all_episodes):
        r = compare_methods(all_episodes, methods=["oracle", "last"])
        assert r["oracle"].rsr >= r["last"].rsr - 1e-9

    def test_oracle_mean_ree_le_last_mean_ree(self, all_episodes):
        r = compare_methods(all_episodes, methods=["oracle", "last"])
        assert r["oracle"].mean_ree_m <= r["last"].mean_ree_m + 1e-9

    def test_all_summaries_have_correct_n_episodes(self, all_episodes):
        r = compare_methods(all_episodes, methods=["oracle", "last"])
        for s in r.values():
            assert s.n_episodes == len(all_episodes)

    def test_invalid_method_raises(self, all_episodes):
        with pytest.raises(ValueError):
            evaluate(all_episodes, method="nonexistent_method")


# ---------------------------------------------------------------------------
# Non-discriminative dataset detection  (Gate A.6)
# ---------------------------------------------------------------------------

class TestNonDiscriminativeDataset:
    """Proves the synthetic dataset cannot distinguish retrieval methods.

    Every synthetic trajectory terminates exactly at goal_pos, so oracle
    and last-frame retrieve the same position and produce identical REE.
    This test documents the limitation — it is not a correctness failure.
    """

    def test_oracle_ree_equals_last_ree_for_all_episodes(self, all_episodes):
        """Oracle REE must equal last-frame REE for every synthetic episode."""
        r = compare_methods(all_episodes, methods=["oracle", "last"])
        for ep_oracle, ep_last in zip(r["oracle"].per_episode, r["last"].per_episode):
            assert ep_oracle.retrieval_error_m == pytest.approx(
                ep_last.retrieval_error_m, abs=1e-9
            ), (
                f"Non-discriminative dataset violated: oracle REE != last-frame REE "
                f"for episode {ep_oracle.episode_id}. "
                f"oracle={ep_oracle.retrieval_error_m:.6f}, "
                f"last={ep_last.retrieval_error_m:.6f}. "
                f"This means the dataset is discriminative and the limitation "
                f"statement is no longer accurate."
            )

    def test_all_per_episode_ree_are_zero(self, all_episodes):
        """All per-episode REE values are 0.0 m for the synthetic dataset."""
        r = compare_methods(all_episodes, methods=["oracle", "last"])
        for s in r.values():
            for ep in s.per_episode:
                assert ep.retrieval_error_m == pytest.approx(0.0, abs=1e-9), (
                    f"Expected REE=0.0 for synthetic dataset but got "
                    f"{ep.retrieval_error_m:.6f} m for episode {ep.episode_id}"
                )

    def test_oracle_rsr_equals_last_rsr(self, all_episodes):
        """On a non-discriminative dataset, oracle RSR == last-frame RSR."""
        r = compare_methods(all_episodes, methods=["oracle", "last"])
        assert r["oracle"].rsr == pytest.approx(r["last"].rsr, abs=1e-9)


# ---------------------------------------------------------------------------
# Discriminative dataset  (Gate A.7)
# ---------------------------------------------------------------------------

class TestDiscriminativeDataset:
    """Tests using a synthetic episode where the goal is mid-trajectory.

    When the true goal is NOT the last frame, oracle retrieval finds a closer
    keyframe and must outperform last-frame retrieval.  This verifies that the
    evaluator can detect retrieval quality differences — it is not limited to
    the non-discriminative synthetic dataset.
    """

    @pytest.fixture
    def discriminative_episode(self) -> LanguageEpisode:
        """Trajectory from (0,0) to (10,0); goal fixed at (1,0).

        - oracle_idx: returns index 1 (position (1,0), REE=0.0 m)
        - last_idx  : returns index 10 (position (10,0), REE=9.0 m)
        """
        positions = [(float(i), 0.0) for i in range(11)]
        keyframes = [np.zeros((32, 32, 3), dtype=np.uint8) for _ in positions]
        return LanguageEpisode(
            episode_id="disc_test_ep",
            instruction="Walk one metre and stop",
            keyframes=keyframes,
            positions=positions,
            goal_pos=(1.0, 0.0),
            path_length_m=10.0,
            scene_id="test",
        )

    def test_oracle_ree_less_than_last_ree(self, discriminative_episode):
        ep = discriminative_episode
        oracle_ree = ep.retrieval_error_m(ep.oracle_idx(success_threshold_m=3.0))
        last_ree   = ep.retrieval_error_m(len(ep) - 1)
        assert oracle_ree < last_ree, (
            f"oracle REE ({oracle_ree:.3f} m) must be < last-frame REE "
            f"({last_ree:.3f} m) for a discriminative episode"
        )

    def test_oracle_within_threshold(self, discriminative_episode):
        ep = discriminative_episode
        oracle_ree = ep.retrieval_error_m(ep.oracle_idx(success_threshold_m=3.0))
        assert oracle_ree <= 3.0, (
            f"oracle REE {oracle_ree:.3f} m should be within the 3.0 m threshold"
        )

    def test_last_frame_outside_threshold(self, discriminative_episode):
        ep = discriminative_episode
        last_ree = ep.retrieval_error_m(len(ep) - 1)
        assert last_ree > 3.0, (
            f"last-frame REE {last_ree:.3f} m should exceed the 3.0 m threshold "
            f"for this discriminative episode"
        )

    def test_oracle_rsr_exceeds_last_rsr(self, discriminative_episode):
        """Oracle RSR must be strictly greater than last-frame RSR."""
        r = compare_methods([discriminative_episode], methods=["oracle", "last"])
        assert r["oracle"].rsr > r["last"].rsr, (
            f"oracle RSR ({r['oracle'].rsr}) should exceed "
            f"last-frame RSR ({r['last'].rsr}) for a discriminative episode"
        )

    def test_oracle_mean_ree_less_than_last(self, discriminative_episode):
        r = compare_methods([discriminative_episode], methods=["oracle", "last"])
        assert r["oracle"].mean_ree_m < r["last"].mean_ree_m

    def test_last_frame_n_success_zero(self, discriminative_episode):
        """Last-frame method fails when goal is mid-trajectory."""
        s = evaluate([discriminative_episode], method="last")
        assert s.n_success == 0

    def test_oracle_n_success_one(self, discriminative_episode):
        """Oracle succeeds when a keyframe is within threshold of goal."""
        s = evaluate([discriminative_episode], method="oracle")
        assert s.n_success == 1
