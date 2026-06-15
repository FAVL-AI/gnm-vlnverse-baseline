# Instruction Target-Exposure Audit

**Date:** 2026-06-15
**Episodes audited:** 253

## Generator provenance

| Field | Value |
|-------|-------|
| Model | gemini-2.5-flash |
| Provider | Google |
| Script | `external/VLNTube/instube/gemini_images_analyzer.py` |
| Prompt template | VLN_PROMPT_IMAGE_SEQUENCE |
| Max frames per call | 30 |
| goal_pos in prompt | False |
| Target frame explicit | False |
| Final frame always sampled | True |

## Exposure classification

| Classification | Count |
|----------------|-------|
| `INDIRECT_TARGET_VISUAL_EXPOSURE` | 253 |

## Summary statistics

| Metric | Count |
|--------|-------|
| Goal-region frames visible to generator | 253 |
| Final trajectory frame included | 253 |
| Episodes where trajectory was uniformly sampled | 230 |
| Evaluation eligible | 253 |

## Claim boundary

> These are upstream Gemini-generated instructions (not human-authored). The instruction generator saw trajectory frames including goal-region frames (INDIRECT_TARGET_VISUAL_EXPOSURE). This is standard for auto-generated VLN benchmarks. Evaluation results should be labelled 'generated-language grounding', not 'human-language generalisation'.

## Classification definitions

| Code | Meaning |
|------|---------|
| `INDIRECT_TARGET_VISUAL_EXPOSURE` | Generator saw trajectory sequence including goal-region frames; endpoint description derived from those frames. Standard for auto-generated VLN. |
| `DIRECT_TARGET_FRAME_EXPOSURE` | A specific target frame was explicitly given to the generator. Not the case here. |
| `GOAL_POSE_EXPOSURE` | goal_pos coordinates were in the generator prompt. Not the case here. |
| `NO_TARGET_EXPOSURE_CONFIRMED` | Confirmed no goal-region frames in generator input. Not the case here. |
| `UNKNOWN` | Cannot verify generator input. |