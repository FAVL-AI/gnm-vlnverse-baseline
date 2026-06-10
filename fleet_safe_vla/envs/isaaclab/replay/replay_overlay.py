"""
replay_overlay.py — Text overlay data builder for the intervention replay viewer.

Produces structured overlay lines suitable for:
  - Terminal printing (plain text)
  - Isaac Sim debug text rendering (omni.debug.draw)
  - matplotlib text annotation (video export)

No Isaac imports. Importable in CI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MOCK_ROLLOUT_WARNING = (
    "⚠  MOCK COUNTERFACTUAL ROLLOUT — engineering only, not publication evidence"
)

ISAAC_ROLLOUT_PENDING = (
    "Isaac branching rollout pending — no publication claim allowed"
)


# Traffic-light zone display strings and ANSI colours (terminal only)
ZONE_LABEL: dict[str, str] = {
    "GREEN": "GREEN  ■",
    "AMBER": "AMBER  ■",
    "RED":   "RED    ■",
}
ZONE_ANSI: dict[str, str] = {
    "GREEN": "\033[92m",   # bright green
    "AMBER": "\033[93m",   # bright yellow
    "RED":   "\033[91m",   # bright red
}
ANSI_RESET = "\033[0m"


@dataclass
class OverlayData:
    """All text overlay content for one replay frame."""
    frame_idx:               int
    timestamp:               float
    total_frames:            int
    intervention_applied:    bool
    intervention_reason:     str
    safety_margin_before:    float
    safety_margin_after:     float
    nearest_obstacle_id:     str
    nearest_obstacle_dist_m: float
    active_constraints:      list[str]
    raw_action:              tuple[float, float, float]
    safe_action:             tuple[float, float, float]
    action_delta:            tuple[float, float, float]
    action_delta_l2:         float
    causal_explanation:      str
    counterfactual_explanation: str
    is_mock_rollout:         bool
    backend:                 str
    model_name:              str
    benchmark_version:       str
    git_commit:              str
    scene_id:                str
    missing_artifacts:       list[str]
    # Social-risk zone fields (populated when social_awareness layer is active)
    active_safety_zone:     str   = "GREEN"
    safety_zone_reason:     str   = ""
    crowding_risk_score:    float = 0.0
    occlusion_risk_score:   float = 0.0
    rare_event_count:       int   = 0
    environment_profile:    str   = "default"

    # ── Formatting helpers ─────────────────────────────────────────────────────

    def _fmt_action(self, a: tuple[float, float, float]) -> str:
        return f"[{a[0]:+.3f}, {a[1]:+.3f}, {a[2]:+.3f}]"

    def _margin_label(self, m: float) -> str:
        if m == float("inf"):
            return "inf"
        return f"{m:.3f} m"

    def _status_prefix(self) -> str:
        if self.intervention_applied:
            return "[INTERV] INTERVENTION"
        if self.active_safety_zone == "RED":
            return "[RED] DANGER — STOP"
        if self.active_safety_zone == "AMBER":
            return "[AMBER] CAUTION"
        if self.nearest_obstacle_dist_m < 0.45:
            return "[NEAR] NEAR-VIOLATION"
        return "[OK] NORMAL"

    def zone_color_rgb(self) -> tuple[float, float, float]:
        """Return an RGB tuple for the active safety zone (for matplotlib / Isaac)."""
        return {
            "GREEN": (0.1, 0.8, 0.1),
            "AMBER": (0.9, 0.7, 0.0),
            "RED":   (0.9, 0.1, 0.1),
        }.get(self.active_safety_zone, (0.5, 0.5, 0.5))

    # ── Line builders ──────────────────────────────────────────────────────────

    def to_lines(self) -> list[str]:
        """Return formatted overlay lines (terminal + matplotlib compatible)."""
        lines: list[str] = []

        # Header
        lines.append("═" * 58)
        lines.append(f"  FleetSafe Intervention Replay Viewer")
        lines.append(f"  model={self.model_name}  backend={self.backend}")
        lines.append(f"  v{self.benchmark_version}  commit={self.git_commit[:8]}")
        lines.append("─" * 58)

        # Frame / status
        lines.append(
            f"  Frame {self.frame_idx:4d} / {self.total_frames - 1:4d}   "
            f"t={self.timestamp:.2f}s   {self._status_prefix()}"
        )
        lines.append("─" * 58)

        # Action block
        lines.append("  Actions")
        lines.append(f"    raw    = {self._fmt_action(self.raw_action)}")
        lines.append(f"    safe   = {self._fmt_action(self.safe_action)}")
        lines.append(f"    delta  = {self._fmt_action(self.action_delta)}")
        lines.append(f"    |Δ|L2  = {self.action_delta_l2:.4f} m/s")
        lines.append("─" * 58)

        # Safety block
        lines.append("  Safety")
        lines.append(f"    nearest obstacle : {self.nearest_obstacle_id}")
        lines.append(f"    distance         : {self._margin_label(self.nearest_obstacle_dist_m)}")
        lines.append(f"    margin_before    : {self._margin_label(self.safety_margin_before)}")
        lines.append(f"    margin_after     : {self._margin_label(self.safety_margin_after)}")
        if self.active_constraints:
            lines.append(f"    constraints      : {len(self.active_constraints)} active")
            for c in self.active_constraints[:3]:
                lines.append(f"      • {c[:52]}")
        lines.append("─" * 58)

        # Social-risk zone block
        lines.append("─" * 58)
        zone_label = ZONE_LABEL.get(self.active_safety_zone, self.active_safety_zone)
        lines.append(f"  Traffic-Light Zone : {zone_label}")
        lines.append(f"  Profile            : {self.environment_profile}")
        lines.append(f"  Crowding risk      : {self.crowding_risk_score:.2f}")
        lines.append(f"  Occlusion risk     : {self.occlusion_risk_score:.2f}")
        lines.append(f"  Rare events (step) : {self.rare_event_count}")
        if self.safety_zone_reason:
            reason_display = self.safety_zone_reason[:54]
            lines.append(f"  Zone reason        : {reason_display}")
        lines.append("─" * 58)

        # Explanation block
        if self.intervention_applied:
            lines.append("  Intervention reason")
            lines.append(f"    {self.intervention_reason[:54]}")
            lines.append("  Causal explanation")
            for chunk in _wrap(self.causal_explanation, 54):
                lines.append(f"    {chunk}")
            lines.append("  Counterfactual")
            for chunk in _wrap(self.counterfactual_explanation, 54):
                lines.append(f"    {chunk}")
        else:
            lines.append(f"  {self.causal_explanation[:56] or 'No intervention this step.'}")

        # Rollout backend warning
        lines.append("─" * 58)
        if self.is_mock_rollout:
            lines.append(f"  ⚠ MOCK COUNTERFACTUAL  — not publication evidence")
        else:
            lines.append(f"  Isaac rollout pending — no publication claim")

        # Missing artifact warning
        if self.missing_artifacts:
            lines.append("─" * 58)
            lines.append("  ⚠ MISSING ARTIFACTS:")
            for m in self.missing_artifacts:
                lines.append(f"    ! {m}")

        lines.append("═" * 58)
        return lines

    def to_terminal_string(self) -> str:
        return "\n".join(self.to_lines())

    def to_plain_lines(self) -> list[str]:
        """Strip box-drawing chars for matplotlib text rendering."""
        return [
            ln.replace("═", "-").replace("─", "-").replace("║", "|")
            for ln in self.to_lines()
        ]


def _wrap(text: str, width: int) -> list[str]:
    """Simple word-wrap."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        if len(current) + len(w) + 1 <= width:
            current = (current + " " + w).strip()
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines or [""]


def build_overlay(
    frame: "ReplayFrame",          # type: ignore[name-defined]
    total_frames: int,
    git_commit: str = "unknown",
    scene_id: str = "",
    missing_artifacts: list[str] | None = None,
) -> OverlayData:
    """Build an OverlayData from a ReplayFrame."""
    return OverlayData(
        frame_idx=frame.frame_idx,
        timestamp=frame.timestamp,
        total_frames=total_frames,
        intervention_applied=frame.intervention_applied,
        intervention_reason=frame.intervention_reason,
        safety_margin_before=frame.safety_margin_before,
        safety_margin_after=frame.safety_margin_after,
        nearest_obstacle_id=frame.nearest_obstacle_id,
        nearest_obstacle_dist_m=frame.nearest_obstacle_distance_m,
        active_constraints=frame.active_constraints,
        raw_action=frame.raw_action,
        safe_action=frame.safe_action,
        action_delta=frame.action_delta,
        action_delta_l2=frame.action_delta_l2,
        causal_explanation=frame.causal_explanation,
        counterfactual_explanation=frame.counterfactual_explanation,
        is_mock_rollout=(frame.backend == "mock"),
        backend=frame.backend,
        model_name=frame.model_name,
        benchmark_version=frame.benchmark_version,
        git_commit=git_commit,
        scene_id=scene_id,
        missing_artifacts=missing_artifacts or [],
        # Social-risk zone — read from frame if present (defaults to GREEN/empty)
        active_safety_zone=getattr(frame, "active_safety_zone", "GREEN"),
        safety_zone_reason=getattr(frame, "safety_zone_reason", ""),
        crowding_risk_score=getattr(frame, "crowding_risk_score", 0.0),
        occlusion_risk_score=getattr(frame, "occlusion_risk_score", 0.0),
        rare_event_count=getattr(frame, "rare_event_count", 0),
        environment_profile=getattr(frame, "environment_profile", "default"),
    )
