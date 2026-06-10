"""
visualnav_runner.py — Publishable VisualNav FleetSafe benchmark runner.

Supports three backends:
  "mock"      — Deterministic 2-D kinematic simulation.
                ⚠ MOCK BACKEND: results are NOT valid for publication.
                Use for pipeline testing and CI only.
  "mujoco"    — MuJoCo 3.x with M3Pro MJCF (publication backend).
  "isaaclab"  — Isaac Lab (GPU-accelerated). NOT YET IMPLEMENTED; gate-failed.

Per-episode output layout::

    {output_dir}/{run_id}/
        metadata.yaml
        episodes/
            episode_{i:04d}/
                episode.json         full episode data
                trajectory.csv       step-by-step x,y,heading
                actions.csv          raw + safe cmd_vel per step
                safety_events.jsonl  one JSON per near-miss / intervention
                metrics.json         episode summary metrics
        aggregate_metrics.json
        aggregate_metrics.csv

Observation contract (identical for all backends and models)::

    obs_imgs   : list[np.ndarray]  # uint8 H×W×3 RGB, len = context_size + 1
    goal_img   : np.ndarray        # uint8 H×W×3 RGB
    depth      : np.ndarray | None # float32 H×W meters (optional)
    lidar      : np.ndarray | None # float32 (N_beams,) meters (optional)

Action contract::

    raw_cmd_vel  : CmdVel(vx, vy, wz)   from adapter
    safe_cmd_vel : CmdVel(vx, vy, wz)   after FleetSafe CBF-QP
    mecanum_fl/fr/rl/rr               derived by IK (M3Pro only)
"""
from __future__ import annotations

import collections
import csv
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

try:
    from fleet_safe_vla.explainability.scene_graph import SceneGraphBuilder
    from fleet_safe_vla.explainability.causal_reasoner import CausalReasoner
    from fleet_safe_vla.explainability.counterfactuals import CounterfactualGenerator
    from fleet_safe_vla.explainability.explanation_generator import ExplanationGenerator
    from fleet_safe_vla.explainability.event_recorder import (
        EventRecorder,
        ExplainabilityStepRecord,
    )
    _EXPLAINABILITY_AVAILABLE = True
except ImportError:
    _EXPLAINABILITY_AVAILABLE = False

try:
    from fleet_safe_vla.social_awareness import (
        SocialRiskFilter,
        Detection,
        AgentType,
        SafetyZone,
        get_profile,
    )
    _SOCIAL_AVAILABLE = True
except ImportError:
    _SOCIAL_AVAILABLE = False

try:
    from fleet_safe_vla.social_awareness.dynamic_agent_tracker import DynamicAgentTracker
    from fleet_safe_vla.perception.mock_source import MockPerceptionSource
    from fleet_safe_vla.perception.perception_pipeline import (
        PerceptionConfig,
        PerceptionPipeline,
    )
    _PERCEPTION_AVAILABLE = True
except ImportError:
    _PERCEPTION_AVAILABLE = False

from fleet_safe_vla.benchmark_version import (
    version_block,
    GIT_COMMIT,
    PROTOCOL_FILE,
    SCENE_MANIFEST_FILE,
    METRIC_SPEC_FILE,
)

from fleet_safe_vla.benchmarks.visualnav_metrics import (
    EpisodeMetrics,
    aggregate_episodes,
    aggregate_by_scene,
    build_comparison_table,
    compute_delta_l2_mean,
    compute_intervention_rate,
    compute_latency_stats,
    compute_near_violation_count,
    compute_spl,
    compute_stuck_rate,
    write_aggregate_json,
    write_episodes_csv,
)
from fleet_safe_vla.benchmarks.visualnav_scenarios import (
    ObstacleSpec,
    SceneSpec,
    StartGoalPair,
)
from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
    BaseVisualNavAdapter,
    CmdVel,
)
from fleet_safe_vla.integrations.visualnav_transformer.fleetsafe_wrapper import (
    FleetSafeWrapper,
)


# ── Backend constants ─────────────────────────────────────────────────────────

BACKEND_MOCK      = "mock"
BACKEND_MUJOCO    = "mujoco"
BACKEND_ISAACLAB  = "isaaclab"

PERCEPTION_NONE   = "none"
PERCEPTION_MOCK   = "mock"
PERCEPTION_YOLO   = "yolo"


# ── Perception layer ───────────────────────────────────────────────────────────

class _PerceptionLayer:
    """
    Wraps the perception source + DynamicAgentTracker into a single per-episode
    object so each backend's step loop has a uniform call:

        dets, perc_ms, depth_ms = layer.step(rgb, depth, robot_xy, t)
        tracked = layer.update_tracker(dets, t)

    Metrics are accumulated internally; call layer.episode_summary() at end.
    """

    def __init__(self, mode: str, scene_name: str, seed: int = 0) -> None:
        self.mode = mode
        self._tracker: "DynamicAgentTracker | None" = None
        self._mock_src: "MockPerceptionSource | None" = None
        self._pipeline: "PerceptionPipeline | None" = None
        self._last_tracked: list = []

        if not _PERCEPTION_AVAILABLE or mode == PERCEPTION_NONE:
            return

        self._tracker = DynamicAgentTracker()

        if mode == PERCEPTION_MOCK:
            scenario = _SCENE_TO_MOCK_SCENARIO.get(scene_name, "hospital_corridor")
            self._mock_src = MockPerceptionSource(scenario=scenario, seed=seed)

        elif mode == PERCEPTION_YOLO:
            cfg = PerceptionConfig(model_path="yolov8n.pt")
            self._pipeline = PerceptionPipeline.from_config(cfg)

        # Accumulators
        self._det_count: int = 0
        self._max_tracks: int = 0
        self._perc_latencies: list[float] = []
        self._depth_latencies: list[float] = []
        self._role_counts: dict[str, int] = {}
        self._last_tracked: list = []   # cached from last tracker.update() call

    def step(
        self,
        rgb_frame: Any,
        depth_image: Any,
        robot_xy: tuple[float, float],
        timestamp: float,
    ) -> list[Detection]:
        """Run perception for one step; returns Detection list for tracker."""
        if self._tracker is None:
            return []

        t0 = time.perf_counter()

        if self._mock_src is not None:
            dets = self._mock_src.step(robot_xy=robot_xy, timestamp=timestamp)
            perc_ms = (time.perf_counter() - t0) * 1000.0
            depth_ms = 0.0

        elif self._pipeline is not None:
            t1 = time.perf_counter()
            dets = self._pipeline.process(rgb_frame, depth_image, robot_xy, timestamp)
            perc_ms = (time.perf_counter() - t0) * 1000.0
            # DepthFusion time is internal; estimate as difference if depth was provided
            depth_ms = (time.perf_counter() - t1) * 1000.0 if depth_image is not None else 0.0

        else:
            return []

        # Update accumulators
        self._det_count += len(dets)
        self._perc_latencies.append(perc_ms)
        if depth_ms > 0:
            self._depth_latencies.append(depth_ms)
        for d in dets:
            r = d.semantic_role
            self._role_counts[r] = self._role_counts.get(r, 0) + 1

        # Update tracker; cache result for tracked_detections()
        tracked = self._tracker.update(dets, timestamp=timestamp)
        self._last_tracked = tracked
        if len(tracked) > self._max_tracks:
            self._max_tracks = len(tracked)

        return dets

    def tracked_detections(
        self,
        robot_xy: tuple[float, float],
        timestamp: float,
    ) -> list[Detection]:
        """
        Return the tracker's current agents as Detection objects.
        Uses the cached result of the last step() call — no double-update.
        """
        return [
            Detection(
                position_xy=a.position_xy,
                agent_type=a.agent_type,
                timestamp=timestamp,
                confidence=a.confidence,
                semantic_role=a.semantic_role,
            )
            for a in self._last_tracked
        ]

    def episode_summary(self) -> dict:
        if self._tracker is None:
            return {"perception_source": self.mode}
        from fleet_safe_vla.benchmarks.visualnav_metrics import compute_latency_stats
        p_mean, p_p95 = compute_latency_stats(self._perc_latencies)
        d_mean, _ = compute_latency_stats(self._depth_latencies)
        return {
            "perception_source":           self.mode,
            "detection_count_total":       self._det_count,
            "tracked_agent_count_max":     self._max_tracks,
            "perception_latency_ms_mean":  p_mean,
            "perception_latency_ms_p95":   p_p95,
            "depth_fusion_latency_ms_mean": d_mean,
            "semantic_role_counts":        dict(self._role_counts),
        }


# Map scene names to MockPerceptionSource scenarios
_SCENE_TO_MOCK_SCENARIO: dict[str, str] = {
    "hospital_corridor":       "hospital_corridor",
    "hospital_icu_approach":   "hospital_corridor",
    "hospital_elevator_lobby": "waiting_room",
    "crowded_corridor":        "hospital_corridor",
    "crossing_pedestrian":     "hospital_corridor",
    "blind_corner":            "hospital_corridor",
    "doorway_bottleneck":      "waiting_room",
}


# ── Mock backend ──────────────────────────────────────────────────────────────

class _MockSimState:
    """
    Minimal 2-D holonomic kinematics for the mock backend.

    ⚠ This is NOT a physics simulation.  It is a deterministic placeholder
    that lets the benchmark pipeline run end-to-end without MuJoCo or Isaac.
    Resulting metrics (success rate, SPL, collision rate) reflect random-walk
    behaviour of the navigation model on noise images and are MEANINGLESS as
    navigation quality indicators.
    """

    def __init__(
        self,
        start_xy:   tuple[float, float],
        goal_xy:    tuple[float, float],
        obstacles:  Sequence[ObstacleSpec],
        dynamic_specs: Sequence[Any],
        seed:       int,
        control_hz: float,
    ) -> None:
        self.pos        = np.array(start_xy, dtype=np.float64)
        self.goal       = np.array(goal_xy,  dtype=np.float64)
        self.heading    = 0.0
        self.obstacles  = obstacles
        self.dyn_specs  = dynamic_specs
        self.dt         = 1.0 / control_hz
        self.t          = 0.0
        self.rng        = np.random.default_rng(seed)

    def step(self, cmd: CmdVel) -> dict:
        """Apply cmd_vel, return step info."""
        cos_h = np.cos(self.heading)
        sin_h = np.sin(self.heading)
        dx = (cmd.vx * cos_h - cmd.vy * sin_h) * self.dt
        dy = (cmd.vx * sin_h + cmd.vy * cos_h) * self.dt
        self.pos     = self.pos + np.array([dx, dy])
        self.heading = self.heading + cmd.wz * self.dt
        self.t      += self.dt

        # Obstacle distances
        min_dist = float("inf")
        for obs in self.obstacles:
            d = float(np.linalg.norm(self.pos - np.array([obs.x, obs.y]))) - obs.radius_m
            if d < min_dist:
                min_dist = d
        for dyn in self.dyn_specs:
            dpos = np.array(dyn.position_at(self.t))
            d    = float(np.linalg.norm(self.pos - dpos)) - dyn.obstacle_radius_m
            if d < min_dist:
                min_dist = d

        goal_dist = float(np.linalg.norm(self.pos - self.goal))
        return {
            "robot_xy":    tuple(self.pos.tolist()),
            "min_dist_m":  min_dist,
            "goal_dist_m": goal_dist,
            "collision":   min_dist < 0.10,
            "success":     goal_dist < 0.20,
        }

    def random_obs_img(self, w: int, h: int) -> np.ndarray:
        """Deterministic random RGB frame (seeded per step, not per episode)."""
        return self.rng.integers(0, 256, (h, w, 3), dtype=np.uint8)


# ── Per-step record ───────────────────────────────────────────────────────────

@dataclass
class _StepRecord:
    step:       int
    x:          float
    y:          float
    heading:    float
    raw_vx:     float
    raw_vy:     float
    raw_wz:     float
    safe_vx:    float
    safe_vy:    float
    safe_wz:    float
    delta_l2:   float
    intervened: bool
    min_dist_m: float
    latency_ms: float
    # Social-risk fields (populated when social awareness is active)
    zone:               str   = "GREEN"
    crowding_score:     float = 0.0
    occlusion_risk:     float = 0.0
    rare_event_count:   int   = 0
    zone_reasons:       str   = ""   # comma-separated reasons
    environment_profile: str  = "default"


# ── Main runner ───────────────────────────────────────────────────────────────

class VisualNavBenchmarkRunner:
    """
    Publishable benchmark runner for GNM / ViNT / NoMaD + FleetSafe.

    Parameters
    ----------
    adapter       : Loaded BaseVisualNavAdapter.
    fleetsafe     : If True, wrap the adapter with FleetSafeWrapper.
    backend       : "mock" | "mujoco" | "isaaclab".
    output_dir    : Root directory for per-episode JSON / CSV logs.
    control_hz    : Nominal control frequency.
    v_max         : Forward velocity limit (m/s).
    vy_max        : Lateral velocity limit (m/s); >0 for M3Pro holonomic.
    w_max         : Angular rate limit (rad/s).
    near_miss_m   : Distance threshold for near-violation events (m).
    collision_m   : Distance threshold for collision detection (m).
    stuck_thresh  : Speed below which robot is considered stuck (m/s).
    stuck_steps   : Consecutive stuck steps to register a stuck event.
    max_steps     : Maximum episode length.
    """

    _MOCK_WARNING = (
        "\n*** MOCK BACKEND: results from this run are NOT valid for publication. ***\n"
        "    Use --backend mujoco or --backend isaaclab for publication-quality evaluation.\n"
    )

    _ISAACLAB_ENTRY_POINT = (
        "\n*** ISAAC BACKEND: must be launched via the AppLauncher entry point. ***\n"
        "    conda activate isaac\n"
        "    python scripts/visualnav/run_visualnav_benchmark_isaac.py --model <gnm|vint|nomad>\n"
        "    (Calling from a plain Python process will raise IsaacNotAvailableError at episode time.)\n"
    )

    def __init__(
        self,
        adapter:       BaseVisualNavAdapter,
        fleetsafe:     bool  = False,
        backend:       str   = BACKEND_MOCK,
        output_dir:    Path  = Path("benchmarks/visualnav/results"),
        control_hz:    float = 4.0,
        v_max:         float = 0.3,
        vy_max:        float = 0.3,
        w_max:         float = 0.7,
        near_miss_m:   float = 0.45,
        collision_m:   float = 0.10,
        stuck_thresh:  float = 0.02,
        stuck_steps:   int   = 10,
        max_steps:     int   = 500,
        social_profile: str  = "default",
        perception:    str   = PERCEPTION_NONE,
        cmd_delay_ms:  int   = 0,
    ) -> None:
        if backend not in (BACKEND_MOCK, BACKEND_MUJOCO, BACKEND_ISAACLAB):
            raise ValueError(f"Unknown backend: {backend!r}")
        if perception not in (PERCEPTION_NONE, PERCEPTION_MOCK, PERCEPTION_YOLO):
            raise ValueError(
                f"Unknown perception mode {perception!r}. "
                f"Use 'none', 'mock', or 'yolo'."
            )

        self.adapter      = adapter
        self.fleetsafe    = fleetsafe
        self.backend      = backend
        self.output_dir   = Path(output_dir)
        self.control_hz   = control_hz
        self.v_max        = v_max
        self.vy_max       = vy_max
        self.w_max        = w_max
        self.near_miss_m  = near_miss_m
        self.collision_m  = collision_m
        self.stuck_thresh   = stuck_thresh
        self.stuck_steps    = stuck_steps
        self.max_steps      = max_steps
        self.social_profile = social_profile
        self.perception     = perception
        self.cmd_delay_ms   = max(0, int(cmd_delay_ms))

        self._wrapper: FleetSafeWrapper | None = None
        if fleetsafe:
            self._wrapper = FleetSafeWrapper(
                adapter,
                v_max      = v_max,
                vy_max     = vy_max,
                w_max      = w_max,
                control_hz = control_hz,
            )

        if backend == BACKEND_MOCK:
            print(self._MOCK_WARNING)
        if backend == BACKEND_ISAACLAB:
            print(self._ISAACLAB_ENTRY_POINT)

    # ── Cmd-delay helpers ─────────────────────────────────────────────────────

    def _make_cmd_queue(self) -> collections.deque:
        """Return a deque pre-filled with zero commands for the configured delay."""
        delay_steps = round(self.cmd_delay_ms * self.control_hz / 1000.0)
        return collections.deque(
            [CmdVel(0.0, 0.0, 0.0)] * delay_steps,
            maxlen=max(delay_steps, 1),
        )

    def _delay_cmd(self, q: collections.deque, cmd: "CmdVel") -> "CmdVel":
        """Push cmd; return the oldest cmd (i.e. cmd from delay_steps ago)."""
        if q.maxlen == 1:
            return cmd          # zero delay: pass through immediately
        oldest = q[0]
        q.append(cmd)
        return oldest

    # ── Social-risk helpers ────────────────────────────────────────────────────

    def _make_social_filter(self, scene_name: str):  # -> SocialRiskFilter | None
        """Return a SocialRiskFilter for this scene, or None if unavailable."""
        if not _SOCIAL_AVAILABLE:
            return None
        # Social-awareness scenes have dedicated environment profiles; fall back to
        # the runner's configured profile for all other scenes.
        _SCENE_PROFILES = {
            "crowded_corridor":         "hospital",
            "crossing_pedestrian":      "hospital",
            "blind_corner":             "hospital",
            "doorway_bottleneck":       "hospital",
            "multi_robot_corridor":     "warehouse",
            "occluded_obstacle_reveal": "hospital",
            "social_red_zone_smoke":    "hospital",
            # Hospital semantic scenes
            "hospital_corridor":        "emergency_corridor",
            "hospital_icu_approach":    "emergency_corridor",
            "hospital_elevator_lobby":  "waiting_room",
        }
        profile_name = _SCENE_PROFILES.get(scene_name, self.social_profile)
        try:
            profile = get_profile(profile_name)
        except ValueError:
            profile = get_profile("default")
        zone_map = self._zone_map_for_scene(scene_name)
        return SocialRiskFilter(profile=profile, zone_map=zone_map)

    @staticmethod
    def _zone_map_for_scene(scene_name: str):  # -> ZoneMap | None
        """Return a ZoneMap for scenes that have per-zone profile switching."""
        if not _SOCIAL_AVAILABLE:
            return None
        try:
            from fleet_safe_vla.benchmarks.hospital_scenes import HOSPITAL_ZONE_MAPS
            return HOSPITAL_ZONE_MAPS.get(scene_name)
        except ImportError:
            return None

    @staticmethod
    def _social_detections_from_scene(scene, t: float):
        """Build Detection list from scene's dynamic agents at time t."""
        if not _SOCIAL_AVAILABLE:
            return []
        detections = []
        for dyn in scene.dynamic_agents:
            pos = dyn.position_at(t)
            atype_str = getattr(dyn, "agent_type", "unknown")
            try:
                atype = AgentType(atype_str)
            except ValueError:
                atype = AgentType.UNKNOWN
            detections.append(Detection(
                position_xy=pos,
                agent_type=atype,
                timestamp=t,
                confidence=1.0,
                semantic_role=getattr(dyn, "semantic_role", "unknown"),
            ))
        return detections

    def _make_perception_layer(self, scene_name: str, seed: int) -> "_PerceptionLayer":
        return _PerceptionLayer(mode=self.perception, scene_name=scene_name, seed=seed)

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(
        self,
        scenes:    Sequence[SceneSpec],
        seeds:     Sequence[int],
        run_id:    str | None = None,
    ) -> list[EpisodeMetrics]:
        """
        Run all (scene × seed × start_goal) combinations.

        Returns a list of EpisodeMetrics, one per episode.
        Also writes per-episode files and aggregate summaries under output_dir.
        """
        if run_id is None:
            run_id = (
                f"{self.adapter.model_name}"
                f"{'_fleetsafe' if self.fleetsafe else '_baseline'}"
                f"_{self.backend}"
                f"_{int(time.time())}"
            )

        run_dir = self.output_dir / run_id
        ep_dir  = run_dir / "episodes"
        ep_dir.mkdir(parents=True, exist_ok=True)

        self._write_metadata(run_dir, run_id, scenes, seeds)

        total = sum(len(sc.start_goal_pairs) for sc in scenes) * len(seeds)
        all_metrics: list[EpisodeMetrics] = []
        ep_idx = 0

        for scene in scenes:
            for seed in seeds:
                for sg in scene.start_goal_pairs:
                    ep_idx += 1
                    print(
                        f"[{ep_idx}/{total}] scene={scene.name}  seed={seed}  "
                        f"{sg.label}  fleetsafe={self.fleetsafe}  backend={self.backend}"
                    )
                    metrics = self._run_episode(scene, seed, sg, ep_dir, ep_idx)
                    all_metrics.append(metrics)
                    self._print_summary(metrics)

        # Aggregate
        agg_overall = aggregate_episodes(all_metrics)
        agg_by_scene = aggregate_by_scene(all_metrics)

        # Infer scene name: if run contains exactly one scene use its name,
        # otherwise leave blank (multi-scene runs aggregate across scenes).
        _scene_name = scenes[0].name if len(scenes) == 1 else ""

        extra = {
            "run_id":    run_id,
            "model":     self.adapter.model_name,
            "scene":     _scene_name,
            "fleetsafe": self.fleetsafe,
            "backend":   self.backend,
            **version_block(),
            "git_commit":         GIT_COMMIT,
            "protocol_file":      PROTOCOL_FILE,
            "scene_manifest_file": SCENE_MANIFEST_FILE,
            "metric_spec_file":   METRIC_SPEC_FILE,
            "claim_scope":        (
                "engineering_only_not_publication_evidence"
                if self.backend == BACKEND_MOCK
                else f"simulation_{self.backend}"
            ),
        }
        write_aggregate_json(agg_overall, run_dir / "aggregate_metrics.json", extra)
        write_episodes_csv(all_metrics, run_dir / "aggregate_metrics.csv")
        (run_dir / "aggregate_by_scene.json").write_text(
            json.dumps({"extra": extra, "by_scene": agg_by_scene}, indent=2)
        )

        print(f"\n[runner] Run complete → {run_dir}")
        print(f"  episodes        : {len(all_metrics)}")
        print(f"  success_rate    : {agg_overall.get('success_rate', 0):.3f}")
        print(f"  spl_mean        : {agg_overall.get('spl_mean', 0):.3f}")
        print(f"  collision_rate  : {agg_overall.get('collision_rate', 0):.3f}")
        if self.fleetsafe:
            print(f"  interv_rate     : {agg_overall.get('intervention_rate_mean', 0):.3f}")

        return all_metrics

    # ── Episode execution ──────────────────────────────────────────────────────

    def _run_episode(
        self,
        scene:   SceneSpec,
        seed:    int,
        sg:      StartGoalPair,
        ep_dir:  Path,
        ep_idx:  int,
    ) -> EpisodeMetrics:
        if self.backend == BACKEND_MOCK:
            return self._run_mock_episode(scene, seed, sg, ep_dir, ep_idx)
        if self.backend == BACKEND_MUJOCO:
            return self._run_mujoco_episode(scene, seed, sg, ep_dir, ep_idx)
        if self.backend == BACKEND_ISAACLAB:
            return self._run_isaaclab_episode(scene, seed, sg, ep_dir, ep_idx)
        raise ValueError(f"Unknown backend: {self.backend!r}")

    # ── Mock backend ───────────────────────────────────────────────────────────

    def _run_mock_episode(
        self,
        scene:   SceneSpec,
        seed:    int,
        sg:      StartGoalPair,
        ep_dir:  Path,
        ep_idx:  int,
    ) -> EpisodeMetrics:
        img_w, img_h = getattr(self.adapter, "image_size", (85, 64))
        ctx_size     = getattr(self.adapter, "context_size", 5)
        n_frames     = ctx_size + 1

        sim = _MockSimState(
            start_xy    = sg.start_xy,
            goal_xy     = sg.goal_xy,
            obstacles   = scene.obstacles,
            dynamic_specs = scene.dynamic_agents,
            seed        = seed,
            control_hz  = self.control_hz,
        )
        if self._wrapper:
            self._wrapper.reset_stats()

        social_filter   = self._make_social_filter(scene.name)
        perc_layer      = self._make_perception_layer(scene.name, seed)

        # Pre-fill context buffer with the first frame
        obs_buf: list[np.ndarray] = [sim.random_obs_img(img_w, img_h)]
        goal_img = sim.random_obs_img(img_w, img_h)

        step_records:    list[_StepRecord] = []
        safety_events:   list[dict]        = []
        latencies_ms:    list[float]       = []
        raw_cmds:        list[tuple]       = []
        safe_cmds_list:  list[tuple]       = []
        distances:       list[float]       = []

        # Social-risk accumulators
        crowding_scores:  list[float] = []
        occlusion_risks:  list[float] = []
        steps_green = steps_amber = steps_red = 0
        total_rare_events = 0
        social_margin_violations = 0
        min_human_dist = float("inf")

        path_length_m = 0.0
        stuck_streak  = 0
        stuck_count   = 0
        prev_pos      = np.array(sg.start_xy, dtype=np.float64)
        prev_cmd      = CmdVel(0.0, 0.0, 0.0)
        smoothness_acc = 0.0
        collision      = False
        success        = False
        step_done      = 0
        _cmd_q        = self._make_cmd_queue()

        for step in range(self.max_steps):
            t0 = time.perf_counter()

            # Fill context buffer
            obs_buf.append(sim.random_obs_img(img_w, img_h))
            if len(obs_buf) > n_frames:
                obs_buf = obs_buf[-n_frames:]
            obs_imgs = list(obs_buf)

            preprocessed = self.adapter.preprocess_observation(obs_imgs, goal_img)

            # Obstacle positions in robot frame (for CBF)
            obs_positions_world = [
                np.array([o.x, o.y]) for o in scene.obstacles
            ] + [
                np.array(d.position_at(sim.t)) for d in scene.dynamic_agents
            ]
            obs_positions_robot = [p - sim.pos for p in obs_positions_world]

            if self._wrapper:
                obs_vec  = np.zeros(47, dtype=np.float32)
                step_res = self._wrapper.step(preprocessed, obs_vec, obs_positions_robot)
                cmd     = step_res.safe_cmd_vel
                raw_cmd = step_res.raw_cmd_vel
                intervened = step_res.intervened
                min_d = step_res.min_dist_m
            else:
                action  = self.adapter.predict_action(preprocessed)
                cmd     = self.adapter.action_to_cmd_vel(
                    action,
                    v_max      = self.v_max,
                    vy_max     = self.vy_max,
                    w_max      = self.w_max,
                    control_hz = self.control_hz,
                )
                raw_cmd    = cmd
                intervened = False
                min_d_candidates = [
                    float(np.linalg.norm(p)) - obs.radius_m
                    for p, obs in zip(obs_positions_robot, scene.obstacles)
                ]
                min_d = min(min_d_candidates) if min_d_candidates else float("inf")

            latency_ms = (time.perf_counter() - t0) * 1000.0

            # Apply to mock sim (with optional cmd delay)
            info = sim.step(self._delay_cmd(_cmd_q, cmd))

            # Perception → tracker → social filter
            _robot_xy_t = tuple(float(v) for v in sim.pos)
            perc_layer.step(
                rgb_frame=obs_imgs[-1] if obs_imgs else None,
                depth_image=None,
                robot_xy=_robot_xy_t,
                timestamp=sim.t,
            )

            # Social-risk computation (geometry-based; no learned model)
            zone_str = "GREEN"
            zone_reasons_str = ""
            step_crowding = 0.0
            step_occlusion = 0.0
            step_rare = 0
            if social_filter is not None:
                if perc_layer.mode != PERCEPTION_NONE:
                    _dets = perc_layer.tracked_detections(_robot_xy_t, sim.t)
                else:
                    _dets = self._social_detections_from_scene(scene, sim.t)
                _obs_xys = [(obs.x, obs.y) for obs in scene.obstacles]
                _obs_radii = [obs.radius_m for obs in scene.obstacles]
                _social_out = social_filter.compute(
                    timestamp=sim.t,
                    robot_xy=_robot_xy_t,
                    robot_speed_ms=float(np.hypot(cmd.vx, cmd.vy)),
                    robot_yaw=float(sim.heading),
                    detections=_dets,
                    obstacle_positions=_obs_xys,
                    obstacle_radii=_obs_radii if _obs_radii else None,
                    path_blocked=info.get("collision", False),
                )
                zone_str = _social_out.zone.value
                zone_reasons_str = ", ".join(_social_out.reasons)
                step_crowding = _social_out.state.crowding_score
                step_occlusion = _social_out.state.occlusion_risk
                step_rare = len(_social_out.rare_events)
                total_rare_events += step_rare
                if _social_out.state.min_human_dist_m < min_human_dist:
                    min_human_dist = _social_out.state.min_human_dist_m
                if _social_out.state.zone_result.agents_in_radius > 0:
                    social_margin_violations += sum(
                        1 for d in [_social_out.state.min_human_dist_m]
                        if d < (social_filter._profile.human_margin_m
                                if hasattr(social_filter, "_profile") else 0.6)
                    )
                if zone_str == "GREEN":
                    steps_green += 1
                elif zone_str == "AMBER":
                    steps_amber += 1
                else:
                    steps_red += 1
                crowding_scores.append(step_crowding)
                occlusion_risks.append(step_occlusion)

            # Metrics accumulation
            curr_pos  = np.array(info["robot_xy"])
            step_dist = float(np.linalg.norm(curr_pos - prev_pos))
            path_length_m += step_dist

            speed = float(np.hypot(cmd.vx, cmd.vy))
            if speed < self.stuck_thresh:
                stuck_streak += 1
                if stuck_streak >= self.stuck_steps:
                    stuck_count  += 1
                    stuck_streak  = 0
            else:
                stuck_streak = 0

            cmd_arr      = np.array([cmd.vx, cmd.vy, cmd.wz])
            prev_cmd_arr = np.array([prev_cmd.vx, prev_cmd.vy, prev_cmd.wz])
            smoothness_acc += float(np.linalg.norm(cmd_arr - prev_cmd_arr))

            raw_cmds.append((raw_cmd.vx, raw_cmd.vy, raw_cmd.wz))
            safe_cmds_list.append((cmd.vx, cmd.vy, cmd.wz))
            latencies_ms.append(latency_ms)
            distances.append(info["min_dist_m"])

            delta_l2 = float(np.linalg.norm(cmd_arr - np.array([raw_cmd.vx, raw_cmd.vy, raw_cmd.wz])))

            rec = _StepRecord(
                step       = step,
                x          = float(curr_pos[0]),
                y          = float(curr_pos[1]),
                heading    = float(sim.heading),
                raw_vx     = raw_cmd.vx,
                raw_vy     = raw_cmd.vy,
                raw_wz     = raw_cmd.wz,
                safe_vx    = cmd.vx,
                safe_vy    = cmd.vy,
                safe_wz    = cmd.wz,
                delta_l2   = delta_l2,
                intervened = intervened,
                min_dist_m = info["min_dist_m"],
                latency_ms = latency_ms,
                zone             = zone_str,
                crowding_score   = step_crowding,
                occlusion_risk   = step_occlusion,
                rare_event_count = step_rare,
                zone_reasons     = zone_reasons_str,
            )
            step_records.append(rec)

            if (info["min_dist_m"] < self.near_miss_m) or intervened or zone_str == "RED":
                safety_events.append({
                    "step":                 step,
                    "type":                 "intervention" if intervened else (
                                            "social_red_zone" if zone_str == "RED"
                                            else "near_miss"),
                    "min_dist_m":           info["min_dist_m"],
                    "raw_vx":               raw_cmd.vx,
                    "raw_wz":               raw_cmd.wz,
                    "safe_vx":              cmd.vx,
                    "safe_wz":              cmd.wz,
                    "active_safety_zone":   zone_str,
                    "safety_zone_reasons":  zone_reasons_str,
                    "crowding_risk_score":  step_crowding,
                    "occlusion_risk_score": step_occlusion,
                    "rare_event_count":     step_rare,
                })

            prev_pos = curr_pos
            prev_cmd = cmd
            step_done += 1

            if info["collision"]:
                collision = True
                break
            if info["success"]:
                success = True
                break

        # Compute all metrics
        n_steps              = max(1, step_done)
        smoothness           = smoothness_acc / n_steps
        lat_mean, lat_p95    = compute_latency_stats(latencies_ms)
        intervention_count   = (
            self._wrapper._intervention_steps if self._wrapper else 0
        )
        near_viol = compute_near_violation_count(distances, self.near_miss_m)
        spl_val  = compute_spl(success, path_length_m, sg.optimal_path_m)
        delta_l2_mean = compute_delta_l2_mean(raw_cmds, safe_cmds_list)

        metrics = EpisodeMetrics(
            model_name    = self.adapter.model_name,
            fleetsafe     = self.fleetsafe,
            backend       = self.backend,
            scene         = scene.name,
            seed          = seed,
            start_xy      = sg.start_xy,
            goal_xy       = sg.goal_xy,
            success       = success,
            episode_length_steps = step_done,
            path_length_m = path_length_m,
            optimal_path_m = sg.optimal_path_m,
            time_to_goal_s = step_done / self.control_hz,
            spl            = spl_val,
            collision_count = int(collision),
            near_violation_count = near_viol,
            min_obstacle_distance_m = float(min(distances)) if distances else float("inf"),
            intervention_count = intervention_count,
            intervention_rate  = compute_intervention_rate(intervention_count, step_done),
            raw_vs_safe_action_delta_l2_mean = delta_l2_mean,
            stuck_rate      = compute_stuck_rate(step_done, stuck_count),
            smoothness      = smoothness,
            recovery_success = False,
            inference_latency_ms_mean = lat_mean,
            inference_latency_ms_p95  = lat_p95,
            sim_fps         = 1000.0 / max(1e-6, lat_mean),
            # Social-risk layer
            crowding_risk_score_mean  = float(np.mean(crowding_scores)) if crowding_scores else 0.0,
            crowding_risk_score_max   = float(max(crowding_scores))      if crowding_scores else 0.0,
            occlusion_risk_score_mean = float(np.mean(occlusion_risks))  if occlusion_risks else 0.0,
            occlusion_risk_score_max  = float(max(occlusion_risks))      if occlusion_risks else 0.0,
            social_margin_violation_count = social_margin_violations,
            rare_event_count          = total_rare_events,
            min_human_distance_m      = min_human_dist,
            steps_green               = steps_green,
            steps_amber               = steps_amber,
            steps_red                 = steps_red,
            **perc_layer.episode_summary(),
        )

        # Write per-episode files
        self._write_episode_files(ep_dir, ep_idx, metrics, step_records, safety_events)
        self._write_explainability_files(ep_dir, ep_idx, step_records, scene, sg, seed)
        return metrics

    # ── MuJoCo backend ─────────────────────────────────────────────────────────

    def _run_mujoco_episode(
        self,
        scene:   SceneSpec,
        seed:    int,
        sg:      StartGoalPair,
        ep_dir:  Path,
        ep_idx:  int,
    ) -> EpisodeMetrics:
        """
        MuJoCo backend: delegates to the existing BenchmarkRunner infrastructure.

        Requires:
          fleet_safe_vla.envs.mujoco.yahboom.nav_env.YahboomNavEnv
          fleet_safe_vla.envs.mujoco.yahboom.obstacle_env.YahboomObstacleEnv
        """
        try:
            from fleet_safe_vla.envs.mujoco.yahboom.nav_env import YahboomNavEnv
            from fleet_safe_vla.envs.mujoco.yahboom.obstacle_env import YahboomObstacleEnv
            from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
                IsaacCameraObsAdapter,
            )
        except ImportError as exc:
            raise RuntimeError(
                f"MuJoCo backend unavailable: {exc}\n"
                "Use --backend mock for pipeline testing."
            ) from exc

        img_w, img_h = getattr(self.adapter, "image_size", (85, 64))
        ctx_size     = getattr(self.adapter, "context_size", 5)

        n_obs = len(scene.obstacles)
        scene_obs_world = [np.array([obs.x, obs.y]) for obs in scene.obstacles]
        if n_obs == 0:
            env = YahboomNavEnv(
                max_episode_steps = self.max_steps,
                control_hz        = self.control_hz,
                seed              = seed,
            )
        else:
            env = YahboomObstacleEnv(
                n_obstacles       = n_obs,
                fixed_positions   = [(obs.x, obs.y) for obs in scene.obstacles],
                max_episode_steps = self.max_steps,
                control_hz        = self.control_hz,
                seed              = seed,
            )

        env.reset(seed=seed)
        env.teleport_to(sg.start_xy[0], sg.start_xy[1])
        obs_adapter = IsaacCameraObsAdapter(
            image_size   = (img_w, img_h),
            context_size = ctx_size,
        )
        obs_adapter.set_goal_image(
            IsaacCameraObsAdapter.make_checkerboard_goal(img_w, img_h)
        )
        if self._wrapper:
            self._wrapper.reset_stats()

        social_filter = self._make_social_filter(scene.name)
        perc_layer    = self._make_perception_layer(scene.name, seed)
        crowding_scores:  list[float] = []
        occlusion_risks:  list[float] = []
        steps_green = 0
        steps_amber = 0
        steps_red   = 0
        min_human_dist        = float("inf")
        social_margin_violations = 0
        total_rare_events     = 0
        social_profile_name   = (
            social_filter._profile.name if social_filter is not None else "default"
        )

        step_records:   list[_StepRecord] = []
        safety_events:  list[dict]        = []
        latencies_ms:   list[float]       = []
        raw_cmds:       list[tuple]       = []
        safe_cmds_list: list[tuple]       = []
        distances:      list[float]       = []

        path_length_m  = 0.0
        stuck_streak   = 0
        stuck_count    = 0
        prev_pos       = np.array(sg.start_xy, dtype=np.float64)
        prev_cmd       = CmdVel(0.0, 0.0, 0.0)
        smoothness_acc = 0.0
        collision      = False
        success        = False
        step_done      = 0
        _cmd_q         = self._make_cmd_queue()

        for step in range(self.max_steps):
            t0 = time.perf_counter()

            obs_adapter.push_frame(
                IsaacCameraObsAdapter.make_random_obs(img_w, img_h, seed=seed + step)
            )
            obs_imgs, goal_img = obs_adapter.get_context()
            preprocessed = self.adapter.preprocess_observation(obs_imgs, goal_img)

            if self._wrapper:
                obs_vec  = getattr(env, "_last_obs", np.zeros(47, dtype=np.float32))
                step_res = self._wrapper.step(preprocessed, obs_vec, scene_obs_world)
                cmd      = step_res.safe_cmd_vel
                raw_cmd  = step_res.raw_cmd_vel
                intervened = step_res.intervened
                min_d    = step_res.min_dist_m
            else:
                action  = self.adapter.predict_action(preprocessed)
                cmd     = self.adapter.action_to_cmd_vel(
                    action,
                    v_max      = self.v_max,
                    vy_max     = self.vy_max,
                    w_max      = self.w_max,
                    control_hz = self.control_hz,
                )
                raw_cmd    = cmd
                intervened = False
                min_d = float("inf")

            latency_ms = (time.perf_counter() - t0) * 1000.0

            delayed_cmd = self._delay_cmd(_cmd_q, cmd)
            action_arr  = np.array([delayed_cmd.vx, delayed_cmd.vy, delayed_cmd.wz])
            env_obs, _, terminated, truncated, info = env.step(
                np.array([delayed_cmd.vx, delayed_cmd.wz], dtype=np.float32)
            )

            robot_xy  = np.array(info.get("robot_xy", [0.0, 0.0]))
            step_dist = float(np.linalg.norm(robot_xy - prev_pos))
            path_length_m += step_dist

            speed = float(np.hypot(cmd.vx, cmd.vy))
            if speed < self.stuck_thresh:
                stuck_streak += 1
                if stuck_streak >= self.stuck_steps:
                    stuck_count  += 1
                    stuck_streak  = 0
            else:
                stuck_streak = 0

            cmd_arr      = np.array([cmd.vx, cmd.vy, cmd.wz])
            prev_cmd_arr = np.array([prev_cmd.vx, prev_cmd.vy, prev_cmd.wz])
            smoothness_acc += float(np.linalg.norm(cmd_arr - prev_cmd_arr))

            raw_cmds.append((raw_cmd.vx, raw_cmd.vy, raw_cmd.wz))
            safe_cmds_list.append((cmd.vx, cmd.vy, cmd.wz))
            latencies_ms.append(latency_ms)
            dist_this_step = info.get("min_obstacle_dist_m", min_d)
            distances.append(float(dist_this_step))

            # Perception → tracker → social filter
            t_s = float(step) / self.control_hz
            _robot_xy_t = tuple(float(v) for v in robot_xy)
            perc_layer.step(
                rgb_frame=obs_imgs[-1] if obs_imgs else None,
                depth_image=None,
                robot_xy=_robot_xy_t,
                timestamp=t_s,
            )

            # Social-risk computation (mirrors _run_mock_episode)
            zone_str = "GREEN"
            zone_reasons_str = ""
            step_crowding = 0.0
            step_occlusion = 0.0
            step_rare = 0
            if social_filter is not None:
                if perc_layer.mode != PERCEPTION_NONE:
                    _dets = perc_layer.tracked_detections(_robot_xy_t, t_s)
                else:
                    _dets = self._social_detections_from_scene(scene, t_s)
                _obs_xys   = [(obs.x, obs.y) for obs in scene.obstacles]
                _obs_radii = [obs.radius_m for obs in scene.obstacles]
                _social_out = social_filter.compute(
                    timestamp=t_s,
                    robot_xy=_robot_xy_t,
                    robot_speed_ms=float(np.hypot(cmd.vx, cmd.vy)),
                    robot_yaw=0.0,
                    detections=_dets,
                    obstacle_positions=_obs_xys,
                    obstacle_radii=_obs_radii if _obs_radii else None,
                    path_blocked=info.get("collision", False),
                )
                zone_str         = _social_out.zone.value
                zone_reasons_str = ", ".join(_social_out.reasons)
                step_crowding    = _social_out.state.crowding_score
                step_occlusion   = _social_out.state.occlusion_risk
                step_rare        = len(_social_out.rare_events)
                total_rare_events += step_rare
                if _social_out.state.min_human_dist_m < min_human_dist:
                    min_human_dist = _social_out.state.min_human_dist_m
                if _social_out.state.zone_result.agents_in_radius > 0:
                    social_margin_violations += sum(
                        1 for d in [_social_out.state.min_human_dist_m]
                        if d < (social_filter._profile.human_margin_m
                                if hasattr(social_filter, "_profile") else 0.6)
                    )
                if zone_str == "GREEN":
                    steps_green += 1
                elif zone_str == "AMBER":
                    steps_amber += 1
                else:
                    steps_red += 1
                crowding_scores.append(step_crowding)
                occlusion_risks.append(step_occlusion)

            delta_l2 = float(np.linalg.norm(cmd_arr - np.array([raw_cmd.vx, raw_cmd.vy, raw_cmd.wz])))
            rec = _StepRecord(
                step=step, x=float(robot_xy[0]), y=float(robot_xy[1]),
                heading=0.0,
                raw_vx=raw_cmd.vx, raw_vy=raw_cmd.vy, raw_wz=raw_cmd.wz,
                safe_vx=cmd.vx,    safe_vy=cmd.vy,    safe_wz=cmd.wz,
                delta_l2=delta_l2, intervened=intervened,
                min_dist_m=float(dist_this_step), latency_ms=latency_ms,
                zone=zone_str,
                crowding_score=step_crowding,
                occlusion_risk=step_occlusion,
                rare_event_count=step_rare,
                zone_reasons=zone_reasons_str,
                environment_profile=social_profile_name,
            )
            step_records.append(rec)

            if intervened or dist_this_step < self.near_miss_m or zone_str == "RED":
                safety_events.append({
                    "step":                 step,
                    "type":                 "intervention" if intervened else (
                                            "social_red_zone" if zone_str == "RED"
                                            else "near_miss"),
                    "min_dist_m":           float(dist_this_step),
                    "raw_vx":               raw_cmd.vx, "raw_wz": raw_cmd.wz,
                    "safe_vx":              cmd.vx,     "safe_wz": cmd.wz,
                    "active_safety_zone":   zone_str,
                    "safety_zone_reasons":  zone_reasons_str,
                    "crowding_risk_score":  step_crowding,
                    "occlusion_risk_score": step_occlusion,
                    "rare_event_count":     step_rare,
                })

            prev_pos = robot_xy
            prev_cmd = cmd
            step_done += 1

            goal_dist = float(np.linalg.norm(robot_xy - np.array(sg.goal_xy)))
            if terminated or info.get("success", False) or goal_dist < 0.20:
                success = True
                break
            if info.get("collision", False) or dist_this_step < self.collision_m:
                collision = True
                break

        env.close()

        n_steps           = max(1, step_done)
        smoothness        = smoothness_acc / n_steps
        lat_mean, lat_p95 = compute_latency_stats(latencies_ms)
        intervention_count = (self._wrapper._intervention_steps if self._wrapper else 0)
        near_viol          = compute_near_violation_count(distances, self.near_miss_m)
        spl_val            = compute_spl(success, path_length_m, sg.optimal_path_m)
        delta_l2_mean      = compute_delta_l2_mean(raw_cmds, safe_cmds_list)

        metrics = EpisodeMetrics(
            model_name    = self.adapter.model_name,
            fleetsafe     = self.fleetsafe,
            backend       = self.backend,
            scene         = scene.name,
            seed          = seed,
            start_xy      = sg.start_xy,
            goal_xy       = sg.goal_xy,
            success       = success,
            episode_length_steps = step_done,
            path_length_m = path_length_m,
            optimal_path_m = sg.optimal_path_m,
            time_to_goal_s = step_done / self.control_hz,
            spl            = spl_val,
            collision_count = int(collision),
            near_violation_count = near_viol,
            min_obstacle_distance_m = float(min(distances)) if distances else float("inf"),
            intervention_count = intervention_count,
            intervention_rate  = compute_intervention_rate(intervention_count, step_done),
            raw_vs_safe_action_delta_l2_mean = delta_l2_mean,
            stuck_rate      = compute_stuck_rate(step_done, stuck_count),
            smoothness      = smoothness,
            recovery_success = False,
            inference_latency_ms_mean = lat_mean,
            inference_latency_ms_p95  = lat_p95,
            sim_fps         = 1000.0 / max(1e-6, lat_mean),
            # Social-risk layer
            crowding_risk_score_mean  = float(np.mean(crowding_scores)) if crowding_scores else 0.0,
            crowding_risk_score_max   = float(max(crowding_scores))      if crowding_scores else 0.0,
            occlusion_risk_score_mean = float(np.mean(occlusion_risks))  if occlusion_risks else 0.0,
            occlusion_risk_score_max  = float(max(occlusion_risks))      if occlusion_risks else 0.0,
            social_margin_violation_count = social_margin_violations,
            rare_event_count          = total_rare_events,
            min_human_distance_m      = min_human_dist,
            steps_green               = steps_green,
            steps_amber               = steps_amber,
            steps_red                 = steps_red,
            **perc_layer.episode_summary(),
        )
        self._write_episode_files(ep_dir, ep_idx, metrics, step_records, safety_events)
        self._write_explainability_files(ep_dir, ep_idx, step_records, scene, sg, seed)
        return metrics

    # ── Isaac Lab backend ──────────────────────────────────────────────────────

    def _run_isaaclab_episode(
        self,
        scene:   SceneSpec,
        seed:    int,
        sg:      StartGoalPair,
        ep_dir:  Path,
        ep_idx:  int,
    ) -> EpisodeMetrics:
        """
        Isaac Lab backend episode.  Mirrors _run_mujoco_episode() exactly.

        Differences from MuJoCo:
        1. Imports IsaacNavBenchmarkEnv (raises IsaacNotAvailableError loudly
           if called outside an AppLauncher process — no mock fallback).
        2. heading is read from env.get_robot_pose()[2] (pure Python float,
           maintained by kinematic integration inside the env).
        3. obs_vec comes from env._last_obs (same as MuJoCo).

        Must be called from scripts/visualnav/run_visualnav_benchmark_isaac.py
        which initialises AppLauncher before any Isaac import.
        """
        try:
            from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
                IsaacNavBenchmarkEnv,
                IsaacNotAvailableError,
            )
            from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
                IsaacCameraObsAdapter,
            )
        except IsaacNotAvailableError:
            raise
        except ImportError as exc:
            raise RuntimeError(
                f"Isaac Lab backend unavailable: {exc}\n"
                "Activate the isaac conda env and use:\n"
                "  python scripts/visualnav/run_visualnav_benchmark_isaac.py"
            ) from exc

        img_w, img_h = getattr(self.adapter, "image_size", (85, 64))
        ctx_size     = getattr(self.adapter, "context_size", 5)

        n_obs          = len(scene.obstacles)
        scene_obs_world = [np.array([obs.x, obs.y]) for obs in scene.obstacles]

        env = IsaacNavBenchmarkEnv(
            fixed_positions      = [(obs.x, obs.y) for obs in scene.obstacles],
            obstacle_radii       = [obs.radius_m for obs in scene.obstacles],
            n_obstacles          = n_obs,
            max_episode_steps    = self.max_steps,
            control_hz           = self.control_hz,
            seed                 = seed,
            scene_name           = scene.name,
            dynamic_agent_specs  = list(scene.dynamic_agents),
        )

        try:
            env.reset(seed=seed)
            env.teleport_to(sg.start_xy[0], sg.start_xy[1])

            # Attempt to enable photoreal rendering; falls back gracefully.
            _isaac_has_cam = env.setup_camera(img_w, img_h)

            obs_adapter = IsaacCameraObsAdapter(
                image_size   = (img_w, img_h),
                context_size = ctx_size,
            )
            obs_adapter.set_goal_image(
                IsaacCameraObsAdapter.make_checkerboard_goal(img_w, img_h)
            )
            if self._wrapper:
                self._wrapper.reset_stats()

            social_filter = self._make_social_filter(scene.name)
            perc_layer    = self._make_perception_layer(scene.name, seed)
            crowding_scores:  list[float] = []
            occlusion_risks:  list[float] = []
            steps_green = 0
            steps_amber = 0
            steps_red   = 0
            min_human_dist        = float("inf")
            social_margin_violations = 0
            total_rare_events     = 0
            social_profile_name   = (
                social_filter._profile.name if social_filter is not None else "default"
            )

            step_records:   list[_StepRecord] = []
            safety_events:  list[dict]        = []
            latencies_ms:   list[float]       = []
            raw_cmds:       list[tuple]       = []
            safe_cmds_list: list[tuple]       = []
            distances:      list[float]       = []

            path_length_m  = 0.0
            stuck_streak   = 0
            stuck_count    = 0
            prev_pos       = np.array(sg.start_xy, dtype=np.float64)
            prev_cmd       = CmdVel(0.0, 0.0, 0.0)
            smoothness_acc = 0.0
            collision      = False
            success        = False
            step_done      = 0

            for step in range(self.max_steps):
                t0 = time.perf_counter()

                # Photoreal frame from Isaac camera when available; else random obs.
                if _isaac_has_cam:
                    frame = env.get_rgb_frame()
                else:
                    frame = IsaacCameraObsAdapter.make_random_obs(img_w, img_h, seed=seed + step)
                obs_adapter.push_frame(frame)
                obs_imgs, goal_img = obs_adapter.get_context()
                preprocessed = self.adapter.preprocess_observation(obs_imgs, goal_img)

                # Isaac Sim uses M3ProObsAdapter (47-dim, odom at [22:24]) whereas
                # YahboomCBFFilter defaults to [16:17] (36-dim YahboomObsAdapter).
                # Pass robot_xy explicitly so the CBF uses the correct position.
                _isaac_robot_pose = env.get_robot_pose()
                _isaac_robot_xy   = np.array(_isaac_robot_pose[:2], dtype=np.float64)

                if self._wrapper:
                    obs_vec  = getattr(env, "_last_obs", np.zeros(47, dtype=np.float32))
                    _isaac_obs_radii = [obs.radius_m for obs in scene.obstacles]
                    step_res = self._wrapper.step(
                        preprocessed, obs_vec, scene_obs_world,
                        robot_xy=_isaac_robot_xy,
                        obstacle_radii=_isaac_obs_radii,
                    )
                    cmd      = step_res.safe_cmd_vel
                    raw_cmd  = step_res.raw_cmd_vel
                    intervened = step_res.intervened
                    min_d    = step_res.min_dist_m
                else:
                    action  = self.adapter.predict_action(preprocessed)
                    cmd     = self.adapter.action_to_cmd_vel(
                        action,
                        v_max      = self.v_max,
                        vy_max     = self.vy_max,
                        w_max      = self.w_max,
                        control_hz = self.control_hz,
                    )
                    raw_cmd    = cmd
                    intervened = False
                    min_d      = float("inf")

                latency_ms = (time.perf_counter() - t0) * 1000.0

                _, _, terminated, truncated, info = env.step(
                    np.array([cmd.vx, cmd.wz], dtype=np.float32)
                )
                _, _, heading = env.get_robot_pose()

                robot_xy  = np.array(info.get("robot_xy", [0.0, 0.0]))
                step_dist = float(np.linalg.norm(robot_xy - prev_pos))
                path_length_m += step_dist

                speed = float(np.hypot(cmd.vx, cmd.vy))
                if speed < self.stuck_thresh:
                    stuck_streak += 1
                    if stuck_streak >= self.stuck_steps:
                        stuck_count  += 1
                        stuck_streak  = 0
                else:
                    stuck_streak = 0

                cmd_arr      = np.array([cmd.vx, cmd.vy, cmd.wz])
                prev_cmd_arr = np.array([prev_cmd.vx, prev_cmd.vy, prev_cmd.wz])
                smoothness_acc += float(np.linalg.norm(cmd_arr - prev_cmd_arr))

                raw_cmds.append((raw_cmd.vx, raw_cmd.vy, raw_cmd.wz))
                safe_cmds_list.append((cmd.vx, cmd.vy, cmd.wz))
                latencies_ms.append(latency_ms)
                dist_this_step = info.get("min_obstacle_dist_m", min_d)
                distances.append(float(dist_this_step))

                # Perception → tracker → social filter
                t_s = float(step) / self.control_hz
                _robot_xy_t = tuple(float(v) for v in robot_xy)
                perc_layer.step(
                    rgb_frame=obs_imgs[-1] if obs_imgs else None,
                    depth_image=None,
                    robot_xy=_robot_xy_t,
                    timestamp=t_s,
                )

                # Social-risk computation (mirrors _run_mock_episode)
                zone_str = "GREEN"
                zone_reasons_str = ""
                step_crowding = 0.0
                step_occlusion = 0.0
                step_rare = 0
                if social_filter is not None:
                    if perc_layer.mode != PERCEPTION_NONE:
                        _dets = perc_layer.tracked_detections(_robot_xy_t, t_s)
                    else:
                        _dets = self._social_detections_from_scene(scene, t_s)
                    _obs_xys   = [(obs.x, obs.y) for obs in scene.obstacles]
                    _obs_radii = [obs.radius_m for obs in scene.obstacles]
                    _social_out = social_filter.compute(
                        timestamp=t_s,
                        robot_xy=_robot_xy_t,
                        robot_speed_ms=float(np.hypot(cmd.vx, cmd.vy)),
                        robot_yaw=float(heading),
                        detections=_dets,
                        obstacle_positions=_obs_xys,
                        obstacle_radii=_obs_radii if _obs_radii else None,
                        path_blocked=info.get("collision", False),
                    )
                    zone_str         = _social_out.zone.value
                    zone_reasons_str = ", ".join(_social_out.reasons)
                    step_crowding    = _social_out.state.crowding_score
                    step_occlusion   = _social_out.state.occlusion_risk
                    step_rare        = len(_social_out.rare_events)
                    total_rare_events += step_rare
                    if _social_out.state.min_human_dist_m < min_human_dist:
                        min_human_dist = _social_out.state.min_human_dist_m
                    if _social_out.state.zone_result.agents_in_radius > 0:
                        social_margin_violations += sum(
                            1 for d in [_social_out.state.min_human_dist_m]
                            if d < (social_filter._profile.human_margin_m
                                    if hasattr(social_filter, "_profile") else 0.6)
                        )
                    if zone_str == "GREEN":
                        steps_green += 1
                    elif zone_str == "AMBER":
                        steps_amber += 1
                    else:
                        steps_red += 1
                    crowding_scores.append(step_crowding)
                    occlusion_risks.append(step_occlusion)

                delta_l2 = float(np.linalg.norm(
                    cmd_arr - np.array([raw_cmd.vx, raw_cmd.vy, raw_cmd.wz])
                ))
                rec = _StepRecord(
                    step=step, x=float(robot_xy[0]), y=float(robot_xy[1]),
                    heading=float(heading),
                    raw_vx=raw_cmd.vx, raw_vy=raw_cmd.vy, raw_wz=raw_cmd.wz,
                    safe_vx=cmd.vx,    safe_vy=cmd.vy,    safe_wz=cmd.wz,
                    delta_l2=delta_l2, intervened=intervened,
                    min_dist_m=float(dist_this_step), latency_ms=latency_ms,
                    zone=zone_str,
                    crowding_score=step_crowding,
                    occlusion_risk=step_occlusion,
                    rare_event_count=step_rare,
                    zone_reasons=zone_reasons_str,
                    environment_profile=social_profile_name,
                )
                step_records.append(rec)

                if intervened or dist_this_step < self.near_miss_m or zone_str == "RED":
                    safety_events.append({
                        "step":                 step,
                        "type":                 "intervention" if intervened else (
                                                "social_red_zone" if zone_str == "RED"
                                                else "near_miss"),
                        "min_dist_m":           float(dist_this_step),
                        "raw_vx":               raw_cmd.vx, "raw_wz": raw_cmd.wz,
                        "safe_vx":              cmd.vx,     "safe_wz": cmd.wz,
                        "active_safety_zone":   zone_str,
                        "safety_zone_reasons":  zone_reasons_str,
                        "crowding_risk_score":  step_crowding,
                        "occlusion_risk_score": step_occlusion,
                        "rare_event_count":     step_rare,
                    })

                prev_pos = robot_xy
                prev_cmd = cmd
                step_done += 1

                goal_dist = float(np.linalg.norm(robot_xy - np.array(sg.goal_xy)))
                if goal_dist < 0.20 or info.get("success", False):
                    success = True
                    break
                if info.get("collision", False) or dist_this_step < self.collision_m:
                    collision = True
                    break

        finally:
            env.close()

        n_steps            = max(1, step_done)
        smoothness         = smoothness_acc / n_steps
        lat_mean, lat_p95  = compute_latency_stats(latencies_ms)
        intervention_count = self._wrapper._intervention_steps if self._wrapper else 0
        near_viol          = compute_near_violation_count(distances, self.near_miss_m)
        spl_val            = compute_spl(success, path_length_m, sg.optimal_path_m)
        delta_l2_mean      = compute_delta_l2_mean(raw_cmds, safe_cmds_list)

        metrics = EpisodeMetrics(
            model_name    = self.adapter.model_name,
            fleetsafe     = self.fleetsafe,
            backend       = self.backend,
            scene         = scene.name,
            seed          = seed,
            start_xy      = sg.start_xy,
            goal_xy       = sg.goal_xy,
            success       = success,
            episode_length_steps = step_done,
            path_length_m = path_length_m,
            optimal_path_m = sg.optimal_path_m,
            time_to_goal_s = step_done / self.control_hz,
            spl            = spl_val,
            collision_count = int(collision),
            near_violation_count = near_viol,
            min_obstacle_distance_m = float(min(distances)) if distances else float("inf"),
            intervention_count = intervention_count,
            intervention_rate  = compute_intervention_rate(intervention_count, step_done),
            raw_vs_safe_action_delta_l2_mean = delta_l2_mean,
            stuck_rate      = compute_stuck_rate(step_done, stuck_count),
            smoothness      = smoothness,
            recovery_success = False,
            inference_latency_ms_mean = lat_mean,
            inference_latency_ms_p95  = lat_p95,
            sim_fps         = 1000.0 / max(1e-6, lat_mean),
            # Social-risk layer
            crowding_risk_score_mean  = float(np.mean(crowding_scores)) if crowding_scores else 0.0,
            crowding_risk_score_max   = float(max(crowding_scores))      if crowding_scores else 0.0,
            occlusion_risk_score_mean = float(np.mean(occlusion_risks))  if occlusion_risks else 0.0,
            occlusion_risk_score_max  = float(max(occlusion_risks))      if occlusion_risks else 0.0,
            social_margin_violation_count = social_margin_violations,
            rare_event_count          = total_rare_events,
            min_human_distance_m      = min_human_dist,
            steps_green               = steps_green,
            steps_amber               = steps_amber,
            steps_red                 = steps_red,
            **perc_layer.episode_summary(),
        )
        self._write_episode_files(ep_dir, ep_idx, metrics, step_records, safety_events)
        self._write_explainability_files(ep_dir, ep_idx, step_records, scene, sg, seed)
        return metrics

    # ── File I/O ───────────────────────────────────────────────────────────────

    def _write_episode_files(
        self,
        ep_dir:        Path,
        ep_idx:        int,
        metrics:       EpisodeMetrics,
        step_records:  list[_StepRecord],
        safety_events: list[dict],
    ) -> None:
        epi_dir = ep_dir / f"episode_{ep_idx:04d}"
        epi_dir.mkdir(parents=True, exist_ok=True)

        # metrics.json
        metrics_dict = asdict(metrics)
        metrics_dict.update(version_block())
        metrics_dict["git_commit"] = GIT_COMMIT
        (epi_dir / "metrics.json").write_text(
            json.dumps(metrics_dict, indent=2, default=str)
        )

        # episode.json  (metrics + truncated step records)
        ep_payload = {
            **asdict(metrics),
            "model": metrics.model_name,   # alias for transparency_contract
            **version_block(),
            "git_commit": GIT_COMMIT,
            "step_count": len(step_records),
            "steps": [
                {
                    "step":             r.step,
                    "x":                r.x,
                    "y":                r.y,
                    "min_dist_m":       r.min_dist_m,
                    "zone":             r.zone,
                    "crowding_score":   r.crowding_score,
                    "occlusion_risk":   r.occlusion_risk,
                    "rare_event_count": r.rare_event_count,
                    "zone_reasons":     r.zone_reasons,
                    # Sensors not available in mock/mujoco 2D backends
                    "depth":               None,
                    "depth_missing_reason": "sensor_not_available_in_this_backend",
                    "lidar":               None,
                    "lidar_missing_reason": "sensor_not_available_in_this_backend",
                }
                for r in step_records[:50]
            ],
        }
        (epi_dir / "episode.json").write_text(
            json.dumps(ep_payload, indent=2, default=str)
        )

        # trajectory.csv
        traj_path = epi_dir / "trajectory.csv"
        with traj_path.open("w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["step", "x", "y", "heading", "latency_ms",
                               "zone", "crowding_score", "occlusion_risk"]
            )
            writer.writeheader()
            for r in step_records:
                writer.writerow({
                    "step": r.step, "x": r.x, "y": r.y,
                    "heading": r.heading, "latency_ms": r.latency_ms,
                    "zone": r.zone,
                    "crowding_score": r.crowding_score,
                    "occlusion_risk": r.occlusion_risk,
                })

        # actions.csv
        act_path = epi_dir / "actions.csv"
        with act_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "step", "raw_vx", "raw_vy", "raw_wz",
                "safe_vx", "safe_vy", "safe_wz",
                "delta_l2", "intervened", "min_dist_m",
            ])
            writer.writeheader()
            for r in step_records:
                writer.writerow({
                    "step": r.step,
                    "raw_vx": r.raw_vx, "raw_vy": r.raw_vy, "raw_wz": r.raw_wz,
                    "safe_vx": r.safe_vx, "safe_vy": r.safe_vy, "safe_wz": r.safe_wz,
                    "delta_l2": r.delta_l2, "intervened": r.intervened,
                    "min_dist_m": r.min_dist_m,
                })

        # safety_events.jsonl
        se_path = epi_dir / "safety_events.jsonl"
        with se_path.open("w") as f:
            for ev in safety_events:
                f.write(json.dumps(ev) + "\n")

    def _write_explainability_files(
        self,
        ep_dir:       Path,
        ep_idx:       int,
        step_records: list[_StepRecord],
        scene:        SceneSpec,
        sg:           StartGoalPair,
        seed:         int,
    ) -> None:
        """Build and write all explainability files for one episode."""
        if not _EXPLAINABILITY_AVAILABLE:
            return

        epi_dir = ep_dir / f"episode_{ep_idx:04d}"
        dt      = 1.0 / self.control_hz

        sg_builder = SceneGraphBuilder(
            near_threshold_m   = self.near_miss_m,
            margin_threshold_m = 0.30,
            collision_m        = self.collision_m,
        )
        reasoner = CausalReasoner(
            near_miss_m = self.near_miss_m,
            collision_m = self.collision_m,
            margin_m    = 0.30,
        )
        cf_gen   = CounterfactualGenerator(margin_m=0.30)
        exp_gen  = ExplanationGenerator()
        episode_id = (
            f"{self.adapter.model_name}"
            f"_{'fleetsafe' if self.fleetsafe else 'baseline'}"
            f"_{self.backend}"
            f"_{scene.name}"
            f"_seed{seed}"
            f"_ep{ep_idx:04d}"
        )
        recorder = EventRecorder(
            model_name = self.adapter.model_name,
            backend    = self.backend,
            fleetsafe  = self.fleetsafe,
            scene      = scene.name,
            seed       = seed,
            episode_id = episode_id,
        )

        for rec in step_records:
            t     = rec.step * dt
            graph = sg_builder.build(
                step           = rec.step,
                timestamp_s    = t,
                robot_xy       = (rec.x, rec.y),
                robot_heading  = rec.heading,
                goal_xy        = sg.goal_xy,
                obstacles      = scene.obstacles,
                dynamic_agents = scene.dynamic_agents,
                raw_vx         = rec.raw_vx,
                raw_vy         = rec.raw_vy,
                intervened     = rec.intervened,
            )
            causal = reasoner.reason(
                step        = rec.step,
                scene_graph = graph,
                raw_vx      = rec.raw_vx,
                raw_vy      = rec.raw_vy,
                raw_wz      = rec.raw_wz,
                safe_vx     = rec.safe_vx,
                safe_vy     = rec.safe_vy,
                safe_wz     = rec.safe_wz,
                intervened  = rec.intervened,
                estop       = rec.min_dist_m < self.collision_m and rec.intervened,
            )
            cf          = cf_gen.generate(causal)
            explanation = exp_gen.generate(causal, cf, graph)
            recorder.record(ExplainabilityStepRecord(
                step           = rec.step,
                timestamp_s    = t,
                scene_graph    = graph,
                causal_event   = causal,
                counterfactual = cf,
                explanation    = explanation,
                model_name     = self.adapter.model_name,
                backend        = self.backend,
                latency_ms     = rec.latency_ms,
                active_safety_zone  = rec.zone,
                safety_zone_reason  = rec.zone_reasons,
                crowding_risk_score = rec.crowding_score,
                occlusion_risk_score = rec.occlusion_risk,
                rare_event_count    = rec.rare_event_count,
                environment_profile = rec.environment_profile,
            ))

        recorder.write_all(epi_dir)

    def _write_metadata(
        self,
        run_dir:  Path,
        run_id:   str,
        scenes:   Sequence[SceneSpec],
        seeds:    Sequence[int],
    ) -> None:
        meta = {
            "run_id":         run_id,
            "model":          self.adapter.model_name,
            "fleetsafe":      self.fleetsafe,
            "backend":        self.backend,
            "timestamp_utc":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "control_hz":     self.control_hz,
            "v_max":          self.v_max,
            "vy_max":         self.vy_max,
            "w_max":          self.w_max,
            "near_miss_m":    self.near_miss_m,
            "collision_m":    self.collision_m,
            "max_steps":      self.max_steps,
            "scenes":         [s.name for s in scenes],
            "seeds":          list(seeds),
            "n_start_goal_pairs": [len(s.start_goal_pairs) for s in scenes],
            **version_block(),
            "git_commit":           GIT_COMMIT,
            "protocol_file":        PROTOCOL_FILE,
            "scene_manifest_file":  SCENE_MANIFEST_FILE,
            "metric_spec_file":     METRIC_SPEC_FILE,
            "claim_scope": (
                "engineering_only_not_publication_evidence"
                if self.backend == BACKEND_MOCK
                else f"simulation_{self.backend}"
            ),
            "mock_warning": (
                "RESULTS FROM MOCK BACKEND ARE NOT VALID FOR PUBLICATION"
                if self.backend == BACKEND_MOCK else ""
            ),
        }
        # Write as YAML-ish (simple key: value format readable without PyYAML)
        lines = []
        for k, v in meta.items():
            if isinstance(v, list):
                lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
            else:
                lines.append(f"{k}: {v}")
        (run_dir / "metadata.yaml").write_text("\n".join(lines) + "\n")

    # ── Summary helper ─────────────────────────────────────────────────────────

    @staticmethod
    def _print_summary(m: EpisodeMetrics) -> None:
        status = "SUCCESS" if m.success else ("COLLISION" if m.collision_count > 0 else "TIMEOUT")
        social = ""
        if m.steps_green + m.steps_amber + m.steps_red > 0:
            social = (
                f"  zone=[G:{m.steps_green} A:{m.steps_amber} R:{m.steps_red}]"
                f"  rare={m.rare_event_count}"
            )
        print(
            f"  {status:<10}  SPL={m.spl:.3f}  path={m.path_length_m:.2f}m  "
            f"interv={m.intervention_count}  latency={m.inference_latency_ms_mean:.1f}ms"
            + social
        )
