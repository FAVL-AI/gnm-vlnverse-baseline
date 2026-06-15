# Dataset Card — vlntube_fleetsafe Generated-Language Manifest

**Manifest file:** `generated_language_manifest.jsonl`  
**Integrity:** `generated_language_manifest.sha256`  
**Date frozen:** 2026-06-15  
**Episodes:** 253 (train: 238, val: 15)

## Source

Navigation instructions sourced from `Eyz/VLNVerse_data` (HuggingFace), produced by the
VLNTube instube pipeline (V3A Group, University of Adelaide). Instructions were generated
by `gemini-2.5-flash` via `external/VLNTube/instube/gemini_images_analyzer.py` using
uniform frame sampling (max 30 frames per episode; final frame always included).

Original episode splits derived from `fine_train.json.gz` (238 episodes) and
`fine_val.json.gz` (15 episodes) in `Eyz/VLNVerse_data`. Instruction texts verified
against those files by SHA-256 (see `results/track_b_language/instruction_provenance/`).

## Instruction provenance

| Field | Value |
|-------|-------|
| Generator model | gemini-2.5-flash |
| Generator provider | Google |
| Generator script | `external/VLNTube/instube/gemini_images_analyzer.py` |
| Max frames per call | 30 (uniform sample; final frame always included) |
| goal_pos in generator prompt | No |
| Target frame explicit | No |
| Upstream dataset | Eyz/VLNVerse_data |

## Target exposure classification

All 253 episodes are classified `INDIRECT_TARGET_VISUAL_EXPOSURE`:
- The generator saw the full trajectory sequence, including goal-region frames.
- The final trajectory frame is always included in the uniform sample.
- goal_pos coordinates were **not** in the generator prompt.
- No specific target frame was explicitly identified to the generator.

This is the standard classification for automatically constructed VLN benchmarks.

## Claim boundary

Evaluation results obtained using this manifest should be reported as
**"generated-language grounding"** — not "human-language generalisation". The
instruction generator saw trajectory images including goal-region frames; the
endpoint description in each instruction may encode visual information from those
frames. This does not invalidate the evaluation but defines the scope of the claim.

## Split discipline

The 15 val episodes (`split: "val"`) must be used **only** for final held-out
evaluation. Method selection and hyperparameter decisions must use only the 238
train episodes (`split: "train"`).

## Licence

Instructions sourced from Eyz/VLNVerse_data. Licence status: LICENCE_REVIEW_REQUIRED.
See `THIRD_PARTY_NOTICES.md` and `docs/legal/LICENSING_STATUS.md`. Do not redistribute
without confirming the upstream dataset licence.

## Schema

Each JSONL record contains:

| Field | Type | Description |
|-------|------|-------------|
| `episode_id` | string | Unique episode identifier |
| `split` | string | `"train"` or `"val"` |
| `scene_id` | string | Kujiale scene identifier |
| `instruction_text` | string | Navigation instruction (verbatim from upstream) |
| `instruction_sha256` | string | SHA-256 of the instruction text (UTF-8) |
| `instruction_source` | string | `"upstream_generated_from_trajectory_frames"` |
| `instruction_generator_model` | string | `"gemini-2.5-flash"` |
| `instruction_generator_provider` | string | `"Google"` |
| `instruction_generation_script` | string | Path to generation script |
| `instruction_provenance_dataset` | string | `"Eyz/VLNVerse_data"` |
| `target_exposure_classification` | string | `"INDIRECT_TARGET_VISUAL_EXPOSURE"` |
| `goal_region_visible_to_generator` | bool | Whether goal-region frames were in sample |
| `final_frame_visible_to_generator` | bool | Whether trajectory final frame was included |
| `goal_pos_in_generator_prompt` | bool | `false` for all episodes |
| `target_frame_explicit` | bool | `false` for all episodes |
| `gate_b_decision` | string | `"READY_FOR_GENERATED_LANGUAGE_BENCHMARK_EVALUATION"` |
| `evaluation_eligible` | bool | `true` for all 253 episodes |
| `n_trajectory_steps` | int | Length of trajectory in traj_data.pkl |
| `n_jpg_frames` | int | Number of JPG frames in episode directory |
