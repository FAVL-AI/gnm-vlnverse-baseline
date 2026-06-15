# Usage Guide

Step-by-step instructions for all documented workflows in this repository.

**Prerequisites:** Python 3.10+, PyTorch 2.2+, git.  
**Tested on:** Ubuntu 22.04 / 24.04, Python 3.13, PyTorch 2.12.

---

## 1. Fresh clone

```bash
git clone https://github.com/FAVL-AI/gnm-vlnverse-baseline.git
cd gnm-vlnverse-baseline
```

---

## 2. Environment creation

Using conda (recommended):

```bash
conda create -n gnm-vlnverse python=3.10 -y
conda activate gnm-vlnverse
```

Or using venv:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## 3. Base installation

```bash
pip install -e .
```

This installs the `gnm-vlnverse-baseline` package plus all required dependencies
(numpy, torch, torchvision, timm, opencv-python-headless, pyyaml, omegaconf,
scipy, pandas, tqdm, Pillow).

---

## 4. Optional language installation (Track B, CLIP retrieval)

```bash
pip install -e '.[language]'
```

This additionally installs `transformers>=4.40`. The CLIP model weights
(`openai/clip-vit-base-patch16`, ~600 MB) are downloaded from HuggingFace Hub
on first use.

---

## 5. Dataset linking

The VLNVerse/vlntube dataset is not committed to this repository. You must link
it from your local copy of FleetSafe-VisualNav-Benchmark.

**Automated link script:**

```bash
bash scripts/gnm/link_vlntube_data.sh /path/to/vlntube
```

For the development workstation:

```bash
bash scripts/gnm/link_vlntube_data.sh \
    ~/robotics/FleetSafe-VisualNav-Benchmark/datasets/vlntube
```

**Verify the link is correct:**

```bash
python3 scripts/gnm/check_demo_ready.py
```

Expected output: no ERROR lines; dataset root confirmed present.

---

## 6. Readiness checks

```bash
python3 scripts/gnm/check_demo_ready.py
```

This verifies:
- Dataset root exists and is readable
- Required splits (train, val) are present
- episode_info.json and traj_data.pkl are readable for a sample of episodes
- instruction.txt files are present

---

## 7. Track A evaluation

### 7a. Reproduce the baseline SR/OSR/NE metrics

```bash
python3 scripts/gnm/evaluate_track_b.py \
    --split val \
    --methods oracle last \
    --output-dir results/track_a_eval
```

### 7b. Train and evaluate the temporal stop head

```bash
python3 scripts/gnm/learn_stop_head.py
```

### 7c. Export the live dashboard (no GUI required)

```bash
python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
```

Evidence written to `results/bo_reviewer_packet/`.

---

## 8. Track B — instruction-provenance audit

```bash
python3 scripts/gnm/audit_track_b_language_data.py \
    --output-dir results/track_b_language/audit
```

This classifies every episode's instruction source (Gate B) and writes:
- `audit.json` — aggregate Gate B decision
- `instruction_sources.jsonl` — per-episode classification
- `audit.md` — human-readable summary

Expected Gate B decision: `READY_FOR_GENERATED_LANGUAGE_BENCHMARK_EVALUATION`
(253 upstream Gemini-generated instructions colocated with 13,491 real images).

---

## 9. Track B — target-exposure audit

```bash
python3 scripts/gnm/audit_instruction_target_exposure.py \
    --output-dir results/track_b_language/target_exposure
```

Classifies how much goal-region information the instruction generator saw.
Expected result: all 253 episodes = `INDIRECT_TARGET_VISUAL_EXPOSURE`.

---

## 10. Track B — embedding creation

CLIP embeddings are created on-the-fly during retrieval. No separate
pre-computation step is required. The model is cached in `~/.cache/huggingface/`.

To verify the encoder is available and record its fingerprint:

```bash
python3 - <<'EOF'
from transformers import CLIPModel, CLIPProcessor
import hashlib, json
m = CLIPModel.from_pretrained("openai/clip-vit-base-patch16")
p = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch16")
w = m.visual_projection.weight.detach().cpu().numpy().tobytes()
print("SHA-256:", hashlib.sha256(w).hexdigest())
print("Params:", sum(x.numel() for x in m.parameters()))
EOF
```

---

## 11. Track B — semantic-only retrieval baseline

```bash
python3 scripts/gnm/dev_set_method_selection.py \
    --split train \
    --stride 5 \
    --route-beta 0.0 \
    --output-dir results/track_b_language/clip_only_baseline
```

This runs pure CLIP (no route prior) on the 238 train episodes.
Expected: SR@3m ≈ 0.344.

---

## 12. Track B — route-prior diagnostic

```bash
python3 scripts/gnm/dev_set_method_selection.py \
    --split train \
    --stride 5 \
    --route-beta 1.0 \
    --output-dir results/track_b_language/dev_set_method_selection
```

Runs 7 methods (random, first, final, oracle, clip, clip_route, clip_route_rej)
on all 238 train episodes. Configuration in
`configs/gnm/track_b_route_prior_diagnostic.yaml`.

Expected: final, oracle, clip_route, clip_route_rej all achieve SR@3m = 1.000
because all trajectories end at goal_pos.

---

## 13. Track B — language-dependence controls

```bash
# Train split (238 episodes)
python3 scripts/gnm/language_dependence_controls.py \
    --split train --seed 42

# Val split (15 episodes)
python3 scripts/gnm/language_dependence_controls.py \
    --split val --seed 42
```

Compares correct instructions against: shuffled, empty, constant, random-text,
route-only, and CLIP-only conditions. Records:
- SR@3m per condition
- 95% confidence intervals
- MRR, Recall@1/3/5
- Final-frame selection rate
- Language-dependence conclusion

Expected conclusion: `LANGUAGE_DEPENDENCE_NOT_DEMONSTRATED` (route prior alone
achieves SR@3m = 1.000 regardless of instruction content).

Output: `results/track_b_language/language_dependence_controls/`

---

## 14. Track B — held-out evaluation (run once)

The 15 val episodes are reserved for final held-out evaluation only. Do not run
this step repeatedly or use val results for method selection.

```bash
python3 scripts/gnm/dev_set_method_selection.py \
    --split val \
    --stride 5 \
    --route-beta 1.0 \
    --output-dir results/track_b_language/real_image_validation
```

Results already committed in `results/track_b_language/real_image_validation/`.
SR@3m = 1.000 (15/15). This reflects the dataset endpoint property, not
language grounding.

---

## 15. Tests

### Full test suite (recommended)

```bash
python3 -m pytest -q
```

Expected: ~1815 passed, 2 pre-existing failures, ~125 skipped.

### Language-grounding tests only

```bash
python3 -m pytest \
    tests/test_vlntube_instruction_audit.py \
    tests/test_language_grounding_pipeline.py -q
```

Expected: 89 passed, 9 skipped (CLIP-dependent tests skip when model absent).

### Track A tests only

```bash
python3 -m pytest tests/gnm/ -q
```

---

## 16. Non-GUI dashboard export

```bash
python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
```

Exports trajectory visualisation frames without requiring Isaac Sim or a GUI.
Output in `results/bo_reviewer_packet/`.

---

## 17. Optional Isaac Sim demonstration

Isaac Sim is required only for live scene rendering or new data generation. It
is not required for evaluation or testing.

**Requirements:**
- Working local Isaac Sim Python environment (`conda activate isaac`)
- `datasets/vlntube/envs` linked to VLNVerse USD scene assets
- Stable local GPU and GUI runtime

```bash
conda activate isaac
python scripts/gnm/isaac_live_trajectory_demo.py
```

For photorealistic replay (more demanding):

```bash
conda activate isaac
LIVE_DASHBOARD=1 AUTO_PLAY=1 SHOW_GNM_PANELS=1 MAX_STEPS=100000 \
    python scripts/gnm/replay_gnm_demo.py
```

---

## 18. Common errors

### `ModuleNotFoundError: No module named 'transformers'`

Install the language extras:

```bash
pip install -e '.[language]'
```

### `ValueError: Sequence length must be less than max_position_embeddings`

CLIP's text encoder accepts at most 77 tokens. The VLNTube instructions (mean
78 words) may exceed this. All scripts pass `truncation=True, max_length=77`
to the processor. If you call the processor directly, set these flags.

### `FileNotFoundError: datasets/vlntube/...`

Run the dataset link step:

```bash
bash scripts/gnm/link_vlntube_data.sh /path/to/vlntube
```

### `AttributeError: 'BaseModelOutputWithPooling' object has no attribute 'norm'`

The CLIP API changed in transformers 5.x. Upgrade to the version in this
repository or apply the `_norm()` helper from `gnm_vlnverse/vln/subgoal_selector.py`.

---

## 19. Generated output locations

| Script | Output directory |
|--------|-----------------|
| `audit_track_b_language_data.py` | `results/track_b_language/audit/` |
| `audit_instruction_target_exposure.py` | `results/track_b_language/target_exposure/` |
| `dev_set_method_selection.py` | `results/track_b_language/dev_set_method_selection/` |
| `language_dependence_controls.py` | `results/track_b_language/language_dependence_controls/` |
| `replay_gnm_demo.py --export-live-dashboard` | `results/bo_reviewer_packet/` |
| `learn_stop_head.py` | `results/track_a_stop_head/` |

---

## 20. Cleanup

Remove generated outputs (preserves source code and committed results):

```bash
rm -rf results/track_b_language/dev_set_method_selection/
rm -rf results/track_b_language/language_dependence_controls/
```

Remove HuggingFace cache (will re-download on next run):

```bash
rm -rf ~/.cache/huggingface/hub/models--openai--clip-vit-base-patch16
```
