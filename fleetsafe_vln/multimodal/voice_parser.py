"""Voice parser — converts audio file to text, then routes to text_parser."""
from __future__ import annotations

from fleetsafe_vln.multimodal.instruction_schema import MultimodalInstruction, NormalizedGoal
from fleetsafe_vln.multimodal.text_parser import parse_text


def parse_voice(instruction: MultimodalInstruction) -> NormalizedGoal:
    """Transcribe voice_file and parse as text. Falls back to text field."""
    transcript = instruction.text

    if instruction.voice_file:
        try:
            transcript = _transcribe(instruction.voice_file)
        except Exception as exc:
            print(f"[voice_parser] Transcription failed ({exc}), using text field.")

    enriched = MultimodalInstruction(
        text=transcript,
        semantic_goal=instruction.semantic_goal,
        constraints=instruction.constraints,
        safety_profile=instruction.safety_profile,
    )
    goal = parse_text(enriched)
    goal.source_modality = "voice"
    return goal


def _transcribe(audio_path: str) -> str:
    try:
        import whisper  # type: ignore
        model = whisper.load_model("base")
        result = model.transcribe(audio_path)
        return str(result.get("text", "")).strip()
    except ImportError:
        raise ImportError(
            "openai-whisper not installed. Install with: pip install openai-whisper"
        )
