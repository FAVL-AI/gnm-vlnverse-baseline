"""InstructionIntake — accept text, voice, or image instructions from multiple sources.

Supported adapters (in priority order):
  1. CLI text argument  --text "..."
  2. stdin (one line per command, for typing or pipe)
  3. ROS2 topic subscription (requires rclpy, optional)
  4. File / transcript path

No cloud APIs. No Whisper required. Adapter interface kept clean for later upgrades.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable, Iterator, Optional

from fleet_safe_vla.vln.instruction_schema import (
    VLNInstruction,
    InstructionSource,
)


class InstructionIntake:
    """Routes instructions from any source into VLNInstruction objects."""

    def __init__(
        self,
        source: InstructionSource = InstructionSource.TEXT,
        ros_topic: Optional[str] = None,
        transcript_confidence_default: float = 0.9,
    ):
        self._source = source
        self._ros_topic = ros_topic
        self._conf = transcript_confidence_default
        self._callbacks: list[Callable[[VLNInstruction], None]] = []

    # ── Adapter: direct text ──────────────────────────────────────────────────

    def from_text(self, text: str) -> VLNInstruction:
        text = text.strip()
        return VLNInstruction(
            source=InstructionSource.TEXT.value,
            raw_text=text,
            transcript=text,
            transcript_confidence=1.0,
            goal_text=text,
        )

    # ── Adapter: voice transcript (file or string) ────────────────────────────

    def from_voice_transcript(self, transcript: str, confidence: float = 0.85) -> VLNInstruction:
        transcript = transcript.strip()
        return VLNInstruction(
            source=InstructionSource.VOICE.value,
            raw_text=transcript,
            transcript=transcript,
            transcript_confidence=confidence,
            goal_text=transcript,
        )

    def from_transcript_file(self, path: str) -> VLNInstruction:
        text = Path(path).read_text().strip().splitlines()[-1]  # use last line
        return self.from_voice_transcript(text)

    # ── Adapter: image goal (stub — full grounding added later) ───────────────

    def from_image_path(self, image_path: str, description: str = "") -> VLNInstruction:
        return VLNInstruction(
            source=InstructionSource.IMAGE.value,
            raw_text=description,
            transcript=description,
            transcript_confidence=None,
            image_path=image_path,
            goal_text=description or "navigate to goal image",
        )

    # ── Adapter: stdin (interactive / demo) ──────────────────────────────────

    def stdin_stream(self, prompt: str = "Instruction> ") -> Iterator[VLNInstruction]:
        """Yield VLNInstructions from stdin one line at a time."""
        while True:
            try:
                if sys.stdin.isatty():
                    sys.stdout.write(prompt)
                    sys.stdout.flush()
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                yield self.from_text(line)
            except KeyboardInterrupt:
                break

    # ── Adapter: ROS2 topic (optional) ────────────────────────────────────────

    def subscribe_ros2(
        self,
        topic: str,
        node_name: str = "fleetsafe_vln_intake",
        on_instruction: Optional[Callable[[VLNInstruction], None]] = None,
    ) -> None:
        """Subscribe to a ROS2 std_msgs/msg/String topic.

        Does nothing if rclpy is not available.
        Calls on_instruction (or registered callbacks) for each message.
        """
        try:
            import rclpy
            from rclpy.node import Node
            from std_msgs.msg import String
        except ImportError:
            print("[VLN] rclpy not available — ROS2 subscription skipped.")
            return

        class _Listener(Node):
            def __init__(inner_self):
                super().__init__(node_name)
                inner_self.create_subscription(String, topic, inner_self._cb, 10)

            def _cb(inner_self, msg: String):
                inst = VLNInstruction(
                    source=InstructionSource.VOICE.value,
                    raw_text=msg.data,
                    transcript=msg.data,
                    transcript_confidence=self._conf,
                    goal_text=msg.data,
                )
                if on_instruction:
                    on_instruction(inst)
                for cb in self._callbacks:
                    cb(inst)

        if not rclpy.ok():
            rclpy.init()
        node = _Listener()
        print(f"[VLN] Subscribed to ROS2 topic: {topic}")
        rclpy.spin(node)

    # ── Callback registration ─────────────────────────────────────────────────

    def register_callback(self, fn: Callable[[VLNInstruction], None]) -> None:
        self._callbacks.append(fn)

    # ── Source discovery ──────────────────────────────────────────────────────

    @staticmethod
    def discover_ros2_voice_topics() -> list[str]:
        """Return ROS2 topics that might carry voice/ASR data."""
        candidates = [
            "/voice_text", "/speech_text", "/asr_text", "/iat_text",
            "/voice_cmd", "/voice_command", "/mic/text", "/wake_word",
            "/xfyun/asr", "/fleetsafe/instruction_voice",
            "/fleetsafe/instruction_text",
        ]
        try:
            import rclpy
            from rclpy.node import Node

            class _Scanner(Node):
                def __init__(self):
                    super().__init__("vln_topic_scanner")

            if not rclpy.ok():
                rclpy.init()
            node = _Scanner()
            live = {name for name, _ in node.get_topic_names_and_types()}
            node.destroy_node()
            return [t for t in candidates if t in live]
        except Exception:
            return []
